"""Input controls for the desktop GUI."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFormLayout, QGroupBox, QLabel, QWidget

from mdhelper.core.analysis import AnalysisRequest, RadialRequest
from mdhelper.core.trajectory import TOPOLOGY_SUFFIXES, TRAJECTORY_SUFFIXES
from mdhelper.gui.components.paths import PathRow


def _filter(label: str, suffixes: tuple[str, ...]) -> str:
    patterns = " ".join(f"*{suffix}" for suffix in suffixes)
    return f"{label} ({patterns});;All files (*)"


class InputPanel(QGroupBox):
    system_changed = Signal()
    index_changed = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__("Inputs", parent)
        form = QFormLayout(self)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.topology = PathRow("Select topology", _filter("GROMACS topology", TOPOLOGY_SUFFIXES))
        self.trajectory = PathRow(
            "Select trajectory",
            _filter("GROMACS trajectory", TRAJECTORY_SUFFIXES),
        )
        self.index_file = PathRow("Select GROMACS index", "GROMACS index (*.ndx);;All files (*)")
        self.index_summary = QLabel()
        self.index_summary.setWordWrap(True)
        self.index_summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        form.addRow("Topology", self.topology)
        form.addRow("Trajectory", self.trajectory)
        form.addRow("Index file", self.index_file)
        form.addRow("Index groups", self.index_summary)
        self.topology.edit.textChanged.connect(lambda _text: self.system_changed.emit())
        self.trajectory.edit.textChanged.connect(lambda _text: self.system_changed.emit())
        self.index_file.edit.textChanged.connect(lambda _text: self.index_changed.emit())

    def index_value(self) -> str | None:
        path = self.index_file.edit.text().strip()
        return path or None

    def apply_request(self, request: AnalysisRequest) -> None:
        if isinstance(request, RadialRequest):
            self.topology.set_path(request.topology)
            self.trajectory.set_path(request.trajectory)
            self.index_file.set_path(request.index_file or "")

    def set_index_groups(self, groups: dict[str, int]) -> None:
        if not groups:
            self.index_summary.setText("No groups found")
            self.index_summary.setToolTip("")
            return
        self.index_summary.setText(f"{len(groups)} groups loaded")
        self.index_summary.setToolTip(", ".join(groups))

    def clear(self) -> None:
        self.topology.edit.clear()
        self.trajectory.edit.clear()
        self.index_file.edit.clear()
        self.set_index_groups({})
