"""GROMACS energy analysis."""

from __future__ import annotations

import re
from pathlib import Path
from threading import Event

from mdhelper.analysis.common import analysis_directory
from mdhelper.analysis.pipeline import AnalysisInput
from mdhelper.core.analysis import AnalysisResult, EnergyRequest
from mdhelper.core.errors import BackendError, FormatError, InputFileError
from mdhelper.integrations.gromacs import output_message
from mdhelper.integrations.manager import IntegrationManager

METHOD_VERSION = "1.0.0"
_TERM_PAIR = re.compile(r"(?:^|\s)(\d+)\s+([^\s]+)")


def parse_energy_terms(output: str) -> tuple[str, ...]:
    """Parse the numbered term menu printed by interactive ``gmx energy``."""

    terms: dict[int, str] = {}
    menu = False
    for raw in output.splitlines():
        line = raw.strip()
        folded = line.casefold()
        if "select the terms" in folded or "end your selection" in folded:
            menu = True
            continue
        matches = tuple(_TERM_PAIR.finditer(raw))
        if not matches or (not menu and len(matches) < 2):
            continue
        for match in matches:
            index = int(match.group(1))
            name = match.group(2).strip()
            if index > 0 and name:
                terms.setdefault(index, name)
    return tuple(terms[index] for index in sorted(terms))


def gmx_terms(
    integrations: IntegrationManager,
    energy_file: str | Path,
    cancel_event: Event | None = None,
    cache_dir: Path | None = None,
) -> tuple[str, ...]:
    """Ask GROMACS for every term stored in one energy file."""

    source = Path(energy_file).expanduser().resolve()
    if not source.is_file():
        raise InputFileError(
            f"GROMACS energy file does not exist: {source}",
            "Select an existing EDR file.",
        )
    with analysis_directory(cache_dir, "gromacs-energy-terms") as root:
        output = root / "unused.xvg"
        record = integrations.run(
            "gromacs",
            ["energy", "-f", str(source), "-o", str(output)],
            root,
            cancel_event=cancel_event,
            input_text="0\n",
            required_capabilities=("energy",),
        )
    terms = parse_energy_terms(f"{record.stdout}\n{record.stderr}")
    if terms:
        return terms
    if record.status != "completed":
        raise BackendError(
            f"GROMACS energy term discovery exited with code {record.exit_code}.",
            details={"integration_run": record.to_dict()},
        )
    raise FormatError(
        "GROMACS did not report any energy terms for the selected EDR file.",
        "Confirm that the file is a readable GROMACS energy file.",
        {"integration_run": record.to_dict()},
    )


def _quoted(line: str) -> str | None:
    match = re.search(r'"(.*)"', line)
    return match.group(1).strip() if match else None


def _parse_xvg(
    path: Path, terms: tuple[str, ...]
) -> tuple[list[float], dict[str, list[float]], str]:
    time_ps: list[float] = []
    series: dict[str, list[float]] = {term: [] for term in terms}
    y_label = "Value"
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        raise FormatError(
            f"Could not read GROMACS energy output: {path}",
            details={"exception": f"{type(exc).__name__}: {exc}"},
        ) from exc
    for line_number, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("@"):
            if "yaxis" in line and "label" in line:
                y_label = _quoted(line) or y_label
            continue
        fields = line.split()
        if len(fields) != len(terms) + 1:
            raise FormatError(
                "GROMACS energy output has an unexpected column count.",
                details={
                    "line": line_number,
                    "expected_columns": len(terms) + 1,
                    "actual_columns": len(fields),
                },
            )
        try:
            values = [float(field) for field in fields]
        except ValueError as exc:
            raise FormatError(
                "GROMACS energy output contains a non-numeric row.",
                details={"line": line_number},
            ) from exc
        time_ps.append(values[0])
        for index, term in enumerate(terms, start=1):
            series[term].append(values[index])
    if not time_ps:
        raise FormatError("GROMACS energy output contains no numeric samples.")
    return time_ps, series, y_label


class EnergyAnalysis:
    def terms(
        self,
        integrations: IntegrationManager,
        energy_file: str | Path,
        cancel_event: Event | None = None,
        cache_dir: Path | None = None,
    ) -> tuple[str, ...]:
        return gmx_terms(integrations, energy_file, cancel_event, cache_dir)

    def run(self, inputs: AnalysisInput) -> AnalysisResult:
        request = inputs.request
        if not isinstance(request, EnergyRequest):
            raise BackendError("The GROMACS energy backend requires an energy request.")
        request.validate()
        source = Path(request.energy_file).expanduser().resolve()
        with analysis_directory(inputs.cache_dir, "gromacs-energy") as root:
            output = root / "energy.xvg"
            arguments = ["energy", "-f", str(source), "-o", str(output)]

            def process_progress(_elapsed: float, stdout: str, stderr: str) -> None:
                message = output_message(stdout, stderr)
                if inputs.progress is not None and message is not None:
                    inputs.progress(0, None, message)

            record = inputs.integrations.run(
                "gromacs",
                arguments,
                root,
                cancel_event=inputs.cancel_event,
                output_files=[output],
                input_text="\n".join(request.energy_terms) + "\n\n",
                process_progress=process_progress,
                required_capabilities=("energy",),
            )
            if record.status != "completed":
                raise BackendError(
                    f"GROMACS energy exited with code {record.exit_code}.",
                    details={"integration_run": record.to_dict()},
                )
            time_ps, series, y_label = _parse_xvg(output, request.energy_terms)
        provenance = dict(inputs.provenance)
        provenance["integration_runs"] = [record.to_dict()]
        return AnalysisResult(
            analysis_type="energy",
            method_version=METHOD_VERSION,
            data={"time_ps": time_ps, "series": series},
            parameters={},
            units={"time_ps": "ps", "series": y_label},
            diagnostics={"n_samples": len(time_ps)},
            provenance=provenance,
            request=request.to_dict(),
        )

