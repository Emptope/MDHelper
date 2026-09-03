"""Table rendering for interactive plot entries."""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QTableWidget,
    QTableWidgetItem,
    QTableWidgetSelectionRange,
)

from mdhelper.core.plotting import PLOT_COLORS
from mdhelper.gui.components.choices import NoWheelComboBox
from mdhelper.gui.formatting import result_analysis_label

from .state import PlotEntry


class PlotTable(QTableWidget):
    color_changed = Signal()

    def __init__(self) -> None:
        super().__init__(0, 6)
        self.setHorizontalHeaderLabels(
            ("Show", "Analysis", "Legend", "Color", "Selection", "Plot")
        )
        self.horizontalHeader().setStretchLastSection(True)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setMinimumHeight(100)
        self.setMaximumHeight(180)

    def show_entries(
        self,
        entries: tuple[PlotEntry, ...],
        scheme: str,
        groups: tuple[str, ...],
        selected: tuple[int, ...] = (),
    ) -> None:
        blocked = self.blockSignals(True)
        try:
            self.setRowCount(0)
            for row, (entry, group) in enumerate(zip(entries, groups, strict=True)):
                self.insertRow(row)
                shown = QTableWidgetItem()
                shown.setFlags(
                    Qt.ItemFlag.ItemIsEnabled
                    | Qt.ItemFlag.ItemIsSelectable
                    | Qt.ItemFlag.ItemIsUserCheckable
                )
                shown.setCheckState(
                    Qt.CheckState.Checked if entry.visible else Qt.CheckState.Unchecked
                )
                analysis = QTableWidgetItem(result_analysis_label(entry.result.analysis_type))
                analysis.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                legend = QTableWidgetItem(entry.label)
                color = NoWheelComboBox()
                for item in PLOT_COLORS:
                    color.addItem(f"{item.color_id}: {item.label}", item.color_id)
                color.setCurrentIndex(color.findData(entry.color_id))
                color.setEnabled(scheme == "fixed")
                color.currentIndexChanged.connect(lambda _index: self.color_changed.emit())
                selection = QTableWidgetItem(entry.selection)
                selection.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                plot = QTableWidgetItem(group)
                plot.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                self.setItem(row, 0, shown)
                self.setItem(row, 1, analysis)
                self.setItem(row, 2, legend)
                self.setCellWidget(row, 3, color)
                self.setItem(row, 4, selection)
                self.setItem(row, 5, plot)
        finally:
            self.blockSignals(blocked)
        self.clearSelection()
        for row in selected:
            if 0 <= row < self.rowCount():
                self.setRangeSelected(
                    QTableWidgetSelectionRange(row, 0, row, self.columnCount() - 1),
                    True,
                )

    def entries(self, current: tuple[PlotEntry, ...]) -> tuple[PlotEntry, ...]:
        if self.rowCount() != len(current):
            raise RuntimeError("Plot rows do not match the active entries.")
        entries: list[PlotEntry] = []
        for row, entry in enumerate(current):
            shown = self.item(row, 0)
            legend = self.item(row, 2)
            color = self.cellWidget(row, 3)
            entries.append(
                replace(
                    entry,
                    label="" if legend is None else legend.text().strip(),
                    visible=(
                        shown is not None
                        and shown.checkState() == Qt.CheckState.Checked
                    ),
                    color_id=(
                        int(color.currentData()) if isinstance(color, QComboBox) else 0
                    ),
                )
            )
        return tuple(entries)

    def selected_rows(self) -> tuple[int, ...]:
        return tuple(sorted({index.row() for index in self.selectedIndexes()}))

    def set_color_enabled(self, enabled: bool) -> None:
        for row in range(self.rowCount()):
            color = self.cellWidget(row, 3)
            if isinstance(color, QComboBox):
                color.setEnabled(enabled)
