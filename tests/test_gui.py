from __future__ import annotations

import os
import time
from importlib import import_module
from pathlib import Path
from threading import Event, get_ident

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLCONFIGDIR", "/tmp/mdhelper-test-matplotlib")

pytest.importorskip("PySide6", reason="Windows GUI dependencies are not installed")

from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QMessageBox,
)
from test_synthetic_system import _write_trajectory

import mdhelper.gui.window as window_module
from mdhelper.app import InputCandidates
from mdhelper.core.analysis import AnalysisResult, RadialRequest, analysis_label
from mdhelper.core.errors import ConfigurationError
from mdhelper.core.integrations import IntegrationConfig, IntegrationStatus
from mdhelper.core.system import SystemSummary
from mdhelper.gui.components.choices import choice_enabled
from mdhelper.gui.dialogs.projects import NewProjectDialog
from mdhelper.gui.dialogs.tools import MakeIndexHelpDialog
from mdhelper.gui.menu import DOCUMENT_LINKS
from mdhelper.gui.window import MainWindow
from mdhelper.services.config import UserConfig, config_path, save_config

gui_main_module = import_module("mdhelper.gui.main")


@pytest.fixture(autouse=True)
def _immediate_integration_detection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "mdhelper.app.features.integrations.IntegrationFeature.detect",
        lambda _self, name, _override=None, _config=None: IntegrationStatus(
            name,
            False,
        ),
    )


def test_gui_detects_integrations_outside_the_main_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    QApplication.instance() or QApplication([])
    config = UserConfig()
    config.integrations["gromacs"] = IntegrationConfig(path="configured-gmx")
    save_config(config, config_path())
    started = Event()
    release = Event()
    threads: list[int] = []

    def detect(
        _self: object,
        name: str,
        _override: object = None,
        _config: object = None,
    ) -> IntegrationStatus:
        threads.append(get_ident())
        started.set()
        release.wait(5)
        return IntegrationStatus(name, False)

    monkeypatch.setattr(
        "mdhelper.app.features.integrations.IntegrationFeature.detect",
        detect,
    )
    main_thread = get_ident()
    window = MainWindow()
    try:
        assert started.wait(1)
        assert window.analysis.parameters.analysis_backend.findData("gromacs") >= 0
        assert len(threads) == 1
        assert threads[0] != main_thread
    finally:
        release.set()
        QTest.qWait(10)
        window.close()


def test_gui_does_not_detect_unconfigured_gromacs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    QApplication.instance() or QApplication([])
    detected: list[str] = []

    def detect(
        _self: object,
        name: str,
        _override: object = None,
        _config: object = None,
    ) -> IntegrationStatus:
        detected.append(name)
        return IntegrationStatus(name, False)

    monkeypatch.setattr(
        "mdhelper.app.features.integrations.IntegrationFeature.detect",
        detect,
    )

    window = MainWindow()

    assert detected == []
    assert window.analysis.parameters.analysis_backend.findData("gromacs") == -1
    window.close()


def test_gui_uses_application_icon() -> None:
    application = QApplication.instance() or QApplication([])

    window = MainWindow()

    assert not application.windowIcon().isNull()
    assert window.windowIcon().cacheKey() == application.windowIcon().cacheKey()
    window.close()


