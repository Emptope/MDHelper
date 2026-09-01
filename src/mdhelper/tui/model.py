"""Mutable terminal-workspace and analysis-draft state."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from mdhelper.core.analysis import (
    AnalysisBackend,
    AnalysisRequest,
    AnalysisResult,
    AnalysisType,
    EnergyBackend,
    EnergyRequest,
    RadialBackend,
    RadialRequest,
)
from mdhelper.core.system import FrameRange, SystemSummary
from mdhelper.project import Project


@dataclass
class AnalysisDraft:
    analysis_type: AnalysisType
    analysis_backend: AnalysisBackend = "auto"
    reference: str = ""
    selection: str = ""
    r_max_nm: float = 1.0
    bin_width_nm: float = 0.002
    energy_file: str = ""
    energy_terms: list[str] = field(default_factory=list)
    frames: FrameRange = field(default_factory=FrameRange)
    output: str = ""
    include_figures: bool = True
    parameter_provenance: dict[str, Any] = field(default_factory=dict)

    def request(self, workspace: Workspace) -> AnalysisRequest:
        if self.analysis_type == "energy":
            energy_request = EnergyRequest(
                analysis_type="energy",
                energy_file=self.energy_file,
                energy_terms=tuple(self.energy_terms),
                analysis_backend=cast(EnergyBackend, self.analysis_backend),
                parameter_provenance=dict(self.parameter_provenance),
            )
            energy_request.validate()
            return energy_request
        radial_request = RadialRequest(
            analysis_type=self.analysis_type,
            topology=workspace.topology,
            trajectory=workspace.trajectory,
            index_file=workspace.index_file,
            reference=self.reference,
            selection=self.selection,
            r_max_nm=self.r_max_nm,
            bin_width_nm=self.bin_width_nm,
            frames=self.frames,
            analysis_backend=cast(RadialBackend, self.analysis_backend),
            species_roles=dict(workspace.roles),
            parameter_provenance={
                **self.parameter_provenance,
                "species_roles": dict(workspace.role_decisions),
            },
        )
        radial_request.validate()
        return radial_request


@dataclass
class Workspace:
    topology: str = ""
    trajectory: str = ""
    index_file: str | None = None
    project: Project | None = None
    summary: SystemSummary | None = None
    roles: dict[str, str] = field(default_factory=dict)
    role_decisions: dict[str, dict[str, Any]] = field(default_factory=dict)
    drafts: dict[AnalysisType, AnalysisDraft] = field(default_factory=dict)
    radial_output: str = ""
    result: AnalysisResult | None = None

    @property
    def loaded(self) -> bool:
        return bool(self.topology and self.trajectory)

    @property
    def label(self) -> str:
        if self.project is not None:
            return f"project {self.project.root.name}"
        if self.loaded:
            return Path(self.trajectory).name
        return "no inputs loaded"

    def clear(self) -> None:
        self.topology = ""
        self.trajectory = ""
        self.index_file = None
        self.project = None
        self.summary = None
        self.roles.clear()
        self.role_decisions.clear()
        self.drafts.clear()
        self.radial_output = ""
        self.result = None

    def output_directory(self, name: str) -> str:
        base = (
            self.project.root / "exports"
            if self.project is not None
            else Path(self.trajectory).expanduser().resolve().parent / "results"
        )
        return str(base / name)

    def radial_output_directory(self) -> str:
        if not self.radial_output:
            self.radial_output = self.output_directory("rdf-cn")
        return self.radial_output

    def draft(self, analysis_type: AnalysisType) -> AnalysisDraft:
        draft = self.drafts.get(analysis_type)
        if draft is None:
            draft = AnalysisDraft(
                analysis_type,
                output=self.output_directory(analysis_type),
            )
            self.drafts[analysis_type] = draft
        return draft
