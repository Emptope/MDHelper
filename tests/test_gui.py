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
from mdhelper.core.analysis import AnalysisResult, RadialRequest
from mdhelper.core.errors import ConfigurationError
from mdhelper.gui.choices import choice_enabled
from mdhelper.gui.projects import NewProjectDialog
from mdhelper.gui.window import MainWindow
from mdhelper.integrations.models import IntegrationConfig, IntegrationStatus
from mdhelper.services.config import UserConfig, config_path, save_config

gui_main_module = import_module("mdhelper.gui.main")


@pytest.fixture(autouse=True)
def _immediate_integration_detection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "mdhelper.app.integrations.IntegrationUseCases.detect",
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
        "mdhelper.app.integrations.IntegrationUseCases.detect",
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
        "mdhelper.app.integrations.IntegrationUseCases.detect",
        detect,
    )

    window = MainWindow()

    assert detected == []
    assert window.analysis.parameters.analysis_backend.findData("gromacs") == -1
    window.close()


def test_gui_requires_check_for_sampled_gromacs_rdf(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(
        "mdhelper.app.integrations.IntegrationUseCases.is_configured",
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
        parameters.stride.setValue(2)
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
    assert messages == [
        (
            "MDHelper Startup Error",
            "Invalid configuration.\n\nRegenerate the configuration.",
        )
    ]
    assert capsys.readouterr().err == ("Invalid configuration.\n\nRegenerate the configuration.\n")


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
    assert window.statusBar().currentMessage() == "Terminal interface opened"
    window.task_controller.shutdown()
    window.close()


def test_gui_completes_coordination_on_generic_system(tmp_path: Path) -> None:
    application = QApplication.instance() or QApplication([])
    trajectory = tmp_path / "generic.gro"
    _write_trajectory(trajectory)
    window = MainWindow()
    window.load.inputs.topology.edit.setText(str(trajectory))
    window.load.inputs.trajectory.edit.setText(str(trajectory))
    window.analysis.parameters.set_analysis_backend("mdanalysis")
    window.load.inputs.selection_source.setCurrentIndex(1)
    window._inspect()
    for row in range(window.load.species.table.rowCount()):
        role = window.load.species.table.cellWidget(row, 2)
        assert isinstance(role, QComboBox)
        role.setCurrentText("other")
    window.analysis.parameters.stop.setText("1")

    window.analysis.parameters.analysis_choice.setCurrentText("Cumulative Coordination Number (CN)")
    window.analysis.parameters.cn_reference.setText("resname REF")
    window.analysis.parameters.cn_selection.setText("resname LIGA")
    window.analysis.parameters.cn_max.setValue(0.5)
    window.analysis.parameters.cn_bin_width.setValue(0.05)
    window._run()
    deadline = time.monotonic() + 10
    while window.task_controller.current is not None and time.monotonic() < deadline:
        application.processEvents()
        window.task_controller.poll()
        time.sleep(0.01)
    assert window.session.result is not None
    assert window.session.result.data["cumulative_number"][-1] == pytest.approx(2.0)
    assert window.session.project is not None
    assert window.session.project.root == tmp_path.resolve()
    assert (tmp_path / "mdhelper-project.json").is_file()
    assert (tmp_path / "results").is_dir()
    assert (tmp_path / "figures").is_dir()

    assert {item["analysis_type"] for item in window.session.project.list_results()} == {
        "cumulative_rdf"
    }
    window.task_controller.shutdown()
    window.close()


def test_gui_automatically_reloads_species_and_index_groups(tmp_path: Path) -> None:
    QApplication.instance() or QApplication([])
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
    window.load.inputs.topology.edit.setText(str(first))
    window.load.inputs.trajectory.edit.setText(str(first))
    QTest.qWait(350)

    first_species = {
        window.load.species.table.item(row, 0).text()
        for row in range(window.load.species.table.rowCount())
    }
    assert first_species == {"REF", "LIGA", "LIGB"}

    window.load.inputs.index_file.edit.setText(str(index))
    QTest.qWait(350)

    assert window.load.inputs.index_summary.text() == "2 groups loaded"
    assert window.load.inputs.index_summary.toolTip() == "Reference, Neighbors"

    window.load.inputs.topology.edit.setText(str(second))
    window.load.inputs.trajectory.edit.setText(str(second))
    assert window.load.species.table.rowCount() == 0
    assert window.load.inputs.index_summary.text() == "No groups found"
    QTest.qWait(350)

    second_species = {
        window.load.species.table.item(row, 0).text()
        for row in range(window.load.species.table.rowCount())
    }
    assert second_species == {"REF", "SOLV", "IONS"}
    assert window.load.inputs.index_summary.text() == "2 groups loaded"

    window.load.inputs.topology.edit.setText(str(tmp_path / "missing.gro"))

    assert window.load.species.table.rowCount() == 0
    assert window.load.inputs.index_summary.text() == "No groups found"
    QTest.qWait(350)
    assert window.load.species.table.rowCount() == 0
    assert window.load.inputs.index_summary.text() == "No groups found"
    window.task_controller.shutdown()
    window.close()


def test_gui_backend_does_not_reload_system_or_control_species_detection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    QApplication.instance() or QApplication([])
    first = tmp_path / "first.gro"
    second = tmp_path / "second.gro"
    _write_trajectory(first)
    second.write_text(
        first.read_text(encoding="ascii").replace("LIGA", "SOLV"),
        encoding="ascii",
    )
    window = MainWindow()
    window.load.inputs.topology.edit.setText(str(first))
    window.load.inputs.trajectory.edit.setText(str(first))
    QTest.qWait(350)
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
    ) -> object:
        inspections.append(True)
        return inspect_system(topology, trajectory, index_file, cache_dir)

    monkeypatch.setattr(
        window.application.checks,
        "inspect_system",
        inspect,
    )
    window.analysis.parameters.set_gromacs_configured(True)
    window.analysis.parameters.set_gromacs_available(True)
    window.analysis.parameters.set_analysis_backend("gromacs")
    QTest.qWait(350)

    assert inspections == []
    assert {
        window.load.species.table.item(row, 0).text()
        for row in range(window.load.species.table.rowCount())
    } == first_species

    window.load.inputs.topology.edit.setText(str(second))
    window.load.inputs.trajectory.edit.setText(str(second))
    QTest.qWait(350)

    assert inspections == [True]
    assert window.analysis.parameters.analysis_backend_value() == "gromacs"
    assert {
        window.load.species.table.item(row, 0).text()
        for row in range(window.load.species.table.rowCount())
    } == {"REF", "SOLV", "LIGB"}
    window.task_controller.shutdown()
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
    assert window.analysis.parameters.analysis_backend.currentText() == "Automatic"
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
    file_menu = next(
        action.menu() for action in window.menuBar().actions() if action.text() == "&File"
    )
    assert file_menu is not None
    assert [action.text() for action in file_menu.actions() if not action.isSeparator()] == [
        "Open Project...",
        "Export Last Result...",
        "Exit",
    ]
    application.processEvents()
    window.task_controller.shutdown()
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
