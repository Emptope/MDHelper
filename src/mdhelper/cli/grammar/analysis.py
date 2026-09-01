"""Inspection and analysis command grammar."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jsonargparse import ArgumentParser

from .common import add_inputs, add_output, command


def _add_frames(parser: ArgumentParser) -> None:
    parser.add_argument("--start", type=int, default=0, help="First zero-based frame.")
    parser.add_argument("--stop", type=int, help="Exclusive zero-based frame stop.")
    parser.add_argument("--stride", type=int, default=1, help="Frame stride.")


def _add_radial(parser: ArgumentParser) -> None:
    add_inputs(parser, roles=True)
    _add_frames(parser)
    add_output(parser)
    parser.add_argument(
        "--reference", required=True, help="Reference expression or GROMACS index group."
    )
    parser.add_argument(
        "--selection", required=True, help="Selection expression or GROMACS index group."
    )
    parser.add_argument(
        "--analysis-backend",
        choices=("auto", "native", "mdanalysis", "gromacs"),
        default="auto",
    )
    parser.add_argument("--r-max", type=float, default=1.0, help="Maximum radius in nm.")
    parser.add_argument("--bin-width", type=float, default=0.002, help="Bin width in nm.")


def add_analysis_commands(commands: Any) -> None:
    inspect_parser = command(commands, "inspect", "Inspect atoms and species.")
    add_inputs(inspect_parser, roles=False)

    analyze_parser = command(commands, "analyze", "Run an analysis or request document.")
    analyses = analyze_parser.add_subcommands(dest="analysis", required=True)

    rdf_parser = command(analyses, "rdf", "Compute a radial distribution function.")
    _add_radial(rdf_parser)

    cumulative_parser = command(
        analyses,
        "cumulative-rdf",
        "Compute a cumulative radial distribution N(r).",
    )
    _add_radial(cumulative_parser)

    energy_parser = command(
        analyses, "energy", "Extract terms from a GROMACS energy file."
    )
    energy_parser.add_argument("--energy-file", type=Path, required=True)
    energy_parser.add_argument(
        "--terms",
        type=list[str],
        required=True,
        help="Ordered energy terms as a JSON or YAML list.",
    )
    energy_parser.add_argument(
        "--analysis-backend",
        choices=("auto", "mdanalysis", "gromacs"),
        default="auto",
    )
    energy_parser.add_argument("--project", type=Path, help="Existing project directory.")
    add_output(energy_parser)

    request_parser = command(
        analyses, "request", "Run a versioned JSON analysis request."
    )
    request_parser.add_argument("--request", type=Path, required=True)
    request_parser.add_argument("--project", type=Path, help="Existing project directory.")
    add_output(request_parser)
