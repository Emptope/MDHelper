"""Readable result and plot export plans."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from mdhelper.core.analysis import (
    AnalysisRequest,
    AnalysisResult,
    EnergyRequest,
    RadialRequest,
)
from mdhelper.core.errors import ConfigurationError
from mdhelper.core.plotting import PlotModel, results_plots

_NAME_LIMIT = 120
SourceAxis = Literal["primary", "secondary"]


@dataclass(frozen=True)
class ResultExport:
    result: AnalysisResult
    name: str


@dataclass(frozen=True)
class PlotExport:
    model: PlotModel
    items: tuple[ResultExport, ...]
    name: str
    item_models: tuple[PlotModel, ...] = ()
    source_axes: tuple[SourceAxis, ...] = ()


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
    while candidate.casefold() in reserved:
        suffix = f"-{number}"
        candidate = f"{name[: _NAME_LIMIT - len(suffix)].rstrip(' ._-')}{suffix}"
        number += 1
    reserved.add(candidate.casefold())
    return candidate


def _plot_name(items: Sequence[ResultExport]) -> str:
    analysis_types = {item.result.analysis_type for item in items}
    if {"rdf", "cumulative_rdf"}.issubset(analysis_types):
        return "rdf-cn"
    if len(items) > 1:
        if analysis_types == {"rdf"}:
            return "rdf"
        if analysis_types == {"cumulative_rdf"}:
            return "cn"
        if analysis_types == {"energy"}:
            return "energy"
    return _safe_name(tuple(item.name for item in items))


def _source_plot(
    result: AnalysisResult,
    series_key: str | None,
    label: str | None,
    color_id: int | None,
    title: str | None,
) -> PlotModel:
    models = results_plots(
        (result,),
        None if label is None else (label,),
        None if color_id is None else (color_id,),
        None if series_key is None else (series_key,),
        titles=None if title is None else (title,),
    )
    if len(models) != 1:
        raise ConfigurationError("An export item must map to exactly one plot.")
    return models[0]


def _source_axis(parent: PlotModel, source: PlotModel) -> SourceAxis:
    return "primary" if source.y_label == parent.y_label else "secondary"


def plot_exports(
    results: tuple[AnalysisResult, ...],
    series_keys: tuple[str | None, ...] | None = None,
    models: tuple[PlotModel, ...] | None = None,
    *,
    labels: tuple[str | None, ...] | None = None,
    color_ids: tuple[int, ...] | None = None,
    group_ids: tuple[str | None, ...] | None = None,
    titles: tuple[str | None, ...] | None = None,
) -> tuple[PlotExport, ...]:
    """Bind each displayed plot to readable names and source export items."""

    values = (
        ("series keys", series_keys),
        ("labels", labels),
        ("color IDs", color_ids),
        ("group IDs", group_ids),
        ("titles", titles),
    )
    for description, selected in values:
        if selected is not None and len(selected) != len(results):
            raise ConfigurationError(
                f"Plot {description} must match the number of results."
            )
    plotted = (
        results_plots(results, labels, color_ids, series_keys, group_ids, titles)
        if models is None
        else models
    )
    plans: list[PlotExport] = []
    for model in plotted:
        items: list[ResultExport] = []
        item_models: list[PlotModel] = []
        seen: set[tuple[str, str]] = set()
        for index in model.source_indices:
            if index < 0 or index >= len(results):
                raise ConfigurationError("A plot source index is outside the result list.")
            series_key = None if series_keys is None else series_keys[index]
            item = _selected_export(results[index], series_key)
            key = (item.result.analysis_id, item.name)
            if key not in seen:
                seen.add(key)
                items.append(item)
                item_models.append(
                    _source_plot(
                        results[index],
                        series_key,
                        None if labels is None else labels[index],
                        None if color_ids is None else color_ids[index],
                        None if titles is None else titles[index],
                    )
                )
        plans.append(
            PlotExport(
                model,
                tuple(items),
                _plot_name(items),
                tuple(item_models),
                tuple(_source_axis(model, item_model) for item_model in item_models),
            )
        )
    return tuple(plans)


def default_plot_exports(results: Sequence[AnalysisResult]) -> tuple[PlotExport, ...]:
    items = tuple(item for result in results for item in result_exports(result))
    return plot_exports(tuple(item.result for item in items))


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
