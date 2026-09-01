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
from mdhelper.core.errors import ConfigurationError
from mdhelper.core.plotting import PlotModel, results_plots

_NAME_LIMIT = 120


@dataclass(frozen=True)
class ResultExport:
    result: AnalysisResult
    name: str


@dataclass(frozen=True)
class PlotExport:
    model: PlotModel
    items: tuple[ResultExport, ...]
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


def _selected_export(result: AnalysisResult, series_key: str | None) -> ResultExport:
    items = result_exports(result)
    if series_key is None and len(items) == 1:
        return items[0]
    for item in items:
        request = AnalysisRequest.from_dict(item.result.request)
        if isinstance(request, EnergyRequest) and request.energy_terms == (series_key,):
            return item
    raise ConfigurationError("A plotted result series has no matching export item.")


def _unique_name(name: str, reserved: set[str]) -> str:
    candidate = name
    number = 2
    while candidate in reserved:
        suffix = f"-{number}"
        candidate = f"{name[: _NAME_LIMIT - len(suffix)].rstrip(' ._-')}{suffix}"
        number += 1
    reserved.add(candidate)
    return candidate


def plot_exports(
    results: tuple[AnalysisResult, ...],
    series_keys: tuple[str | None, ...] | None = None,
    models: tuple[PlotModel, ...] | None = None,
) -> tuple[PlotExport, ...]:
    """Bind each displayed plot to readable names and source export items."""

    if series_keys is not None and len(series_keys) != len(results):
        raise ConfigurationError("Plot series keys must match the number of results.")
    plotted = results_plots(results) if models is None else models
    plans: list[PlotExport] = []
    reserved: set[str] = set()
    for model in plotted:
        items: list[ResultExport] = []
        seen: set[tuple[str, str]] = set()
        for index in model.source_indices:
            series_key = None if series_keys is None else series_keys[index]
            item = _selected_export(results[index], series_key)
            key = (item.result.analysis_id, item.name)
            if key not in seen:
                seen.add(key)
                items.append(item)
        name = _safe_name(tuple(item.name for item in items))
        plans.append(PlotExport(model, tuple(items), _unique_name(name, reserved)))
    return tuple(plans)


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
