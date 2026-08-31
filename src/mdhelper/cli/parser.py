"""Argument grammar for the command-line adapter."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from mdhelper.core.species import SPECIES_ROLES
from mdhelper.core.trajectory import TOPOLOGY_SUFFIXES, TRAJECTORY_SUFFIXES
from mdhelper.integrations import DEFAULT_INTEGRATION_REGISTRY
from mdhelper.version import __version__


def _parse_role(value: str) -> tuple[str, str]:
    try:
        species, role = value.split("=", 1)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Expected SPECIES=ROLE.") from exc
    if not species.strip() or not role.strip():
        raise argparse.ArgumentTypeError("Species and role cannot be empty.")
    if role.strip() not in SPECIES_ROLES:
        raise argparse.ArgumentTypeError(f"Role must be one of: {', '.join(SPECIES_ROLES)}.")
    return species.strip(), role.strip()


def _add_inputs(parser: argparse.ArgumentParser, *, include_backend: bool = True) -> None:
    topology = ", ".join(TOPOLOGY_SUFFIXES)
    trajectory = ", ".join(TRAJECTORY_SUFFIXES)
    parser.add_argument("--topology", help=f"Topology file ({topology}).")
    parser.add_argument("--trajectory", help=f"Trajectory file ({trajectory}).")
    parser.add_argument(
        "--index",
        help="GROMACS .ndx file; selection arguments are exact group names when provided.",
    )
    parser.add_argument("--project", help="Existing .mdhelper project directory.")
    parser.add_argument(
        "--role",
        action="append",
        type=_parse_role,
        default=[],
        metavar="SPECIES=ROLE",
        help="Species role; repeat for multiple species.",
    )
    if include_backend:
        parser.add_argument(
            "--backend",
            choices=("auto", "native", "mdanalysis", "gromacs"),
            default="auto",
        )


def _add_frames(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--start", type=int, default=0, help="First zero-based frame.")
    parser.add_argument("--stop", type=int, help="Exclusive zero-based frame stop.")
    parser.add_argument("--stride", type=int, default=1, help="Frame stride.")


def _add_output(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output", required=True, help="Output directory.")
    parser.add_argument("--no-figures", action="store_true", help="Skip PNG/SVG/PDF export.")
    parser.add_argument(
        "--json-progress", action="store_true", help="Write JSON progress events to stderr."
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mdhelper",
        description="Reproducible GROMACS trajectory analysis.",
    )
    parser.add_argument("--version", action="version", version=f"MDHelper {__version__}")
    parser.add_argument("--debug", action="store_true", help="Show internal tracebacks.")
    parser.add_argument(
        "--config", type=Path, help="Explicit user configuration path for this invocation."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    config_parser = subparsers.add_parser("config", help="Manage user configuration.")
    config_sub = config_parser.add_subparsers(dest="config_command", required=True)
    config_sub.add_parser("path", help="Print the active configuration path.")
    init_parser = config_sub.add_parser("init", help="Create a commented configuration template.")
    init_parser.add_argument("--force", action="store_true")
    config_sub.add_parser("check", help="Validate the active configuration.")
    config_sub.add_parser("show", help="Print resolved configuration as JSON.")

    integration_parser = subparsers.add_parser(
        "integrations", help="Detect and run supported external software."
    )
    integration_sub = integration_parser.add_subparsers(
        dest="integration_command", required=True
    )
    integration_sub.add_parser("list", help="List supported and configured integrations.")
    templates_parser = integration_sub.add_parser(
        "templates", help="List or show bundled text templates."
    )
    templates_parser.add_argument("key", nargs="?", help="Template key to show.")
    detect_parser = integration_sub.add_parser(
        "detect", help="Detect one supported integration."
    )
    detect_parser.add_argument("integration", choices=DEFAULT_INTEGRATION_REGISTRY.names())
    detect_parser.add_argument("--path", help="Per-run executable path override.")
    run_parser = integration_sub.add_parser(
        "run", help="Explicitly run a detected integration."
    )
    run_parser.add_argument("integration", choices=DEFAULT_INTEGRATION_REGISTRY.names())
    run_parser.add_argument("--path", help="Per-run executable path override.")
    run_parser.add_argument("--cwd", default=".", help="Explicit working directory.")
    run_parser.add_argument("--project", help="Project used to record invocation provenance.")
    run_parser.add_argument("--timeout", type=float, help="Timeout in seconds.")
    run_parser.add_argument(
        "--output-file", action="append", default=[], help="Output file to fingerprint."
    )
    run_parser.set_defaults(arguments=[])

    inspect_parser = subparsers.add_parser("inspect", help="Inspect atoms and species.")
    _add_inputs(inspect_parser, include_backend=False)

    rdf_parser = subparsers.add_parser("rdf", help="Compute a radial distribution function.")
    _add_inputs(rdf_parser)
    _add_frames(rdf_parser)
    _add_output(rdf_parser)
    rdf_parser.add_argument(
        "--reference", required=True, help="Reference expression or GROMACS index group."
    )
    rdf_parser.add_argument(
        "--selection", required=True, help="Selection expression or GROMACS index group."
    )
    rdf_parser.add_argument("--r-max", type=float, default=1.0, help="Maximum radius in nm.")
    rdf_parser.add_argument("--bin-width", type=float, default=0.002, help="Bin width in nm.")

    cn_parser = subparsers.add_parser(
        "cn", help="Compute the cumulative number RDF N(r)."
    )
    _add_inputs(cn_parser)
    _add_frames(cn_parser)
    _add_output(cn_parser)
    cn_parser.add_argument(
        "--reference", required=True, help="Reference expression or GROMACS index group."
    )
    cn_parser.add_argument(
        "--selection", required=True, help="Selection expression or GROMACS index group."
    )
    cn_parser.add_argument("--r-max", type=float, default=1.0, help="Maximum radius in nm.")
    cn_parser.add_argument("--bin-width", type=float, default=0.002, help="Bin width in nm.")

    energy_parser = subparsers.add_parser(
        "energy", help="Extract and plot terms from a GROMACS energy file."
    )
    energy_parser.add_argument("--energy-file", required=True, help="GROMACS .edr file.")
    energy_parser.add_argument(
        "--term", action="append", required=True, help="Energy term; repeat as needed."
    )
    energy_parser.add_argument(
        "--backend",
        choices=("auto", "mdanalysis", "gromacs"),
        default="auto",
    )
    energy_parser.add_argument("--project", help="Existing .mdhelper project directory.")
    _add_output(energy_parser)

    request_parser = subparsers.add_parser("run", help="Run a versioned JSON analysis request.")
    request_parser.add_argument("--request", required=True, help="Request JSON path.")
    request_parser.add_argument("--project", help="Existing project directory.")
    _add_output(request_parser)

    project_parser = subparsers.add_parser("project", help="Manage portable projects.")
    project_sub = project_parser.add_subparsers(dest="project_command", required=True)
    create_parser = project_sub.add_parser("create", help="Create a project directory.")
    create_parser.add_argument("--path", required=True)
    create_parser.add_argument("--topology", required=True)
    create_parser.add_argument("--trajectory", required=True)
    create_parser.add_argument("--index", help="Optional GROMACS .ndx selection file.")
    create_parser.add_argument("--role", action="append", type=_parse_role, default=[])
    show_parser = project_sub.add_parser("show", help="Show a project manifest.")
    show_parser.add_argument("--path", required=True)
    show_parser.add_argument("--no-verify", action="store_true")
    relocate_parser = project_sub.add_parser("relocate", help="Relocate one project input.")
    relocate_parser.add_argument("--path", required=True)
    relocate_parser.add_argument(
        "--role", required=True, choices=("topology", "trajectory", "index")
    )
    relocate_parser.add_argument("--file", required=True)
    roles_parser = project_sub.add_parser(
        "set-roles", help="Replace the project's confirmed species-role mapping."
    )
    roles_parser.add_argument("--path", required=True)
    roles_parser.add_argument(
        "--role", action="append", type=_parse_role, required=True, metavar="SPECIES=ROLE"
    )
    integration_preference = project_sub.add_parser(
        "set-integration",
        help="Set a portable integration preference and capability requirement.",
    )
    integration_preference.add_argument("--path", required=True)
    integration_preference.add_argument(
        "--integration", required=True, choices=DEFAULT_INTEGRATION_REGISTRY.names()
    )
    integration_preference.add_argument("--not-preferred", action="store_true")
    integration_preference.add_argument(
        "--required-capability", action="append", default=[]
    )
    list_parser = project_sub.add_parser(
        "list-results", help="List completed results stored in a project."
    )
    list_parser.add_argument("--path", required=True)
    show_result = project_sub.add_parser(
        "show-result", help="Load one completed project result as JSON."
    )
    show_result.add_argument("--path", required=True)
    show_result.add_argument("--analysis-id", required=True)
    export_parser = project_sub.add_parser(
        "export-result", help="Export one completed project result."
    )
    export_parser.add_argument("--path", required=True)
    export_parser.add_argument("--analysis-id", required=True)
    export_parser.add_argument("--output", required=True)
    export_parser.add_argument("--no-figures", action="store_true")
    return parser


def parse_args(parser: argparse.ArgumentParser, argv: list[str] | None) -> argparse.Namespace:
    """Parse CLI arguments while preserving tool arguments after ``--``."""

    values = list(sys.argv[1:] if argv is None else argv)
    if "--" not in values:
        return parser.parse_args(values)
    boundary = values.index("--")
    args = parser.parse_args(values[:boundary])
    if args.command != "integrations" or args.integration_command != "run":
        parser.error(f"unrecognized arguments: {' '.join(values[boundary:])}")
    args.arguments = values[boundary + 1 :]
    return args
