"""Simulation input controls for the desktop GUI."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QComboBox, QFormLayout, QGroupBox, QLabel, QWidget

from mdhelper.core.analysis import AnalysisRequest
from mdhelper.core.errors import InputError
from mdhelper.core.trajectory import TOPOLOGY_SUFFIXES, TRAJECTORY_SUFFIXES
from mdhelper.gui.choices import choice_enabled, set_choice_enabled
from mdhelper.gui.dialogs import PathRow


def _filter(label: str, suffixes: tuple[str, ...]) -> str:
    patterns = " ".join(f"*{suffix}" for suffix in suffixes)
    return f"{label} ({patterns});;All files (*)"


class InputPanel(QGroupBox):
    system_changed = Signal()
    index_changed = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__("Simulation Inputs", parent)
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
        self.index_summary = QLabel()
        self.index_summary.setWordWrap(True)
        self.index_summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.backend = QComboBox()
        self.backend.addItem("auto", "auto")
        self.backend.addItem("native", "native")
        self.backend.addItem("MDAnalysis", "mdanalysis")
        self.backend.addItem("GROMACS (local gmx)", "gromacs")
        form.addRow("Topology", self.topology)
        form.addRow("Trajectory", self.trajectory)
        form.addRow("Index file", self.index_file)
        form.addRow("Selection source", self.selection_source)
        form.addRow("Index groups", self.index_summary)
        form.addRow("Backend", self.backend)
        self.topology.edit.textChanged.connect(lambda _text: self.system_changed.emit())
        self.trajectory.edit.textChanged.connect(lambda _text: self.system_changed.emit())
        self.index_file.edit.textChanged.connect(lambda _text: self.index_changed.emit())

    def index_path(self, required: bool = False) -> str | None:
        if self.selection_source.currentData() != "index":
            return None
        path = self.index_value()
        if required and not path:
            raise InputError(
                "No GROMACS index file was selected.",
                "Select a .ndx file or confirm the MDAnalysis expression fallback.",
            )
        return path

    def index_value(self) -> str | None:
        path = self.index_file.edit.text().strip()
        return path or None

    def backend_value(self) -> str:
        value = self.backend.currentData()
        if not isinstance(value, str):
            raise InputError("No backend was selected.")
        return value

    def set_backend(self, value: str) -> None:
        index = self.backend.findData(value)
        if index < 0:
            raise InputError(f"Unknown backend: {value}")
        if not choice_enabled(self.backend, value):
            raise InputError(
                f"Backend {value!r} is unavailable.",
                "Configure a compatible GROMACS executable or select another reader.",
            )
        self.backend.setCurrentIndex(index)

    def set_gromacs_available(self, available: bool) -> None:
        set_choice_enabled(self.backend, "gromacs", available, "auto")
        index = self.backend.findData("gromacs")
        label = "GROMACS (local gmx)" if available else "GROMACS (local gmx) - Unavailable"
        self.backend.setItemText(index, label)

    def apply_request(self, request: AnalysisRequest) -> None:
        self.topology.edit.setText(request.topology)
        self.trajectory.edit.setText(request.trajectory)
        self.index_file.edit.setText(request.index_file or "")
        self.selection_source.setCurrentIndex(0 if request.index_file else 1)
        self.set_backend(request.backend)

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
        self.selection_source.setCurrentIndex(0)
        self.set_backend("auto")
        self.set_index_groups({})
