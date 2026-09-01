"""External integration command grammar."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mdhelper.integrations import DEFAULT_INTEGRATION_REGISTRY

from .common import command


def add_integration_commands(commands: Any) -> None:
    parser = command(commands, "integrations", "Inspect and run external integrations.")
    actions = parser.add_subcommands(dest="action", required=True)
    command(actions, "list", "List supported and configured integrations.")

    detect_parser = command(actions, "detect", "Detect one supported integration.")
    detect_parser.add_argument("integration", choices=DEFAULT_INTEGRATION_REGISTRY.names())
    detect_parser.add_argument("--path", type=Path, help="Executable path override.")

    run_parser = command(actions, "run", "Run one integration with explicit arguments.")
    run_parser.add_argument("integration", choices=DEFAULT_INTEGRATION_REGISTRY.names())
    run_parser.add_argument("--path", type=Path, help="Executable path override.")
    run_parser.add_argument("--cwd", type=Path, default=Path("."))
    run_parser.add_argument("--project", type=Path, help="Project used to record provenance.")
    run_parser.add_argument("--timeout", type=float, help="Timeout in seconds.")
    run_parser.add_argument(
        "--output-files",
        type=list[Path],
        default=[],
        help="Files to fingerprint as a JSON or YAML list.",
    )
    run_parser.add_argument(
        "arguments",
        nargs="+",
        help="Integration arguments. Use -- before values that start with a dash.",
    )
