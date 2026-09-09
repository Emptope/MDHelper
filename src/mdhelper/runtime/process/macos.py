"""Native desktop terminal command transport."""

from __future__ import annotations

import shlex
from pathlib import Path

_SCRIPT = '''on run argv
    tell application "Terminal"
        activate
        do script (item 1 of argv)
    end tell
end run'''


def script_command(
    executable: str,
    arguments: list[str],
    working_directory: str | Path | None,
    environment: dict[str, str] | None,
) -> list[str]:
    """Pass shell-quoted data separately from the fixed automation program."""

    command = list(arguments)
    if environment is not None:
        command = [
            "/usr/bin/env", "-i",
            *(f"{key}={value}" for key, value in environment.items()),
            *command,
        ]
    payload = shlex.join(command)
    if working_directory is not None:
        directory = shlex.quote(str(Path(working_directory).expanduser().resolve()))
        payload = f"cd {directory} && {payload}"
    return [executable, "-e", _SCRIPT, "--", payload]
