"""Project command grammar."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import command


def add_project_commands(commands: Any) -> None:
    parser = command(commands, "project", "Manage portable projects.")
    actions = parser.add_subcommands(dest="action", required=True)

    create_parser = command(actions, "create", "Create a project directory.")
    create_parser.add_argument("--path", type=Path, required=True)
    create_parser.add_argument("--topology", type=Path, required=True)
    create_parser.add_argument("--trajectory", type=Path, required=True)
    create_parser.add_argument("--index", type=Path)
    create_parser.add_argument("--roles", type=dict[str, str], default={})

    show_parser = command(actions, "show", "Show a project manifest.")
    show_parser.add_argument("--path", type=Path, required=True)
    show_parser.add_argument("--verify", type=bool, default=True)

    relocate_parser = command(actions, "relocate", "Relocate one project input.")
    relocate_parser.add_argument("--path", type=Path, required=True)
    relocate_parser.add_argument(
        "--input", required=True, choices=("topology", "trajectory", "index")
    )
    relocate_parser.add_argument("--file", type=Path, required=True)

    roles_parser = command(actions, "set-roles", "Replace confirmed species roles.")
    roles_parser.add_argument("--path", type=Path, required=True)
    roles_parser.add_argument("--roles", type=dict[str, str], required=True)

    list_parser = command(actions, "list-results", "List completed project results.")
    list_parser.add_argument("--path", type=Path, required=True)

    result_parser = command(actions, "show-result", "Load one project result as JSON.")
    result_parser.add_argument("--path", type=Path, required=True)
    result_parser.add_argument("--analysis-id", required=True)

    export_parser = command(actions, "export-result", "Export one project result.")
    export_parser.add_argument("--path", type=Path, required=True)
    export_parser.add_argument("--analysis-id", required=True)
    export_parser.add_argument("--output", type=Path, required=True)
    export_parser.add_argument("--figures", type=bool, default=True)
