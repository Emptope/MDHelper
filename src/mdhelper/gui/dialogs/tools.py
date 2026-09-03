"""Reference pages for GUI tools."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLabel, QLineEdit, QVBoxLayout, QWidget

MAKE_INDEX_DOCUMENTATION = (
    "https://manual.gromacs.org/documentation/current/onlinehelp/gmx-make_ndx.html"
)


class MakeIndexHelpDialog(QDialog):
    """Explain how to create an index file without a configured integration."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Make Index File")
        self.setMinimumWidth(540)

        summary = QLabel(
            "GROMACS is not configured. Configure it under Tools > Integrations, "
            "or run this command in a terminal:"
        )
        summary.setWordWrap(True)
        self.command = QLineEdit("gmx make_ndx -f structure.gro -o index.ndx")
        self.command.setReadOnly(True)
        self.documentation = QLabel(
            f'<a href="{MAKE_INDEX_DOCUMENTATION}">Open the gmx make_ndx documentation</a>'
        )
        self.documentation.setOpenExternalLinks(True)
        self.documentation.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        layout.addWidget(summary)
        layout.addWidget(self.command)
        layout.addWidget(self.documentation)
