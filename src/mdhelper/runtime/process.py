"""Platform process-creation policy."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence

TerminalFinder = Callable[[str], str | None]

_POSIX_TERMINALS = (
    ("xdg-terminal-exec", ()),
    ("x-terminal-emulator", ("-e",)),
    ("gnome-terminal", ("--",)),
    ("konsole", ("-e",)),
    ("xfce4-terminal", ("--execute",)),
    ("xterm", ("-e",)),
)


def hidden_window_flags(platform: str | None = None) -> int:
    system = os.name if platform is None else platform
    if system != "nt":
        return 0
    return int(vars(subprocess)["CREATE_NO_WINDOW"])


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
