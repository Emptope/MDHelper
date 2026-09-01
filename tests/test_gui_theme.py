from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6", reason="GUI dependencies are not installed")

from PySide6.QtCore import QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QFont, QFontDatabase, QImage, QPalette, QWheelEvent
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QTableWidgetSelectionRange,
    QTabWidget,
    QWidget,
)

import mdhelper.gui.window as window_module
from mdhelper.app import ApplicationService
from mdhelper.core.analysis import AnalysisResult, RadialRequest
from mdhelper.core.errors import InputError
from mdhelper.core.plotting import PlotLimits
from mdhelper.core.system import FrameRange
from mdhelper.gui.analysis import AnalysisPanel
from mdhelper.gui.choices import choice_enabled
from mdhelper.gui.dialogs import IntegrationsDialog
from mdhelper.gui.fonts import configure_ui_font
from mdhelper.gui.inputs import InputPanel
from mdhelper.gui.layout import PAGE_MARGIN, PAGE_SPACING, ActionBar
from mdhelper.gui.parameters import ParameterPanel
from mdhelper.gui.results import ResultPanel
from mdhelper.gui.selections import (
    SELECTION_HINTS,
    SelectionInput,
    SelectionSeries,
)
from mdhelper.gui.species import SpeciesPanel
from mdhelper.gui.templates import TemplatesDialog
from mdhelper.gui.window import MainWindow
from mdhelper.integrations.models import IntegrationConfig, IntegrationStatus
from mdhelper.services.config import UserConfig, load_config

_QT_APPLICATION = QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _immediate_integration_detection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "mdhelper.app.integrations.IntegrationUseCases.detect",
        lambda _self, name, _override=None, _config=None: IntegrationStatus(
            name,
            False,
        ),
    )


def _contrast(palette: QPalette) -> tuple[int, int]:
    return (
        palette.color(QPalette.ColorRole.Window).lightness(),
        palette.color(QPalette.ColorRole.WindowText).lightness(),
    )


def _rendered_contrast(widget: QWidget, rect: QRect) -> int:
    image = widget.grab().toImage()
    area = rect.intersected(image.rect()).adjusted(1, 1, -1, -1)
    values = [
        image.pixelColor(x, y).lightness()
        for y in range(area.top(), area.bottom() + 1)
        for x in range(area.left(), area.right() + 1)
    ]
    return max(values) - min(values)


def _tone_pixels(widget: QWidget, light: bool) -> int:
    image = widget.grab().toImage()
    right = max(4, image.width() - 32)
    area = QRect(4, 2, right - 4, max(1, image.height() - 4))
    values = [
        image.pixelColor(x, y).lightness()
        for y in range(area.top(), area.bottom() + 1)
        for x in range(area.left(), area.right() + 1)
    ]
    return sum(value > 200 if light else value < 80 for value in values)


def test_analysis_progress_leaves_busy_state_when_a_task_stops() -> None:
    panel = AnalysisPanel()

    panel.set_running(True)
    assert panel.progress.minimum() == 0
    assert panel.progress.maximum() == 0

    panel.set_running(False)

    assert panel.progress.maximum() == 100
    assert panel.progress.value() == 0
    assert panel.run_button.isEnabled()
    assert not panel.cancel_button.isEnabled()
    panel.close()


def test_input_and_rdf_labels_use_public_terminology() -> None:
    inputs = InputPanel()
    form = inputs.layout()
    assert isinstance(form, QFormLayout)
    assert form.labelForField(inputs.index_file).text() == "Index file"
    assert not hasattr(inputs, "backend")
    assert all(
        button.text() != "Inspect loaded system" for button in inputs.findChildren(QPushButton)
    )

    parameters = ParameterPanel()
    assert [
        parameters.analysis_backend.itemText(index)
        for index in range(parameters.analysis_backend.count())
    ][:3] == ["Automatic", "Native", "MDAnalysis"]
    parameters.set_analysis_backend("mdanalysis")
    assert parameters.analysis_backend_value() == "mdanalysis"
    assert [
        parameters.analysis_choice.itemText(index)
        for index in range(parameters.analysis_choice.count())
    ] == [
        "Radial Distribution Function (RDF)",
        "Cumulative Coordination Number (CN)",
        "Energy Analysis",
    ]
    rdf_form = parameters.stack.widget(0).layout()
    assert isinstance(rdf_form, QFormLayout)
    assert parameters.rdf_inputs.reference_label.text() == "Reference"
    assert parameters.rdf_inputs.selection_label.text() == "Selection"
    assert parameters.rdf_inputs.findChildren(QPushButton) == [
        parameters.rdf_inputs.hint_button
    ]
    headers = [
        parameters.rdf_series.table.horizontalHeaderItem(column).text()
        for column in range(parameters.rdf_series.table.columnCount())
    ]
    assert headers[:4] == ["Run", "Reference", "Selection", "Legend"]

    species = SpeciesPanel()
    assert species.table.horizontalHeaderItem(2).text() == "Role"


