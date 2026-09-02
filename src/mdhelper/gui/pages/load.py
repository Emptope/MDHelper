"""Input loading and inspected-system views for the desktop GUI."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QSplitter, QWidget

from mdhelper.core.analysis import AnalysisRequest, RadialRequest
from mdhelper.gui.components.inputs import InputPanel
from mdhelper.gui.components.layout import page_layout
from mdhelper.gui.components.species import SpeciesPanel


class LoadPanel(QWidget):
    selection_inputs_changed = Signal(bool, object)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.inputs = InputPanel()
        self.species = SpeciesPanel()
        self.index_groups: dict[str, int] = {}
        self.inputs.index_changed.connect(lambda: self.set_index_groups({}))
        sections = QSplitter(Qt.Orientation.Vertical)
        sections.setChildrenCollapsible(False)
        sections.addWidget(self.inputs)
        sections.addWidget(self.species)
        sections.setStretchFactor(0, 0)
        sections.setStretchFactor(1, 1)
        sections.setSizes((self.inputs.sizeHint().height(), 1))
        layout = page_layout(self)
        layout.addWidget(sections, 1)
        self.sections = sections
        self._selection_inputs_changed()

    def _selection_inputs_changed(self) -> None:
        self.selection_inputs_changed.emit(
            self.inputs.index_value() is not None,
            dict(self.index_groups),
        )

    def set_index_groups(self, groups: dict[str, int]) -> None:
        self.index_groups = dict(groups)
        self.inputs.set_index_groups(groups)
        self._selection_inputs_changed()

    def common(
        self,
        role_provenance: dict[str, Any],
        frames: object,
        require_selections: bool = True,
    ) -> dict[str, Any]:
        return {
            "topology": self.inputs.topology.edit.text().strip(),
            "trajectory": self.inputs.trajectory.edit.text().strip(),
            "index_file": self.inputs.index_value(),
            "frames": frames,
            "species_roles": self.species.roles(require_all=require_selections),
            "parameter_provenance": {"species_roles": dict(role_provenance)},
        }

    def apply_request(self, request: AnalysisRequest, preserve_inputs: bool = False) -> None:
        if not preserve_inputs:
            self.inputs.apply_request(request)
        if isinstance(request, RadialRequest):
            self.species.apply_roles(request.species_roles)
