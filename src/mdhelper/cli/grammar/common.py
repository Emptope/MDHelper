"""Shared CLI grammar fragments."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jsonargparse import ArgumentParser

from mdhelper.core.trajectory import TOPOLOGY_SUFFIXES, TRAJECTORY_SUFFIXES


def command(commands: Any, name: str, help_text: str) -> ArgumentParser:
    parser = ArgumentParser(description=help_text)
    commands.add_subcommand(name, parser, help=help_text)
    return parser


def add_inputs(parser: ArgumentParser, *, roles: bool) -> None:
    topology = ", ".join(TOPOLOGY_SUFFIXES)
    trajectory = ", ".join(TRAJECTORY_SUFFIXES)
    parser.add_argument("--topology", type=Path, help=f"Topology file ({topology}).")
    parser.add_argument("--trajectory", type=Path, help=f"Trajectory file ({trajectory}).")
    parser.add_argument(
        "--index",
        type=Path,
        help="GROMACS .ndx file; selections are exact group names when it is provided.",
    )
    parser.add_argument("--project", type=Path, help="Existing project directory.")
    if roles:
        parser.add_argument(
            "--roles",
            type=dict[str, str],
            default={},
            help="Species-to-role mapping as a JSON or YAML object.",
        )


def add_output(parser: ArgumentParser) -> None:
    parser.add_argument("--output", type=Path, required=True, help="Output directory.")
    parser.add_argument(
        "--figures", type=bool, default=True, help="Export PNG, SVG, and PDF figures."
    )
    parser.add_argument(
        "--json-progress", action="store_true", help="Write JSON progress events to stderr."
    )
