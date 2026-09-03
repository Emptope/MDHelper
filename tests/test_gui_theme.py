from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6", reason="GUI dependencies are not installed")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QMessageBox,
    QTableWidgetSelectionRange,
    QWidget,
)

import mdhelper.gui.window as window_module
from mdhelper.app import ApplicationService
from mdhelper.core.analysis import AnalysisResult, RadialRequest
from mdhelper.core.errors import InputError
from mdhelper.core.integrations import IntegrationConfig, IntegrationStatus
from mdhelper.core.plotting import PlotAppearance, PlotLimits
from mdhelper.core.species import SpeciesRoleSuggestion
from mdhelper.core.system import FrameRange, SystemSummary
from mdhelper.gui.components.choices import choice_enabled
from mdhelper.gui.components.parameters import ParameterPanel
from mdhelper.gui.components.selections import SelectionInput, SelectionSeries
from mdhelper.gui.dialogs.integrations import IntegrationsDialog
from mdhelper.gui.dialogs.log import JobLogDialog
from mdhelper.gui.pages.results import ResultPanel
from mdhelper.gui.plotting.settings import PlotSettingsDialog
from mdhelper.gui.window import MainWindow
from mdhelper.gui.windows import WindowManager
from mdhelper.jobs import JobHandle
from mdhelper.services.config import UserConfig, load_config

_QT_APPLICATION = QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _immediate_integration_detection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "mdhelper.app.features.integrations.IntegrationFeature.detect",
        lambda _self, name, _override=None, _config=None: IntegrationStatus(
            name,
            False,
        ),
    )


def test_window_manager_reuses_and_resizes_non_modal_windows() -> None:
    owner = QWidget()
    windows = WindowManager(owner)
    prepared: list[QDialog] = []
    configured: list[QDialog] = []

    first = windows.show(
        QDialog,
        prepared.append,
        setup=configured.append,
    )
    second = windows.show(
        QDialog,
        prepared.append,
        setup=configured.append,
    )

    assert first is second
    assert prepared == [first, first]
    assert configured == [first]
    assert first.isVisible()
    assert first.windowModality() == Qt.WindowModality.NonModal
    group = windows.resize(QDialog, 2)
    assert group[0] is first
    assert len(group) == 2
    assert all(window.parent() is owner for window in group)

    windows.resize(QDialog, 1)
    windows.close_all()

    assert windows.items(QDialog) == (first,)
    assert not first.isVisible()
    owner.close()


def test_gromacs_backend_availability_does_not_hide_energy_analysis() -> None:
    parameters = ParameterPanel()

    assert parameters.analysis_backend.findData("gromacs") == -1
    parameters.set_gromacs_configured(True)
    parameters.set_gromacs_available(False)

    assert not choice_enabled(parameters.analysis_backend, "gromacs")
    assert choice_enabled(parameters.analysis_choice, "energy")
    with pytest.raises(InputError, match="unavailable"):
        parameters.set_analysis_backend("gromacs")

    parameters.set_gromacs_available(True)
    parameters.set_analysis_backend("gromacs")
    parameters._set_analysis("energy")

    assert parameters.analysis_backend_value() == "gromacs"
    assert parameters.analysis_choice.currentData() == "energy"
    parameters.close()


