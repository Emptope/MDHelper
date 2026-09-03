"""Contracts and registry for external integration adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod

from mdhelper.core.errors import ConfigurationError


class IntegrationAdapter(ABC):
    """Contract for one supported external software family."""

    name: str
    display_name: str = ""

    @abstractmethod
    def candidate_names(self) -> tuple[str, ...]:
        """Return platform-specific command names in preference order."""

    def environment_paths(self, environment: dict[str, str]) -> tuple[tuple[str, str], ...]:
        return ()

    def candidate_paths(self, environment: dict[str, str]) -> tuple[str, ...]:
        return ()

    def version_detect(self) -> tuple[str, str] | None:
        return None

    def version_arguments(self, detect_path: str | None = None) -> tuple[str, ...]:
        del detect_path
        return ("--version",)

    def command_prefix(self) -> tuple[str, ...]:
        return ()

    @abstractmethod
    def parse_version(self, stdout: str, stderr: str, exit_code: int) -> str | None:
        """Return a normalized version or None when identity validation fails."""

    def capability_arguments(self) -> tuple[str, ...] | None:
        return None

    def parse_capabilities(
        self, stdout: str, stderr: str, exit_code: int
    ) -> tuple[str, ...]:
        return ()

    def capability_detection_required(self) -> bool:
        return self.capability_arguments() is not None

    def default_capabilities(self) -> tuple[str, ...]:
        return ()

    def file_suffixes(self, command: str, option: str) -> tuple[str, ...]:
        del command, option
        return ()

    def environment_keys(self) -> frozenset[str]:
        return frozenset()

    def provenance_environment_keys(self) -> frozenset[str]:
        return frozenset()


class IntegrationRegistry:
    """Supported external software keyed by stable integration name."""

    def __init__(self) -> None:
        self._adapters: dict[str, IntegrationAdapter] = {}

    def register(self, adapter: IntegrationAdapter, replace: bool = False) -> None:
        name = adapter.name.strip().casefold()
        if not name:
            raise ConfigurationError("An integration adapter must have a name.")
        if name in self._adapters and not replace:
            raise ConfigurationError(f"An integration adapter is already registered: {name}")
        self._adapters[name] = adapter

    def get(self, name: str) -> IntegrationAdapter:
        try:
            return self._adapters[name.casefold()]
        except KeyError as exc:
            raise ConfigurationError(
                f"No integration adapter is registered for {name!r}.",
                f"Registered integrations: {', '.join(self.names()) or 'none'}.",
            ) from exc

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._adapters))

    def display_name(self, name: str) -> str:
        adapter = self.get(name)
        return adapter.display_name.strip() or adapter.name
