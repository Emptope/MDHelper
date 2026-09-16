"""Tree view that keeps focus from selecting an entry."""

from __future__ import annotations

from PySide6.QtCore import QModelIndex
from PySide6.QtGui import QFocusEvent
from PySide6.QtWidgets import QTreeView


class FolderTree(QTreeView):
    """Folder tree that selects entries only through explicit navigation."""

    def focusInEvent(self, event: QFocusEvent) -> None:
        selection = self.selectionModel()
        current = self.currentIndex()
        if selection is None:
            super().focusInEvent(event)
            return
        blocked = selection.blockSignals(True)
        try:
            super().focusInEvent(event)
            # Native focus handling selects the first entry when no entry is
            # current; without that selection no file opens by accident.
            if not current.isValid():
                self.setCurrentIndex(QModelIndex())
                selection.clear()
        finally:
            selection.blockSignals(blocked)
