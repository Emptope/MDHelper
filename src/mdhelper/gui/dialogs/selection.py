"""Selection syntax reference dialog."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

SelectionHints = tuple[tuple[str, str, str], ...]

MDANALYSIS_SELECTION_HINTS: SelectionHints = (
    ("all", "Every atom", "all"),
    ("name", "Atom name; patterns are accepted", "name O*"),
    ("type", "Topology atom type", "type OW"),
    ("element", "Chemical element", "element O"),
    ("resname", "Residue or species name", "resname SOL"),
    ("resid", "Residue ID; ranges are accepted", "resid 10:20"),
    ("index", "Zero-based atom index", "index 0 4 8"),
    ("bynum", "One-based atom serial number", "bynum 1:10"),
    ("and / or / not", "Combine or exclude matches", "resname SOL and element O"),
    ("( expression )", "Make precedence explicit", "(resname SOL or resname ADD) and name O*"),
)

GROMACS_SELECTION_HINTS: SelectionHints = (
    ("Reference (-ref)", "GROMACS Selection Language", "Passed to gmx rdf -ref"),
    ("Selection (-sel)", "GROMACS Selection Language", "Passed to gmx rdf -sel"),
)

SELECTION_DOCUMENTATION = {
    "gromacs": "https://manual.gromacs.org/current/onlinehelp/selections.html",
    "mdanalysis": "https://userguide.mdanalysis.org/stable/selections.html",
}

SELECTION_HINTS = MDANALYSIS_SELECTION_HINTS


class SelectionHintDialog(QDialog):
    """Show common selection building blocks for one expression backend."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.resize(760, 390)
        self.setMinimumSize(680, 340)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(("Selector", "Meaning", "Example"))
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.addWidget(self.table)
        self.documentation = QLabel()
        self.documentation.setOpenExternalLinks(True)
        self.documentation.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction
        )
        layout.addWidget(self.documentation)
        self.backend = ""
        self.set_backend("mdanalysis")

    def set_backend(self, backend: str) -> None:
        backend = "gromacs" if backend == "gromacs" else "mdanalysis"
        if backend == self.backend:
            return
        self.backend = backend
        if backend == "gromacs":
            title = "GROMACS Selection Language"
            hints = GROMACS_SELECTION_HINTS
            headers = ("Field", "Syntax", "Handling")
        else:
            title = "MDAnalysis Selection Syntax"
            hints = MDANALYSIS_SELECTION_HINTS
            headers = ("Selector", "Meaning", "Example")
        self.setWindowTitle(title)
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(len(hints))
        for row, values in enumerate(hints):
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(value))
        url = SELECTION_DOCUMENTATION[backend]
        self.documentation.setText(f'More info: <a href="{url}">{url}</a>')
