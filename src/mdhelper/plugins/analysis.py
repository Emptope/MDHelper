"""Unified interface and registry for analysis backends."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from threading import Event
from typing import Protocol

from mdhelper.core.analysis import AnalysisRequest, AnalysisResult
from mdhelper.core.errors import ConfigurationError
from mdhelper.core.progress import ProgressCallback
from mdhelper.core.trajectory import TrajectorySource
from mdhelper.integrations.manager import IntegrationManager

AnalysisRunner = Callable[
    [
        TrajectorySource,
        AnalysisRequest,
        dict[str, object],
        ProgressCallback | None,
        Event | None,
        int,
    ],
    AnalysisResult,
]


@dataclass(frozen=True)
class AnalysisInput:
    request: AnalysisRequest
    source: TrajectorySource | None
    provenance: dict[str, object]
    integrations: IntegrationManager
    progress: ProgressCallback | None
    cancel_event: Event | None
    max_pairs_per_chunk: int


class AnalysisBackend(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def display_name(self) -> str: ...

    @property
    def needs_trajectory(self) -> bool: ...

    def run(self, inputs: AnalysisInput) -> AnalysisResult: ...


@dataclass(frozen=True)
class FunctionBackend:
    runner: AnalysisRunner
    name: str = "native"
    display_name: str = "Native"
    needs_trajectory: bool = True

    def run(self, inputs: AnalysisInput) -> AnalysisResult:
        if inputs.source is None:
            raise ConfigurationError(
                f"Analysis backend {self.name!r} requires a trajectory source."
            )
        return self.runner(
            inputs.source,
            inputs.request,
            inputs.provenance,
            inputs.progress,
            inputs.cancel_event,
            inputs.max_pairs_per_chunk,
        )


class AnalysisRegistry:
    def __init__(self) -> None:
        self._backends: dict[tuple[str, str], AnalysisBackend] = {}

    def register(
        self,
        analysis_type: str,
        backend: AnalysisBackend,
        replace: bool = False,
    ) -> None:
        analysis = analysis_type.strip().casefold()
        name = backend.name.strip().casefold()
        if not analysis or not name:
            raise ConfigurationError(
                "An analysis backend requires non-empty analysis and backend names."
            )
        key = (analysis, name)
        if key in self._backends and not replace:
            raise ConfigurationError(
                f"An analysis backend is already registered: {analysis}/{name}"
            )
        self._backends[key] = backend

    def get(self, analysis_type: str, backend_name: str) -> AnalysisBackend:
        key = (analysis_type.casefold(), backend_name.casefold())
        try:
            return self._backends[key]
        except KeyError as exc:
            available = ", ".join(self.names(analysis_type)) or "none"
            raise ConfigurationError(
                f"No {backend_name!r} backend is registered for {analysis_type!r}.",
                f"Registered backends for this analysis: {available}.",
            ) from exc

    def names(self, analysis_type: str | None = None) -> tuple[str, ...]:
        if analysis_type is None:
            return tuple(
                sorted(f"{analysis}/{backend}" for analysis, backend in self._backends)
            )
        key = analysis_type.casefold()
        return tuple(sorted(backend for analysis, backend in self._backends if analysis == key))
