"""File path input controls for the desktop GUI."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLineEdit, QPushButton, QWidget


class PathRow(QWidget):
    """Line edit with a platform-native file picker."""

    path_selected = Signal(str)

    def __init__(self, caption: str, file_filter: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.caption = caption
        self.file_filter = file_filter
        self.edit = QLineEdit()
        self.button = QPushButton("Browse...")
        self.button.clicked.connect(self._browse)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.edit, 1)
        layout.addWidget(self.button)

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, self.caption, self.edit.text(), self.file_filter
        )
        if path:
            self.edit.setText(path)
            self.path_selected.emit(path)
