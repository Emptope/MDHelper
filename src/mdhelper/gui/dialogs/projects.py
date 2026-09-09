"""Project input selection for the desktop GUI."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from mdhelper.app import InputCandidates
from mdhelper.core.trajectory import TOPOLOGY_SUFFIXES, TRAJECTORY_SUFFIXES
from mdhelper.gui.components.path_choice import PathChoice


class NewProjectDialog(QDialog):
    def __init__(self, candidates: InputCandidates, parent: QWidget | None = None):
        super().__init__(parent)
        self.candidates = candidates
        self.setWindowTitle("Select Inputs")
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
        self.topology = PathChoice(
            candidates.topology, "Select topology file", candidates.root,
            "Topology", TOPOLOGY_SUFFIXES,
        )
        self.trajectory = PathChoice(
            candidates.trajectory, "Select trajectory file", candidates.root,
            "Trajectory", TRAJECTORY_SUFFIXES,
        )
        self.index_file = PathChoice(
            candidates.index, "Do not use an index file", candidates.root, "Index file", (".ndx",),
        )
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

    def set_inputs(self, inputs: dict[str, Path]) -> None:
        if not inputs:
            return
        for role, combo in (
            ("topology", self.topology), ("trajectory", self.trajectory), ("index", self.index_file)
        ):
            path = inputs.get(role)
            if path is None:
                combo.setCurrentIndex(0)
            else:
                combo.select_path(path)

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
