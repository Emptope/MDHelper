"""Energy analysis backends for GROMACS EDR files."""

from __future__ import annotations

import re
import tempfile
from pathlib import Path
from threading import Event
from typing import TYPE_CHECKING

from mdhelper.analysis.common import check_cancel
from mdhelper.core.analysis import AnalysisResult
from mdhelper.core.errors import BackendError, FormatError, InputFileError
from mdhelper.integrations.manager import IntegrationManager
from mdhelper.plugins.analysis import AnalysisInput

if TYPE_CHECKING:
    from MDAnalysis.auxiliary.EDR import EDRReader

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
) -> tuple[str, ...]:
    """Ask GROMACS for every term stored in one energy file."""

    source = Path(energy_file).expanduser().resolve()
    if not source.is_file():
        raise InputFileError(
            f"GROMACS energy file does not exist: {source}",
            "Select an existing EDR file.",
        )
    with tempfile.TemporaryDirectory(prefix="mdhelper-energy-terms-") as directory:
        root = Path(directory)
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


def _energy_source(energy_file: str | Path) -> Path:
    source = Path(energy_file).expanduser().resolve()
    if not source.is_file():
        raise InputFileError(
            f"GROMACS energy file does not exist: {source}",
            "Select an existing EDR file.",
        )
    return source


def _edr_reader(source: Path) -> EDRReader:
    try:
        from MDAnalysis.auxiliary.EDR import EDRReader

        return EDRReader(str(source), convert_units=False)
    except ImportError as exc:
        raise BackendError(
            "MDAnalysis cannot read EDR files because its pyedr parser is unavailable.",
            "Install MDHelper with its complete runtime dependencies.",
            {"exception": f"{type(exc).__name__}: {exc}"},
        ) from exc
    except (EOFError, OSError, TypeError, ValueError) as exc:
        raise FormatError(
            f"MDAnalysis could not read the GROMACS energy file: {source}",
            "Confirm that the file is a valid EDR file supported by the installed MDAnalysis.",
            {"exception": f"{type(exc).__name__}: {exc}"},
        ) from exc


def mda_terms(
    energy_file: str | Path,
    cancel_event: Event | None = None,
) -> tuple[str, ...]:
    """Read the ordered EDR term list through MDAnalysis."""

    source = _energy_source(energy_file)
    check_cancel(cancel_event)
    reader = _edr_reader(source)
    try:
        terms = tuple(term for term in reader.terms if term != "Time")
    finally:
        reader.close()
    check_cancel(cancel_event)
    if terms:
        return terms
    raise FormatError(
        "MDAnalysis did not report any energy terms for the selected EDR file.",
        "Confirm that the file contains GROMACS energy series.",
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


class GmxEnergy:
    name = "gromacs"
    display_name = "GROMACS"
    needs_trajectory = False

    def terms(
        self,
        integrations: IntegrationManager,
        energy_file: str | Path,
        cancel_event: Event | None = None,
    ) -> tuple[str, ...]:
        return gmx_terms(integrations, energy_file, cancel_event)

    def run(self, inputs: AnalysisInput) -> AnalysisResult:
        request = inputs.request
        request.validate()
        assert request.energy_file is not None
        source = Path(request.energy_file).expanduser().resolve()
        with tempfile.TemporaryDirectory(prefix="mdhelper-energy-") as directory:
            root = Path(directory)
            output = root / "energy.xvg"
            record = inputs.integrations.run(
                "gromacs",
                ["energy", "-f", str(source), "-o", str(output)],
                root,
                cancel_event=inputs.cancel_event,
                output_files=[output],
                input_text="\n".join(request.energy_terms) + "\n\n",
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
            parameters={
                "energy_file": request.energy_file,
                "terms": list(request.energy_terms),
                "analysis_backend": self.name,
            },
            units={"time_ps": "ps", "series": y_label},
            uncertainty={},
            diagnostics={"n_samples": len(time_ps)},
            provenance=provenance,
            request=request.to_dict(),
        )


class MdaEnergy:
    name = "mdanalysis"
    display_name = "MDAnalysis"
    needs_trajectory = False

    def terms(
        self,
        _integrations: IntegrationManager,
        energy_file: str | Path,
        cancel_event: Event | None = None,
    ) -> tuple[str, ...]:
        return mda_terms(energy_file, cancel_event)

    def run(self, inputs: AnalysisInput) -> AnalysisResult:
        request = inputs.request
        request.validate()
        assert request.energy_file is not None
        source = _energy_source(request.energy_file)
        check_cancel(inputs.cancel_event)
        reader = _edr_reader(source)
        try:
            available = set(reader.terms)
            missing = [term for term in request.energy_terms if term not in available]
            if missing:
                raise FormatError(
                    "The selected EDR file does not contain every requested energy term.",
                    "Refresh the available terms after selecting an EDR file.",
                    {"missing_terms": missing},
                )
            raw = reader.get_data(list(request.energy_terms))
            time_ps = [float(value) for value in raw["Time"]]
            series = {
                term: [float(value) for value in raw[term]]
                for term in request.energy_terms
            }
            series_units = {
                term: str(reader.unit_dict.get(term, ""))
                for term in request.energy_terms
            }
            time_unit = str(reader.unit_dict.get("Time", "ps")) or "ps"
        finally:
            reader.close()
        check_cancel(inputs.cancel_event)
        if not time_ps:
            raise FormatError("The selected EDR file contains no energy samples.")
        unique_units = {unit for unit in series_units.values() if unit}
        series_unit = unique_units.pop() if len(unique_units) == 1 else "Value"
        if inputs.progress:
            inputs.progress(len(time_ps), len(time_ps), "Read EDR energy samples")
        return AnalysisResult(
            analysis_type="energy",
            method_version=METHOD_VERSION,
            data={"time_ps": time_ps, "series": series},
            parameters={
                "energy_file": request.energy_file,
                "terms": list(request.energy_terms),
                "analysis_backend": self.name,
            },
            units={"time_ps": time_unit, "series": series_unit},
            uncertainty={},
            diagnostics={
                "n_samples": len(time_ps),
                "series_units": series_units,
            },
            provenance=dict(inputs.provenance),
            request=request.to_dict(),
        )
