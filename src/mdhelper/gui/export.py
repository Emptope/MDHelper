"""Readable per-item directory planning for GUI result exports."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from mdhelper.core.analysis import (
    AnalysisRequest,
    AnalysisResult,
    EnergyRequest,
    RadialRequest,
)

_NAME_LIMIT = 120


@dataclass(frozen=True)
class ResultExport:
    result: AnalysisResult
    name: str


def _safe_name(parts: tuple[str, ...]) -> str:
    value = "-".join(parts)
    safe = "".join(
        character if character.isalnum() or character in "-_." else "-"
        for character in value
    )
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe[:_NAME_LIMIT].strip(" ._-") or "analysis"


def result_exports(result: AnalysisResult) -> tuple[ResultExport, ...]:
    """Describe independently exported analysis items with readable names."""

    request = AnalysisRequest.from_dict(result.request)
    if isinstance(request, RadialRequest):
        analysis = "rdf" if request.analysis_type == "rdf" else "cn"
        name = _safe_name((analysis, request.reference, request.selection))
        return (ResultExport(result, name),)
    if isinstance(request, EnergyRequest):
        series = result.data["series"]
        if not isinstance(series, dict):
            return ()
        items: list[ResultExport] = []
        for term in request.energy_terms:
            item_request = replace(request, energy_terms=(term,))
            item_result = replace(
                result,
                data={"time_ps": result.data["time_ps"], "series": {term: series[term]}},
                request=item_request.to_dict(),
            )
            item_result.validate()
            items.append(ResultExport(item_result, _safe_name(("energy", term))))
        return tuple(items)
    return (ResultExport(result, _safe_name((result.analysis_type,))),)


def export_directories(
    root: Path,
    items: tuple[ResultExport, ...],
) -> tuple[Path, ...]:
    """Allocate non-conflicting directories for a set of result export items."""

    directories: list[Path] = []
    reserved: set[Path] = set()
    for item in items:
        output = root / item.name
        number = 2
        while output.exists() or output in reserved:
            output = root / f"{item.name}-{number}"
            number += 1
        directories.append(output)
        reserved.add(output)
    return tuple(directories)
