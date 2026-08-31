"""Result history, plot, and export controls for the desktop GUI."""

from __future__ import annotations

from uuid import uuid4

from matplotlib.figure import Figure
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCloseEvent, QDoubleValidator
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTableWidgetSelectionRange,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from mdhelper.core.analysis import AnalysisRequest, AnalysisResult
from mdhelper.core.errors import ConfigurationError
from mdhelper.core.plotting import (
    DEFAULT_PLOT_SCHEME,
    MAX_PLOT_TITLE_LENGTH,
    PLOT_COLORS,
    PLOT_SCHEMES,
    PlotLimits,
    PlotModel,
    PlotSelection,
    PlotState,
    draw_plot,
    results_plots,
)
from mdhelper.core.units import ANGSTROM_SYMBOL
from mdhelper.gui.choices import NoWheelComboBox
from mdhelper.gui.formatting import (
    result_analysis_label,
    result_label,
    result_summary_html,
)
from mdhelper.gui.layout import ActionBar, page_layout
from mdhelper.gui.plot_window import PlotWindow

_RESULT_ROLE = int(Qt.ItemDataRole.UserRole)
_SERIES_ROLE = _RESULT_ROLE + 1
_GROUP_ROLE = _RESULT_ROLE + 2
_TITLE_ROLE = _RESULT_ROLE + 3