def test_selection_hints_follow_expression_source_and_use_a_table() -> None:
    parameters = ParameterPanel()

    assert not parameters.rdf_inputs.hint_button.isHidden()
    assert not parameters.cn_inputs.hint_button.isHidden()
    parameters.set_selection_source("index", {"System": 10})
    assert parameters.rdf_inputs.hint_button.isHidden()
    assert parameters.cn_inputs.hint_button.isHidden()
    parameters.set_selection_source("expression", {})
    assert not parameters.rdf_inputs.hint_button.isHidden()
    assert not parameters.cn_inputs.hint_button.isHidden()

    parameters.set_gromacs_configured(True)
    parameters.set_gromacs_available(True)
    parameters.set_analysis_backend("gromacs")
    assert parameters.rdf_inputs.hint_button.isHidden()
    assert parameters.cn_inputs.hint_button.isHidden()
    parameters.set_analysis_backend("mdanalysis")
    assert not parameters.rdf_inputs.hint_button.isHidden()
    assert not parameters.cn_inputs.hint_button.isHidden()

    parameters.rdf_inputs.hint_button.click()
    dialog = parameters._hint_dialog
    assert dialog is not None
    assert not dialog.isModal()
    assert dialog.isVisible()

    assert dialog.table.rowCount() == len(SELECTION_HINTS)
    assert dialog.table.columnCount() == 3
    assert [
        dialog.table.horizontalHeaderItem(column).text() for column in range(3)
    ] == ["Selector", "Meaning", "Example"]
    assert dialog.table.item(0, 0).text() == "all"
    assert dialog.table.item(4, 2).text() == "resname SOL"
    dialog.close()


def test_selection_source_language_follows_the_complete_backend() -> None:
    inputs = InputPanel()

    inputs.set_analysis_backend("mdanalysis")
    expression = inputs.selection_source.findData("expression")
    assert inputs.selection_source.itemText(expression) == (
        "MDAnalysis selection expressions"
    )
    assert choice_enabled(inputs.selection_source, "expression")

    inputs.set_analysis_backend("gromacs")
    assert inputs.selection_source.itemText(expression) == (
        "GROMACS selection expressions"
    )
    assert choice_enabled(inputs.selection_source, "expression")

    inputs.selection_source.setCurrentIndex(expression)
    inputs.set_analysis_backend("native")
    assert not choice_enabled(inputs.selection_source, "expression")
    assert inputs.selection_source.currentData() == "index"
    inputs.close()


def test_gromacs_backend_availability_does_not_hide_energy_analysis() -> None:
    parameters = ParameterPanel()

    assert parameters.analysis_backend.findData("gromacs") == -1
    parameters.set_gromacs_configured(True)
    parameters.set_gromacs_available(False)

    assert not choice_enabled(parameters.analysis_backend, "gromacs")
    assert choice_enabled(parameters.analysis_choice, "energy")
    assert "Unavailable" in parameters.analysis_backend.itemText(
        parameters.analysis_backend.findData("gromacs")
    )
    with pytest.raises(InputError, match="unavailable"):
        parameters.set_analysis_backend("gromacs")

    parameters.set_gromacs_available(True)
    parameters.set_analysis_backend("gromacs")
    parameters._set_analysis("energy")

    assert parameters.analysis_backend_value() == "gromacs"
    assert parameters.analysis_choice.currentData() == "energy"
    parameters.close()


def test_main_window_hides_unconfigured_gromacs_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "mdhelper.app.integrations.IntegrationUseCases.detect",
        lambda _self, name, _override=None, _config=None: IntegrationStatus(
            name,
            False,
        ),
    )

    window = MainWindow()

    assert window.analysis.parameters.analysis_backend.findData("gromacs") == -1
    assert choice_enabled(window.analysis.parameters.analysis_choice, "energy")
    window.task_controller.shutdown()
    window.close()


