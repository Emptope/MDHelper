"""Contracts shared by external-process adapters."""

from __future__ import annotations

from typing import Protocol

from mdhelper.core.errors import BackendError


class ExecutionAdapter(Protocol):
    name: str
    display_name: str

    def command_prefix(self) -> tuple[str, ...]: ...

    def environment_keys(self) -> frozenset[str]: ...

    def provenance_environment_keys(self) -> frozenset[str]: ...


class ExecutionStatus(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def available(self) -> bool: ...

    @property
    def path(self) -> str | None: ...

    @property
    def version(self) -> str | None: ...


def integration_argv(
    adapter: ExecutionAdapter,
    integration: ExecutionStatus,
    arguments: list[str],
) -> list[str]:
    if integration.name.casefold() != adapter.name.casefold():
        raise BackendError("The integration status does not match the selected adapter.")
    if not integration.available or not integration.path or not integration.version:
        raise BackendError("An integration must pass detection before execution.")
    if any("\x00" in argument for argument in arguments):
        raise BackendError("Integration arguments cannot contain NUL bytes.")
    return [integration.path, *adapter.command_prefix(), *arguments]
