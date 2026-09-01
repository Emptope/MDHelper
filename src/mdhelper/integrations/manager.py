"""Configuration, detection, status, and execution for external software."""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from pathlib import Path
from threading import Event
from typing import cast

from mdhelper.core.errors import BackendError
from mdhelper.integrations.models import (
    Detection,
    IntegrationConfig,
    IntegrationRegistry,
    IntegrationRunRecord,
    IntegrationStatus,
)
from mdhelper.runtime.detection import canonical_path, detect_candidate
from mdhelper.runtime.execution import format_command, run_integration


class IntegrationManager:
    def __init__(
        self,
        configs: dict[str, IntegrationConfig],
        registry: IntegrationRegistry,
        environment: dict[str, str] | None = None,
    ):
        self.configs = configs
        self.registry = registry
        self.environment = dict(os.environ if environment is None else environment)
        self._statuses: dict[str, IntegrationStatus] = {}

    def names(self) -> tuple[str, ...]:
        return self.registry.names()

    def display_name(self, name: str) -> str:
        return self.registry.display_name(name)

    def config(self, name: str) -> IntegrationConfig:
        return self.configs.get(name.casefold(), IntegrationConfig())

    def _candidates(
        self,
        name: str,
        override: str | None,
        config: IntegrationConfig,
    ) -> tuple[tuple[str, str], ...]:
        adapter = self.registry.get(name)
        values: list[tuple[str, str]] = []
        if override:
            values.append(("run_override", override))
        if not config.enabled:
            return tuple(values)
        if config.path:
            values.append(("user_config", config.path))
        values.extend(("configured_path", value) for value in config.search_paths)
        if config.use_environment:
            values.extend(adapter.environment_paths(self.environment))
        for command in adapter.candidate_names():
            resolved = shutil.which(command, path=self.environment.get("PATH"))
            if resolved:
                values.append(("PATH", resolved))
        values.extend(
            ("candidate_path", value)
            for value in adapter.candidate_paths(self.environment)
        )
        return tuple(values)

    def detect(
        self,
        name: str,
        override: str | None = None,
        config: IntegrationConfig | None = None,
    ) -> IntegrationStatus:
        key = name.casefold()
        current = self.config(key) if config is None else config
        candidates = self._candidates(key, override, current)
        seen: set[str] = set()
        detections: list[Detection] = []
        for rank, (source, candidate) in enumerate(candidates):
            canonical = canonical_path(candidate)
            if canonical in seen:
                continue
            seen.add(canonical)
            detections.append(
                detect_candidate(
                    self.registry.get(key),
                    candidate,
                    source,
                    rank,
                    current.detect_timeout_seconds,
                    self.environment,
                    Detection,
                )
            )
        selected = next((item for item in detections if item.available), None)
        if selected is None:
            error = (
                f"Integration {key} is disabled."
                if not current.enabled and not override
                else f"No validated {key} installation is available."
            )
            status = IntegrationStatus(
                key,
                False,
                error=error,
                detections=tuple(detections),
            )
        else:
            status = IntegrationStatus(
                key,
                True,
                selected.path,
                selected.version,
                selected.capabilities,
                selected.source,
                detections=tuple(detections),
            )
        if config is None:
            self._statuses[key] = status
        return status

    def invalidate(self, names: tuple[str, ...] = ()) -> None:
        if not names:
            self._statuses.clear()
            return
        for name in names:
            self._statuses.pop(name.casefold(), None)

    def status(self, name: str) -> IntegrationStatus:
        key = name.casefold()
        return self._statuses.get(key) or self.detect(key)

    def statuses(self, refresh: bool = False) -> tuple[IntegrationStatus, ...]:
        if refresh:
            self._statuses.clear()
        return tuple(self.status(name) for name in self.names())

    def format_command(self, name: str, arguments: list[str]) -> str:
        status = self.status(name)
        if not status.available or status.path is None:
            raise BackendError(f"No validated {name} installation is available.")
        adapter = self.registry.get(name)
        command = [status.path, *adapter.command_prefix(), *arguments]
        return format_command(command)

    def run(
        self,
        name: str,
        arguments: list[str],
        working_directory: str | Path,
        override: str | None = None,
        timeout_seconds: float | None = None,
        cancel_event: Event | None = None,
        output_files: list[str | Path] | None = None,
        input_text: str | None = None,
        process_progress: Callable[[float, str, str], None] | None = None,
        required_capabilities: tuple[str, ...] = (),
    ) -> IntegrationRunRecord:
        config = self.config(name)
        status = self.detect(name, override) if override else self.status(name)
        missing = sorted(set(required_capabilities) - set(status.capabilities))
        if missing:
            raise BackendError(
                f"The selected {name} integration lacks required capabilities.",
                "Change the requirement or select another detected installation.",
                {"missing_capabilities": missing, "integration": status.to_dict()},
            )
        timeout = config.run_timeout_seconds if timeout_seconds is None else timeout_seconds
        return cast(
            IntegrationRunRecord,
            run_integration(
                self.registry.get(name),
                status,
                arguments,
                working_directory,
                timeout,
                cancel_event,
                output_files,
                self.environment,
                input_text,
                process_progress,
                IntegrationRunRecord,
            ),
        )