def test_gui_requires_check_for_sampled_gromacs_rdf(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(
        "mdhelper.app.features.integrations.IntegrationFeature.is_configured",
        lambda _self, _name: True,
    )
    window = MainWindow()
    try:
        QTest.qWait(20)
        window._integration_detected(
            "gromacs",
            IntegrationStatus(
                "gromacs",
                True,
                path="gmx",
                capabilities=("rdf", "trjconv"),
            ),
        )
        parameters = window.analysis.parameters

        assert choice_enabled(parameters.analysis_backend, "gromacs")
        parameters.frames.stride.setValue(2)
        assert not choice_enabled(parameters.analysis_backend, "gromacs")
    finally:
        window.close()


def test_gui_startup_reports_configuration_errors_without_traceback(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    QApplication.instance() or QApplication([])
    messages: list[tuple[str, str]] = []

    def fail_window() -> None:
        raise ConfigurationError("Invalid configuration.", "Regenerate the configuration.")

    monkeypatch.setattr(window_module, "MainWindow", fail_window)
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda _parent, title, message: messages.append((title, message)),
    )

    assert gui_main_module.main([]) == 3
    assert len(messages) == 1
    assert "Invalid configuration." in messages[0][1]
    assert "Regenerate the configuration." in messages[0][1]
    assert "Invalid configuration." in capsys.readouterr().err


def test_gui_error_output_allows_windowed_standard_streams(monkeypatch) -> None:
    monkeypatch.setattr(gui_main_module.sys, "stderr", None)

    gui_main_module._write_error("startup failed")


def test_gui_menu_opens_tui_through_the_unified_process(monkeypatch) -> None:
    QApplication.instance() or QApplication([])
    calls: list[bool] = []
    monkeypatch.setattr(gui_main_module, "start_tui", lambda: calls.append(True) or True)
    window = MainWindow()

    window.menu_actions.terminal.trigger()

    assert calls == [True]
    window.job_controller.shutdown()
    window.close()


def test_help_documents_open_registered_https_targets(monkeypatch) -> None:
    QApplication.instance() or QApplication([])
    opened: list[str] = []
    monkeypatch.setattr(
        window_module.QDesktopServices,
        "openUrl",
        lambda url: opened.append(url.toString()) or True,
    )
    window = MainWindow()

    for name in DOCUMENT_LINKS:
        window.menu_actions.documents[name].trigger()

    assert set(window.menu_actions.documents) == set(DOCUMENT_LINKS)
    assert all(url.startswith("https://") for url in DOCUMENT_LINKS.values())
    assert opened == list(DOCUMENT_LINKS.values())
    window.close()


def test_help_document_reports_browser_failure(monkeypatch) -> None:
    QApplication.instance() or QApplication([])
    errors: list[tuple[str, str]] = []
    monkeypatch.setattr(window_module.QDesktopServices, "openUrl", lambda _url: False)
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda _parent, title, message: errors.append((title, message)),
    )
    window = MainWindow()

    next(iter(window.menu_actions.documents.values())).trigger()

    assert len(errors) == 1
    window.close()


def test_make_index_opens_help_without_configuration() -> None:
    QApplication.instance() or QApplication([])
    window = MainWindow()

    window.menu_actions.make_index.trigger()

    help_dialog = window.windows.get(MakeIndexHelpDialog)
    assert help_dialog is not None
    assert help_dialog.isVisible()
    assert help_dialog.documentation.openExternalLinks()
    window.close()


def test_make_index_uses_loaded_topology_for_configured_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    QApplication.instance() or QApplication([])
    source = tmp_path / "loaded topology.g96"
    source.write_text("structure", encoding="ascii")
    calls: list[tuple[str, list[str], Path, tuple[str, ...]]] = []
    monkeypatch.setattr(
        "mdhelper.app.features.integrations.IntegrationFeature.is_configured",
        lambda _self, _name: True,
    )
    monkeypatch.setattr(
        "mdhelper.app.features.integrations.IntegrationFeature.open_terminal",
        lambda _self, name, arguments, cwd, required_capabilities=(): calls.append(
            (name, arguments, Path(cwd), required_capabilities)
        )
        or "command",
    )
    window = MainWindow()
    window.load.inputs.topology.edit.setText(str(source))

    window.menu_actions.make_index.trigger()

    assert calls == [
        (
            "gromacs",
            ["make_ndx", "-f", str(source), "-o", "index.ndx"],
            tmp_path,
            ("make_ndx",),
        )
    ]
    assert window.statusBar().currentMessage()
    window.close()


def test_make_index_loads_output_after_the_file_is_complete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = QApplication.instance() or QApplication([])
    source = tmp_path / "structure.gro"
    output = tmp_path / "index.ndx"
    _write_trajectory(source)
    output.write_text("[ Original ]\n1\n", encoding="ascii")
    monkeypatch.setattr(
        "mdhelper.app.features.integrations.IntegrationFeature.is_configured",
        lambda _self, _name: True,
    )

    def launch(*_args, **_kwargs) -> str:
        output.write_text("[ Updated ]\n1 2\n", encoding="ascii")
        return "command"

    monkeypatch.setattr(
        "mdhelper.app.features.integrations.IntegrationFeature.open_terminal",
        launch,
    )
    window = MainWindow()
    window._inspection_timer.setInterval(0)
    window.load.inputs.topology.edit.setText(str(source))
    window.load.inputs.trajectory.edit.setText(str(source))
    window.load.inputs.index_file.edit.setText(str(output.resolve()))
    application.processEvents()
    assert window.load.index_groups == {"Original": 1}

    window.menu_actions.make_index.trigger()
    window.system_actions.poll_index_file()
    window.system_actions.poll_index_file()
    application.processEvents()

    assert window.load.inputs.index_value() == str(output.resolve())
    assert window.load.index_groups == {"Updated": 2}
    window.close()


