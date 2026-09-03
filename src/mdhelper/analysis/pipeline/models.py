"""Analysis pipeline inputs and backend protocol."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Protocol

from mdhelper.core.analysis import AnalysisRequest, AnalysisResult
from mdhelper.core.progress import ProgressCallback
from mdhelper.core.system import FrameRange
from mdhelper.core.trajectory import TrajectorySource
from mdhelper.integrations.manager import IntegrationManager


@dataclass(frozen=True)
class BackendQuery:
    analysis_type: str
    topology: str | None = None
    trajectory: str | None = None
    index_file: str | None = None
    frames: FrameRange | None = None


@dataclass(frozen=True)
class AnalysisInput:
    request: AnalysisRequest
    source: TrajectorySource | None
    provenance: dict[str, object]
    integrations: IntegrationManager
    progress: ProgressCallback | None
    cancel_event: Event | None
    cache_dir: Path | None


class BackendAdapter(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def display_name(self) -> str: ...

    @property
    def analysis_types(self) -> frozenset[str]: ...

    def auto_priority(
        self,
        query: BackendQuery,
        integrations: IntegrationManager,
    ) -> int | None: ...

    def required_capabilities(self, query: BackendQuery) -> tuple[str, ...]: ...

    def validate_request(self, request: AnalysisRequest) -> None: ...

    def opens_trajectory(self, request: AnalysisRequest) -> bool: ...

    def fingerprints_inputs(self, request: AnalysisRequest) -> bool: ...

    def run(self, inputs: AnalysisInput) -> AnalysisResult: ...