class ResultPanel(QWidget):
    load_requested = Signal()
    save_project_requested = Signal()
    export_requested = Signal()
    state_changed = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.result: AnalysisResult | None = None
        self._results: dict[str, AnalysisResult] = {}
        self._limits = PlotLimits()
        self._plot_rows: tuple[tuple[int, ...], ...] = ()
        self._plot_titles: tuple[str, ...] = ()
        self._restoring = False
        self.project_available = False
        self._plot_windows = [PlotWindow()]
        self.plot_window = self._plot_windows[0]
        # Keep these attributes available to callers that inspect or export the
        # current figure; the canvas itself lives in the standalone window.
        self.figure = self.plot_window.figure
        self.canvas = self.plot_window.canvas
        layout = page_layout(self)
        history = QHBoxLayout()
        history.addWidget(QLabel("Saved results"))
        self.project_results = QComboBox()
        self.project_results.setEnabled(False)
        self.project_results.activated.connect(self.load_requested)
        self.load_button = QPushButton("Load")
        self.load_button.setEnabled(False)
        self.load_button.clicked.connect(self.load_requested)
        history.addWidget(self.project_results, 1)
        history.addWidget(self.load_button)
        layout.addLayout(history)
        self.text = QTextBrowser()
        self.text.setReadOnly(True)
        self.text.setOpenExternalLinks(False)
        self.summary_box = QGroupBox("Result overview")
        summary_layout = QVBoxLayout(self.summary_box)
        summary_layout.setContentsMargins(12, 12, 12, 12)
        summary_layout.setSpacing(8)
        summary_layout.addWidget(self.text)
        plot_panel = QWidget()
        plot_layout = QVBoxLayout(plot_panel)
        plot_layout.setContentsMargins(0, 0, 0, 0)
        plot_layout.setSpacing(layout.spacing())
        series_controls = QHBoxLayout()
        series_controls.addWidget(QLabel("Plot series"))
        self.combine_series_button = QPushButton("Combine")
        self.combine_series_button.setEnabled(False)
        self.combine_series_button.clicked.connect(self.combine_selected_series)
        self.separate_series_button = QPushButton("Separate")
        self.separate_series_button.setEnabled(False)
        self.separate_series_button.clicked.connect(self.separate_selected_series)
        self.remove_series_button = QPushButton("Remove")
        self.remove_series_button.clicked.connect(self.remove_selected_series)
        self.clear_series_button = QPushButton("Clear All")
        self.clear_series_button.clicked.connect(self.clear_series)
        series_controls.addWidget(self.combine_series_button)
        series_controls.addWidget(self.separate_series_button)
        series_controls.addStretch(1)
        series_controls.addWidget(self.remove_series_button)
        series_controls.addWidget(self.clear_series_button)
        plot_layout.addLayout(series_controls)
        self.plot_series = QTableWidget(0, 6)
        self.plot_series.setHorizontalHeaderLabels(
            ("Show", "Analysis", "Legend", "Color", "Selection", "Plot")
        )
        self.plot_series.horizontalHeader().setStretchLastSection(True)
        self.plot_series.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.plot_series.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.plot_series.setMinimumHeight(100)
        self.plot_series.setMaximumHeight(180)
        self.plot_series.itemChanged.connect(self._plot_changed)
        self.plot_series.itemSelectionChanged.connect(self._plot_selection_changed)
        plot_layout.addWidget(self.plot_series)
        settings = QGroupBox("Plot Settings")
        plot_controls = QGridLayout(settings)
        plot_controls.setContentsMargins(12, 10, 12, 10)
        plot_controls.setHorizontalSpacing(10)
        plot_controls.setVerticalSpacing(8)
        plot_controls.addWidget(QLabel("Title"), 0, 0)
        self.plot_title = QLineEdit()
        self.plot_title.setMaxLength(MAX_PLOT_TITLE_LENGTH)
        self.plot_title.setEnabled(False)
        self.plot_title.editingFinished.connect(self._apply_title)
        plot_controls.addWidget(self.plot_title, 0, 1, 1, 2)
        plot_controls.addWidget(QLabel("Color by"), 1, 0)
        self.color_scheme = QComboBox()
        for scheme in PLOT_SCHEMES:
            self.color_scheme.addItem(scheme.label, scheme.key)
        default_scheme = self.color_scheme.findData(DEFAULT_PLOT_SCHEME)
        self.color_scheme.setCurrentIndex(default_scheme)
        self.color_scheme.currentIndexChanged.connect(self._coloring_changed)
        plot_controls.addWidget(self.color_scheme, 1, 1)
        self.x_min = _limit_edit("Min")
        self.x_max = _limit_edit("Max")
        self.y_min = _limit_edit("Min")
        self.y_max = _limit_edit("Max")
        self.y2_min = _limit_edit("Min")
        self.y2_max = _limit_edit("Max")
        for edit in (
            self.x_min,
            self.x_max,
            self.y_min,
            self.y_max,
            self.y2_min,
            self.y2_max,
        ):
            edit.editingFinished.connect(self._apply_limits)
        plot_controls.addWidget(QLabel("Range"), 2, 0)
        plot_controls.addWidget(QLabel("Minimum"), 2, 1)
        plot_controls.addWidget(QLabel("Maximum"), 2, 2)
        for row, (label, minimum, maximum) in enumerate(
            (
                (f"Distance X ({ANGSTROM_SYMBOL})", self.x_min, self.x_max),
                ("Primary Y", self.y_min, self.y_max),
                ("Secondary Y", self.y2_min, self.y2_max),
            ),
            start=3,
        ):
            plot_controls.addWidget(QLabel(label), row, 0)
            plot_controls.addWidget(minimum, row, 1)
            plot_controls.addWidget(maximum, row, 2)
        self.open_plot_button = QPushButton("Open Plot Window")
        self.open_plot_button.setEnabled(False)
        self.open_plot_button.clicked.connect(self.open_plot_window)
        for column in range(3):
            plot_controls.setColumnStretch(column, 1)
        plot_controls.setRowStretch(plot_controls.rowCount(), 1)
        plot_layout.addWidget(settings)
        self.plot_settings = settings
        sections = QSplitter(Qt.Orientation.Horizontal)
        sections.setChildrenCollapsible(False)
        sections.addWidget(self.summary_box)
        sections.addWidget(plot_panel)
        sections.setStretchFactor(0, 2)
        sections.setStretchFactor(1, 3)
        sections.setSizes((320, 480))
        layout.addWidget(sections, 1)
        self.sections = sections
        self.plot_panel = plot_panel
        self.project_button = QPushButton("Save Plot")
        self.project_button.setEnabled(False)
        self.project_button.clicked.connect(self.save_project_requested)
        self.export_button = QPushButton("Export...")
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self.export_requested)
        actions = ActionBar()
        actions.add_button(self.open_plot_button)
        actions.add_button(self.project_button)
        actions.add_button(self.export_button, primary=True)
        layout.addWidget(actions)
        self.action_bar = actions

    def set_history(
        self, entries: tuple[dict[str, object], ...], selected_id: str | None = None
    ) -> None:
        self.project_results.clear()
        usable = [entry for entry in entries if entry.get("available", True) is not False]
        for entry in reversed(usable):
            analysis_id = str(entry.get("analysis_id", ""))
            self.project_results.addItem(result_label(entry), analysis_id)
        available = self.project_results.count() > 0
        self.project_results.setEnabled(available)
        self.load_button.setEnabled(available)
        if selected_id:
            index = self.project_results.findData(selected_id)
            if index >= 0:
                self.project_results.setCurrentIndex(index)

    def current_id(self) -> str | None:
        value = self.project_results.currentData()
        return None if value is None else str(value)

    def show_result(self, result: AnalysisResult, label: str | None = None) -> None:
        self.result = result
        self.text.setHtml(result_summary_html(result))
        if result.analysis_id not in self._results:
            self._results[result.analysis_id] = result
            self._append_series(result, label)
        else:
            self._results[result.analysis_id] = result
        self._redraw()
        self.state_changed.emit()
        self.export_button.setEnabled(True)
        self.project_button.setEnabled(self.project_available)
        self.open_plot_button.setEnabled(True)

    def begin_batch(self, analysis_type: str) -> None:
        """Announce a batch without discarding stored plot representations."""

        self.result = None
        self.text.setPlainText(
            f"Running {result_analysis_label(analysis_type)} plot series..."
        )
        self.export_button.setEnabled(False)
        self.project_button.setEnabled(False)
        self.open_plot_button.setEnabled(bool(self._results))

    def open_plot_window(self) -> None:
        """Show each independent plot in its own standalone window."""

        if not self._results:
            return
        self._redraw()
        for window in self._plot_windows:
            window.show()
            window.raise_()
            window.activateWindow()

    @property
    def plot_windows(self) -> tuple[PlotWindow, ...]:
        return tuple(self._plot_windows)

    def close_plot_windows(self) -> None:
        for window in self._plot_windows:
            window.close()

    def plot_results(self) -> tuple[AnalysisResult, ...]:
        return tuple(item[0] for item in self._visible_series())

    def plot_labels(self) -> tuple[str | None, ...]:
        return tuple(item[1] for item in self._visible_series())

    def plot_color_ids(self) -> tuple[int, ...]:
        return tuple(item[2] for item in self._visible_series())

    def plot_series_keys(self) -> tuple[str | None, ...]:
        return tuple(item[3] or None for item in self._visible_series())

    def plot_group_ids(self) -> tuple[str | None, ...]:
        return tuple(item[4] or None for item in self._visible_series())

    def plot_titles(self) -> tuple[str | None, ...]:
        return tuple(item[5] or None for item in self._visible_series())

    def plot_scheme(self) -> str:
        return str(self.color_scheme.currentData())

    def plot_limits(self) -> PlotLimits:
        return self._limits

    def plot_state(self) -> PlotState:
        selections: list[PlotSelection] = []
        for row in range(self.plot_series.rowCount()):
            shown = self.plot_series.item(row, 0)
            legend = self.plot_series.item(row, 2)
            color = self.plot_series.cellWidget(row, 3)
            if shown is None:
                continue
            selections.append(
                PlotSelection(
                    str(shown.data(_RESULT_ROLE)),
                    "" if legend is None else legend.text().strip(),
                    shown.checkState() == Qt.CheckState.Checked,
                    int(color.currentData()) if isinstance(color, QComboBox) else 0,
                    str(shown.data(_SERIES_ROLE) or ""),
                    str(shown.data(_GROUP_ROLE) or ""),
                    str(shown.data(_TITLE_ROLE) or ""),
                )
            )
        return PlotState(tuple(selections), self.plot_scheme(), self._limits)

    def restore_state(
        self,
        state: PlotState,
        results: tuple[AnalysisResult, ...],
    ) -> None:
        state.validate()
        available = {result.analysis_id: result for result in results}
        self._restoring = True
        try:
            self.result = results[-1] if results else None
            self._results.clear()
            self.plot_series.setRowCount(0)
            for selection in state.selections:
                result = available.get(selection.result_id)
                if result is None:
                    continue
                self._results[result.analysis_id] = result
                self._append_series(
                    result,
                    selection.label or None,
                    selection.visible,
                    selection.color_id,
                    selection.series or None,
                    selection.group,
                    selection.title,
                )
            scheme_index = self.color_scheme.findData(state.scheme)
            if scheme_index >= 0:
                self.color_scheme.setCurrentIndex(scheme_index)
            self._limits = state.limits
            self._show_limits(state.limits)
            if self.result is not None:
                self.text.setHtml(result_summary_html(self.result))
            else:
                self.text.clear()
            self.export_button.setEnabled(self.result is not None)
            self.project_button.setEnabled(
                self.project_available and self.result is not None
            )
            self.open_plot_button.setEnabled(bool(self._results))
            self._update_color_controls()
            self._normalize_plot_groups()
            self._update_plot_groups()
            self._update_series_actions()
            self._redraw()
        finally:
            self._restoring = False

    def clear_result(self) -> None:
        self.result = None
        self._results.clear()
        self.plot_series.blockSignals(True)
        self.plot_series.setRowCount(0)
        self.plot_series.blockSignals(False)
        self.text.clear()
        self.close_plot_windows()
        self._resize_plot_windows(1)
        self.figure.clear()
        self.figure.set_facecolor("white")
        self.canvas.draw_idle()
        self.export_button.setEnabled(False)
        self.project_button.setEnabled(False)
        self.open_plot_button.setEnabled(False)
        self._plot_rows = ()
        self._plot_titles = ()
        self._update_title_control()
        self._update_series_actions()

    def set_project(self, available: bool) -> None:
        self.project_available = available
        self.project_button.setEnabled(available and self.result is not None)

    def show_message(self, text: str) -> None:
        self.text.setPlainText(text)

    def clear_limits(self) -> None:
        for edit in (
            self.x_min,
            self.x_max,
            self.y_min,
            self.y_max,
            self.y2_min,
            self.y2_max,
        ):
            edit.clear()
        self._limits = PlotLimits()
        self._redraw()
        self.state_changed.emit()

    def closeEvent(self, event: QCloseEvent) -> None:
        self.close_plot_windows()
        super().closeEvent(event)

    def remove_selected_series(self) -> None:
        rows = sorted(
            {index.row() for index in self.plot_series.selectedIndexes()}, reverse=True
        )
        self.plot_series.blockSignals(True)
        try:
            for row in rows:
                self.plot_series.removeRow(row)
        finally:
            self.plot_series.blockSignals(False)
        used = {
            str(item.data(_RESULT_ROLE))
            for row in range(self.plot_series.rowCount())
            if (item := self.plot_series.item(row, 0)) is not None
        }
        self._results = {
            result_id: result
            for result_id, result in self._results.items()
            if result_id in used
        }
        self.open_plot_button.setEnabled(bool(self._results))
        self._normalize_plot_groups()
        self._update_plot_groups()
        self._update_series_actions()
        self._redraw()
        self.state_changed.emit()

    def clear_series(self) -> None:
        self._results.clear()
        self.plot_series.blockSignals(True)
        self.plot_series.setRowCount(0)
        self.plot_series.blockSignals(False)
        self.close_plot_windows()
        self._resize_plot_windows(1)
        self.figure.clear()
        self.figure.set_facecolor("white")
        self.canvas.draw_idle()
        self.open_plot_button.setEnabled(False)
        self._plot_rows = ()
        self._plot_titles = ()
        self._update_title_control()
        self._update_series_actions()
        self.state_changed.emit()

    def combine_selected_series(self) -> None:
        rows = self._selected_plot_rows()
        if len(rows) < 2 or not all(self._is_energy_row(row) for row in rows):
            return
        group = f"energy-{uuid4()}"
        current = self.plot_series.currentRow()
        title_rows = (current, *rows) if current in rows else rows
        title = next(
            (
                str(item.data(_TITLE_ROLE) or "")
                for row in title_rows
                if (item := self.plot_series.item(row, 0)) is not None
                and item.data(_TITLE_ROLE)
            ),
            "",
        )
        blocked = self.plot_series.blockSignals(True)
        try:
            for row in rows:
                shown = self.plot_series.item(row, 0)
                if shown is not None:
                    shown.setData(_GROUP_ROLE, group)
                    shown.setData(_TITLE_ROLE, title)
        finally:
            self.plot_series.blockSignals(blocked)
        self._normalize_plot_groups()
        self._update_plot_groups()
        self._update_series_actions()
        self._redraw()
        self.state_changed.emit()

    def separate_selected_series(self) -> None:
        rows = self._selected_plot_rows()
        if not rows:
            return
        blocked = self.plot_series.blockSignals(True)
        try:
            for row in rows:
                shown = self.plot_series.item(row, 0)
                if shown is not None:
                    shown.setData(_GROUP_ROLE, "")
        finally:
            self.plot_series.blockSignals(blocked)
        self._normalize_plot_groups()
        self._update_plot_groups()
        self._update_series_actions()
        self._redraw()
        self.state_changed.emit()

    def _selected_plot_rows(self) -> tuple[int, ...]:
        return tuple(sorted({index.row() for index in self.plot_series.selectedIndexes()}))

    def _is_energy_row(self, row: int) -> bool:
        shown = self.plot_series.item(row, 0)
        if shown is None or not str(shown.data(_SERIES_ROLE) or ""):
            return False
        result = self._results.get(str(shown.data(_RESULT_ROLE)))
        return result is not None and result.analysis_type == "energy"

    def _row_group(self, row: int) -> str:
        shown = self.plot_series.item(row, 0)
        return "" if shown is None else str(shown.data(_GROUP_ROLE) or "")

    def _normalize_plot_groups(self) -> None:
        counts: dict[str, int] = {}
        for row in range(self.plot_series.rowCount()):
            shown = self.plot_series.item(row, 0)
            group = "" if shown is None else str(shown.data(_GROUP_ROLE) or "")
            if group:
                counts[group] = counts.get(group, 0) + 1
        blocked = self.plot_series.blockSignals(True)
        try:
            for row in range(self.plot_series.rowCount()):
                shown = self.plot_series.item(row, 0)
                if shown is None:
                    continue
                group = str(shown.data(_GROUP_ROLE) or "")
                if group and counts.get(group) == 1:
                    shown.setData(_GROUP_ROLE, "")
        finally:
            self.plot_series.blockSignals(blocked)

    def _update_plot_groups(self) -> None:
        positions: dict[str, int] = {}
        blocked = self.plot_series.blockSignals(True)
        try:
            for row in range(self.plot_series.rowCount()):
                shown = self.plot_series.item(row, 0)
                plot = self.plot_series.item(row, 5)
                if shown is None or plot is None:
                    continue
                series = str(shown.data(_SERIES_ROLE) or "")
                if not series:
                    plot.setText("Automatic")
                    continue
                group = str(shown.data(_GROUP_ROLE) or "")
                key = group or f"row-{row}"
                if key not in positions:
                    positions[key] = len(positions) + 1
                suffix = " - Combined" if group else ""
                plot.setText(f"Plot {positions[key]}{suffix}")
        finally:
            self.plot_series.blockSignals(blocked)

    def _update_series_actions(self) -> None:
        rows = self._selected_plot_rows()
        energy = bool(rows) and all(self._is_energy_row(row) for row in rows)
        self.combine_series_button.setEnabled(energy and len(rows) >= 2)
        self.separate_series_button.setEnabled(
            energy
            and any(bool(self._row_group(row)) for row in rows)
        )

    def _append_series(
        self,
        result: AnalysisResult,
        label: str | None,
        visible: bool = True,
        color_id: int | None = None,
        series_key: str | None = None,
        group: str = "",
        title: str = "",
    ) -> None:
        request = AnalysisRequest.from_dict(result.request)
        result_default = (
            f"{request.reference}-{request.selection}"
            if request.selection
            else request.reference
            or ", ".join(request.energy_terms)
        )
        keys: tuple[str, ...]
        if result.analysis_type == "energy":
            values = result.data.get("series")
            if not isinstance(values, dict):
                return
            available = tuple(str(key) for key in values)
            keys = available if series_key is None else (series_key,)
            if any(key not in available for key in keys):
                return
        else:
            keys = ("",)
        first_row = self.plot_series.rowCount()
        self.plot_series.blockSignals(True)
        try:
            for key in keys:
                row = self.plot_series.rowCount()
                default = key or result_default
                selected_label = label
                if label and len(keys) > 1:
                    selected_label = f"{label}: {key}"
                self.plot_series.insertRow(row)
                shown = QTableWidgetItem()
                shown.setFlags(
                    Qt.ItemFlag.ItemIsEnabled
                    | Qt.ItemFlag.ItemIsSelectable
                    | Qt.ItemFlag.ItemIsUserCheckable
                )
                shown.setCheckState(
                    Qt.CheckState.Checked if visible else Qt.CheckState.Unchecked
                )
                shown.setData(_RESULT_ROLE, result.analysis_id)
                shown.setData(_SERIES_ROLE, key)
                shown.setData(_GROUP_ROLE, group)
                shown.setData(_TITLE_ROLE, title)
                analysis = QTableWidgetItem(result_analysis_label(result.analysis_type))
                analysis.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                legend = QTableWidgetItem(selected_label or default)
                color = NoWheelComboBox()
                for item in PLOT_COLORS:
                    color.addItem(f"{item.color_id}: {item.label}", item.color_id)
                selected_color = row % len(PLOT_COLORS) if color_id is None else color_id
                color.setCurrentIndex(color.findData(selected_color))
                color.currentIndexChanged.connect(self._plot_changed)
                selection = QTableWidgetItem(default)
                selection.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                plot = QTableWidgetItem()
                plot.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                self.plot_series.setItem(row, 0, shown)
                self.plot_series.setItem(row, 1, analysis)
                self.plot_series.setItem(row, 2, legend)
                self.plot_series.setCellWidget(row, 3, color)
                self.plot_series.setItem(row, 4, selection)
                self.plot_series.setItem(row, 5, plot)
                color.setEnabled(self.plot_scheme() == "fixed")
        finally:
            self.plot_series.blockSignals(False)
        if keys:
            self.plot_series.clearSelection()
            self.plot_series.setRangeSelected(
                QTableWidgetSelectionRange(
                    first_row,
                    0,
                    self.plot_series.rowCount() - 1,
                    self.plot_series.columnCount() - 1,
                ),
                True,
            )
        self._update_plot_groups()
        self._update_series_actions()

    def _visible_series(
        self,
    ) -> tuple[tuple[AnalysisResult, str | None, int, str, str, str, int], ...]:
        visible: list[
            tuple[AnalysisResult, str | None, int, str, str, str, int]
        ] = []
        for row in range(self.plot_series.rowCount()):
            shown = self.plot_series.item(row, 0)
            legend = self.plot_series.item(row, 2)
            color = self.plot_series.cellWidget(row, 3)
            if shown is None or shown.checkState() != Qt.CheckState.Checked:
                continue
            result = self._results.get(str(shown.data(_RESULT_ROLE)))
            if result is None:
                continue
            text = "" if legend is None else legend.text().strip()
            color_id = int(color.currentData()) if isinstance(color, QComboBox) else 0
            visible.append(
                (
                    result,
                    text or None,
                    color_id,
                    str(shown.data(_SERIES_ROLE) or ""),
                    str(shown.data(_GROUP_ROLE) or ""),
                    str(shown.data(_TITLE_ROLE) or ""),
                    row,
                )
            )
        return tuple(visible)

    def _plot_selection_changed(self) -> None:
        self._show_selected_series()
        self._update_series_actions()
        self._update_title_control()

    def _show_selected_series(self) -> None:
        row = self.plot_series.currentRow()
        if row < 0:
            return
        shown = self.plot_series.item(row, 0)
        if shown is None:
            return
        result = self._results.get(str(shown.data(_RESULT_ROLE)))
        if result is None:
            return
        self.result = result
        self.text.setHtml(result_summary_html(result))

    def _apply_limits(self) -> None:
        try:
            limits = PlotLimits(
                _limit_value(self.x_min),
                _limit_value(self.x_max),
                _limit_value(self.y_min),
                _limit_value(self.y_max),
                _limit_value(self.y2_min),
                _limit_value(self.y2_max),
            )
            limits.validate()
        except (ConfigurationError, ValueError, TypeError) as exc:
            self.show_message(f"Invalid plot range: {exc}")
            return
        self._limits = limits
        self._redraw()
        self.state_changed.emit()

    def _show_limits(self, limits: PlotLimits) -> None:
        values = (
            (self.x_min, limits.x_min),
            (self.x_max, limits.x_max),
            (self.y_min, limits.y_min),
            (self.y_max, limits.y_max),
            (self.y2_min, limits.y2_min),
            (self.y2_max, limits.y2_max),
        )
        for edit, value in values:
            edit.setText("" if value is None else f"{value:g}")

    def _current_plot_index(self) -> int | None:
        row = self.plot_series.currentRow()
        return next(
            (index for index, rows in enumerate(self._plot_rows) if row in rows),
            None,
        )

    def _update_title_control(self) -> None:
        index = self._current_plot_index()
        blocked = self.plot_title.blockSignals(True)
        try:
            if index is None:
                self.plot_title.clear()
                self.plot_title.setEnabled(False)
            else:
                self.plot_title.setEnabled(True)
                self.plot_title.setText(self._plot_titles[index])
        finally:
            self.plot_title.blockSignals(blocked)

    def _apply_title(self) -> None:
        index = self._current_plot_index()
        if index is None:
            return
        title = self.plot_title.text().strip()
        blocked = self.plot_series.blockSignals(True)
        try:
            for row in self._plot_rows[index]:
                shown = self.plot_series.item(row, 0)
                if shown is not None:
                    shown.setData(_TITLE_ROLE, title)
        finally:
            self.plot_series.blockSignals(blocked)
        self._redraw()
        if not self._restoring:
            self.state_changed.emit()

    def _plot_changed(self, _value: object = None) -> None:
        self._redraw()
        if not self._restoring:
            self.state_changed.emit()

    def _coloring_changed(self, _value: object = None) -> None:
        self._update_color_controls()
        self._plot_changed()

    def _update_color_controls(self) -> None:
        enabled = self.plot_scheme() == "fixed"
        for row in range(self.plot_series.rowCount()):
            color = self.plot_series.cellWidget(row, 3)
            if isinstance(color, QComboBox):
                color.setEnabled(enabled)

    def _redraw(self, _item: QTableWidgetItem | None = None) -> None:
        visible = self._visible_series()
        windows_open = any(window.isVisible() for window in self._plot_windows)
        models: tuple[PlotModel, ...] = ()
        if visible:
            models = results_plots(
                tuple(item[0] for item in visible),
                tuple(item[1] for item in visible),
                tuple(item[2] for item in visible),
                tuple(item[3] or None for item in visible),
                tuple(item[4] or None for item in visible),
                tuple(item[5] or None for item in visible),
            )
        self._plot_rows = tuple(
            tuple(visible[source][6] for source in model.source_indices)
            for model in models
        )
        self._plot_titles = tuple(model.title for model in models)
        self._resize_plot_windows(max(1, len(models)))
        for index, window in enumerate(self._plot_windows):
            figure = window.figure
            figure.clear()
            figure.set_facecolor("white")
            if index < len(models):
                model = models[index]
                axis = figure.add_subplot(1, 1, 1)
                draw_plot(axis, model, self.plot_scheme(), self._limits)
                window.setWindowTitle(f"MDHelper Plot - {model.title}")
                _style_plot(figure)
            else:
                window.setWindowTitle("MDHelper Plot")
            window.canvas.draw_idle()
        self._update_title_control()
        if windows_open:
            for window in self._plot_windows:
                window.show()
                window.raise_()

    def _resize_plot_windows(self, count: int) -> None:
        while len(self._plot_windows) < count:
            self._plot_windows.append(PlotWindow())
        while len(self._plot_windows) > count:
            self._plot_windows.pop().close()


def _style_plot(figure: Figure) -> None:
    """Keep plots in a consistent light publication style."""

    figure.set_facecolor("white")
    for axis in figure.axes:
        axis.set_facecolor("white")
        axis.title.set_color("#202020")
        axis.xaxis.label.set_color("#202020")
        axis.yaxis.label.set_color("#202020")
        axis.tick_params(colors="#202020")
        for spine in axis.spines.values():
            spine.set_color("#707070")
        if axis.patch.get_visible():
            axis.grid(color="#b0b0b0", alpha=0.35)
        else:
            axis.grid(False)


def _limit_edit(placeholder: str) -> QLineEdit:
    edit = QLineEdit()
    validator = QDoubleValidator(edit)
    validator.setNotation(QDoubleValidator.Notation.ScientificNotation)
    edit.setValidator(validator)
    edit.setPlaceholderText(placeholder)
    edit.setMaximumWidth(76)
    return edit


def _limit_value(edit: QLineEdit) -> float | None:
    text = edit.text().strip()
    return None if not text else float(text)
