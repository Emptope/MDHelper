"""Interactive external-terminal launch."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from mdhelper.core.errors import BackendError
from mdhelper.runtime.environment import terminal_environment
from mdhelper.runtime.logging import record_command

from .contracts import ExecutionAdapter, ExecutionStatus, integration_argv
from .records import format_command

TerminalFinder = Callable[[str], str | None]

_POSIX_TERMINALS = (
    ("xdg-terminal-exec", ()),
    ("x-terminal-emulator", ("-e",)),
    ("gnome-terminal", ("--",)),
    ("konsole", ("-e",)),
    ("xfce4-terminal", ("--execute",)),
    ("xterm", ("-e",)),
)


def terminal_command(
    arguments: Sequence[str],
    platform: str | None = None,
    finder: TerminalFinder | None = None,
) -> tuple[list[str], int]:
    """Wrap an argv for an interactive external terminal."""

    command = list(arguments)
    if not command:
        raise OSError("An external terminal command cannot be empty.")
    system = sys.platform if platform is None else platform
    if system == "win32":
        return command, int(vars(subprocess)["CREATE_NEW_CONSOLE"])
    find = shutil.which if finder is None else finder
    for name, prefix in _POSIX_TERMINALS:
        if executable := find(name):
            return [executable, *prefix, *command], 0
    raise OSError("No supported external terminal is available.")


def launch_in_terminal(
    adapter: ExecutionAdapter,
    integration: ExecutionStatus,
    arguments: list[str],
    working_directory: str | Path,
    environment: dict[str, str] | None = None,
) -> str:
    """Launch a validated integration command in an interactive terminal."""

    argv = integration_argv(adapter, integration, arguments)
    cwd = Path(working_directory).expanduser().resolve()
    if not cwd.is_dir():
        raise BackendError(f"Integration working directory does not exist: {cwd}")
    raw_environment = dict(os.environ if environment is None else environment)
    child_env = terminal_environment(adapter, raw_environment)
    command = format_command(argv)
    record_command(command, cwd)
    try:
        launcher, creationflags = terminal_command(argv)
        subprocess.Popen(
            launcher,
            cwd=cwd,
            env=child_env,
            shell=False,
            close_fds=True,
            creationflags=creationflags,
            start_new_session=sys.platform != "win32",
        )
    except OSError as exc:
        raise BackendError(
            "Could not open an external terminal.",
            "Install a terminal application or run the command from an existing terminal.",
            {"command": command, "exception": f"{type(exc).__name__}: {exc}"},
        ) from exc
    return command
