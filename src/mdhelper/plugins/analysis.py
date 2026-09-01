"""Complete analysis-pipeline interface and registry."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Protocol

from mdhelper.core.analysis import AnalysisRequest, AnalysisResult
from mdhelper.core.errors import ConfigurationError
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
    max_pairs_per_chunk: int
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


class AnalysisRegistry:
    def __init__(self, backends: tuple[BackendAdapter, ...] = ()) -> None:
        self._backends: dict[str, BackendAdapter] = {}
        for backend in backends:
            self.register(backend)

    def register(
        self,
        backend: BackendAdapter,
        replace: bool = False,
    ) -> None:
        name = backend.name.strip().casefold()
        if not name or not backend.analysis_types:
            raise ConfigurationError("An analysis backend requires a name and analyses.")
        if name in self._backends and not replace:
            raise ConfigurationError(f"An analysis backend is already registered: {name}")
        self._backends[name] = backend

    def get(self, backend_name: str, analysis_type: str) -> BackendAdapter:
        name = backend_name.casefold()
        try:
            backend = self._backends[name]
        except KeyError as exc:
            available = ", ".join(self.names(analysis_type)) or "none"
            raise ConfigurationError(
                f"No {backend_name!r} backend is registered for {analysis_type!r}.",
                f"Registered backends for this analysis: {available}.",
            ) from exc
        if analysis_type.casefold() not in backend.analysis_types:
            available = ", ".join(self.names(analysis_type)) or "none"
            raise ConfigurationError(
                f"Backend {backend_name!r} does not support {analysis_type!r}.",
                f"Registered backends for this analysis: {available}.",
            )
        return backend

    def names(self, analysis_type: str | None = None) -> tuple[str, ...]:
        if analysis_type is None:
            return tuple(sorted(self._backends))
        analysis = analysis_type.casefold()
        return tuple(
            sorted(
                name
                for name, backend in self._backends.items()
                if analysis in backend.analysis_types
            )
        )

    def auto(
        self,
        query: BackendQuery,
        integrations: IntegrationManager,
    ) -> tuple[BackendAdapter, ...]:
        candidates: list[tuple[int, str, BackendAdapter]] = []
        for name, backend in self._backends.items():
            if query.analysis_type.casefold() not in backend.analysis_types:
                continue
            priority = backend.auto_priority(query, integrations)
            if priority is not None:
                candidates.append((priority, name, backend))
        return tuple(item[2] for item in sorted(candidates, key=lambda item: item[:2]))