def test_gui_completes_cumulative_rdf_on_generic_system(tmp_path: Path) -> None:
    application = QApplication.instance() or QApplication([])
    trajectory = tmp_path / "generic.gro"
    _write_trajectory(trajectory)
    window = MainWindow()
    window.load.inputs.topology.edit.setText(str(trajectory))
    window.load.inputs.trajectory.edit.setText(str(trajectory))
    window.analysis.parameters.set_analysis_backend("mdanalysis")
    window._inspect()
    for row in range(window.load.species.table.rowCount()):
        role = window.load.species.table.cellWidget(row, 2)
        assert isinstance(role, QComboBox)
        role.setCurrentText("solvent")
    window.analysis.parameters.frames.stop.setText("1")

    window.analysis.parameters.analysis_choice.setCurrentText(
        analysis_label("cumulative_rdf")
    )
    window.analysis.parameters.cumulative.reference.setText("resname REF")
    window.analysis.parameters.cumulative.selection.setText("resname LIGA")
    window.analysis.parameters.cumulative.r_max.setValue(0.5)
    window.analysis.parameters.cumulative.bin_width.setValue(0.05)
    window._run()
    deadline = time.monotonic() + 10
    while window.job_controller.current is not None and time.monotonic() < deadline:
        application.processEvents()
        window.job_controller.poll()
        time.sleep(0.01)
    assert window.session.result is not None
    assert window.job_controller.latest is not None
    assert window.job_controller.latest.log_snapshot()
    assert window.analysis.details_button.isEnabled()
    assert window.session.result.data["cumulative_number"][-1] == pytest.approx(2.0)
    assert window.session.project is not None
    assert window.session.project.root == tmp_path.resolve()
    assert (tmp_path / "mdhelper-project.json").is_file()
    assert (tmp_path / "results").is_dir()
    assert (tmp_path / "figures").is_dir()

    assert {item["analysis_type"] for item in window.session.project.list_results()} == {
        "cumulative_rdf"
    }
    window.job_controller.shutdown()
    window.close()


def test_gui_warns_when_inspected_system_has_net_charge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = MainWindow()
    charged = SystemSummary(
        topology="topology",
        trajectory="trajectory",
        n_atoms=1,
        n_frames=1,
        species={},
        atom_names={},
        backend="test",
        system_charge_e=0.5,
    )
    warnings: list[bool] = []
    monkeypatch.setattr(
        window.application.checks,
        "inspect_system",
        lambda *_args, **_kwargs: charged,
    )
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *_args, **_kwargs: warnings.append(True),
    )

    window.system_actions.inspect({})

    assert warnings == [True]
    window.close()


def test_gui_automatically_reloads_species_and_index_groups(tmp_path: Path) -> None:
    application = QApplication.instance() or QApplication([])
    first = tmp_path / "first.gro"
    second = tmp_path / "second.gro"
    index = tmp_path / "groups.ndx"
    _write_trajectory(first)
    second.write_text(
        first.read_text(encoding="ascii").replace("LIGA", "SOLV").replace("LIGB", "IONS"),
        encoding="ascii",
    )
    index.write_text("[ Reference ]\n1\n[ Neighbors ]\n2 3 4\n", encoding="ascii")
    window = MainWindow()
    window._inspection_timer.setInterval(0)
    window.load.inputs.topology.edit.setText(str(first))
    window.load.inputs.trajectory.edit.setText(str(first))
    application.processEvents()

    first_species = {
        window.load.species.table.item(row, 0).text()
        for row in range(window.load.species.table.rowCount())
    }
    assert first_species == {"REF", "LIGA", "LIGB"}

    window.load.inputs.index_file.edit.setText(str(index))
    application.processEvents()

    window.load.inputs.topology.edit.setText(str(second))
    window.load.inputs.trajectory.edit.setText(str(second))
    assert window.load.species.table.rowCount() == 0
    application.processEvents()

    second_species = {
        window.load.species.table.item(row, 0).text()
        for row in range(window.load.species.table.rowCount())
    }
    assert second_species == {"REF", "SOLV", "IONS"}

    window.load.inputs.topology.edit.setText(str(tmp_path / "missing.gro"))

    assert window.load.species.table.rowCount() == 0
    application.processEvents()
    assert window.load.species.table.rowCount() == 0
    window.job_controller.shutdown()
    window.close()


