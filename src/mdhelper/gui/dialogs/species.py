"""Species role suggestion details."""

from __future__ import annotations

from collections.abc import Mapping

from PySide6.QtWidgets import (
    QDialog,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from mdhelper.core.species import SpeciesRoleSuggestion
from mdhelper.gui.formatting import role_suggestions_html


class SuggestionDetailsDialog(QDialog):
    """Show complete evidence for every detected role suggestion."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Role Suggestion Details")
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
