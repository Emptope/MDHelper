"""MDAnalysis energy analysis."""

from __future__ import annotations

from pathlib import Path
from threading import Event
from typing import TYPE_CHECKING

from mdhelper.analysis.common import check_cancel
from mdhelper.analysis.pipeline import AnalysisInput
from mdhelper.core.analysis import AnalysisResult, EnergyRequest
from mdhelper.core.errors import BackendError, FormatError, InputFileError
from mdhelper.integrations.manager import IntegrationManager

if TYPE_CHECKING:
    from MDAnalysis.auxiliary.EDR import EDRReader

METHOD_VERSION = "1.0.0"


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


def energy_terms(
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


class EnergyAnalysis:
    def terms(
        self,
        _integrations: IntegrationManager,
        energy_file: str | Path,
        cancel_event: Event | None = None,
        cache_dir: Path | None = None,
    ) -> tuple[str, ...]:
        del cache_dir
        return energy_terms(energy_file, cancel_event)

    def run(self, inputs: AnalysisInput) -> AnalysisResult:
        request = inputs.request
        if not isinstance(request, EnergyRequest):
            raise BackendError("The MDAnalysis energy backend requires an energy request.")
        request.validate()
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
            method_version=METHOD_VERSION,
            data={"time_ps": time_ps, "series": series},
            parameters={},
            units={"time_ps": time_unit, "series": series_unit},
            diagnostics={
                "n_samples": len(time_ps),
                "series_units": series_units,
            },
            provenance=dict(inputs.provenance),
            request=request.to_dict(),
        )
