"""Project input selection for the desktop GUI."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from mdhelper.app import InputCandidates


class NewProjectDialog(QDialog):
    def __init__(self, candidates: InputCandidates, parent: QWidget | None = None):
        super().__init__(parent)
        self.candidates = candidates
        self.setWindowTitle("New Project")
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)

        directory = QLabel(str(candidates.root))
        directory.setWordWrap(True)
        directory.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.topology = self._files(candidates.topology, "Select topology file")
        self.trajectory = self._files(candidates.trajectory, "Select trajectory file")
        self.index_file = self._files(candidates.index, "Do not use an index file")
        if len(candidates.index) == 1:
            self.index_file.setCurrentIndex(1)
        form.addRow("Directory", directory)
        form.addRow("Topology", self.topology)
        form.addRow("Trajectory", self.trajectory)
        form.addRow("Index file", self.index_file)
        layout.addLayout(form)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.topology.currentIndexChanged.connect(self._update_accept)
        self.trajectory.currentIndexChanged.connect(self._update_accept)
        self._update_accept()

    @staticmethod
    def _files(paths: tuple[Path, ...], placeholder: str) -> QComboBox:
        combo = QComboBox()
        combo.addItem(placeholder, None)
        for path in paths:
            combo.addItem(path.name, path)
        return combo

    def _update_accept(self) -> None:
        button = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        button.setEnabled(
            isinstance(self.topology.currentData(), Path)
            and isinstance(self.trajectory.currentData(), Path)
        )

    @property
    def topology_path(self) -> Path:
        path = self.topology.currentData()
        if not isinstance(path, Path):
            raise RuntimeError("No topology file is selected.")
        return path

    @property
    def trajectory_path(self) -> Path:
        path = self.trajectory.currentData()
        if not isinstance(path, Path):
            raise RuntimeError("No trajectory file is selected.")
        return path

    @property
    def index_path(self) -> Path | None:
        path = self.index_file.currentData()
        return path if isinstance(path, Path) else None
