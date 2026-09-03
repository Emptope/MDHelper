from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6", reason="GUI dependencies are not installed")

from PySide6.QtCore import QDir, QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QFont, QFontDatabase, QPalette, QWheelEvent
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QTableWidgetSelectionRange,
    QTabWidget,
    QWidget,
)

import mdhelper.gui.window as window_module
import mdhelper.io.export.figures as export_module
from mdhelper.app import ApplicationService
from mdhelper.app.analysis import export_directories, result_exports
from mdhelper.core.analysis import AnalysisResult, RadialRequest
from mdhelper.core.errors import InputError
from mdhelper.core.plotting import PlotAppearance, PlotLimits
from mdhelper.core.species import SPECIES_ROLES, SpeciesRoleSuggestion
from mdhelper.core.system import FrameRange, SystemSummary
from mdhelper.gui.components.choices import choice_enabled
from mdhelper.gui.components.inputs import InputPanel
from mdhelper.gui.components.layout import PAGE_MARGIN, PAGE_SPACING, ActionBar
from mdhelper.gui.components.parameters import ParameterPanel, RadialParameters
from mdhelper.gui.components.paths import PathRow
from mdhelper.gui.components.selections import SelectionInput, SelectionSeries
from mdhelper.gui.components.species import SpeciesPanel
from mdhelper.gui.dialogs.integrations import IntegrationsDialog
from mdhelper.gui.dialogs.log import JobLogDialog
from mdhelper.gui.dialogs.results import ResultDetailsDialog
from mdhelper.gui.dialogs.selection import (
    GROMACS_SELECTION_HINTS,
    SELECTION_DOCUMENTATION,
    SELECTION_HINTS,
    SelectionHintDialog,
)
from mdhelper.gui.dialogs.species import RoleHelpDialog, SuggestionDetailsDialog
from mdhelper.gui.dialogs.templates import TemplatesDialog
from mdhelper.gui.fonts import configure_ui_font
from mdhelper.gui.formatting import result_details_html, result_summary_html
from mdhelper.gui.pages.analysis import AnalysisPanel
from mdhelper.gui.pages.results import ResultPanel
from mdhelper.gui.plotting.controls import PlotControls
from mdhelper.gui.plotting.settings import PlotSettingsDialog
from mdhelper.gui.theme import ThemeController
from mdhelper.gui.window import MainWindow
from mdhelper.gui.windows import WindowManager
from mdhelper.integrations.models import IntegrationConfig, IntegrationStatus
from mdhelper.jobs import JobHandle
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


def test_path_rows_use_native_separators() -> None:
    row = PathRow("", "")
    value = "directory/child/file.ext"

    row.set_path(value)

    assert row.edit.text() == QDir.toNativeSeparators(value)
    row.close()


def test_analysis_progress_leaves_busy_state_when_a_job_stops() -> None:
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


def test_job_log_dialog_is_non_modal_and_copies_raw_messages() -> None:
    job = JobHandle(name="Analysis: Li - O")
    job.update_progress(1, 2, "Reading frame 0")
    job.update_progress(2, 2, "Reading frame 1")
    dialog = JobLogDialog()

    dialog.set_content(job.job_id, job.name, job.log_snapshot())
    dialog.show()
    _QT_APPLICATION.processEvents()

    assert not dialog.isModal()
    assert dialog.windowModality() == Qt.WindowModality.NonModal
    flags = dialog.windowFlags()
    assert flags & Qt.WindowType.WindowMinimizeButtonHint
    assert flags & Qt.WindowType.WindowMaximizeButtonHint
    assert flags & Qt.WindowType.WindowCloseButtonHint
    assert dialog.heading.text() == job.name
    assert dialog.log.isReadOnly()
    assert dialog.log.toPlainText() == "Reading frame 0\nReading frame 1"
    dialog.copy_button.click()
    assert _QT_APPLICATION.clipboard().text() == dialog.log.toPlainText()
    notice = dialog.copy_notice
    assert notice is not None
    assert notice.isVisible()
    assert not notice.isModal()
    dialog.close()


