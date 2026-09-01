"""Composition root for the command-line grammar."""

from __future__ import annotations

from pathlib import Path

from jsonargparse import ActionConfigFile, ArgumentParser, Namespace

from mdhelper.cli.grammar import (
    add_analysis_commands,
    add_config_commands,
    add_integration_commands,
    add_project_commands,
    add_template_commands,
)
from mdhelper.version import __version__


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(
        prog="mdhelper",
        description="Reproducible molecular-dynamics analysis.",
    )
    parser.add_argument("--version", action="version", version=f"MDHelper {__version__}")
    parser.add_argument("--debug", action="store_true", help="Show internal tracebacks.")
    parser.add_argument(
        "--settings",
        type=Path,
        help="Application settings path for this invocation.",
    )
    parser.add_argument(
        "--args-file",
        action=ActionConfigFile,
        help="Load command arguments from a JSON or YAML file.",
    )
    commands = parser.add_subcommands(dest="command", required=True)
    add_analysis_commands(commands)
    add_project_commands(commands)
    add_integration_commands(commands)
    add_template_commands(commands)
    add_config_commands(commands)
    return parser


def parse_args(parser: ArgumentParser, argv: list[str] | None) -> Namespace:
    return parser.parse_args(argv)
