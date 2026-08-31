"""Bounded child-process environment construction."""

from __future__ import annotations

from typing import Protocol


class EnvironmentAdapter(Protocol):
    def environment_keys(self) -> frozenset[str]: ...

BASE_ENVIRONMENT_KEYS = frozenset(
    {
        "PATH",
        "PATHEXT",
        "SystemRoot",
        "SYSTEMROOT",
        "COMSPEC",
        "TEMP",
        "TMP",
        "TMPDIR",
        "HOME",
        "USERPROFILE",
        "LANG",
        "LC_ALL",
    }
)


def child_environment(
    adapter: EnvironmentAdapter, environment: dict[str, str]
) -> dict[str, str]:
    """Return only platform essentials and adapter-declared variables."""

    allowed = BASE_ENVIRONMENT_KEYS | adapter.environment_keys()
    return {key: value for key, value in environment.items() if key in allowed}