def test_job_log_follows_new_messages_until_the_user_scrolls_up() -> None:
    dialog = JobLogDialog()
    messages = tuple(f"message {number}" for number in range(200))
    dialog.show()
    dialog.set_content("job-1", "Analysis", messages)
    _QT_APPLICATION.processEvents()
    scroll = dialog.log.verticalScrollBar()

    assert scroll.maximum() > 0
    assert scroll.value() == scroll.maximum()

    scroll.setValue(0)
    dialog.set_content("job-1", "Analysis", (*messages, "latest message"))
    assert scroll.value() == 0

    scroll.setValue(scroll.maximum())
    dialog.set_content(
        "job-1",
        "Analysis",
        (*messages, "latest message", "newest message"),
    )
    assert scroll.value() == scroll.maximum()
    assert dialog.log.toPlainText().endswith("latest message\nnewest message")
    dialog.close()


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


def test_input_and_radial_controls_use_independent_widgets() -> None:
    inputs = InputPanel()
    assert not hasattr(inputs, "backend")
    assert not hasattr(inputs, "selection_source")

    parameters = ParameterPanel()
    assert isinstance(parameters.stack.widget(0), RadialParameters)
    assert isinstance(parameters.stack.widget(1), RadialParameters)
    assert parameters.stack.widget(0) is not parameters.stack.widget(1)
    parameters.set_analysis_backend("mdanalysis")
    assert parameters.analysis_backend_value() == "mdanalysis"
    assert parameters.rdf.inputs.findChildren(QPushButton) == [
        parameters.rdf.inputs.hint_button
    ]


