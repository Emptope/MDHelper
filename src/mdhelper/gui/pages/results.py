"""Result history, summary, and export controls for the desktop GUI."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from mdhelper.core.analysis import AnalysisResult, analysis_label
from mdhelper.core.plotting import PlotAppearance, PlotLimits, PlotModel, PlotSize, PlotState
from mdhelper.gui.components.layout import ActionBar, page_layout
from mdhelper.gui.formatting import result_analysis_label, result_label, result_summary_html
from mdhelper.gui.plotting.panel import PlotPanel
from mdhelper.gui.windows import WindowManager

if TYPE_CHECKING:
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
    from matplotlib.figure import Figure

    from mdhelper.gui.plotting.window import PlotWindow


class ResultPanel(QWidget):
    load_requested = Signal()
    save_project_requested = Signal()
    export_requested = Signal()
    details_requested = Signal()
    advanced_plot_requested = Signal()
    state_changed = Signal()

    def __init__(
        self,
        parent: QWidget | None = None,
        windows: WindowManager | None = None,
    ):
        super().__init__(parent)
        self._windows = windows or WindowManager(self)
        self.result: AnalysisResult | None = None
        self._context_names: dict[str, str] = {}
        self.project_available = False

        layout = page_layout(self)
        history = QHBoxLayout()
        history.addWidget(QLabel("Saved results"))
        self.project_results = QComboBox()
        self.project_results.setEnabled(False)
        self.project_results.activated.connect(self.load_requested)
        history.addWidget(self.project_results, 1)
        layout.addLayout(history)

        self.text = QTextBrowser()
        self.text.setReadOnly(True)
        self.text.setOpenExternalLinks(False)
        self.summary_box = QGroupBox("Overview")
        summary_layout = QVBoxLayout(self.summary_box)
        summary_layout.setContentsMargins(12, 12, 12, 12)
        summary_layout.setSpacing(8)
        summary_layout.addWidget(self.text)
        self.details_button = QPushButton("Details")
        self.details_button.setEnabled(False)
        self.details_button.clicked.connect(self.details_requested)
        self.result_action_bar = ActionBar()
        self.result_action_bar.add_button(self.details_button)
        summary_layout.addWidget(self.result_action_bar)

        plots = PlotPanel(self._windows)
        plots.result_selected.connect(self._show_selected_result)
        plots.results_changed.connect(self._retain_context)
        plots.state_changed.connect(self.state_changed)
        plots.message.connect(self.show_message)
        plots.advanced_button.clicked.connect(self.advanced_plot_requested)
        self.plot_panel = plots
        self.plot_controls = plots
        self.combine_queue_button = plots.combine_button
        self.separate_queue_button = plots.separate_button
        self.remove_queue_button = plots.remove_button
        self.clear_queue_button = plots.clear_button
        self.plot_queue = plots.queue
        self.plot_title = plots.title
        self.color_scheme = plots.scheme
        self.x_min = plots.x_min
        self.x_max = plots.x_max
        self.y_min = plots.y_min
        self.y_max = plots.y_max
        self.y2_min = plots.y2_min
        self.y2_max = plots.y2_max
        self.open_plot_button = plots.open_button
        self.advanced_plot_button = plots.advanced_button
        self.plot_settings = plots.settings

        self.sections = QSplitter(Qt.Orientation.Horizontal)
        self.sections.setChildrenCollapsible(False)
        self.sections.addWidget(self.summary_box)
        self.sections.addWidget(plots)
        self.sections.setStretchFactor(0, 2)
        self.sections.setStretchFactor(1, 3)
        self.sections.setSizes((320, 480))
        layout.addWidget(self.sections, 1)

        self.project_button = QPushButton("Save Plot")
        self.project_button.setEnabled(False)
        self.project_button.clicked.connect(self.save_project_requested)
        self.export_button = QPushButton("Export...")
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self.export_requested)
        self.action_bar = ActionBar()
        self.action_bar.add_button(self.open_plot_button)
        self.action_bar.add_button(self.project_button)
        self.action_bar.add_button(self.export_button, primary=True)
        layout.addWidget(self.action_bar)

    def set_history(
        self,
        entries: tuple[dict[str, object], ...],
        selected_id: str | None = None,
    ) -> None:
        self.project_results.clear()
        usable = [entry for entry in entries if entry.get("available", True) is not False]
        for entry in reversed(usable):
            analysis_id = str(entry.get("analysis_id", ""))
            self.project_results.addItem(result_label(entry), analysis_id)
        available = self.project_results.count() > 0
        self.project_results.setEnabled(available)
        if selected_id:
            index = self.project_results.findData(selected_id)
            if index >= 0:
                self.project_results.setCurrentIndex(index)

    def current_id(self) -> str | None:
        value = self.project_results.currentData()
        return None if value is None else str(value)

    def show_result(
        self,
        result: AnalysisResult,
        label: str | None = None,
        context_name: str | None = None,
    ) -> None:
        self.result = result
        self.text.setHtml(result_summary_html(result))
        if context_name:
            self._context_names[result.analysis_id] = context_name
        elif result.analysis_id not in self._context_names:
            name = analysis_label(result.analysis_type)
            self._context_names[result.analysis_id] = f"{name}: {label}" if label else name
        self.plot_panel.add_result(result, label)
        self.state_changed.emit()
        self.export_button.setEnabled(True)
        self.project_button.setEnabled(self.project_available)
        self.details_button.setEnabled(True)

    def begin_batch(self, analysis_type: str) -> None:
        self.result = None
        self.text.setPlainText(
            f"Running {result_analysis_label(analysis_type)} queue..."
        )
        self.export_button.setEnabled(False)
        self.project_button.setEnabled(False)
        self.open_plot_button.setEnabled(self.plot_panel.has_results)
        self.details_button.setEnabled(False)

    def context_name(self) -> str:
        if self.result is None:
            return "Analysis"
        return self._context_names.get(
            self.result.analysis_id,
            analysis_label(self.result.analysis_type),
        )

    def restore_state(
        self,
        state: PlotState,
        results: tuple[AnalysisResult, ...],
    ) -> None:
        state.validate()
        self.plot_panel.restore_state(state, results)
        self.result = results[-1] if results else None
        self._context_names = {
            result.analysis_id: analysis_label(result.analysis_type) for result in results
        }
        if self.result is None:
            self.text.clear()
        else:
            self.text.setHtml(result_summary_html(self.result))
        available = self.result is not None
        self.export_button.setEnabled(available)
        self.project_button.setEnabled(self.project_available and available)
        self.details_button.setEnabled(available)

    def clear_result(self) -> None:
        self.result = None
        self._context_names.clear()
        self.plot_panel.clear()
        self.text.clear()
        self.export_button.setEnabled(False)
        self.project_button.setEnabled(False)
        self.details_button.setEnabled(False)

    def set_project(self, available: bool) -> None:
        self.project_available = available
        self.project_button.setEnabled(available and self.result is not None)

    def show_message(self, text: str) -> None:
        self.text.setPlainText(text)

    def open_plot_window(self) -> None:
        self.plot_panel.open_plot_window()

    @property
    def plot_window(self) -> PlotWindow:
        return self.plot_panel.plot_window

    @property
    def figure(self) -> Figure:
        return self.plot_panel.figure

    @property
    def canvas(self) -> FigureCanvasQTAgg:
        return self.plot_panel.canvas

    @property
    def plot_windows(self) -> tuple[PlotWindow, ...]:
        return self.plot_panel.plot_windows

    def close_plot_windows(self) -> None:
        self.plot_panel.close_plot_windows()

    def plot_results(self) -> tuple[AnalysisResult, ...]:
        return self.plot_panel.plot_results()

    def plot_labels(self) -> tuple[str | None, ...]:
        return self.plot_panel.plot_labels()

    def plot_color_ids(self) -> tuple[int, ...]:
        return self.plot_panel.plot_color_ids()

    def queue_series_keys(self) -> tuple[str | None, ...]:
        return self.plot_panel.queue_series_keys()

    def plot_group_ids(self) -> tuple[str | None, ...]:
        return self.plot_panel.plot_group_ids()

    def plot_titles(self) -> tuple[str | None, ...]:
        return self.plot_panel.plot_titles()

    def plot_models(self) -> tuple[PlotModel, ...]:
        return self.plot_panel.plot_models()

    def plot_scheme(self) -> str:
        return self.plot_panel.plot_scheme()

    def plot_limits(self) -> PlotLimits:
        return self.plot_panel.plot_limits()

    def plot_appearance(self) -> PlotAppearance:
        return self.plot_panel.plot_appearance()

    def plot_size(self) -> PlotSize:
        return self.plot_panel.plot_size()

    def plot_sizes(self) -> tuple[PlotSize, ...]:
        return self.plot_panel.plot_sizes()

    def plot_state(self) -> PlotState:
        return self.plot_panel.plot_state()

    def clear_limits(self) -> None:
        self.plot_panel.clear_limits()

    def _apply_limits(self) -> None:
        self.plot_panel._apply_limits()

    def apply_plot_appearance(self, appearance: PlotAppearance) -> None:
        self.plot_panel.apply_plot_appearance(appearance)

    def remove_selected_queue_items(self) -> None:
        self.plot_panel.remove_selected_queue_items()

    def clear_queue(self) -> None:
        self.plot_panel.clear_queue()

    def combine_selected_queue_items(self) -> None:
        self.plot_panel.combine_selected_queue_items()

    def separate_selected_queue_items(self) -> None:
        self.plot_panel.separate_selected_queue_items()

    def _show_selected_result(self, result: AnalysisResult) -> None:
        self.result = result
        self.text.setHtml(result_summary_html(result))
        self.details_button.setEnabled(True)

    def _retain_context(self, identifiers: set[str]) -> None:
        self._context_names = {
            result_id: name
            for result_id, name in self._context_names.items()
            if result_id in identifiers
        }
