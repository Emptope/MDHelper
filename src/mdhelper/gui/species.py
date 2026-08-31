"""Detected-species role confirmation controls."""

from __future__ import annotations

import json
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHeaderView,
    QMessageBox,
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
    role_decision,
    role_description,
)
from mdhelper.core.system import SystemSummary
from mdhelper.gui.layout import ActionBar


class SpeciesPanel(QGroupBox):
    suggestions_requested = Signal()
    save_requested = Signal()
    role_edited = Signal(str, str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__("Detected Species and Roles", parent)
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
        self.apply_button = QPushButton("Apply Suggestions")
        self.apply_button.clicked.connect(self.suggestions_requested)
        self.save_button = QPushButton("Save Roles")
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self.save_requested)
        self.help_button = QPushButton("Role Help")
        self.help_button.clicked.connect(self._show_role_help)
        self.review_button = QPushButton("Review Suggestion")
        self.review_button.setEnabled(False)
        self.review_button.clicked.connect(self._show_selected_suggestion)
        controls = ActionBar()
        controls.add_button(self.help_button)
        controls.add_button(self.review_button)
        controls.add_button(self.save_button)
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
                "Select a role for every species; use 'other' when no domain role applies.",
            )
        return roles

    def set_summary(self, summary: SystemSummary, existing_roles: dict[str, str]) -> None:
        self.table.setRowCount(len(summary.species))
        for row, (species, count) in enumerate(summary.species.items()):
            self.table.setItem(row, 0, QTableWidgetItem(species))
            self.table.setItem(row, 1, QTableWidgetItem(str(count)))
            suggestion = summary.role_suggestions[species]
            text = (
                f"{suggestion.suggested_role} ({suggestion.confidence})"
                if suggestion.available
                else f"No safe suggestion ({suggestion.confidence})"
            )
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
        self.apply_button.setEnabled(
            any(suggestion.available for suggestion in summary.role_suggestions.values())
        )
        self.review_button.setEnabled(bool(summary.species))
        if self.table.rowCount():
            self.table.selectRow(0)

    def apply_suggestions(
        self, suggestions: dict[str, SpeciesRoleSuggestion]
    ) -> dict[str, dict[str, Any]]:
        decisions: dict[str, dict[str, Any]] = {}
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            role = self.table.cellWidget(row, 2)
            if item is None or not isinstance(role, QComboBox):
                continue
            species = item.text()
            suggestion = suggestions[species]
            if suggestion.suggested_role is None:
                continue
            role.setCurrentText(suggestion.suggested_role)
            decisions[species] = role_decision(
                suggestion.suggested_role, suggestion, "suggestion_batch"
            )
        return decisions

    def apply_roles(self, roles: dict[str, str]) -> None:
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            role = self.table.cellWidget(row, 2)
            if item is not None and isinstance(role, QComboBox):
                role.setCurrentText(roles.get(item.text(), ""))

    def clear(self) -> None:
        self.table.setRowCount(0)
        self.apply_button.setEnabled(False)
        self.save_button.setEnabled(False)
        self.review_button.setEnabled(False)

    def _show_selected_suggestion(self) -> None:
        row = self.table.currentRow()
        item = self.table.item(row, 0) if row >= 0 else None
        if item is None:
            QMessageBox.information(self, "Species Role Suggestion", "Select a species to review.")
            return
        suggestion_item = self.table.item(row, 3)
        suggestion = (
            None if suggestion_item is None else suggestion_item.data(Qt.ItemDataRole.UserRole)
        )
        if not isinstance(suggestion, SpeciesRoleSuggestion):
            return
        QMessageBox.information(
            self,
            "Species Role Suggestion",
            self._suggestion_text(item.text(), suggestion),
        )

    def _show_role_help(self) -> None:
        lines = [
            "Roles describe how a species is used in the workflow and are saved in project "
            "metadata and provenance.",
            "They never change atom selections or numerical analysis algorithms.",
            "",
        ]
        lines.extend(f"{role}: {role_description(role)}" for role in SPECIES_ROLES)
        QMessageBox.information(self, "Species Roles", "\n".join(lines))

    @staticmethod
    def _suggestion_text(species: str, suggestion: SpeciesRoleSuggestion) -> str:
        candidates = ", ".join(suggestion.candidates) or "none"
        reason = suggestion.reason or "No additional reason was provided."
        return (
            f"Suggestion for {species}: {suggestion.suggested_role or 'unavailable'}\n"
            f"Confidence: {suggestion.confidence}\n"
            f"Method: {suggestion.method}\n"
            f"Reason: {reason}\n"
            f"Candidates: {candidates}\n"
            f"Evidence:\n{json.dumps(suggestion.evidence, indent=2, sort_keys=True)}\n"
            "Confirmation is always required."
        )