def test_gui_backend_does_not_reload_system_or_control_species_detection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    application = QApplication.instance() or QApplication([])
    first = tmp_path / "first.gro"
    second = tmp_path / "second.gro"
    _write_trajectory(first)
    second.write_text(
        first.read_text(encoding="ascii").replace("LIGA", "SOLV"),
        encoding="ascii",
    )
    window = MainWindow()
    window._inspection_timer.setInterval(0)
    window.load.inputs.topology.edit.setText(str(first))
    window.load.inputs.trajectory.edit.setText(str(first))
    application.processEvents()
    first_species = {
        window.load.species.table.item(row, 0).text()
        for row in range(window.load.species.table.rowCount())
    }
    inspect_system = window.application.checks.inspect_system
    inspections: list[bool] = []

    def inspect(
        topology: str,
        trajectory: str,
        index_file: str | None,
        cache_dir: str | Path | None,
        project_root: str | Path | None,
    ) -> object:
        inspections.append(True)
        return inspect_system(topology, trajectory, index_file, cache_dir, project_root)

    monkeypatch.setattr(
        window.application.checks,
        "inspect_system",
        inspect,
    )
    window.analysis.parameters.set_gromacs_configured(True)
    window.analysis.parameters.set_gromacs_available(True)
    window.analysis.parameters.set_analysis_backend("gromacs")

    assert inspections == []
    assert not window._inspection_timer.isActive()
    assert {
        window.load.species.table.item(row, 0).text()
        for row in range(window.load.species.table.rowCount())
    } == first_species

    window.load.inputs.topology.edit.setText(str(second))
    window.load.inputs.trajectory.edit.setText(str(second))
    application.processEvents()

    assert inspections == [True]
    assert window.analysis.parameters.analysis_backend_value() == "gromacs"
    assert {
        window.load.species.table.item(row, 0).text()
        for row in range(window.load.species.table.rowCount())
    } == {"REF", "SOLV", "LIGB"}
    window.job_controller.shutdown()
    window.close()


def test_gui_derives_selection_inputs_from_index_file() -> None:
    QApplication.instance() or QApplication([])
    window = MainWindow()
    window.analysis.parameters.set_gromacs_configured(True)
    window.analysis.parameters.set_gromacs_available(True)
    window.analysis.parameters.set_analysis_backend("gromacs")

    parameters = window.analysis.parameters
    assert window.load.inputs.index_value() is None
    assert parameters.rdf.reference.currentWidget() is parameters.rdf.reference.expression
    assert parameters.rdf.selection.currentWidget() is parameters.rdf.selection.expression
    assert not parameters.rdf.inputs.hint_button.isHidden()

    window.load.inputs.index_file.edit.setText("missing.ndx")
    assert window.load.common(object(), require_selections=False)["index_file"] == "missing.ndx"
    assert parameters.rdf.reference.currentWidget() is parameters.rdf.reference.group
    assert parameters.rdf.reference.group.count() == 1
    assert parameters.rdf.reference.group.currentData() is None
    assert not parameters.rdf.reference.group.isEnabled()
    assert parameters.rdf.inputs.hint_button.isHidden()

    window.load.inputs.index_file.edit.clear()
    assert window.load.common(object(), require_selections=False)["index_file"] is None
    assert parameters.rdf.reference.currentWidget() is parameters.rdf.reference.expression
    assert not parameters.rdf.inputs.hint_button.isHidden()
    window.job_controller.shutdown()
    window.close()


