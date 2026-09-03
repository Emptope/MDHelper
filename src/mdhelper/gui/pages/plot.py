"""Plot state and controls for the desktop result page."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QComboBox, QTableWidgetItem, QTableWidgetSelectionRange, QWidget

from mdhelper.core.analysis import AnalysisRequest, AnalysisResult, EnergyRequest, RadialRequest
from mdhelper.core.errors import ConfigurationError
from mdhelper.core.plotting import (
    PLOT_COLORS,
    PlotAppearance,
    PlotLimits,
    PlotModel,
    PlotSelection,
    PlotSize,
    PlotState,
    results_plots,
)
from mdhelper.gui.components.choices import NoWheelComboBox
from mdhelper.gui.components.plot_controls import PlotControls
from mdhelper.gui.formatting import result_analysis_label
from mdhelper.gui.windows import WindowManager

if TYPE_CHECKING:
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
    from matplotlib.figure import Figure

    from mdhelper.gui.dialogs.plot import PlotWindow

_RESULT_ROLE = int(Qt.ItemDataRole.UserRole)
_SERIES_ROLE = _RESULT_ROLE + 1
_GROUP_ROLE = _RESULT_ROLE + 2
_TITLE_ROLE = _RESULT_ROLE + 3


class PlotPanel(PlotControls):
    state_changed = Signal()
    result_selected = Signal(object)
    results_changed = Signal(object)
    message = Signal(str)

    def __init__(
        self,
        windows: WindowManager,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._windows = windows
        self._results: dict[str, AnalysisResult] = {}
        self._limits = PlotLimits()
        self._appearance = PlotAppearance()
        self._plot_rows: tuple[tuple[int, ...], ...] = ()
        self._plot_titles: tuple[str, ...] = ()
        self._restoring = False

        self.combine_button.clicked.connect(self.combine_selected_series)
        self.separate_button.clicked.connect(self.separate_selected_series)
        self.remove_button.clicked.connect(self.remove_selected_series)
        self.clear_button.clicked.connect(self.clear_series)
        self.series.itemChanged.connect(self._plot_changed)
        self.series.itemSelectionChanged.connect(self._plot_selection_changed)
        self.title.editingFinished.connect(self._apply_title)
        self.scheme.currentIndexChanged.connect(self._coloring_changed)
        for edit in self.limit_edits():
            edit.editingFinished.connect(self._apply_limits)
        self.open_button.clicked.connect(self.open_plot_window)

    @property
    def has_results(self) -> bool:
        return bool(self._results)

    def add_result(self, result: AnalysisResult, label: str | None = None) -> None:
        if result.analysis_id not in self._results:
            self._results[result.analysis_id] = result
            self._append_series(result, label)
        else:
            self._results[result.analysis_id] = result
        self.open_button.setEnabled(True)
        self._redraw()

    def open_plot_window(self) -> None:
        if not self._results:
            return
        self._redraw()
        from mdhelper.gui.dialogs.plot import PlotWindow

        self._windows.show_all(PlotWindow)

    @property
    def plot_window(self) -> PlotWindow:
        windows = self._plot_window_items()
        if not windows:
            self._resize_plot_windows(1)
            windows = self._plot_window_items()
        return windows[0]

    @property
    def figure(self) -> Figure:
        return self.plot_window.figure

    @property
    def canvas(self) -> FigureCanvasQTAgg:
        return self.plot_window.canvas

    @property
    def plot_windows(self) -> tuple[PlotWindow, ...]:
        windows = self._plot_window_items()
        if not windows:
            self._resize_plot_windows(1)
            windows = self._plot_window_items()
        return windows

    def close_plot_windows(self) -> None:
        from mdhelper.gui.dialogs.plot import PlotWindow

        self._windows.close(PlotWindow)

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

    def plot_models(self) -> tuple[PlotModel, ...]:
        visible = self._visible_series()
        if not visible:
            return ()
        return results_plots(
            tuple(item[0] for item in visible),
            tuple(item[1] for item in visible),
            tuple(item[2] for item in visible),
            tuple(item[3] or None for item in visible),
            tuple(item[4] or None for item in visible),
            tuple(item[5] or None for item in visible),
        )

    def plot_scheme(self) -> str:
        return str(self.scheme.currentData())

    def plot_limits(self) -> PlotLimits:
        return self._limits

    def plot_appearance(self) -> PlotAppearance:
        return self._appearance

    def plot_size(self) -> PlotSize:
        width, height = self.figure.get_size_inches()
        return PlotSize(float(width), float(height))

    def plot_sizes(self) -> tuple[PlotSize, ...]:
        return tuple(
            PlotSize(*(float(value) for value in window.figure.get_size_inches()))
            for window in self.plot_windows
        )

    def plot_state(self) -> PlotState:
        selections: list[PlotSelection] = []
        for row in range(self.series.rowCount()):
            shown = self.series.item(row, 0)
            legend = self.series.item(row, 2)
            color = self.series.cellWidget(row, 3)
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
        return PlotState(
            tuple(selections),
            self.plot_scheme(),
            self._limits,
            self._appearance,
        )

    def restore_state(
        self,
        state: PlotState,
        results: tuple[AnalysisResult, ...],
    ) -> None:
        state.validate()
        available = {result.analysis_id: result for result in results}
        self._restoring = True
        try:
            self._results.clear()
            self.series.setRowCount(0)
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
            scheme_index = self.scheme.findData(state.scheme)
            if scheme_index >= 0:
                self.scheme.setCurrentIndex(scheme_index)
            self._limits = state.limits
            self._appearance = state.appearance
            self.set_limits(state.limits)
            self.open_button.setEnabled(bool(self._results))
            self._update_color_controls()
            self._normalize_plot_groups()
            self._update_plot_groups()
            self._update_series_actions()
            self._redraw()
        finally:
            self._restoring = False

    def clear(self) -> None:
        self._results.clear()
        self.series.blockSignals(True)
        self.series.setRowCount(0)
        self.series.blockSignals(False)
        windows = self._plot_window_items()
        self.close_plot_windows()
        if windows:
            self._resize_plot_windows(1)
            self.plot_window.clear_plot()
        self.open_button.setEnabled(False)
        self._plot_rows = ()
        self._plot_titles = ()
        self._update_title_control()
        self._update_series_actions()
        self.results_changed.emit(set())

    def clear_limits(self) -> None:
        for edit in self.limit_edits():
            edit.clear()
        self._limits = PlotLimits()
        self._redraw()
        self.state_changed.emit()

    def apply_plot_appearance(self, appearance: PlotAppearance) -> None:
        appearance.validate()
        self._appearance = appearance
        self._redraw()
        self.state_changed.emit()

    def remove_selected_series(self) -> None:
        rows = sorted({index.row() for index in self.series.selectedIndexes()}, reverse=True)
        self.series.blockSignals(True)
        try:
            for row in rows:
                self.series.removeRow(row)
        finally:
            self.series.blockSignals(False)
        used = {
            str(item.data(_RESULT_ROLE))
            for row in range(self.series.rowCount())
            if (item := self.series.item(row, 0)) is not None
        }
        self._results = {
            result_id: result
            for result_id, result in self._results.items()
            if result_id in used
        }
        self.open_button.setEnabled(bool(self._results))
        self._normalize_plot_groups()
        self._update_plot_groups()
        self._update_series_actions()
        self._redraw()
        self.results_changed.emit(used)
        self.state_changed.emit()

    def clear_series(self) -> None:
        self.clear()
        self.state_changed.emit()

    def combine_selected_series(self) -> None:
        rows = self._selected_plot_rows()
        if len(rows) < 2 or not all(self._is_energy_row(row) for row in rows):
            return
        group = f"energy-{uuid4()}"
        current = self.series.currentRow()
        title_rows = (current, *rows) if current in rows else rows
        title = next(
            (
                str(item.data(_TITLE_ROLE) or "")
                for row in title_rows
                if (item := self.series.item(row, 0)) is not None
                and item.data(_TITLE_ROLE)
            ),
            "",
        )
        blocked = self.series.blockSignals(True)
        try:
            for row in rows:
                shown = self.series.item(row, 0)
                if shown is not None:
                    shown.setData(_GROUP_ROLE, group)
                    shown.setData(_TITLE_ROLE, title)
        finally:
            self.series.blockSignals(blocked)
        self._normalize_plot_groups()
        self._update_plot_groups()
        self._update_series_actions()
        self._redraw()
        self.state_changed.emit()

    def separate_selected_series(self) -> None:
        rows = self._selected_plot_rows()
        if not rows:
            return
        blocked = self.series.blockSignals(True)
        try:
            for row in rows:
                shown = self.series.item(row, 0)
                if shown is not None:
                    shown.setData(_GROUP_ROLE, "")
        finally:
            self.series.blockSignals(blocked)
        self._normalize_plot_groups()
        self._update_plot_groups()
        self._update_series_actions()
        self._redraw()
        self.state_changed.emit()

    def _selected_plot_rows(self) -> tuple[int, ...]:
        return tuple(sorted({index.row() for index in self.series.selectedIndexes()}))

    def _is_energy_row(self, row: int) -> bool:
        shown = self.series.item(row, 0)
        if shown is None or not str(shown.data(_SERIES_ROLE) or ""):
            return False
        result = self._results.get(str(shown.data(_RESULT_ROLE)))
        return result is not None and result.analysis_type == "energy"

    def _row_group(self, row: int) -> str:
        shown = self.series.item(row, 0)
        return "" if shown is None else str(shown.data(_GROUP_ROLE) or "")

    def _normalize_plot_groups(self) -> None:
        counts: dict[str, int] = {}
        for row in range(self.series.rowCount()):
            shown = self.series.item(row, 0)
            group = "" if shown is None else str(shown.data(_GROUP_ROLE) or "")
            if group:
                counts[group] = counts.get(group, 0) + 1
        blocked = self.series.blockSignals(True)
        try:
            for row in range(self.series.rowCount()):
                shown = self.series.item(row, 0)
                if shown is None:
                    continue
                group = str(shown.data(_GROUP_ROLE) or "")
                if group and counts.get(group) == 1:
                    shown.setData(_GROUP_ROLE, "")
        finally:
            self.series.blockSignals(blocked)

    def _update_plot_groups(self) -> None:
        positions: dict[str, int] = {}
        blocked = self.series.blockSignals(True)
        try:
            for row in range(self.series.rowCount()):
                shown = self.series.item(row, 0)
                plot = self.series.item(row, 5)
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
            self.series.blockSignals(blocked)

    def _update_series_actions(self) -> None:
        rows = self._selected_plot_rows()
        energy = bool(rows) and all(self._is_energy_row(row) for row in rows)
        self.combine_button.setEnabled(energy and len(rows) >= 2)
        self.separate_button.setEnabled(
            energy and any(bool(self._row_group(row)) for row in rows)
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
        if isinstance(request, RadialRequest):
            result_default = f"{request.reference}-{request.selection}"
        elif isinstance(request, EnergyRequest):
            result_default = ", ".join(request.energy_terms)
        else:
            return
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
        first_row = self.series.rowCount()
        self.series.blockSignals(True)
        try:
            for key in keys:
                row = self.series.rowCount()
                default = key or result_default
                selected_label = label
                if label and len(keys) > 1:
                    selected_label = f"{label}: {key}"
                self.series.insertRow(row)
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
                self.series.setItem(row, 0, shown)
                self.series.setItem(row, 1, analysis)
                self.series.setItem(row, 2, legend)
                self.series.setCellWidget(row, 3, color)
                self.series.setItem(row, 4, selection)
                self.series.setItem(row, 5, plot)
                color.setEnabled(self.plot_scheme() == "fixed")
        finally:
            self.series.blockSignals(False)
        if keys:
            self.series.clearSelection()
            self.series.setRangeSelected(
                QTableWidgetSelectionRange(
                    first_row,
                    0,
                    self.series.rowCount() - 1,
                    self.series.columnCount() - 1,
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
        for row in range(self.series.rowCount()):
            shown = self.series.item(row, 0)
            legend = self.series.item(row, 2)
            color = self.series.cellWidget(row, 3)
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
        row = self.series.currentRow()
        if row >= 0:
            shown = self.series.item(row, 0)
            if shown is not None:
                result = self._results.get(str(shown.data(_RESULT_ROLE)))
                if result is not None:
                    self.result_selected.emit(result)
        self._update_series_actions()
        self._update_title_control()

    def _apply_limits(self) -> None:
        try:
            limits = self.limits()
            limits.validate()
        except (ConfigurationError, ValueError, TypeError) as exc:
            self.message.emit(f"Invalid plot range: {exc}")
            return
        self._limits = limits
        self._redraw()
        self.state_changed.emit()

    def _current_plot_index(self) -> int | None:
        row = self.series.currentRow()
        return next(
            (index for index, rows in enumerate(self._plot_rows) if row in rows),
            None,
        )

    def _update_title_control(self) -> None:
        index = self._current_plot_index()
        blocked = self.title.blockSignals(True)
        try:
            if index is None:
                self.title.clear()
                self.title.setEnabled(False)
            else:
                self.title.setEnabled(True)
                self.title.setText(self._plot_titles[index])
        finally:
            self.title.blockSignals(blocked)

    def _apply_title(self) -> None:
        index = self._current_plot_index()
        if index is None:
            return
        title = self.title.text().strip()
        blocked = self.series.blockSignals(True)
        try:
            for row in self._plot_rows[index]:
                shown = self.series.item(row, 0)
                if shown is not None:
                    shown.setData(_TITLE_ROLE, title)
        finally:
            self.series.blockSignals(blocked)
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
        for row in range(self.series.rowCount()):
            color = self.series.cellWidget(row, 3)
            if isinstance(color, QComboBox):
                color.setEnabled(enabled)

    def _redraw(self, _item: QTableWidgetItem | None = None) -> None:
        visible = self._visible_series()
        windows = self._plot_window_items()
        windows_open = any(window.isVisible() for window in windows)
        models = self.plot_models()
        self._plot_rows = tuple(
            tuple(visible[source][6] for source in model.source_indices)
            for model in models
        )
        self._plot_titles = tuple(model.title for model in models)
        if models or windows:
            self._resize_plot_windows(max(1, len(models)))
        windows = self._plot_window_items()
        for index, window in enumerate(windows):
            if index < len(models):
                window.draw(
                    models[index],
                    self.plot_scheme(),
                    self._limits,
                    self._appearance,
                )
            else:
                window.clear_plot()
        self._update_title_control()
        if windows_open:
            from mdhelper.gui.dialogs.plot import PlotWindow

            self._windows.show_all(PlotWindow, activate=False)

    def _plot_window_items(self) -> tuple[PlotWindow, ...]:
        from mdhelper.gui.dialogs.plot import PlotWindow

        return self._windows.items(PlotWindow)

    def _resize_plot_windows(self, count: int) -> None:
        from mdhelper.gui.dialogs.plot import PlotWindow

        self._windows.resize(PlotWindow, count)
