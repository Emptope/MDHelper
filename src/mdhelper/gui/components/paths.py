"""File path input controls for the desktop GUI."""

from __future__ import annotations

from PySide6.QtCore import QDir, Signal
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLineEdit, QPushButton, QWidget


class PathRow(QWidget):
    """Line edit with a platform-native file picker."""

    path_selected = Signal(str)

    def __init__(self, caption: str, file_filter: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.caption = caption
        self.file_filter = file_filter
        self.edit = QLineEdit()
        self.edit.editingFinished.connect(self._normalize)
        self.button = QPushButton("Browse...")
        self.button.clicked.connect(self._browse)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.edit, 1)
        layout.addWidget(self.button)

    def set_path(self, path: str) -> None:
        self.edit.setText(QDir.toNativeSeparators(path))

    def _normalize(self) -> None:
        self.set_path(self.edit.text())

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, self.caption, self.edit.text(), self.file_filter
        )
        if path:
            self.set_path(path)
            self.path_selected.emit(self.edit.text())
