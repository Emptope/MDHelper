"""Selection controls that adapt to index groups or expression input."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal, cast

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mdhelper.core.errors import InputError
from mdhelper.gui.components.layout import configure_button


class SelectionInput(QStackedWidget):
    """Show a named-group picker or a free-form expression editor."""

    def __init__(self):
        super().__init__()
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMaximumHeight(36)
        self.expression = QLineEdit()
        self.group = QComboBox()
        self.addWidget(self.expression)
        self.addWidget(self.group)
        self.source = "expression"
        self._group_value = ""
        self.group.currentIndexChanged.connect(self._remember_group)

    def setPlaceholderText(self, text: str) -> None:
        self.expression.setPlaceholderText(text)

    def set_source(self, source: str, groups: dict[str, int]) -> None:
        if self.source == "index":
            self._remember_group()
        self.source = source
        if source == "index":
            selected = self._group_value
            self.group.blockSignals(True)
            try:
                self.group.clear()
                for name, count in groups.items():
                    self.group.addItem(f"{name} ({count} atoms)", name)
                if groups:
                    self.group.setEnabled(True)
                    index = self.group.findData(selected)
                    self.group.setCurrentIndex(index if index >= 0 else 0)
                else:
                    self.group.addItem("No index groups loaded")
                    self.group.setEnabled(False)
            finally:
                self.group.blockSignals(False)
            self.setCurrentWidget(self.group)
            if groups:
                self._remember_group()
            else:
                self._group_value = ""
        else:
            self.setCurrentWidget(self.expression)

    def text(self) -> str:
        if self.source == "index":
            value = self.group.currentData()
            return "" if value is None else str(value)
        return cast(str, self.expression.text()).strip()

    def setText(self, value: str) -> None:
        text = value.strip()
        if self.source == "index":
            index = self.group.findData(text)
            if index < 0 and text:
                self.group.addItem(f"{text} (not inspected)", text)
                index = self.group.count() - 1
            self.group.setCurrentIndex(index)
            self._group_value = text
        else:
            self.expression.setText(value)

    def _remember_group(self) -> None:
        value = self.group.currentData()
        if value is not None:
            self._group_value = str(value)



class SelectionPairEditor(QWidget):
    """Place one shared syntax action beside a reference-selection pair."""

    def __init__(
        self,
        reference: SelectionInput,
        selection: SelectionInput,
        show_hint: Callable[[], None],
    ):
        super().__init__()
        self.reference_label = QLabel("Reference")
        self.selection_label = QLabel("Selection")
        self.hint_button = QPushButton("Hint")
        configure_button(self.hint_button)
        self.hint_button.clicked.connect(show_hint)
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(14)
        layout.setVerticalSpacing(10)
        layout.addWidget(self.reference_label, 0, 0)
        layout.addWidget(reference, 0, 1)
        layout.addWidget(self.selection_label, 1, 0)
        layout.addWidget(selection, 1, 1)
        layout.addWidget(self.hint_button, 0, 2, 2, 1, Qt.AlignmentFlag.AlignVCenter)
        layout.setColumnStretch(1, 1)

    def set_hint_visible(self, visible: bool) -> None:
        self.hint_button.setVisible(visible)


@dataclass(frozen=True)
class SelectionPair:
    """One enabled pair in a GUI analysis batch."""

    reference: str
    selection: str
    label: str
    parameters: dict[str, int | float] = field(default_factory=dict)


@dataclass(frozen=True)
class SelectionField:
    """One editable per-pair analysis parameter."""

    key: str
    label: str
    kind: Literal["float", "int"]


class SelectionQueue(QWidget):
    """Ordered selection pairs waiting to run and populate result plots."""

    row_loaded = Signal(object)

    def __init__(
        self,
        reference: SelectionInput,
        selection: SelectionInput,
        fields: tuple[SelectionField, ...] = (),
        labels: tuple[str, str] = ("Reference", "Selection"),
    ):
        super().__init__()
        self.reference = reference
        self.selection = selection
        self.fields = fields
        self._active_row: int | None = None
        self._defaults: dict[str, int | float] = {}
        self.table = QTableWidget(0, 4 + len(fields))
        self.table.setHorizontalHeaderLabels(
            ("Run", *labels, "Legend", *(item.label for item in fields))
        )
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setMinimumHeight(120)
        self.table.cellClicked.connect(self._load_row)

        self.add_button = QPushButton("Add Current")
        self.add_button.clicked.connect(self.add_current)
        self.remove_button = QPushButton("Remove")
        self.remove_button.clicked.connect(self.remove_selected)
        self.clear_button = QPushButton("Clear All")
        self.clear_button.clicked.connect(self.clear)
        configure_button(self.add_button, primary=True, compact=True)
        configure_button(self.remove_button, compact=True)
        configure_button(self.clear_button, compact=True)
        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.setSpacing(8)
        buttons.addWidget(QLabel("Queue items"))
        buttons.addStretch(1)
        buttons.addWidget(self.add_button)
        buttons.addWidget(self.remove_button)
        buttons.addWidget(self.clear_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addLayout(buttons)
        layout.addWidget(self.table, 1)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_defaults(
        self,
        parameters: dict[str, int | float],
    ) -> None:
        """Set values copied into subsequently added selection pairs."""

        self._defaults = {
            item.key: parameters[item.key] for item in self.fields if item.key in parameters
        }

    def set_current_parameter(self, key: str, value: int | float) -> None:
        """Apply a control edit to the active row or to future-row defaults."""

        field = next((item for item in self.fields if item.key == key), None)
        if field is None:
            return
        row = self._active_row
        if row is None or row < 0 or row >= self.table.rowCount():
            self._defaults[key] = value
            return
        column = 4 + self.fields.index(field)
        cell = self.table.item(row, column)
        if cell is not None:
            cell.setText(_parameter_text(value, field.kind))

    def add_current(self) -> None:
        reference = self.reference.text()
        selection = self.selection.text()
        if not reference or not selection:
            return
        for row in range(self.table.rowCount()):
            if self._text(row, 1) == reference and self._text(row, 2) == selection:
                self.table.setCurrentCell(row, 1)
                return
        self.add(
            SelectionPair(
                reference,
                selection,
                f"{reference}-{selection}",
                dict(self._defaults),
            )
        )

    def add(self, pair: SelectionPair) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        enabled = QTableWidgetItem()
        enabled.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
        enabled.setCheckState(Qt.CheckState.Checked)
        enabled.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        reference = QTableWidgetItem(pair.reference)
        selection = QTableWidgetItem(pair.selection)
        for cell in (reference, selection):
            cell.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        label = QTableWidgetItem(pair.label)
        label.setFlags(
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsEditable
        )
        self.table.setItem(row, 0, enabled)
        self.table.setItem(row, 1, reference)
        self.table.setItem(row, 2, selection)
        self.table.setItem(row, 3, label)
        for offset, spec in enumerate(self.fields, start=4):
            value = pair.parameters.get(spec.key, self._defaults.get(spec.key))
            parameter = QTableWidgetItem(
                "" if value is None else _parameter_text(value, spec.kind)
            )
            self.table.setItem(row, offset, parameter)
        self.table.setCurrentCell(row, 1)

    def pairs(self) -> tuple[SelectionPair, ...]:
        if not self.table.rowCount():
            reference = self.reference.text()
            selection = self.selection.text()
            if not reference or not selection:
                return ()
            return (
                SelectionPair(
                    reference,
                    selection,
                    f"{reference}-{selection}",
                    dict(self._defaults),
                ),
            )
        pairs: list[SelectionPair] = []
        for row in range(self.table.rowCount()):
            enabled = self.table.item(row, 0)
            if enabled is None or enabled.checkState() != Qt.CheckState.Checked:
                continue
            pairs.append(self._row_pair(row))
        return tuple(pairs)

    def remove_selected(self) -> None:
        rows = sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True)
        for row in rows:
            self.table.removeRow(row)
        self._active_row = None

    def clear(self) -> None:
        self.table.setRowCount(0)
        self._active_row = None

    def _load_row(self, row: int, _column: int) -> None:
        self._active_row = row
        self.reference.setText(self._text(row, 1))
        self.selection.setText(self._text(row, 2))
        self.row_loaded.emit(self._row_pair(row))

    def _text(self, row: int, column: int) -> str:
        item = self.table.item(row, column)
        return "" if item is None else item.text()

    def _row_pair(self, row: int) -> SelectionPair:
        reference = self._text(row, 1)
        selection = self._text(row, 2)
        label = self._text(row, 3).strip() or f"{reference}-{selection}"
        parameters: dict[str, int | float] = {}
        for offset, item in enumerate(self.fields, start=4):
            value = _parameter_value(self._text(row, offset), item)
            parameters[item.key] = value
        return SelectionPair(reference, selection, label, parameters)


def _parameter_text(value: int | float, kind: Literal["float", "int"]) -> str:
    return str(int(value)) if kind == "int" else f"{float(value):g}"


def _parameter_value(text: str, field: SelectionField) -> int | float:
    try:
        value: int | float = int(text) if field.kind == "int" else float(text)
    except ValueError as exc:
        raise InputError(
            f"Selection queue field {field.label!r} must be a {field.kind}."
        ) from exc
    return value
