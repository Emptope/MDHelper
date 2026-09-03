"""External software integration use cases."""

from __future__ import annotations

from pathlib import Path
from threading import Event

from mdhelper.app.context import ApplicationContext
from mdhelper.core.errors import MDHelperError
from mdhelper.integrations.models import (
    IntegrationConfig,
    IntegrationRunRecord,
    IntegrationStatus,
)
from mdhelper.project import Project


class IntegrationUseCases:
    def __init__(self, context: ApplicationContext):
        self.context = context
        self._configured: set[str] = set()

    def detect(
        self,
        name: str,
        override: str | None = None,
        config: IntegrationConfig | None = None,
    ) -> IntegrationStatus:
        self._configured.add(name.casefold())
        return self.context.integrations.detect(name, override, config)

    def is_configured(self, name: str) -> bool:
        key = name.casefold()
        return key in self._configured or bool(
            self.context.config.integration(key).path.strip()
        )

    def configure(self, configs: dict[str, IntegrationConfig]) -> None:
        normalized: dict[str, IntegrationConfig] = {}
        for name, config in configs.items():
            key = name.casefold()
            self.context.integrations.registry.get(key)
            normalized[key] = config
        self.context.config.integrations.update(normalized)
        self._configured.update(
            name for name, config in normalized.items() if config.path.strip()
        )
        self.context.integrations.invalidate(tuple(normalized))

    def status(self, name: str) -> IntegrationStatus:
        return self.context.integrations.status(name)

    def supports(self, name: str, *capabilities: str) -> bool:
        status = self.status(name)
        return status.available and set(capabilities).issubset(status.capabilities)

    def statuses(self, refresh: bool = False) -> tuple[IntegrationStatus, ...]:
        return self.context.integrations.statuses(refresh)

    def names(self) -> tuple[str, ...]:
        return self.context.integrations.names()

    def display_name(self, name: str) -> str:
        return self.context.integrations.display_name(name)

    def validate_input_file(
        self,
        name: str,
        command: str,
        option: str,
        path: str | Path,
    ) -> Path:
        return self.context.integrations.validate_input_file(
            name,
            command,
            option,
            path,
        )

    def run(
        self,
        name: str,
        arguments: list[str],
        working_directory: str | Path,
        override: str | None = None,
        timeout_seconds: float | None = None,
        cancel_event: Event | None = None,
        output_files: list[str | Path] | None = None,
        project: Project | None = None,
        input_text: str | None = None,
        required_capabilities: tuple[str, ...] = (),
    ) -> IntegrationRunRecord:
        try:
            record = self.context.integrations.run(
                name,
                arguments,
                working_directory,
                override,
                timeout_seconds,
                cancel_event,
                output_files,
                input_text=input_text,
                required_capabilities=required_capabilities,
            )
        except MDHelperError as exc:
            integration_run = (exc.details or {}).get("integration_run")
            if project and isinstance(integration_run, dict):
                project.record_integration_run(integration_run)
            raise
        if project:
            project.record_integration_run(record.to_dict())
        return record

    def open_terminal(
        self,
        name: str,
        arguments: list[str],
        working_directory: str | Path,
        required_capabilities: tuple[str, ...] = (),
    ) -> str:
        return self.context.integrations.open_terminal(
            name,
            arguments,
            working_directory,
            required_capabilities,
        )
