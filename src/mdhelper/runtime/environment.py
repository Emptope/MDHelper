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

TERMINAL_ENVIRONMENT_KEYS = frozenset(
    {
        "DBUS_SESSION_BUS_ADDRESS",
        "DISPLAY",
        "WAYLAND_DISPLAY",
        "XAUTHORITY",
        "XDG_RUNTIME_DIR",
    }
)


def child_environment(
    adapter: EnvironmentAdapter, environment: dict[str, str]
) -> dict[str, str]:
    """Return only platform essentials and adapter-declared variables."""

    allowed = BASE_ENVIRONMENT_KEYS | adapter.environment_keys()
    return {key: value for key, value in environment.items() if key in allowed}


def terminal_environment(
    adapter: EnvironmentAdapter, environment: dict[str, str]
) -> dict[str, str]:
    """Return the integration environment plus desktop-session routing."""

    allowed = BASE_ENVIRONMENT_KEYS | TERMINAL_ENVIRONMENT_KEYS | adapter.environment_keys()
    return {key: value for key, value in environment.items() if key in allowed}