def test_appearance_menu_applies_and_persists_theme(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = tmp_path / "config.toml"
    monkeypatch.setenv("MDHELPER_CONFIG", str(path))
    existing = QApplication.instance()
    application = existing if isinstance(existing, QApplication) else QApplication([])
    window = MainWindow()
    native_style = application.style().objectName()
    native_palette = QPalette(application.palette())

    try:
        actions = window.menu_actions.themes
        assert actions["system"].isChecked()

        actions["dark"].trigger()
        application.processEvents()
        assert load_config(path).gui.theme == "dark"
        assert application.style().objectName().casefold() == "fusion"
        assert _contrast(application.palette())[0] < _contrast(application.palette())[1]
        assert window.results.figure.get_facecolor()[:3] == (1.0, 1.0, 1.0)
        assert window.results.export_button.text() == "Export..."
        assert actions["dark"].isChecked()
        assert sum(action.isChecked() for action in actions.values()) == 1
        window.show()
        application.processEvents()
        for control in (
            window.analysis.run_button,
            window.load.inputs.selection_source,
            window.analysis.parameters.analysis_choice,
        ):
            assert _tone_pixels(control, light=True) > 3

        actions["light"].trigger()
        application.processEvents()
        assert load_config(path).gui.theme == "light"
        assert application.style().objectName().casefold() == "fusion"
        assert _contrast(application.palette())[0] > _contrast(application.palette())[1]
        assert actions["light"].isChecked()
        application.processEvents()
        for control in (
            window.analysis.run_button,
            window.load.inputs.selection_source,
            window.analysis.parameters.analysis_choice,
        ):
            assert _rendered_contrast(control, control.rect()) > 40
        menu_bar = window.menuBar()
        first_action = menu_bar.actions()[0]
        assert _rendered_contrast(menu_bar, menu_bar.actionGeometry(first_action)) > 80
        tabs = window.findChild(QTabWidget)
        assert tabs is not None
        tabs.setCurrentIndex(1)
        application.processEvents()
        assert _rendered_contrast(tabs.tabBar(), tabs.tabBar().tabRect(0)) > 80

        actions["system"].trigger()
        application.processEvents()
        assert load_config(path).gui.theme == "system"
        assert application.style().objectName() == native_style
        assert application.palette() == native_palette
    finally:
        window.theme.apply("system")
        window.close()


def test_result_history_hides_missing_artifacts_and_uses_readable_labels() -> None:
    existing = QApplication.instance()
    _application = existing if isinstance(existing, QApplication) else QApplication([])
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
    assert "available-id" not in window.results.project_results.currentText()
    assert "LI-O_FSI" in window.results.project_results.currentText()
    window.close()


def test_ui_font_retains_the_native_family(monkeypatch: pytest.MonkeyPatch) -> None:
    existing = QApplication.instance()
    application = existing if isinstance(existing, QApplication) else QApplication([])
    native = QFont("Native UI")
    native.setPointSizeF(9.0)
    monkeypatch.setattr(
        QFontDatabase,
        "systemFont",
        lambda _role: QFont(native),
    )

    configure_ui_font(application, 10.0)

    font = application.font()
    assert font.family() == "Native UI"
    assert font.pointSizeF() == 10.0
    assert font.hintingPreference() == QFont.HintingPreference.PreferDefaultHinting
    assert font.styleStrategy() == QFont.StyleStrategy.PreferDefault


def test_configured_font_size_is_applied(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        'schema_version=1\n[gui]\ntheme="system"\nfont_size=13.5\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("MDHELPER_CONFIG", str(path))
    existing = QApplication.instance()
    application = existing if isinstance(existing, QApplication) else QApplication([])

    window = MainWindow()
    try:
        assert application.font().pointSizeF() == 13.5
        assert window.font().pointSizeF() == 13.5
    finally:
        window.close()
        configure_ui_font(application)


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


def test_plot_representations_colors_and_axis_ranges_are_editable() -> None:
    existing = QApplication.instance()
    _application = existing if isinstance(existing, QApplication) else QApplication([])
    panel = ResultPanel()
    panel.show_result(_rdf_result("A", "B"), "first")
    panel.show_result(_rdf_result("A", "C"), "second")

    assert panel.plot_series.rowCount() == 2
    assert [text.get_text() for text in panel.figure.axes[0].get_legend().get_texts()] == [
        "g(r) first",
        "g(r) second",
    ]
    panel.color_scheme.setCurrentIndex(panel.color_scheme.findData("fixed"))
    assert [line.get_color() for line in panel.figure.axes[0].lines[:2]] == [
        "#4040ff",
        "#ff0000",
    ]
    assert all(
        isinstance(panel.plot_series.cellWidget(row, 3), QComboBox)
        and panel.plot_series.cellWidget(row, 3).isEnabled()
        for row in range(2)
    )

    panel.x_min.setText("0")
    panel.x_max.setText("5")
    panel.y_min.setText("-1")
    panel.y_max.setText("3")
    panel._apply_limits()
    assert panel.figure.axes[0].get_xlim() == pytest.approx((0.0, 5.0))
    assert panel.figure.axes[0].get_ylim() == pytest.approx((-1.0, 3.0))
    panel.clear_limits()
    assert panel.x_min.text() == ""
    panel.close()


def test_plot_color_does_not_change_from_wheel_input() -> None:
    panel = ResultPanel()
    panel.show_result(_rdf_result("A", "B"))
    panel.color_scheme.setCurrentIndex(panel.color_scheme.findData("fixed"))
    color = panel.plot_series.cellWidget(0, 3)
    assert isinstance(color, QComboBox)
    color.setCurrentIndex(color.findData(1))

    event = QWheelEvent(
        QPointF(1, 1),
        QPointF(1, 1),
        QPoint(),
        QPoint(0, 120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.ScrollUpdate,
        False,
    )
    QApplication.sendEvent(color, event)

    assert color.currentData() == 1
    assert not event.isAccepted()
    panel.close()


def test_result_panel_prioritizes_overview_and_separates_plot_controls() -> None:
    existing = QApplication.instance()
    application = existing if isinstance(existing, QApplication) else QApplication([])
    panel = ResultPanel()
    panel.resize(1100, 900)
    panel.show()
    application.processEvents()

    layout = panel.layout()
    assert layout is not None
    assert panel.sections.orientation() == Qt.Orientation.Horizontal
    assert panel.sections.indexOf(panel.summary_box) == 0
    assert panel.sections.indexOf(panel.plot_panel) == 1
    assert panel.summary_box.height() >= panel.height() // 2
    assert panel.clear_series_button.text() == "Clear All"
    assert panel.color_scheme.currentData() == "residue_name"
    controls = panel.plot_settings.layout()
    assert isinstance(controls, QGridLayout)
    for row in range(6):
        widgets = [
            item.widget()
            for column in range(3)
            if (item := controls.itemAtPosition(row, column)) is not None
            and item.widget() is not None
        ]
        assert widgets
        assert controls.cellRect(row, 0).height() <= max(
            widget.sizeHint().height() for widget in widgets if widget is not None
        ) + 1
    assert {button.text() for button in panel.plot_settings.findChildren(QPushButton)}.isdisjoint(
        {"Auto", "Apply"}
    )
    panel.close()


@pytest.mark.parametrize("height", (800, 680))
def test_result_overview_stays_inside_its_scrollable_area(
    height: int, energy_result: AnalysisResult
) -> None:
    window = MainWindow()
    window.resize(760, height)
    window.tabs.setCurrentWidget(window.results)
    window.results.show_result(energy_result)
    window.show()
    _QT_APPLICATION.processEvents()

    overview = window.results.summary_box
    text = window.results.text
    assert overview.height() >= window.results.height() // 2
    assert overview.contentsRect().contains(text.geometry())
    text.setPlainText("\n".join(f"Result line {index}" for index in range(100)))
    _QT_APPLICATION.processEvents()
    assert text.verticalScrollBar().maximum() > 0
    window.close()


def test_selected_plot_series_updates_result_overview() -> None:
    existing = QApplication.instance()
    _application = existing if isinstance(existing, QApplication) else QApplication([])
    panel = ResultPanel()
    first = _rdf_result("A", "B")
    second = _rdf_result("A", "C")
    panel.show_result(first)
    panel.show_result(second)

    assert panel.result is second
    panel.plot_series.selectRow(0)
    assert panel.result is first
    assert "A - B" in panel.text.toPlainText()
    assert "A - C" not in panel.text.toPlainText()
    panel.close()


def test_selection_series_stores_enabled_pairs_and_editable_legends() -> None:
    existing = QApplication.instance()
    _application = existing if isinstance(existing, QApplication) else QApplication([])
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


def test_selection_series_uses_a_compact_ordered_action_row() -> None:
    existing = QApplication.instance()
    application = existing if isinstance(existing, QApplication) else QApplication([])
    reference = SelectionInput()
    selection = SelectionInput()
    reference.setText("A")
    selection.setText("B")
    series = SelectionSeries(reference, selection)
    series.add_current()
    series.resize(900, 240)
    series.show()
    application.processEvents()

    assert series.add_button.height() == 24
    assert series.clear_button.text() == "Clear All"
    assert series.add_button.x() < series.remove_button.x() < series.clear_button.x()
    assert series.table.horizontalHeader().sectionSize(0) < 80
    assert series.table.currentColumn() == 1
    assert series.sizePolicy().verticalPolicy() == QSizePolicy.Policy.Expanding
    assert series.table.sizePolicy().verticalPolicy() == QSizePolicy.Policy.Expanding
    series.close()


def test_configured_series_table_absorbs_vertical_window_growth() -> None:
    existing = QApplication.instance()
    application = existing if isinstance(existing, QApplication) else QApplication([])
    panel = ParameterPanel()
    panel.resize(900, 700)
    panel.show()
    application.processEvents()
    series = panel.rdf_series
    compact_top = series.mapTo(panel, series.rect().topLeft()).y()
    compact_table_top = series.table.mapTo(panel, series.table.rect().topLeft()).y()
    compact_table_height = series.table.height()

    panel.resize(900, 950)
    application.processEvents()

    assert series.mapTo(panel, series.rect().topLeft()).y() == compact_top
    assert series.table.mapTo(panel, series.table.rect().topLeft()).y() == compact_table_top
    assert series.table.height() > compact_table_height
    panel.close()


def test_frame_controls_use_exclusive_gui_stop_and_round_trip_requests() -> None:
    existing = QApplication.instance()
    _application = existing if isinstance(existing, QApplication) else QApplication([])
    panel = ParameterPanel()
    labels = {item.text() for item in panel.frames.findChildren(QLabel)}

    assert "First frame (0-based)" in labels
    assert "Stop frame (exclusive)" in labels
    assert "Stride (frames)" in labels
    assert "Uncertainty block (frames)" not in labels
    panel.start.setValue(2)
    panel.stop.setText("7")
    panel.stride.setValue(2)
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
    assert panel.start.value() == 3
    assert panel.stop.text() == "9"
    assert panel.frame_range() == request.frames
    panel.close()


def test_species_table_prioritizes_species_and_suggestion_columns() -> None:
    existing = QApplication.instance()
    _application = existing if isinstance(existing, QApplication) else QApplication([])
    panel = SpeciesPanel()
    header = panel.table.horizontalHeader()

    assert panel.table.horizontalHeaderItem(1).text() == "Numbers"
    assert header.sectionSize(0) == 180
    assert header.sectionSize(2) == 200
    panel.close()


def test_selection_series_builds_requests_with_independent_parameters() -> None:
    existing = QApplication.instance()
    _application = existing if isinstance(existing, QApplication) else QApplication([])
    panel = ParameterPanel()
    panel.analysis_choice.setCurrentText("Radial Distribution Function (RDF)")
    panel.rdf_reference.setText("A")
    panel.rdf_selection.setText("B")
    panel.rdf_max.setValue(0.8)
    panel.rdf_bin_width.setValue(0.004)
    panel.rdf_series.add_current()
    panel.rdf_selection.setText("C")
    panel.rdf_max.setValue(1.2)
    panel.rdf_bin_width.setValue(0.006)
    panel.rdf_series.add_current()
    panel.rdf_series.table.selectRow(0)
    panel.rdf_series.table.item(0, 4).setText("0.9")
    panel.rdf_series.table.cellClicked.emit(0, 0)
    assert panel.rdf_max.value() == pytest.approx(0.9)
    assert panel.rdf_bin_width.value() == pytest.approx(0.004)
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
    existing = QApplication.instance()
    _application = existing if isinstance(existing, QApplication) else QApplication([])
    panel = ResultPanel()
    rdf = _rdf_result("A", "B")
    cn = _cumulative_rdf_result("A", "B")
    panel.show_result(rdf)
    panel.show_result(cn)

    assert panel.plot_series.rowCount() == 2
    assert [panel.plot_series.item(row, 1).text() for row in range(2)] == [
        "RDF",
        "CN",
    ]
    assert [axis.get_title() for axis in panel.figure.axes if axis.get_title()] == [
        "RDF and Cumulative Coordination Number"
    ]
    assert len(panel.figure.axes) == 2
    assert not any(line.get_visible() for line in panel.figure.axes[1].yaxis.get_gridlines())
    panel.plot_series.selectRow(0)
    assert panel.plot_title.isEnabled()
    assert panel.plot_title.text() == "RDF and Cumulative Coordination Number"
    panel.plot_title.setText("Ion coordination comparison")
    panel.plot_title.editingFinished.emit()
    assert panel.figure.axes[0].get_title() == "Ion coordination comparison"
    assert panel.plot_titles() == (
        "Ion coordination comparison",
        "Ion coordination comparison",
    )
    panel.plot_series.item(0, 2).setText("RDF saved")
    panel.plot_series.item(1, 2).setText("CN saved")
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
    panel.plot_series.selectRow(1)

    assert panel.plot_title.text() == "Energy Analysis: Temperature"
    panel.plot_title.setText("Temperature stability")
    panel.plot_title.editingFinished.emit()

    assert [window.figure.axes[0].get_title() for window in panel.plot_windows] == [
        "Energy Analysis: Potential",
        "Temperature stability",
        "Energy Analysis: Pressure",
    ]
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
    assert [panel.plot_series.item(row, 4).text() for row in range(3)] == [
        "Potential",
        "Temperature",
        "Pressure",
    ]
    assert [panel.plot_series.item(row, 5).text() for row in range(3)] == [
        "Plot 1",
        "Plot 2",
        "Plot 3",
    ]
    assert sorted({index.row() for index in panel.plot_series.selectedIndexes()}) == [
        0,
        1,
        2,
    ]
    assert panel.combine_series_button.isEnabled()
    assert not panel.separate_series_button.isEnabled()
    assert len(panel.plot_windows) == 3
    assert all(len(window.figure.axes) == 1 for window in panel.plot_windows)
    assert [window.figure.axes[0].get_title() for window in panel.plot_windows] == [
        "Energy Analysis: Potential",
        "Energy Analysis: Temperature",
        "Energy Analysis: Pressure",
    ]
    panel.open_plot_window()
    assert all(window.isVisible() for window in panel.plot_windows)
    panel.plot_series.clearSelection()
    panel.plot_series.setRangeSelected(QTableWidgetSelectionRange(0, 0, 1, 5), True)
    assert panel.combine_series_button.isEnabled()

    panel.combine_series_button.click()

    assert len(panel.plot_windows) == 2
    assert all(len(window.figure.axes) == 1 for window in panel.plot_windows)
    assert len(panel.figure.axes[0].lines) == 2
    assert panel.plot_series.item(0, 5).text() == "Plot 1 - Combined"
    assert panel.plot_series.item(1, 5).text() == "Plot 1 - Combined"
    assert panel.plot_series.item(2, 5).text() == "Plot 2"
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
    assert [restored.plot_series.item(row, 5).text() for row in range(3)] == [
        "Plot 1",
        "Plot 2",
        "Plot 3",
    ]
    restored.close()
    panel.close()


def test_main_window_separates_load_and_analysis_settings() -> None:
    existing = QApplication.instance()
    _application = existing if isinstance(existing, QApplication) else QApplication([])
    window = MainWindow()

    assert window.size().width() == 860
    assert window.size().height() == 800
    assert window.tabs.count() == 3
    assert [window.tabs.tabText(index) for index in range(3)] == [
        "Load",
        "Analysis Settings",
        "Result",
    ]
    assert window.load.sections.orientation() == Qt.Orientation.Vertical
    assert window.load.sections.count() == 2
    opened: list[bool] = []
    window.results.open_plot_window = lambda: opened.append(True)
    window._task_completed(_rdf_result("A", "B"))
    assert opened == [True]
    assert window.tabs.currentWidget() is window.results
    window.close()


def test_main_pages_use_consistent_action_surfaces() -> None:
    existing = QApplication.instance()
    _application = existing if isinstance(existing, QApplication) else QApplication([])
    window = MainWindow()

    bars = (
        window.load.species.action_bar,
        window.analysis.action_bar,
        window.results.action_bar,
    )
    assert not hasattr(window.load.inputs, "action_bar")
    assert all(isinstance(bar, ActionBar) for bar in bars)
    assert all(bar.frameShape() == QFrame.Shape.NoFrame for bar in bars)
    assert all(bar.sizeHint().height() <= 40 for bar in (bars[0], bars[2]))
    assert window.analysis.action_bar.stacked
    assert 40 < window.analysis.action_bar.sizeHint().height() <= 80
    assert window.analysis.progress.parent() is window.analysis.action_bar
    assert window.load.layout().contentsMargins().left() == PAGE_MARGIN
    assert window.load.layout().spacing() == PAGE_SPACING
    assert window.analysis.run_button.property("importance") == "primary"
    assert window.results.export_button.property("importance") == "primary"
    assert window.results.open_plot_button.parent() is window.results.action_bar
    assert window.results.open_plot_button.text() == "Open Plot Window"
    assert window.results.project_button.text() == "Save Plot"
    assert window.analysis.parameters.frames.title() == "Frame Sampling"
    window.close()


def test_about_dialog_shows_developer_affiliation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    messages: list[tuple[str, str]] = []
    monkeypatch.setattr(
        QMessageBox,
        "about",
        lambda _parent, title, text: messages.append((title, text)),
    )
    window = MainWindow()
    help_menu = next(
        action.menu() for action in window.menuBar().actions() if action.text() == "&Help"
    )
    assert help_menu is not None
    next(action for action in help_menu.actions() if action.text() == "About").trigger()

    assert messages == [
        (
            "About MDHelper",
            "MDHelper 0.1.0<br>"
            "A toolkit for the analysis of <b>Molecular Dynamics</b> data."
            "<br><br>"
            "Developer: Tuo Yao (Shanghai Jiao Tong University)"
            "<br><br>"
            "License: GNU General Public License v2.0 (GPL-2.0)"
            "<br><br>"
            "MDHelper is free software: you are free to use, study, share, "
            "and modify it under the terms of the GNU General Public License.",
        )
    ]
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

    assert [action.text() for action in window.menuBar().actions()] == [
        "&File",
        "&Tools",
        "&View",
        "&Settings",
        "&Help",
    ]
    window.menu_actions.settings.trigger()

    assert path.is_file()
    assert load_config(path) == window.application.config
    assert [Path(value) for value in opened] == [path]
    assert window.statusBar().currentMessage() == f"Opened configuration: {path}"
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

    assert messages
    assert messages[0][0] == "MDHelper Error"
    assert "default text application" in messages[0][1]
    window.close()


def test_gui_export_includes_every_visible_result_and_current_plot(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    existing = QApplication.instance()
    _application = existing if isinstance(existing, QApplication) else QApplication([])
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
    display_width, display_height = window.results.figure.get_size_inches()
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
        assert "Exported comparison" in (output / f"{output.name}.svg").read_text(
            encoding="utf-8"
        )
    image = QImage(str(outputs[0] / "rdf-A-B.png"))
    assert image.width() / image.height() == pytest.approx(
        display_width / display_height,
        abs=0.001,
    )
    window.close()


def test_gui_save_plot_exports_each_plot_window_to_separate_files(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    energy_result: AnalysisResult,
) -> None:
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
    for title in ("Potential", "Temperature", "Pressure"):
        assert title in (output / f"energy-{title}.svg").read_text(encoding="utf-8")
    window.close()


def test_gui_export_directories_add_readable_numeric_suffixes(tmp_path: Path) -> None:
    first = _rdf_result("A", "B")
    second = _rdf_result("A", "B")
    (tmp_path / "rdf-A-B").mkdir()

    items = (*window_module.result_exports(first), *window_module.result_exports(second))
    directories = window_module.export_directories(tmp_path, items)

    assert tuple(path.name for path in directories) == ("rdf-A-B-2", "rdf-A-B-3")


def test_gui_exports_each_energy_curve_to_its_own_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    energy_result: AnalysisResult,
) -> None:
    window = MainWindow()
    window.results.show_result(energy_result)
    window.session.result = energy_result
    monkeypatch.setattr(
        window_module.QFileDialog,
        "getExistingDirectory",
        lambda *_args, **_kwargs: str(tmp_path),
    )
    monkeypatch.setattr(QMessageBox, "information", lambda *_args, **_kwargs: None)

    window._export_result()

    for term in ("Potential", "Temperature", "Pressure"):
        output = tmp_path / f"energy-{term}"
        assert {path.name for path in output.iterdir()} == {
            "result.json",
            "energy.csv",
            f"energy-{term}.png",
            f"energy-{term}.svg",
            f"energy-{term}.pdf",
        }
        assert (output / "energy.csv").read_text(encoding="utf-8").splitlines()[0] == (
            f"time_ps,{term}"
        )
    window.close()


def test_integration_dialog_reports_detection_without_command_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing = QApplication.instance()
    _application = existing if isinstance(existing, QApplication) else QApplication([])
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
    assert dialog.tool.currentText() == "GROMACS"
    assert dialog.executable.edit.text() == "gmx"
    assert [dialog.capabilities.item(index).text() for index in range(3)] == [
        "alpha",
        "beta",
        "new-command",
    ]
    assert not hasattr(dialog, "run_button")
    assert not dialog.findChildren(QPlainTextEdit)
    vmd = dialog.tool.findData("vmd")
    dialog.tool.setCurrentIndex(vmd)
    assert dialog.tool.currentText() == "VMD"
    dialog.tool.setCurrentIndex(dialog.tool.findData("gromacs"))
    assert dialog.executable.edit.text() == "gmx"
    dialog.close()
    window.close()


def test_integration_dialog_saves_configured_executable(tmp_path: Path) -> None:
    existing = QApplication.instance()
    _application = existing if isinstance(existing, QApplication) else QApplication([])
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
    existing = QApplication.instance()
    _application = existing if isinstance(existing, QApplication) else QApplication([])
    panel = ParameterPanel()
    panel.analysis_choice.setCurrentText("Energy Analysis")
    panel.energy_file.edit.setText("sample.edr")
    panel.set_energy_terms(
        "sample.edr",
        ("Bond", "Potential", "Temperature", "Pressure"),
    )

    panel.energy_queue.available.item(2).setSelected(True)
    panel.energy_queue.add_selected()
    panel.energy_queue.available.clearSelection()
    panel.energy_queue.available.item(1).setSelected(True)
    panel.energy_queue.add_selected()
    panel.energy_queue.add_all()

    assert panel.energy_queue.items() == (
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
    assert request.energy_terms == panel.energy_queue.items()
    assert not hasattr(panel, "energy_terms")
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
    panel.analysis_choice.setCurrentText("Energy Analysis")

    panel.energy_file.edit.setText(str(first))
    panel.energy_file.path_selected.emit(str(first))

    assert calls == [(str(first), "auto", None)]
    assert panel.energy_queue.available.count() == 2
    panel.energy_queue.add_all()
    assert panel.energy_queue.items() == ("Potential", "Temperature")

    panel.energy_file.edit.setText(str(second))

    assert panel.energy_queue.available.count() == 0
    assert panel.energy_queue.items() == ()
    panel.energy_file.path_selected.emit(str(second))
    assert calls == [(str(first), "auto", None), (str(second), "auto", None)]
    assert panel.energy_queue.available.item(0).text() == "Pressure"
    panel.set_analysis_backend("mdanalysis")
    assert calls[-1] == (str(second), "mdanalysis", None)
    assert all(
        button.text() != "Load Energy Terms"
        for button in panel.findChildren(QPushButton)
    )
    window.task_controller.shutdown()
    window.close()


def test_templates_are_exposed_by_the_tools_menu() -> None:
    existing = QApplication.instance()
    _application = existing if isinstance(existing, QApplication) else QApplication([])
    window = MainWindow()
    dialog = TemplatesDialog(window.application, window)

    assert window.menu_actions.templates.text() == "Templates..."
    assert dialog.template_list.count() >= 2
    assert dialog.text.toPlainText().isascii()
    assert dialog.copy_button.isEnabled()
    assert dialog.save_button.isEnabled()
    dialog.close()
    window.close()


def test_window_manager_close_requires_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing = QApplication.instance()
    _application = existing if isinstance(existing, QApplication) else QApplication([])
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

    assert calls == [("Really Quit?", "Quit MDHelper?")]
    assert event.ignored and not event.accepted
    window.task_controller.shutdown()


def test_gui_analysis_initializes_project_in_trajectory_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    existing = QApplication.instance()
    _application = existing if isinstance(existing, QApplication) else QApplication([])
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
    submitted: list[bool] = []
    window.load.inputs.selection_source.setCurrentIndex(1)
    monkeypatch.setattr(window.load, "common", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(
        window.analysis,
        "request_series",
        lambda *_args, **_kwargs: ((request, ""),),
    )
    monkeypatch.setattr(window, "_submit_next", lambda: submitted.append(True))

    window._run()

    assert window.session.project is not None
    assert window.session.project.root == tmp_path.resolve()
    assert submitted == [True]
    assert (tmp_path / "mdhelper-project.json").is_file()
    assert (tmp_path / "results").is_dir()
    assert (tmp_path / "figures").is_dir()
    window.task_controller.shutdown()
