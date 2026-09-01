"""Bundled template command grammar."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import command


def add_template_commands(commands: Any) -> None:
    parser = command(commands, "templates", "List, show, or save bundled templates.")
    actions = parser.add_subcommands(dest="action", required=True)
    command(actions, "list", "List bundled templates.")
    show_parser = command(actions, "show", "Show one bundled template.")
    show_parser.add_argument("key")
    save_parser = command(actions, "save", "Save one bundled template.")
    save_parser.add_argument("key")
    save_parser.add_argument("--output", type=Path, required=True)
