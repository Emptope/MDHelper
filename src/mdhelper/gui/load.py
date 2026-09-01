"""Input loading and inspected-system views for the desktop GUI."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QSplitter, QWidget

from mdhelper.core.analysis import AnalysisRequest, RadialRequest
from mdhelper.gui.inputs import InputPanel
from mdhelper.gui.layout import page_layout
from mdhelper.gui.species import SpeciesPanel


class LoadPanel(QWidget):
    selection_source_changed = Signal(str, object)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.inputs = InputPanel()
        self.species = SpeciesPanel()
        self.index_groups: dict[str, int] = {}
        self.inputs.selection_source.currentIndexChanged.connect(
            self._selection_source_changed
        )
        sections = QSplitter(Qt.Orientation.Vertical)
        sections.setChildrenCollapsible(False)
        sections.addWidget(self.inputs)
        sections.addWidget(self.species)
        sections.setStretchFactor(0, 0)
        sections.setStretchFactor(1, 1)
        sections.setSizes((260, 520))
        layout = page_layout(self)
        layout.addWidget(sections, 1)
        self.sections = sections
        self._selection_source_changed()

    def _selection_source_changed(self) -> None:
        self.selection_source_changed.emit(
            str(self.inputs.selection_source.currentData()),
            dict(self.index_groups),
        )

    def set_index_groups(self, groups: dict[str, int]) -> None:
        self.index_groups = dict(groups)
        self.inputs.set_index_groups(groups)
        self._selection_source_changed()

    def common(
        self,
        role_provenance: dict[str, Any],
        frames: object,
        require_selections: bool = True,
    ) -> dict[str, Any]:
        return {
            "topology": self.inputs.topology.edit.text().strip(),
            "trajectory": self.inputs.trajectory.edit.text().strip(),
            "index_file": self.inputs.index_path(required=require_selections),
            "frames": frames,
            "backend": self.inputs.backend_value(),
            "species_roles": self.species.roles(require_all=require_selections),
            "parameter_provenance": {"species_roles": dict(role_provenance)},
        }

    def apply_request(self, request: AnalysisRequest, preserve_inputs: bool = False) -> None:
        if not preserve_inputs:
            self.inputs.apply_request(request)
        else:
            self.inputs.set_backend(request.backend)
        if isinstance(request, RadialRequest):
            self.species.apply_roles(request.species_roles)
