"""Plot coordination for the desktop result page."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget

from mdhelper.core.analysis import AnalysisResult
from mdhelper.core.errors import ConfigurationError
from mdhelper.core.plotting import PlotAppearance, PlotLimits, PlotModel, PlotSize, PlotState
from mdhelper.gui.windows import WindowManager

from .controls import PlotControls
from .state import PlotSession
from .window import PlotWindow

if TYPE_CHECKING:
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
    from matplotlib.figure import Figure


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
        self._state = PlotSession()
        self._plot_rows: tuple[tuple[int, ...], ...] = ()
        self._plot_titles: tuple[str, ...] = ()
        self._restoring = False

        self.combine_button.clicked.connect(self.combine_selected_queue_items)
        self.separate_button.clicked.connect(self.separate_selected_queue_items)
        self.remove_button.clicked.connect(self.remove_selected_queue_items)
        self.clear_button.clicked.connect(self.clear_queue)
        self.queue.itemChanged.connect(self._plot_changed)
        self.queue.itemSelectionChanged.connect(self._plot_selection_changed)
        self.queue.color_changed.connect(self._plot_changed)
        self.title.editingFinished.connect(self._apply_title)
        self.scheme.currentIndexChanged.connect(self._coloring_changed)
        for edit in self.limit_edits():
            edit.editingFinished.connect(self._apply_limits)
        self.open_button.clicked.connect(self.open_plot_window)

    @property
    def has_results(self) -> bool:
        return bool(self._state.results)

    def add_result(self, result: AnalysisResult, label: str | None = None) -> None:
        selected = self._state.add(result, label)
        if selected:
            self._render(selected)
        self.open_button.setEnabled(True)
        self._redraw()

    def open_plot_window(self) -> None:
        if not self._state.results:
            return
        self._redraw()
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
        self._windows.close(PlotWindow)

    def plot_results(self) -> tuple[AnalysisResult, ...]:
        return tuple(item[0] for item in self._visible_queue_items())

    def plot_labels(self) -> tuple[str | None, ...]:
        return tuple(item[1] for item in self._visible_queue_items())

    def plot_color_ids(self) -> tuple[int, ...]:
        return tuple(item[2] for item in self._visible_queue_items())

    def queue_series_keys(self) -> tuple[str | None, ...]:
        return tuple(item[3] or None for item in self._visible_queue_items())

    def plot_group_ids(self) -> tuple[str | None, ...]:
        return tuple(item[4] or None for item in self._visible_queue_items())

    def plot_titles(self) -> tuple[str | None, ...]:
        return tuple(item[5] or None for item in self._visible_queue_items())

    def plot_models(self) -> tuple[PlotModel, ...]:
        self._sync()
        return self._state.models()

    def plot_scheme(self) -> str:
        return str(self.scheme.currentData())

    def plot_limits(self) -> PlotLimits:
        return self._state.limits

    def plot_appearance(self) -> PlotAppearance:
        return self._state.appearance

    def plot_size(self) -> PlotSize:
        width, height = self.figure.get_size_inches()
        return PlotSize(float(width), float(height))

    def plot_sizes(self) -> tuple[PlotSize, ...]:
        return tuple(
            PlotSize(*(float(value) for value in window.figure.get_size_inches()))
            for window in self.plot_windows
        )

    def plot_state(self) -> PlotState:
        self._sync()
        return self._state.state(self.plot_scheme())

    def restore_state(
        self,
        state: PlotState,
        results: tuple[AnalysisResult, ...],
    ) -> None:
        self._restoring = True
        try:
            self._state.restore(state, results)
            scheme_index = self.scheme.findData(state.scheme)
            if scheme_index >= 0:
                self.scheme.setCurrentIndex(scheme_index)
            self.set_limits(state.limits)
            self._render()
            self.open_button.setEnabled(bool(self._state.results))
            self._update_queue_actions()
            self._redraw()
        finally:
            self._restoring = False

    def clear(self) -> None:
        self._state.clear()
        self._render()
        windows = self._plot_window_items()
        self.close_plot_windows()
        if windows:
            self._resize_plot_windows(1)
            self.plot_window.clear_plot()
        self.open_button.setEnabled(False)
        self._plot_rows = ()
        self._plot_titles = ()
        self._update_title_control()
        self._update_queue_actions()
        self.results_changed.emit(set())

    def clear_limits(self) -> None:
        for edit in self.limit_edits():
            edit.clear()
        self._state.limits = PlotLimits()
        self._redraw()
        self.state_changed.emit()

    def apply_plot_appearance(self, appearance: PlotAppearance) -> None:
        appearance.validate()
        self._state.appearance = appearance
        self._redraw()
        self.state_changed.emit()

    def remove_selected_queue_items(self) -> None:
        self._sync()
        used = self._state.remove(self._selected_plot_rows())
        self._render()
        self.open_button.setEnabled(bool(self._state.results))
        self._update_queue_actions()
        self._redraw()
        self.results_changed.emit(used)
        self.state_changed.emit()

    def clear_queue(self) -> None:
        self.clear()
        self.state_changed.emit()

    def combine_selected_queue_items(self) -> None:
        self._sync()
        rows = self._selected_plot_rows()
        if not self._state.combine(rows, self.queue.currentRow()):
            return
        self._render(rows)
        self._update_queue_actions()
        self._redraw()
        self.state_changed.emit()

    def separate_selected_queue_items(self) -> None:
        self._sync()
        rows = self._selected_plot_rows()
        if not self._state.separate(rows):
            return
        self._render(rows)
        self._update_queue_actions()
        self._redraw()
        self.state_changed.emit()

    def _selected_plot_rows(self) -> tuple[int, ...]:
        return self.queue.selected_rows()

    def _is_energy_row(self, row: int) -> bool:
        return self._state.is_energy(row)

    def _row_group(self, row: int) -> str:
        if row < 0 or row >= len(self._state.entries):
            return ""
        return self._state.entries[row].group

    def _update_queue_actions(self) -> None:
        rows = self._selected_plot_rows()
        energy = bool(rows) and all(self._is_energy_row(row) for row in rows)
        self.combine_button.setEnabled(energy and len(rows) >= 2)
        self.separate_button.setEnabled(
            energy and any(bool(self._row_group(row)) for row in rows)
        )

    def _visible_queue_items(
        self,
    ) -> tuple[tuple[AnalysisResult, str | None, int, str, str, str, int], ...]:
        self._sync()
        return tuple(
            (
                entry.result,
                entry.label or None,
                entry.color_id,
                entry.series,
                entry.group,
                entry.title,
                row,
            )
            for entry, row in self._state.visible()
        )

    def _plot_selection_changed(self) -> None:
        row = self.queue.currentRow()
        if 0 <= row < len(self._state.entries):
            self.result_selected.emit(self._state.entries[row].result)
        self._update_queue_actions()
        self._update_title_control()

    def _apply_limits(self) -> None:
        try:
            limits = self.limits()
            limits.validate()
        except (ConfigurationError, ValueError, TypeError) as exc:
            self.message.emit(f"Invalid plot range: {exc}")
            return
        self._state.limits = limits
        self._redraw()
        self.state_changed.emit()

    def _current_plot_index(self) -> int | None:
        row = self.queue.currentRow()
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
        self._sync()
        rows = self._plot_rows[index]
        self._state.set_title(rows, self.title.text().strip())
        self._render(self._selected_plot_rows())
        self._redraw()
        if not self._restoring:
            self.state_changed.emit()

    def _plot_changed(self, _value: object = None) -> None:
        self._sync()
        self._redraw()
        if not self._restoring:
            self.state_changed.emit()

    def _coloring_changed(self, _value: object = None) -> None:
        self.queue.set_color_enabled(self.plot_scheme() == "fixed")
        self._plot_changed()

    def _redraw(self) -> None:
        self._sync()
        windows = self._plot_window_items()
        windows_open = any(window.isVisible() for window in windows)
        models = self._state.models()
        self._plot_rows = self._state.rows(models)
        self._plot_titles = tuple(model.title for model in models)
        if models or windows:
            self._resize_plot_windows(max(1, len(models)))
        windows = self._plot_window_items()
        for index, window in enumerate(windows):
            if index < len(models):
                window.draw(
                    models[index],
                    self.plot_scheme(),
                    self._state.limits,
                    self._state.appearance,
                )
            else:
                window.clear_plot()
        self._update_title_control()
        if windows_open:
            self._windows.show_all(PlotWindow, activate=False)

    def _render(self, selected: tuple[int, ...] = ()) -> None:
        self.queue.show_entries(
            self._state.entries,
            self.plot_scheme(),
            self._state.group_labels(),
            selected,
        )

    def _sync(self) -> None:
        self._state.replace(self.queue.entries(self._state.entries))

    def _plot_window_items(self) -> tuple[PlotWindow, ...]:
        return self._windows.items(PlotWindow)

    def _resize_plot_windows(self, count: int) -> None:
        self._windows.resize(PlotWindow, count)
