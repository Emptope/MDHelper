"""Species role reference and suggestion dialogs."""

from __future__ import annotations

from collections.abc import Mapping

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from mdhelper.core.species import SPECIES_ROLES, SpeciesRoleSuggestion, role_description
from mdhelper.gui.formatting import role_suggestions_html


def _close_only(dialog: QDialog) -> None:
    dialog.setWindowFlags(
        Qt.WindowType.Dialog
        | Qt.WindowType.WindowTitleHint
        | Qt.WindowType.WindowCloseButtonHint
    )


class RoleHelpDialog(QDialog):
    """Show the role vocabulary in a compact reference table."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        _close_only(self)
        self.setWindowTitle("Species Roles")
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.resize(680, 340)
        self.setMinimumSize(520, 280)

        self.table = QTableWidget(len(SPECIES_ROLES), 2)
        self.table.setHorizontalHeaderLabels(("Role", "Meaning"))
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for row, role in enumerate(SPECIES_ROLES):
            self.table.setItem(row, 0, QTableWidgetItem(role))
            self.table.setItem(row, 1, QTableWidgetItem(role_description(role)))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.addWidget(self.table)


class SuggestionDetailsDialog(QDialog):
    """Show complete evidence for every detected role suggestion."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Role Suggestion Details")
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.resize(700, 460)
        self.setMinimumSize(520, 320)
        self.text = QTextBrowser()
        self.text.setReadOnly(True)
        self.text.setOpenExternalLinks(False)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.addWidget(self.text)

    def set_suggestions(
        self, suggestions: Mapping[str, SpeciesRoleSuggestion]
    ) -> None:
        self.text.setHtml(role_suggestions_html(suggestions))
