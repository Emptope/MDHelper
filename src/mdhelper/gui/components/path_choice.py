"""Candidate file selection with an inline external-file action."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QFileDialog, QWidget

from mdhelper.gui.components.paths import file_filter


class PathChoice(QComboBox):
    def __init__(
        self, paths: tuple[Path, ...], placeholder: str, root: Path,
        label: str, suffixes: tuple[str, ...], parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.root = root
        self.label = label
        self.suffixes = suffixes
        self._previous = 0
        self.setMinimumWidth(0)
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.setMinimumContentsLength(20)
        self.addItem(placeholder, None)
        for path in paths:
            self.addItem(path.name, path)
            self.setItemData(self.count() - 1, str(path), Qt.ItemDataRole.ToolTipRole)
        self.addItem("Browse...", None)
        self.currentIndexChanged.connect(self._changed)
        self.activated.connect(self._activated)

    def _changed(self, index: int) -> None:
        if index != self.count() - 1:
            self._previous = index

    def _activated(self, index: int) -> None:
        if index != self.count() - 1:
            return
        self.setCurrentIndex(self._previous)
        path, _ = QFileDialog.getOpenFileName(
            self, f"Select {self.label.lower()}", str(self.currentData() or self.root),
            file_filter(self.label, self.suffixes),
        )
        if path:
            self.select_path(Path(path).expanduser().resolve())

    def select_path(self, path: Path) -> None:
        index = next((index for index in range(self.count()) if self.itemData(index) == path), -1)
        if index < 0:
            index = self.count() - 1
            self.insertItem(index, str(path), path)
            self.setItemData(index, str(path), Qt.ItemDataRole.ToolTipRole)
        self.setCurrentIndex(index)