def test_gui_project_directory_open_handles_new_and_existing_projects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    application = QApplication.instance() or QApplication([])
    trajectory = tmp_path / "generic.gro"
    trajectory_input = tmp_path / "generic.xtc"
    index_input = tmp_path / "index.ndx"
    _write_trajectory(trajectory)
    trajectory_input.write_bytes(b"")
    index_input.write_text("[ System ]\n1 2 3 4\n", encoding="ascii")
    window = MainWindow()
    window.load.inputs.topology.edit.setText(str(trajectory))
    window.load.inputs.trajectory.edit.setText(str(trajectory))
    window.results.show_message("old workspace")

    monkeypatch.setattr(
        window_module.QFileDialog,
        "getExistingDirectory",
        lambda *_args, **_kwargs: "",
    )
    window._open_project()

    assert window.session.project is None
    assert window.load.inputs.topology.edit.text() == str(trajectory)
    assert window.load.inputs.trajectory.edit.text() == str(trajectory)
    assert window.results.text.toPlainText() == "old workspace"

    class RejectedDialog:
        def __init__(self, _candidates: InputCandidates, _parent: object):
            pass

        def exec(self) -> QDialog.DialogCode:
            return QDialog.DialogCode.Rejected

    monkeypatch.setattr(
        window_module.QFileDialog,
        "getExistingDirectory",
        lambda *_args, **_kwargs: str(tmp_path),
    )
    monkeypatch.setattr(window_module, "NewProjectDialog", RejectedDialog)
    window._open_project()

    assert window.load.inputs.topology.edit.text() == str(trajectory)
    assert window.load.inputs.trajectory.edit.text() == str(trajectory)
    assert window.results.text.toPlainText() == "old workspace"

    class AcceptedDialog:
        def __init__(self, candidates: InputCandidates, _parent: object):
            self.topology_path = candidates.topology[0]
            self.trajectory_path = next(
                path for path in candidates.trajectory if path.suffix.casefold() == ".xtc"
            )
            self.index_path = candidates.index[0]

        def exec(self) -> QDialog.DialogCode:
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(window_module, "NewProjectDialog", AcceptedDialog)
    inspections: list[bool] = []
    monkeypatch.setattr(
        window,
        "_inspect",
        lambda *_args, **_kwargs: inspections.append(True),
    )
    window._open_project()

    assert window.session.project is not None
    assert window.session.project.root == tmp_path.resolve()
    assert window.results.project_available
    assert window.load.inputs.topology.edit.text() == str(trajectory.resolve())
    assert window.load.inputs.trajectory.edit.text() == str(trajectory_input.resolve())
    assert window.load.inputs.index_file.edit.text() == str(index_input.resolve())
    assert not window.results.text.toPlainText()
    assert inspections == [True]
    assert (tmp_path / "mdhelper-project.json").is_file()
    assert (tmp_path / "results").is_dir()
    assert (tmp_path / "figures").is_dir()
    request = RadialRequest(
        analysis_type="rdf",
        topology=str(trajectory),
        trajectory=str(trajectory_input),
        reference="A",
        selection="B",
    )
    window.results.show_result(
        AnalysisResult(
            analysis_type="rdf",
            data={"radius_nm": [0.1], "g_r": [1.0]},
            parameters={},
            units={},
            diagnostics={},
            provenance={},
            request=request.to_dict(),
        )
    )
    assert window.results.project_button.isEnabled()
    project = window.application.projects.create(tmp_path / "saved-project", trajectory, trajectory)
    monkeypatch.setattr(
        window_module.QFileDialog,
        "getExistingDirectory",
        lambda *_args, **_kwargs: str(project.root),
    )

    window._open_project()

    assert window.session.project is not None
    assert window.session.project.root == project.root
    assert window.load.inputs.topology.edit.text() == str(trajectory.resolve())
    application.processEvents()
    window.job_controller.shutdown()
    window.close()


def test_new_project_dialog_requires_manual_input_choices(tmp_path: Path) -> None:
    application = QApplication.instance() or QApplication([])
    topology = tmp_path / "system.tpr"
    trajectory = tmp_path / "run.xtc"
    index = tmp_path / "groups.ndx"
    candidates = InputCandidates(tmp_path, (topology,), (trajectory,), (index,))
    dialog = NewProjectDialog(candidates)
    accept = dialog.buttons.button(QDialogButtonBox.StandardButton.Ok)

    assert not accept.isEnabled()
    assert dialog.topology.currentIndex() == 0
    assert dialog.trajectory.currentIndex() == 0
    assert dialog.index_file.currentData() == index
    dialog.topology.setCurrentIndex(1)
    assert not accept.isEnabled()
    dialog.trajectory.setCurrentIndex(1)

    assert accept.isEnabled()
    assert dialog.topology_path == topology
    assert dialog.trajectory_path == trajectory
    assert dialog.index_path == index
    dialog.close()
    application.processEvents()


def test_new_project_dialog_leaves_multiple_or_missing_index_candidates_optional(
    tmp_path: Path,
) -> None:
    application = QApplication.instance() or QApplication([])
    topology = tmp_path / "system.gro"
    trajectory = tmp_path / "run.xtc"
    first = tmp_path / "first.ndx"
    second = tmp_path / "second.ndx"
    multiple = NewProjectDialog(
        InputCandidates(tmp_path, (topology,), (trajectory,), (first, second))
    )
    missing = NewProjectDialog(InputCandidates(tmp_path, (topology,), (trajectory,), ()))

    assert multiple.index_path is None
    multiple.index_file.setCurrentIndex(2)
    assert multiple.index_path == second
    assert missing.index_path is None
    multiple.close()
    missing.close()
    application.processEvents()