def test_appearance_menu_applies_and_persists_theme(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = tmp_path / "config.toml"
    monkeypatch.setenv("MDHELPER_CONFIG", str(path))
    window = MainWindow()
    actions = window.menu_actions.themes

    for name in ("dark", "light", "system"):
        actions[name].trigger()
        assert load_config(path).gui.theme == name
        assert actions[name].isChecked()
        assert sum(action.isChecked() for action in actions.values()) == 1

    window.close()


def test_result_history_hides_missing_artifacts() -> None:
    window = MainWindow()
    entries = (
        {
            "analysis_id": "missing-id",
            "analysis_type": "rdf",
            "committed_at": "2026-08-28T06:00:00+00:00",
            "request": {"reference": "LI", "selection": "O_FSI"},
            "available": False,
        },
        {
            "analysis_id": "available-id",
            "analysis_type": "rdf",
            "committed_at": "2026-08-28T07:00:00+00:00",
            "request": {"reference": "LI", "selection": "O_FSI"},
            "available": True,
        },
    )

    window.results.set_history(entries)

    assert window.results.project_results.count() == 1
    assert window.results.project_results.currentData() == "available-id"
    window.close()


def test_result_history_selection_requests_load_without_separate_action() -> None:
    panel = ResultPanel()
    entries = (
        {
            "analysis_id": "first-id",
            "analysis_type": "rdf",
            "committed_at": "2026-08-28T06:00:00+00:00",
            "request": {"reference": "A", "selection": "B"},
        },
        {
            "analysis_id": "second-id",
            "analysis_type": "rdf",
            "committed_at": "2026-08-28T07:00:00+00:00",
            "request": {"reference": "A", "selection": "C"},
        },
    )
    loaded: list[str | None] = []
    panel.load_requested.connect(lambda: loaded.append(panel.current_id()))

    panel.set_history(entries)
    panel.project_results.setCurrentIndex(1)
    selected = panel.current_id()
    panel.project_results.activated.emit(1)

    assert loaded == [selected]
    panel.close()


def _rdf_result(reference: str, selection: str) -> AnalysisResult:
    request = RadialRequest(
        analysis_type="rdf",
        topology="topology",
        trajectory="trajectory",
        reference=reference,
        selection=selection,
    )
    return AnalysisResult(
        analysis_type="rdf",
        data={
            "radius_nm": [0.1, 0.2, 0.3],
            "g_r": [0.0, 2.0, 1.0],
        },
        parameters={},
        units={},
        diagnostics={},
        provenance={},
        request=request.to_dict(),
    )


def _cumulative_rdf_result(reference: str, selection: str) -> AnalysisResult:
    request = RadialRequest(
        analysis_type="cumulative_rdf",
        topology="topology",
        trajectory="trajectory",
        reference=reference,
        selection=selection,
    )
    return AnalysisResult(
        analysis_type="cumulative_rdf",
        data={
            "radius_nm": [0.1, 0.2],
            "cumulative_number": [0.25, 0.75],
        },
        parameters={},
        units={},
        diagnostics={},
        provenance={},
        request=request.to_dict(),
    )


def test_plot_settings_dialog_applies_and_reverts_one_edit_session() -> None:
    appearance = PlotAppearance(
        legend_visible=False,
        legend_location="lower_left",
        grid_visible=False,
        line_width=2.8,
        title_font_size=17,
        label_font_size=13,
        tick_font_size=9,
        legend_font_size=8,
    )
    dialog = PlotSettingsDialog()
    dialog.begin(appearance)
    dialog.show()
    _QT_APPLICATION.processEvents()
    applied: list[PlotAppearance] = []
    reverted: list[PlotAppearance] = []
    dialog.applied.connect(applied.append)
    dialog.reverted.connect(reverted.append)

    assert dialog.appearance() == appearance

    dialog.line_width.setValue(3.4)
    dialog.grid_visible.setChecked(True)

    assert not applied

    dialog.apply_button.click()

    assert applied == [dialog.appearance()]
    assert dialog.isVisible()

    dialog.reset_button.click()

    assert dialog.appearance() == PlotAppearance()
    assert len(applied) == 1

    dialog.ok_button.click()

    assert applied[-1] == PlotAppearance()
    assert not reverted
    assert dialog.result() == QDialog.DialogCode.Accepted

    cancelled = PlotSettingsDialog()
    cancelled.begin(appearance)
    cancelled.show()
    _QT_APPLICATION.processEvents()
    cancelled_values: list[PlotAppearance] = []
    reverted_values: list[PlotAppearance] = []
    cancelled.applied.connect(cancelled_values.append)
    cancelled.reverted.connect(reverted_values.append)
    cancelled.line_width.setValue(4.0)
    cancelled.apply_button.click()
    cancelled.cancel_button.click()

    assert len(cancelled_values) == 1
    assert reverted_values == [appearance]
    assert cancelled.result() == QDialog.DialogCode.Rejected


def test_selection_series_stores_enabled_pairs_and_editable_legends() -> None:
    reference = SelectionInput()
    selection = SelectionInput()
    series = SelectionSeries(reference, selection)
    reference.setText("A")
    selection.setText("B")
    series.add_current()
    selection.setText("C")
    series.add_current()
    first = series.table.item(0, 0)
    second_label = series.table.item(1, 3)
    assert first is not None and second_label is not None
    first.setCheckState(Qt.CheckState.Unchecked)
    second_label.setText("custom legend")

    assert series.pairs()[0].selection == "C"
    assert series.pairs()[0].label == "custom legend"
    series.close()


def test_frame_controls_use_exclusive_gui_stop_and_round_trip_requests() -> None:
    panel = ParameterPanel()
    panel.frames.start.setValue(2)
    panel.frames.stop.setText("7")
    panel.frames.stride.setValue(2)
    assert panel.frame_range() == FrameRange(start=2, stop=7, stride=2)

    request = RadialRequest(
        analysis_type="rdf",
        topology="topology",
        trajectory="trajectory",
        reference="A",
        selection="B",
        frames=FrameRange(start=3, stop=9, stride=3),
    )
    panel.apply_request(request)
    assert panel.frames.start.value() == 3
    assert panel.frames.stop.text() == "9"
    assert panel.frame_range() == request.frames
    panel.close()


def _species_summary() -> SystemSummary:
    suggestions = {
        "alpha": SpeciesRoleSuggestion(
            "cation",
            ("cation", "other"),
            "net charge",
            "high",
            {"net_charge_e": 1.0},
            reason="Positive molecular charge.",
        ),
        "beta": SpeciesRoleSuggestion(
            "anion",
            ("anion", "other"),
            "net charge",
            "high",
            {"net_charge_e": -1.0},
            reason="Negative molecular charge.",
        ),
    }
    return SystemSummary(
        topology="topology",
        trajectory="trajectory",
        n_atoms=2,
        n_frames=1,
        species={name: 1 for name in suggestions},
        atom_names={"X": 2},
        backend="test",
        role_suggestions=suggestions,
    )


def test_apply_role_suggestions_saves_and_cancel_clears(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = MainWindow()
    summary = _species_summary()
    window.role_suggestions = dict(summary.role_suggestions)
    window.load.species.set_summary(summary, {})
    window.session.project = SimpleNamespace()
    saved: list[dict[str, str]] = []
    monkeypatch.setattr(
        window.session,
        "set_species_roles",
        lambda roles: saved.append(dict(roles)),
    )
    manual = window.load.species.table.cellWidget(0, 2)
    assert isinstance(manual, QComboBox)
    manual.setCurrentText("other")

    window.load.species.apply_button.click()

    expected = {
        species: suggestion.suggested_role
        for species, suggestion in summary.role_suggestions.items()
    }
    expected[window.load.species.table.item(0, 0).text()] = "other"
    assert window.load.species.roles() == expected
    assert saved[-1] == expected

    window.load.species.cancel_button.click()

    assert window.load.species.roles() == {"alpha": "other"}
    assert set(window.role_provenance) == {"alpha"}
    assert saved[-1] == {"alpha": "other"}
    window.close()


def test_selection_series_builds_requests_with_independent_parameters() -> None:
    panel = ParameterPanel()
    panel._set_analysis("rdf")
    panel.rdf.reference.setText("A")
    panel.rdf.selection.setText("B")
    panel.rdf.r_max.setValue(0.8)
    panel.rdf.bin_width.setValue(0.004)
    panel.rdf.series.add_current()
    panel.rdf.selection.setText("C")
    panel.rdf.r_max.setValue(1.2)
    panel.rdf.bin_width.setValue(0.006)
    panel.rdf.series.add_current()
    panel.rdf.series.table.selectRow(0)
    panel.rdf.series.table.item(0, 4).setText("0.9")
    panel.rdf.series.table.cellClicked.emit(0, 0)
    assert panel.rdf.r_max.value() == pytest.approx(0.9)
    assert panel.rdf.bin_width.value() == pytest.approx(0.004)
    common = {
        "topology": "topology",
        "trajectory": "trajectory",
        "index_file": None,
        "frames": FrameRange(),
        "species_roles": {},
        "parameter_provenance": {"species_roles": {}},
    }

    runs = panel.request_series(common)

    assert [(run.r_max_nm, run.bin_width_nm) for run, _label in runs] == [
        (0.9, 0.004),
        (1.2, 0.006),
    ]
    assert "r_max_nm" not in runs[0][0].parameter_provenance
    panel.close()


def test_result_panel_keeps_mixed_analysis_types_in_one_figure() -> None:
    panel = ResultPanel()
    rdf = _rdf_result("A", "B")
    cn = _cumulative_rdf_result("A", "B")
    panel.show_result(rdf)
    panel.show_result(cn)

    assert panel.plot_series.rowCount() == 2
    assert len(panel.figure.axes) == 2
    assert not any(line.get_visible() for line in panel.figure.axes[1].yaxis.get_gridlines())
    panel.plot_series.selectRow(0)
    assert panel.plot_title.isEnabled()
    panel.plot_title.setText("Ion coordination comparison")
    panel.plot_title.editingFinished.emit()
    assert panel.figure.axes[0].get_title() == "Ion coordination comparison"
    assert panel.plot_titles() == (
        "Ion coordination comparison",
        "Ion coordination comparison",
    )
    panel.plot_series.item(0, 2).setText("RDF saved")
    panel.plot_series.item(1, 2).setText("Cumulative saved")
    panel.plot_series.item(1, 0).setCheckState(Qt.CheckState.Unchecked)
    panel.color_scheme.setCurrentIndex(panel.color_scheme.findData("fixed"))
    panel.x_min.setText("0")
    panel.x_max.setText("5")
    panel.y_min.setText("-1")
    panel.y_max.setText("3")
    panel.y2_min.setText("-2")
    panel.y2_max.setText("8")
    panel._apply_limits()
    state = panel.plot_state()
    assert state.scheme == "fixed"
    assert state.limits == PlotLimits(0.0, 5.0, -1.0, 3.0, -2.0, 8.0)
    assert [selection.visible for selection in state.selections] == [True, False]
    assert [selection.title for selection in state.selections] == [
        "Ion coordination comparison",
        "Ion coordination comparison",
    ]
    restored = ResultPanel()
    restored.restore_state(state, (rdf, cn))
    assert restored.plot_state() == state
    assert len(restored.figure.axes) == 1
    assert restored.figure.axes[0].get_title() == "Ion coordination comparison"
    restored.close()
    panel.close()


def test_result_panel_edits_only_the_selected_energy_plot_title(
    energy_result: AnalysisResult,
) -> None:
    panel = ResultPanel()
    panel.show_result(energy_result)
    original = tuple(window.figure.axes[0].get_title() for window in panel.plot_windows)
    panel.plot_series.selectRow(1)

    panel.plot_title.setText("Temperature stability")
    panel.plot_title.editingFinished.emit()

    titles = tuple(window.figure.axes[0].get_title() for window in panel.plot_windows)
    assert titles[0] == original[0]
    assert titles[1] == "Temperature stability"
    assert titles[2] == original[2]
    assert [selection.title for selection in panel.plot_state().selections] == [
        "",
        "Temperature stability",
        "",
    ]
    panel.close()


def test_result_panel_combines_selected_energy_terms_and_restores_group(
    energy_result: AnalysisResult,
) -> None:
    panel = ResultPanel()
    panel.show_result(energy_result)

    assert panel.plot_series.rowCount() == 3
    assert len(panel.plot_windows) == 3
    assert all(len(window.figure.axes) == 1 for window in panel.plot_windows)
    panel.open_plot_window()
    assert all(window.isVisible() for window in panel.plot_windows)
    panel.plot_series.clearSelection()
    panel.plot_series.setRangeSelected(QTableWidgetSelectionRange(0, 0, 1, 5), True)
    assert panel.combine_series_button.isEnabled()

    panel.combine_series_button.click()

    assert len(panel.plot_windows) == 2
    assert all(len(window.figure.axes) == 1 for window in panel.plot_windows)
    assert len(panel.figure.axes[0].lines) == 2
    state = panel.plot_state()
    assert [selection.series for selection in state.selections] == [
        "Potential",
        "Temperature",
        "Pressure",
    ]
    assert state.selections[0].group
    assert state.selections[0].group == state.selections[1].group
    assert not state.selections[2].group

    restored = ResultPanel()
    restored.restore_state(state, (energy_result,))

    assert restored.plot_state() == state
    assert restored.plot_series.rowCount() == 3
    assert len(restored.plot_windows) == 2
    assert all(len(window.figure.axes) == 1 for window in restored.plot_windows)
    restored.plot_series.clearSelection()
    restored.plot_series.setRangeSelected(
        QTableWidgetSelectionRange(0, 0, 1, 5), True
    )
    assert restored.separate_series_button.isEnabled()
    restored.separate_series_button.click()
    assert len(restored.plot_windows) == 3
    assert all(len(window.figure.axes) == 1 for window in restored.plot_windows)
    assert all(not selection.group for selection in restored.plot_state().selections)
    restored.close()
    panel.close()


def test_analysis_details_opens_the_retained_job_log() -> None:
    window = MainWindow()
    details = window.analysis.details_button
    window.tabs.setCurrentWidget(window.analysis)
    window.show()
    _QT_APPLICATION.processEvents()

    assert not details.isEnabled()

    job = JobHandle(name="Radial Distribution Function (RDF): Water - Ion")
    job.update_progress(1, 1, "Analyzed RDF frame 0")
    window.job_controller.latest = job
    window._job_changed(job)
    details.click()
    _QT_APPLICATION.processEvents()

    dialog = window.windows.get(JobLogDialog)
    assert dialog is not None
    assert dialog.isVisible()
    assert not dialog.isModal()
    assert dialog.heading.text() == job.name
    assert dialog.log.toPlainText() == "Analyzed RDF frame 0"
    assert window.menuBar().isEnabled()

    window.job_controller.current = None
    details.click()
    assert dialog.log.toPlainText() == "Analyzed RDF frame 0"
    window.close()


def test_settings_menu_creates_and_opens_the_active_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    path = tmp_path / "config.toml"
    monkeypatch.setenv("MDHELPER_CONFIG", str(path))
    opened: list[str] = []
    monkeypatch.setattr(
        window_module.QDesktopServices,
        "openUrl",
        lambda url: opened.append(url.toLocalFile()) or True,
    )
    window = MainWindow()

    window.menu_actions.settings.trigger()

    assert path.is_file()
    assert load_config(path) == window.application.config
    assert [Path(value) for value in opened] == [path]
    window.close()


def test_settings_menu_reports_missing_default_text_application(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    messages: list[tuple[str, str]] = []
    monkeypatch.setattr(window_module.QDesktopServices, "openUrl", lambda _url: False)
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda _parent, title, text: messages.append((title, text)),
    )
    window = MainWindow()

    window.menu_actions.settings.trigger()

    assert len(messages) == 1
    window.close()


def test_gui_export_includes_every_visible_result_and_current_plot(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    stub_figure_exports,
) -> None:
    stub_figure_exports()
    window = MainWindow()
    first = _rdf_result("A", "B")
    second = _rdf_result("A", "C")
    window.results.show_result(first, "first")
    window.results.show_result(second, "second")
    window.results.plot_series.selectRow(0)
    window.results.plot_title.setText("Exported comparison")
    window.results.plot_title.editingFinished.emit()
    window.results.open_plot_window()
    _QT_APPLICATION.processEvents()
    window.session.result = second
    monkeypatch.setattr(
        window_module.QFileDialog,
        "getExistingDirectory",
        lambda *_args, **_kwargs: str(tmp_path),
    )
    monkeypatch.setattr(QMessageBox, "information", lambda *_args, **_kwargs: None)

    window._export_result()

    assert not tuple(tmp_path.glob("plot.*"))
    outputs = (
        tmp_path / "rdf-A-B",
        tmp_path / "rdf-A-C",
    )
    for output in outputs:
        assert {path.name for path in output.iterdir()} == {
            "result.json",
            "rdf.csv",
            f"{output.name}.png",
            f"{output.name}.svg",
            f"{output.name}.pdf",
        }
    window.close()


def test_gui_save_plot_exports_each_plot_window_to_separate_files(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    energy_result: AnalysisResult,
    stub_figure_exports,
) -> None:
    stub_figure_exports()
    window = MainWindow()
    window.results.show_result(energy_result)
    window.session.project = SimpleNamespace(root=tmp_path)  # type: ignore[assignment]
    window.session.result = energy_result
    monkeypatch.setattr(QMessageBox, "information", lambda *_args, **_kwargs: None)

    window._save_project_figures()

    output = tmp_path / "figures"
    assert {path.name for path in output.iterdir()} == {
        f"energy-{term}.{suffix}"
        for term in ("Potential", "Temperature", "Pressure")
        for suffix in ("png", "svg", "pdf")
    }
    window.close()


def test_integration_dialog_reports_detection_without_command_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = MainWindow()
    dialog = IntegrationsDialog(window.application, window)
    status = IntegrationStatus(
        "gromacs",
        True,
        path="gmx",
        version="test",
        capabilities=("alpha", "beta", "new-command"),
        source="test",
    )
    detected: list[IntegrationConfig | None] = []

    def detect(
        _name: str,
        _override: str | None = None,
        config: IntegrationConfig | None = None,
    ) -> IntegrationStatus:
        detected.append(config)
        return status

    monkeypatch.setattr(dialog.application.integrations, "detect", detect)
    configured = str(Path("configured") / "gmx")
    dialog.executable.edit.setText(configured)

    dialog._detect()

    assert detected and detected[0] is not None
    assert detected[0].path == configured
    assert dialog.tool.currentData() == "gromacs"
    vmd = dialog.tool.findData("vmd")
    dialog.tool.setCurrentIndex(vmd)
    assert dialog.tool.currentData() == "vmd"
    dialog.tool.setCurrentIndex(dialog.tool.findData("gromacs"))
    dialog.close()
    window.close()


def test_integration_dialog_saves_configured_executable(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    application = ApplicationService(UserConfig(), user_config_path=config_path)
    dialog = IntegrationsDialog(application)
    configured = str(tmp_path / "bin" / "gmx")
    dialog.executable.edit.setText(configured)

    dialog._save()

    assert application.config.integration("gromacs").path == configured
    assert load_config(config_path).integration("gromacs").path == configured
    dialog.close()


def test_energy_terms_are_selected_through_an_ordered_queue() -> None:
    panel = ParameterPanel()
    panel._set_analysis("energy")
    panel.energy.file.edit.setText("sample.edr")
    panel.set_energy_terms(
        "sample.edr",
        ("Bond", "Potential", "Temperature", "Pressure"),
    )

    panel.energy.queue.available.item(2).setSelected(True)
    panel.energy.queue.add_selected()
    panel.energy.queue.available.clearSelection()
    panel.energy.queue.available.item(1).setSelected(True)
    panel.energy.queue.add_selected()
    panel.energy.queue.add_all()

    assert panel.energy.queue.items() == (
        "Temperature",
        "Potential",
        "Bond",
        "Pressure",
    )
    request = panel.request(
        {
            "topology": "",
            "trajectory": "",
            "index_file": None,
            "frames": FrameRange(),
            "species_roles": {},
            "parameter_provenance": {},
        }
    )
    assert request.energy_terms == panel.energy.queue.items()
    panel.close()


def test_energy_file_selection_automatically_reloads_terms_without_button(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = tmp_path / "first.edr"
    second = tmp_path / "second.edr"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    window = MainWindow()
    panel = window.analysis.parameters
    calls: list[tuple[str, str, object]] = []

    def terms(
        path: str, backend: str, *, cache_dir: object = None
    ) -> tuple[str, ...]:
        calls.append((path, backend, cache_dir))
        return ("Potential", "Temperature") if path == str(first) else ("Pressure",)

    monkeypatch.setattr(window.application.analyses, "energy_terms", terms)
    panel._set_analysis("energy")

    panel.energy.file.edit.setText(str(first))
    panel.energy.file.path_selected.emit(str(first))

    assert calls == [(str(first), "auto", None)]
    assert panel.energy.queue.available.count() == 2
    panel.energy.queue.add_all()
    assert panel.energy.queue.items() == ("Potential", "Temperature")

    panel.energy.file.edit.setText(str(second))

    assert panel.energy.queue.available.count() == 0
    assert panel.energy.queue.items() == ()
    panel.energy.file.path_selected.emit(str(second))
    assert calls == [(str(first), "auto", None), (str(second), "auto", None)]
    assert panel.energy.queue.available.item(0).text() == "Pressure"
    panel.set_analysis_backend("mdanalysis")
    assert calls[-1] == (str(second), "mdanalysis", None)
    window.job_controller.shutdown()
    window.close()


def test_window_manager_close_requires_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = MainWindow()
    calls: list[tuple[str, str]] = []

    class CloseEvent:
        ignored = False
        accepted = False

        @staticmethod
        def spontaneous() -> bool:
            return True

        def ignore(self) -> None:
            self.ignored = True

        def accept(self) -> None:
            self.accepted = True

    def reject(_parent: object, title: str, message: str) -> QMessageBox.StandardButton:
        calls.append((title, message))
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "question", reject)
    event = CloseEvent()
    window.closeEvent(event)  # type: ignore[arg-type]

    assert len(calls) == 1
    assert event.ignored and not event.accepted
    window.job_controller.shutdown()


def test_gui_analysis_initializes_project_in_trajectory_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    window = MainWindow()
    topology = tmp_path / "topology.dat"
    trajectory = tmp_path / "trajectory.dat"
    topology.write_text("topology\n", encoding="ascii")
    trajectory.write_text("trajectory\n", encoding="ascii")
    request = RadialRequest(
        analysis_type="rdf",
        topology=str(topology),
        trajectory=str(trajectory),
        reference="A",
        selection="B",
    )
    submitted: list[tuple[RadialRequest, str]] = []
    monkeypatch.setattr(window.load, "common", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(
        window.analysis,
        "request_series",
        lambda *_args, **_kwargs: ((request, ""),),
    )
    monkeypatch.setattr(
        window.analysis_actions.controller,
        "start",
        lambda items: submitted.extend(items),
    )

    window._run()

    assert window.session.project is not None
    assert window.session.project.root == tmp_path.resolve()
    assert submitted == [(request, "")]
    assert (tmp_path / "mdhelper-project.json").is_file()
    assert (tmp_path / "results").is_dir()
    assert (tmp_path / "figures").is_dir()
    window.job_controller.shutdown()
