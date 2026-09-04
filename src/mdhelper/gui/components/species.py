"""Detected-species role confirmation controls."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHeaderView,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mdhelper.core.errors import InputError
from mdhelper.core.species import (
    SPECIES_ROLES,
    SpeciesRoleSuggestion,
)
from mdhelper.core.system import SystemSummary
from mdhelper.gui.components.layout import ActionBar


class SpeciesPanel(QGroupBox):
    suggestions_requested = Signal()
    suggestions_cancelled = Signal()
    details_requested = Signal()
    role_edited = Signal(str, str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__("Species and Roles", parent)
        layout = QVBoxLayout(self)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(("Species", "Numbers", "Role", "Role suggestion"))
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.resizeSection(0, 180)
        header.resizeSection(2, 200)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self.table)
        self.apply_button = QPushButton("Apply")
        self.apply_button.setEnabled(False)
        self.apply_button.clicked.connect(self.suggestions_requested)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.suggestions_cancelled)
        self.details_button = QPushButton("Detail Suggestions")
        self.details_button.setEnabled(False)
        self.details_button.clicked.connect(self.details_requested)
        controls = ActionBar()
        controls.add_button(self.details_button)
        controls.add_button(self.cancel_button)
        controls.add_button(self.apply_button, primary=True)
        layout.addWidget(controls)
        self.action_bar = controls

    def roles(self, require_all: bool = False) -> dict[str, str]:
        roles: dict[str, str] = {}
        for row in range(self.table.rowCount()):
            species_item = self.table.item(row, 0)
            role = self.table.cellWidget(row, 2)
            if species_item and isinstance(role, QComboBox) and role.currentData():
                roles[species_item.text()] = str(role.currentData())
        if require_all and not self.table.rowCount():
            raise InputError(
                "The selected system has not been loaded.",
                "Select valid topology and trajectory files, then confirm every species role.",
            )
        if require_all and len(roles) != self.table.rowCount():
            raise InputError(
                "At least one detected species has no confirmed role.",
                "Review the automatic suggestions and select a role for every species.",
            )
        return roles

    def set_summary(self, summary: SystemSummary, existing_roles: dict[str, str]) -> None:
        self.table.setRowCount(len(summary.species))
        for row, (species, count) in enumerate(summary.species.items()):
            self.table.setItem(row, 0, QTableWidgetItem(species))
            self.table.setItem(row, 1, QTableWidgetItem(str(count)))
            suggestion = summary.role_suggestions[species]
            text = suggestion.suggested_role or "No safe suggestion"
            item = QTableWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, suggestion)
            self.table.setItem(row, 3, item)
            role = QComboBox()
            role.addItem("Select role...", "")
            for option in SPECIES_ROLES:
                role.addItem(option, option)
            if species in existing_roles:
                role.setCurrentText(existing_roles[species])
            role.currentTextChanged.connect(
                lambda selected, current=species: self.role_edited.emit(current, selected)
            )
            self.table.setCellWidget(row, 2, role)
        available = any(
            suggestion.suggested_role is not None
            for suggestion in summary.role_suggestions.values()
        )
        self.apply_button.setEnabled(available)
        self.cancel_button.setEnabled(available)
        self.details_button.setEnabled(bool(summary.role_suggestions))
        if self.table.rowCount():
            self.table.selectRow(0)

    def apply_suggestions(
        self, suggestions: dict[str, SpeciesRoleSuggestion]
    ) -> set[str]:
        applied: set[str] = set()
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            role = self.table.cellWidget(row, 2)
            if item is None or not isinstance(role, QComboBox):
                continue
            species = item.text()
            suggestion = suggestions[species]
            if suggestion.suggested_role is None or role.currentData():
                continue
            role.setCurrentText(suggestion.suggested_role)
            applied.add(species)
        return applied

    def apply_roles(self, roles: dict[str, str]) -> None:
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            role = self.table.cellWidget(row, 2)
            if item is not None and isinstance(role, QComboBox):
                role.setCurrentText(roles.get(item.text(), ""))

    def clear_roles(self, species: set[str]) -> None:
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            role = self.table.cellWidget(row, 2)
            if item is not None and item.text() in species and isinstance(role, QComboBox):
                role.setCurrentIndex(0)

    def clear(self) -> None:
        self.table.setRowCount(0)
        self.apply_button.setEnabled(False)
        self.cancel_button.setEnabled(False)
        self.details_button.setEnabled(False)
