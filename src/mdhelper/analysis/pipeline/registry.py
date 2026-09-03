"""Registry and automatic ordering for complete analysis backends."""

from __future__ import annotations

from mdhelper.core.errors import ConfigurationError
from mdhelper.integrations.manager import IntegrationManager

from .models import BackendAdapter, BackendQuery


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