def test_selection_hints_follow_index_file_and_use_a_table() -> None:
    window = MainWindow()
    panel = window.analysis
    parameters = panel.parameters

    assert not parameters.rdf.inputs.hint_button.isHidden()
    assert not parameters.cumulative.inputs.hint_button.isHidden()
    parameters.set_selection_groups(True, {"System": 10})
    assert parameters.rdf.inputs.hint_button.isHidden()
    assert parameters.cumulative.inputs.hint_button.isHidden()
    parameters.set_selection_groups(False, {})
    assert not parameters.rdf.inputs.hint_button.isHidden()
    assert not parameters.cumulative.inputs.hint_button.isHidden()

    parameters.set_gromacs_configured(True)
    parameters.set_gromacs_available(True)
    parameters.set_analysis_backend("gromacs")
    assert not parameters.rdf.inputs.hint_button.isHidden()
    assert not parameters.cumulative.inputs.hint_button.isHidden()
    parameters.rdf.inputs.hint_button.click()
    dialog = window.windows.get(SelectionHintDialog)
    assert dialog is not None
    assert dialog.table.rowCount() == len(GROMACS_SELECTION_HINTS)
    assert dialog.documentation.openExternalLinks()
    url = SELECTION_DOCUMENTATION[dialog.backend]
    link = f'<a href="{url}">{url}</a>'
    assert dialog.documentation.text().endswith(link)
    assert dialog.documentation.text() != link

    parameters.set_selection_groups(True, {"System": 10})
    assert parameters.rdf.inputs.hint_button.isHidden()
    assert parameters.cumulative.inputs.hint_button.isHidden()
    assert parameters.rdf.reference.currentWidget() is parameters.rdf.reference.group
    assert parameters.rdf.reference.group.count() == 1
    assert parameters.rdf.reference.group.currentData() == "System"

    parameters.set_analysis_backend("mdanalysis")
    assert parameters.rdf.inputs.hint_button.isHidden()
    assert parameters.cumulative.inputs.hint_button.isHidden()

    parameters.set_selection_groups(False, {})
    assert not parameters.rdf.inputs.hint_button.isHidden()
    assert not parameters.cumulative.inputs.hint_button.isHidden()

    parameters.rdf.inputs.hint_button.click()
    dialog = window.windows.get(SelectionHintDialog)
    assert dialog is not None
    assert not dialog.isModal()
    assert dialog.isVisible()

    assert dialog.table.rowCount() == len(SELECTION_HINTS)
    assert dialog.table.columnCount() == 3
    window.close()


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
    application = _QT_APPLICATION
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
        assert actions["dark"].isChecked()
        assert sum(action.isChecked() for action in actions.values()) == 1
        window.show()
        application.processEvents()
        for control in (
            window.analysis.run_button,
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


def test_ui_font_retains_the_native_family(monkeypatch: pytest.MonkeyPatch) -> None:
    application = _QT_APPLICATION
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
    application = _QT_APPLICATION

    window = MainWindow()
    try:
        assert application.font().pointSizeF() == 13.5
        assert window.font().pointSizeF() == 13.5
    finally:
        window.close()
        configure_ui_font(application)


def test_theme_switch_preserves_the_configured_font(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = _QT_APPLICATION
    configure_ui_font(application, 13.5)
    existing_control = QPushButton()
    controller = ThemeController(application)
    set_style = application.setStyle

    def style_with_native_font(style: str) -> object:
        result = set_style(style)
        native = QFont(application.font())
        native.setPointSizeF(9.0)
        application.setFont(native)
        return result

    monkeypatch.setattr(application, "setStyle", style_with_native_font)

    try:
        controller.apply("dark")
        new_control = QPushButton()
        assert {
            application.font().pointSizeF(),
            existing_control.font().pointSizeF(),
            new_control.font().pointSizeF(),
        } == {13.5}
        new_control.close()
    finally:
        controller.apply("system")
        configure_ui_font(application)
        existing_control.close()


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
    panel = ResultPanel()
    assert isinstance(panel.plot_panel, PlotControls)
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
    assert (
        dialog.reset_button.x()
        < dialog.ok_button.x()
        < dialog.cancel_button.x()
        < dialog.apply_button.x()
    )

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


def test_result_panel_applies_confirmed_advanced_plot_settings() -> None:
    selected = PlotAppearance(
        legend_visible=False,
        legend_location="lower_right",
        grid_visible=False,
        line_width=3.0,
        title_font_size=16,
        label_font_size=12,
        tick_font_size=9,
        legend_font_size=8,
    )

    window = MainWindow()
    panel = window.results
    result = _rdf_result("A", "B")
    panel.show_result(result)
    window.tabs.setCurrentWidget(panel)
    window.resize(900, 700)
    window.show()
    _QT_APPLICATION.processEvents()
    changes: list[bool] = []
    panel.state_changed.connect(lambda: changes.append(True))

    button_rect = panel.advanced_plot_button.geometry()
    assert button_rect.top() > panel.y2_max.geometry().bottom()
    assert button_rect.right() >= panel.y2_max.geometry().right()

    panel.advanced_plot_button.click()
    dialog = window.windows.get(PlotSettingsDialog)
    assert dialog is not None
    assert dialog.windowModality() == Qt.WindowModality.NonModal
    assert dialog.isVisible()
    assert window.isEnabled()
    assert panel.plot_appearance() == PlotAppearance()
    assert not changes

    panel.advanced_plot_button.click()
    assert window.windows.get(PlotSettingsDialog) is dialog

    dialog.set_appearance(selected)
    dialog.apply_button.click()
    assert panel.plot_appearance() == selected
    assert panel.plot_state().appearance == selected
    assert changes == [True]
    dialog.cancel_button.click()
    assert panel.plot_appearance() == PlotAppearance()
    assert changes == [True, True]
    assert not dialog.isVisible()

    panel.advanced_plot_button.click()
    confirmed = window.windows.get(PlotSettingsDialog)
    assert confirmed is dialog
    confirmed.set_appearance(selected)
    confirmed.ok_button.click()

    assert panel.plot_appearance() == selected
    assert panel.plot_state().appearance == selected
    assert changes == [True, True, True]
    assert panel.figure.axes[0].get_legend() is None
    assert not any(
        line.get_visible() for line in panel.figure.axes[0].get_xgridlines()
    )
    restored = ResultPanel()
    restored.restore_state(panel.plot_state(), (result,))
    assert restored.plot_appearance() == selected
    assert restored.figure.axes[0].get_legend() is None
    restored.close()
    window.close()


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
    application = _QT_APPLICATION
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
    panel.close()


def test_result_overview_excludes_metadata_kept_in_details() -> None:
    result = _rdf_result("A", "B")

    overview = result_summary_html(result)
    details = result_details_html(result)

    assert result.analysis_id not in overview
    assert result.analysis_id in details


def test_result_actions_only_expose_details() -> None:
    window = MainWindow()
    result = _rdf_result("A", "B")
    name = "Queued radial analysis"
    window.results.show_result(result, context_name=name)
    window.tabs.setCurrentWidget(window.results)
    window.resize(1000, 800)
    window.show()
    _QT_APPLICATION.processEvents()

    panel = window.results
    details_top = panel.details_button.mapTo(panel.summary_box, QPoint()).y()
    assert details_top > panel.text.geometry().bottom()
    assert not hasattr(panel, "logs_button")

    panel.details_button.click()
    _QT_APPLICATION.processEvents()
    details_dialog = window.windows.get(ResultDetailsDialog)
    assert details_dialog is not None
    assert details_dialog.heading.text() == name
    assert result.analysis_id in details_dialog.text.toPlainText()
    assert (
        details_dialog.copy_button.mapTo(details_dialog, QPoint()).y()
        > details_dialog.text.geometry().bottom()
    )
    details_dialog.copy_button.click()
    assert _QT_APPLICATION.clipboard().text() == details_dialog.text.toPlainText()
    window.close()


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
    panel = ResultPanel()
    first = _rdf_result("A", "B")
    second = _rdf_result("A", "C")
    panel.show_result(first)
    panel.show_result(second)

    assert panel.result is second
    panel.plot_series.selectRow(0)
    assert panel.result is first
    panel.close()


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


def test_selection_series_uses_a_compact_ordered_action_row() -> None:
    application = _QT_APPLICATION
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
    assert series.add_button.x() < series.remove_button.x() < series.clear_button.x()
    assert series.table.horizontalHeader().sectionSize(0) < 80
    assert series.table.currentColumn() == 1
    assert series.sizePolicy().verticalPolicy() == QSizePolicy.Policy.Expanding
    assert series.table.sizePolicy().verticalPolicy() == QSizePolicy.Policy.Expanding
    series.close()


def test_configured_series_table_absorbs_vertical_window_growth() -> None:
    application = _QT_APPLICATION
    panel = ParameterPanel()
    panel.resize(900, 700)
    panel.show()
    application.processEvents()
    series = panel.rdf.series
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


def test_species_table_prioritizes_species_and_suggestion_columns() -> None:
    panel = SpeciesPanel()
    header = panel.table.horizontalHeader()

    assert header.sectionSize(0) == 180
    assert header.sectionSize(2) == 200
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


def test_species_actions_separate_help_from_suggestion_actions() -> None:
    panel = SpeciesPanel()
    panel.resize(760, 360)
    panel.set_summary(_species_summary(), {})
    panel.show()
    _QT_APPLICATION.processEvents()

    assert panel.help_button.geometry().left() < panel.details_button.geometry().left()
    assert panel.details_button.geometry().right() < panel.cancel_button.geometry().left()
    assert panel.cancel_button.geometry().right() < panel.apply_button.geometry().left()
    assert not hasattr(panel, "review_button")
    assert not hasattr(panel, "save_button")
    panel.close()


def test_species_help_uses_role_meaning_table_and_close_only() -> None:
    dialog = RoleHelpDialog()
    flags = dialog.windowFlags()

    assert dialog.table.columnCount() == 2
    assert dialog.table.rowCount() == len(SPECIES_ROLES)
    assert flags & Qt.WindowType.WindowCloseButtonHint
    assert not flags & Qt.WindowType.WindowMinimizeButtonHint
    assert not flags & Qt.WindowType.WindowMaximizeButtonHint
    assert not flags & Qt.WindowType.WindowContextHelpButtonHint
    dialog.close()


def test_species_details_format_all_suggestions() -> None:
    summary = _species_summary()
    dialog = SuggestionDetailsDialog()

    dialog.set_suggestions(summary.role_suggestions)

    plain_text = dialog.text.toPlainText()
    assert all(species in plain_text for species in summary.species)
    assert "<table" in dialog.text.toHtml().casefold()
    dialog.close()


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
    panel.analysis_choice.setCurrentText("Radial Distribution Function (RDF)")
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
    assert [panel.plot_series.item(row, 4).text() for row in range(3)] == [
        "Potential",
        "Temperature",
        "Pressure",
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


def test_main_window_separates_load_and_analysis() -> None:
    window = MainWindow()

    assert window.size().width() == 860
    assert window.size().height() == 800
    assert window.tabs.count() == 3
    assert window.load.sections.orientation() == Qt.Orientation.Vertical
    assert window.load.sections.count() == 2
    window.show()
    _QT_APPLICATION.processEvents()
    assert window.load.inputs.height() <= window.load.inputs.sizeHint().height() + 1
    opened: list[bool] = []
    window.results.open_plot_window = lambda: opened.append(True)
    window._job_completed(_rdf_result("A", "B"))
    assert opened == [True]
    assert window.tabs.currentWidget() is window.results
    window.close()


def test_main_pages_use_consistent_action_surfaces() -> None:
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
    window.tabs.setCurrentWidget(window.analysis)
    window.show()
    _QT_APPLICATION.processEvents()
    controls = (
        window.analysis.action_bar.title,
        window.analysis.cancel_button,
        window.analysis.run_button,
    )
    centers = [widget.geometry().center().y() for widget in controls]
    assert max(centers) - min(centers) <= 1
    assert (
        window.analysis.cancel_button.geometry().left()
        < window.analysis.run_button.geometry().left()
    )
    assert window.analysis.progress.geometry().top() > max(
        widget.geometry().bottom() for widget in controls
    )
    assert window.load.layout().contentsMargins().left() == PAGE_MARGIN
    assert window.load.layout().spacing() == PAGE_SPACING
    assert window.analysis.run_button.property("importance") == "primary"
    assert window.results.export_button.property("importance") == "primary"
    assert window.results.open_plot_button.parent() is window.results.action_bar
    window.close()


def test_analysis_details_opens_the_retained_job_log() -> None:
    window = MainWindow()
    details = window.analysis.details_button
    progress = window.analysis.progress
    window.tabs.setCurrentWidget(window.analysis)
    window.show()
    _QT_APPLICATION.processEvents()

    assert details.parent() is window.analysis.action_bar
    assert details.geometry().left() > progress.geometry().right()
    assert abs(details.geometry().center().y() - progress.geometry().center().y()) <= 1
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


def test_export_preserves_open_plot_content_aspect_ratio(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    window = MainWindow()
    rdf = _rdf_result("LI", "O_FSI")
    cn = _cumulative_rdf_result("LI", "O_FSI")
    window.results.show_result(rdf)
    window.results.show_result(cn)
    window.results.canvas.draw()

    def content_ratio(figure) -> float:
        width, height = figure.get_size_inches()
        bounds = figure.axes[0].get_position()
        return float(bounds.width * width / (bounds.height * height))

    planned_size = window.results.plot_size()
    planned = content_ratio(window.results.figure)
    window.results.open_plot_window()
    _QT_APPLICATION.processEvents()
    window.results.canvas.draw()
    displayed = content_ratio(window.results.figure)
    exported: list[float] = []

    def capture(figure, _output: Path, _filename: str) -> list[Path]:
        figure.canvas.draw()
        exported.append(content_ratio(figure))
        return []

    monkeypatch.setattr(export_module, "_save_figure", capture)
    window.application.exports.export_plot_model(
        window.results.plot_models()[0],
        tmp_path,
        "rdf-LI-O_FSI",
        window.results.plot_scheme(),
        window.results.plot_limits(),
        planned_size,
    )

    assert window.results.plot_size() == planned_size
    assert displayed == pytest.approx(planned, abs=0.001)
    assert exported == pytest.approx([displayed], abs=0.001)
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


def test_gui_save_plot_uses_fixed_name_for_combined_energy_terms(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    energy_result: AnalysisResult,
    stub_figure_exports,
) -> None:
    stub_figure_exports()
    window = MainWindow()
    window.results.show_result(energy_result)
    window.results.plot_series.clearSelection()
    window.results.plot_series.setRangeSelected(
        QTableWidgetSelectionRange(0, 0, 1, 5),
        True,
    )
    window.results.combine_series_button.click()
    window.session.project = SimpleNamespace(root=tmp_path)  # type: ignore[assignment]
    window.session.result = energy_result
    monkeypatch.setattr(QMessageBox, "information", lambda *_args, **_kwargs: None)

    window._save_project_figures()

    output = tmp_path / "figures"
    assert {path.name for path in output.iterdir()} == {
        f"{stem}.{suffix}"
        for stem in ("energy", "energy-Pressure")
        for suffix in ("png", "svg", "pdf")
    }
    window.close()


def test_gui_save_plot_increments_combined_rdf_cn_names(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    stub_figure_exports,
) -> None:
    stub_figure_exports()
    window = MainWindow()
    rdf = _rdf_result("LI", "O_FSI")
    cn = _cumulative_rdf_result("LI", "O_FSI")
    window.results.show_result(rdf)
    window.results.show_result(cn)
    window.session.project = SimpleNamespace(root=tmp_path)  # type: ignore[assignment]
    window.session.result = cn
    monkeypatch.setattr(QMessageBox, "information", lambda *_args, **_kwargs: None)

    window._save_project_figures()
    window._save_project_figures()

    output = tmp_path / "figures"
    assert {path.name for path in output.iterdir()} == {
        f"{stem}.{suffix}"
        for stem in ("rdf-cn", "rdf-cn-2")
        for suffix in ("png", "svg", "pdf")
    }
    window.close()


def test_gui_export_directories_add_readable_numeric_suffixes(tmp_path: Path) -> None:
    first = _rdf_result("A", "B")
    second = _rdf_result("A", "B")
    (tmp_path / "rdf-A-B").mkdir()

    items = (*result_exports(first), *result_exports(second))
    directories = export_directories(tmp_path, items)

    assert tuple(path.name for path in directories) == ("rdf-A-B-2", "rdf-A-B-3")


def test_gui_exports_each_energy_curve_to_its_own_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    energy_result: AnalysisResult,
    stub_figure_exports,
) -> None:
    stub_figure_exports()
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
    panel.analysis_choice.setCurrentText("Energy Analysis")
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


def test_templates_are_exposed_by_the_tools_menu() -> None:
    window = MainWindow()
    dialog = TemplatesDialog(window.application, window)

    assert dialog.template_list.count() >= 2
    assert dialog.text.toPlainText().isascii()
    assert dialog.copy_button.isEnabled()
    assert dialog.save_button.isEnabled()
    dialog.close()
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

    assert calls == [("Really Quit?", "Quit MDHelper?")]
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
