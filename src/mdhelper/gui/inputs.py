"""Simulation input controls for the desktop GUI."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QComboBox, QFormLayout, QGroupBox, QLabel, QWidget

from mdhelper.core.analysis import AnalysisRequest, RadialRequest
from mdhelper.core.errors import InputError
from mdhelper.core.trajectory import TOPOLOGY_SUFFIXES, TRAJECTORY_SUFFIXES
from mdhelper.gui.choices import set_choice_enabled
from mdhelper.gui.dialogs import PathRow


def _filter(label: str, suffixes: tuple[str, ...]) -> str:
    patterns = " ".join(f"*{suffix}" for suffix in suffixes)
    return f"{label} ({patterns});;All files (*)"


class InputPanel(QGroupBox):
    system_changed = Signal()
    index_changed = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__("Simulation Inputs", parent)
        self._analysis_backend = "auto"
        self._index_groups: dict[str, int] = {}
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
        self.selection_source = QComboBox()
        self.selection_source.addItem("GROMACS index groups (.ndx)", "index")
        self.selection_source.addItem("MDAnalysis selection expressions", "expression")
        self.selection_source.setCurrentIndex(1)
        self.index_summary = QLabel()
        self.index_summary.setWordWrap(True)
        self.index_summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        form.addRow("Topology", self.topology)
        form.addRow("Trajectory", self.trajectory)
        form.addRow("Index file", self.index_file)
        form.addRow("Selection source", self.selection_source)
        form.addRow("Index groups", self.index_summary)
        self.topology.edit.textChanged.connect(lambda _text: self.system_changed.emit())
        self.trajectory.edit.textChanged.connect(lambda _text: self.system_changed.emit())
        self.index_file.edit.textChanged.connect(lambda _text: self.index_changed.emit())
        self._sync_source_choices()

    def set_analysis_backend(self, backend: str) -> None:
        self._analysis_backend = backend
        labels = {
            "auto": "MDAnalysis selection expressions",
            "native": "Selection expressions unavailable for Native",
            "mdanalysis": "MDAnalysis selection expressions",
            "gromacs": "GROMACS selection expressions",
        }
        index = self.selection_source.findData("expression")
        self.selection_source.setItemText(index, labels.get(backend, labels["auto"]))
        self._sync_source_choices()

    def _sync_source_choices(self) -> None:
        expression = self._analysis_backend != "native"
        index = self._analysis_backend == "native" or bool(self._index_groups) or bool(
            self.index_value()
        )
        if expression:
            set_choice_enabled(self.selection_source, "expression", True, "index")
        if index:
            set_choice_enabled(self.selection_source, "index", True, "expression")
        if not index:
            set_choice_enabled(self.selection_source, "index", False, "expression")
        if not expression:
            set_choice_enabled(self.selection_source, "expression", False, "index")

    def index_path(self, required: bool = False) -> str | None:
        if self.selection_source.currentData() != "index":
            return None
        path = self.index_value()
        if required and not path:
            raise InputError(
                "No GROMACS index file was selected.",
                "Select a .ndx file or choose an expression-capable analysis backend.",
            )
        return path

    def index_value(self) -> str | None:
        path = self.index_file.edit.text().strip()
        return path or None

    def apply_request(self, request: AnalysisRequest) -> None:
        if isinstance(request, RadialRequest):
            self.topology.edit.setText(request.topology)
            self.trajectory.edit.setText(request.trajectory)
            self.index_file.edit.setText(request.index_file or "")
            self.selection_source.setCurrentIndex(0 if request.index_file else 1)

    def set_index_groups(self, groups: dict[str, int]) -> None:
        self._index_groups = dict(groups)
        self._sync_source_choices()
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
        source = "index" if self._analysis_backend == "native" else "expression"
        self.selection_source.setCurrentIndex(self.selection_source.findData(source))
