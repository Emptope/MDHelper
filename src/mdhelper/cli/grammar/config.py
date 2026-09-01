"""User configuration command grammar."""

from __future__ import annotations

from typing import Any

from .common import command


def add_config_commands(commands: Any) -> None:
    parser = command(commands, "config", "Manage user configuration.")
    actions = parser.add_subcommands(dest="action", required=True)
    command(actions, "path", "Print the active configuration path.")
    init_parser = command(actions, "init", "Create a configuration template.")
    init_parser.add_argument("--force", action="store_true")
    command(actions, "check", "Validate the active configuration.")
    command(actions, "show", "Print resolved configuration as JSON.")
