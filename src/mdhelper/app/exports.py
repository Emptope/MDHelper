"""Readable analysis export planning shared by interactive frontends."""

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
from mdhelper.core.plotting import (
    DEFAULT_PLOT_SCHEME,
    PlotAppearance,
    PlotLimits,
    PlotModel,
    PlotSize,
    results_plots,
)
from mdhelper.io.export import export_plot_model, export_result

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


def _plot_sizes(
    plots: Sequence[PlotExport],
    sizes: Sequence[PlotSize | None] | None,
) -> tuple[PlotSize | None, ...]:
    values = tuple(None for _plot in plots) if sizes is None else tuple(sizes)
    if len(values) != len(plots):
        raise ConfigurationError("Plot sizes must match the number of exported plots.")
    return values


def _item_limits(
    axis: SourceAxis,
    limits: PlotLimits | None,
) -> PlotLimits | None:
    if limits is None:
        return None
    if axis == "secondary":
        return PlotLimits(
            limits.x_min,
            limits.x_max,
            limits.y2_min,
            limits.y2_max,
        )
    return PlotLimits(
        limits.x_min,
        limits.x_max,
        limits.y_min,
        limits.y_max,
    )


def _existing_plot_names(output: Path) -> set[str]:
    if not output.is_dir():
        return set()
    suffixes = {".png", ".svg", ".pdf"}
    return {
        path.stem.casefold()
        for path in output.iterdir()
        if path.suffix.casefold() in suffixes
    }


def export_bundle(
    plots: Sequence[PlotExport],
    root: str | Path,
    scheme: str = DEFAULT_PLOT_SCHEME,
    limits: PlotLimits | None = None,
    sizes: Sequence[PlotSize | None] | None = None,
    appearance: PlotAppearance | None = None,
) -> list[Path]:
    """Export result data and put each plot in its corresponding analysis directory."""

    plans = tuple(plots)
    if not plans:
        raise ConfigurationError("At least one plot is required for result export.")
    entries: dict[
        tuple[str, str],
        tuple[ResultExport, PlotModel, SourceAxis, PlotSize | None],
    ] = {}
    plan_sizes = _plot_sizes(plans, sizes)
    for plot, size in zip(plans, plan_sizes, strict=True):
        item_models = plot.item_models or tuple(
            _source_plot(item.result, None, None, None, None) for item in plot.items
        )
        source_axes = plot.source_axes or tuple(
            _source_axis(plot.model, item_model) for item_model in item_models
        )
        if len(item_models) != len(plot.items):
            raise ConfigurationError(
                "Standalone plot models must match the number of export items."
            )
        if len(source_axes) != len(plot.items):
            raise ConfigurationError(
                "Source plot axes must match the number of export items."
            )
        for item, model, axis in zip(
            plot.items,
            item_models,
            source_axes,
            strict=True,
        ):
            key = (item.result.analysis_id, item.name)
            entries.setdefault(key, (item, model, axis, size))
    unique_items = tuple(entry[0] for entry in entries.values())
    outputs = export_directories(Path(root).expanduser().resolve(), unique_items)
    paths: list[Path] = []
    for item, output in zip(unique_items, outputs, strict=True):
        paths.extend(export_result(item.result, output, include_figures=False))
    for entry, output in zip(entries.values(), outputs, strict=True):
        _item, model, axis, size = entry
        paths.extend(
            export_plot_model(
                model,
                output,
                output.name,
                scheme,
                _item_limits(axis, limits),
                size,
                appearance,
            )
        )
    return paths


def save_plots(
    plots: Sequence[PlotExport],
    output: str | Path,
    scheme: str = DEFAULT_PLOT_SCHEME,
    limits: PlotLimits | None = None,
    sizes: Sequence[PlotSize | None] | None = None,
    appearance: PlotAppearance | None = None,
) -> list[Path]:
    """Save every plot directly under one directory with its readable name."""

    plans = tuple(plots)
    if not plans:
        raise ConfigurationError("At least one plot is required for figure export.")
    destination = Path(output).expanduser().resolve()
    reserved = _existing_plot_names(destination)
    paths: list[Path] = []
    for plot, size in zip(plans, _plot_sizes(plans, sizes), strict=True):
        name = _unique_name(plot.name, reserved)
        paths.extend(
            export_plot_model(
                plot.model,
                destination,
                name,
                scheme,
                limits,
                size,
                appearance,
            )
        )
    return paths
