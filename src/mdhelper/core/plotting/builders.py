"""Build backend-neutral plot models from analysis results."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from typing import Literal

from ..analysis import AnalysisRequest, AnalysisResult, RadialRequest, analysis_label
from ..errors import ConfigurationError
from ..units import convert_distance
from .appearance import plot_color
from .models import PlotModel, PlotSeries
from .state import validate_plot_title


def _numbers(value: object, field: str) -> tuple[float, ...]:
    if not isinstance(value, (list, tuple)):
        raise ConfigurationError(f"Plot field {field!r} must be an array.")
    try:
        return tuple(float(item) for item in value)
    except (TypeError, ValueError) as exc:
        raise ConfigurationError(f"Plot field {field!r} must contain numbers.") from exc


def _selection_label(request: RadialRequest) -> str:
    selection = request.selection
    return f"{request.reference}-{selection}" if selection else request.reference


def _category_key(value: object, fallback: str) -> str:
    if not isinstance(value, list) or not value:
        return fallback
    names = sorted({item for item in value if isinstance(item, str) and item})
    return "|".join(names) or fallback


def _selection_residue_key(
    result: AnalysisResult,
    role: str,
    fallback: str,
) -> str:
    resolutions = result.diagnostics.get("selection_resolution")
    record = resolutions.get(role) if isinstance(resolutions, dict) else None
    if not isinstance(record, dict):
        return fallback
    return _category_key(record.get("residue_names"), fallback)


def result_plot(result: AnalysisResult) -> PlotModel:
    """Create the most useful default plot for a completed result."""

    request = AnalysisRequest.from_dict(result.request)
    radial_request = request if isinstance(request, RadialRequest) else None
    if result.analysis_type == "rdf":
        if radial_request is None:
            raise ConfigurationError("RDF plotting requires a radial request.")
        selection = _selection_label(radial_request)
        residue_key = _selection_residue_key(
            result, "selection", radial_request.selection
        )
        x = convert_distance(
            _numbers(result.data.get("radius_nm"), "radius_nm"),
            "nm",
            "angstrom",
        )
        y = _numbers(result.data.get("g_r"), "g_r")
        if len(x) != len(y):
            raise ConfigurationError("RDF radius and g(r) arrays have different lengths.")
        return PlotModel(
            "line",
            (
                PlotSeries(
                    x,
                    y,
                    selection,
                    None,
                    "g(r)",
                    color_key=selection,
                    residue_name_key=residue_key,
                ),
            ),
            r"$r$ ($\mathrm{\AA}$)",
            r"$g(r)$",
            "Radial distribution function",
            reference_y=1.0,
            domain="radial_distance",
            axis_order=0,
            combined_title=f"RDF and {analysis_label('cumulative_rdf')}",
        )
    if result.analysis_type == "cumulative_rdf":
        if radial_request is None:
            raise ConfigurationError("Cumulative RDF plotting requires a radial request.")
        selection = _selection_label(radial_request)
        residue_key = _selection_residue_key(
            result, "selection", radial_request.selection
        )
        x = convert_distance(
            _numbers(result.data.get("radius_nm"), "radius_nm"),
            "nm",
            "angstrom",
        )
        y = _numbers(result.data.get("cumulative_number"), "cumulative_number")
        if len(x) != len(y):
            raise ConfigurationError(
                "Cumulative RDF radius and cumulative-number arrays have different lengths."
            )
        return PlotModel(
            "line",
            (
                PlotSeries(
                    x,
                    y,
                    selection,
                    None,
                    "Cumulative RDF",
                    color_key=selection,
                    residue_name_key=residue_key,
                ),
            ),
            r"$r$ ($\mathrm{\AA}$)",
            "number",
            analysis_label("cumulative_rdf"),
            domain="radial_distance",
            axis_order=1,
            combined_title=f"RDF and {analysis_label('cumulative_rdf')}",
        )
    if result.analysis_type == "energy":
        x = _numbers(result.data.get("time_ps"), "time_ps")
        values = result.data.get("series")
        if not isinstance(values, dict) or not values:
            raise ConfigurationError("Energy plotting requires numeric series.")
        energy_series = tuple(
            PlotSeries(
                x,
                _numbers(raw, f"series.{name}"),
                str(name),
                color_key=str(name),
                residue_name_key=str(name),
            )
            for name, raw in values.items()
        )
        if any(len(item.x) != len(item.y) for item in energy_series):
            raise ConfigurationError("Energy time and value arrays have different lengths.")
        return PlotModel(
            "line",
            energy_series,
            "Time (ps)",
            result.units.get("series", "Value"),
            "Energy Analysis",
            domain="time",
            combined_title="Energy Analysis",
        )
    raise ConfigurationError(f"No plot model is defined for {result.analysis_type!r}.")


def results_plot(
    results: Sequence[AnalysisResult],
    labels: Sequence[str | None] | None = None,
    color_ids: Sequence[int] | None = None,
) -> PlotModel:
    """Combine compatible results into one labelled plot."""

    plots = results_plots(results, labels, color_ids)
    if len(plots) != 1:
        raise ConfigurationError(
            "Results with different axes require a multi-panel figure."
        )
    return plots[0]


def results_plots(
    results: Sequence[AnalysisResult],
    labels: Sequence[str | None] | None = None,
    color_ids: Sequence[int] | None = None,
    series_keys: Sequence[str | None] | None = None,
    group_ids: Sequence[str | None] | None = None,
    titles: Sequence[str | None] | None = None,
) -> tuple[PlotModel, ...]:
    """Group arbitrary results into compatible panels in one figure."""

    if not results:
        raise ConfigurationError("At least one result is required for plotting.")
    if labels is not None and len(labels) != len(results):
        raise ConfigurationError("Plot labels must match the number of results.")
    if color_ids is not None and len(color_ids) != len(results):
        raise ConfigurationError("Plot color IDs must match the number of results.")
    if series_keys is not None and len(series_keys) != len(results):
        raise ConfigurationError("Plot series keys must match the number of results.")
    if group_ids is not None and len(group_ids) != len(results):
        raise ConfigurationError("Plot group IDs must match the number of results.")
    if titles is not None and len(titles) != len(results):
        raise ConfigurationError("Plot titles must match the number of results.")
    groups: list[
        tuple[
            tuple[object, ...],
            list[tuple[PlotModel, str | None, int | None, str, int]],
        ]
    ] = []
    positions: dict[tuple[object, ...], int] = {}
    for index, result in enumerate(results):
        source = result_plot(result)
        series_key = None if series_keys is None else series_keys[index]
        models = _selected_models(source, result.analysis_type, series_key)
        custom = None if labels is None else labels[index]
        color_id = None if color_ids is None else color_ids[index]
        group_id = None if group_ids is None else group_ids[index]
        raw_title = None if titles is None else titles[index]
        title = "" if raw_title is None else raw_title
        validate_plot_title(title)
        if color_id is not None:
            plot_color(color_id)
        for model_index, model in enumerate(models):
            if group_id:
                key = ("explicit", group_id, *_plot_key(model))
            elif result.analysis_type == "energy":
                key = ("energy", index, model_index)
            else:
                key = ("automatic", *_plot_key(model))
            if key not in positions:
                positions[key] = len(groups)
                groups.append((key, []))
            groups[positions[key]][1].append((model, custom, color_id, title, index))
    return tuple(_combine_models(items) for _key, items in groups)


def _selected_models(
    model: PlotModel,
    analysis_type: str,
    series_key: str | None,
) -> tuple[PlotModel, ...]:
    if series_key:
        selected = tuple(series for series in model.series if series.label == series_key)
        if len(selected) != 1:
            raise ConfigurationError(f"Plot series {series_key!r} is not available.")
        return (replace(model, series=selected, title=_series_title(model, selected[0])),)
    if analysis_type != "energy":
        return (model,)
    return tuple(
        replace(model, series=(series,), title=_series_title(model, series))
        for series in model.series
    )


def _series_title(model: PlotModel, series: PlotSeries) -> str:
    return f"{model.title}: {series.label}"


def _plot_key(model: PlotModel) -> tuple[object, ...]:
    if model.domain:
        return (model.kind, model.domain, model.x_label)
    return (
        model.kind,
        model.x_label,
        model.y_label,
        model.secondary_y_label,
        model.title,
        model.reference_y,
    )


def _combine_models(
    items: Sequence[tuple[PlotModel, str | None, int | None, str, int]],
) -> PlotModel:
    base = min(
        (model for model, _custom, _color, _title, _index in items),
        key=lambda model: model.axis_order,
    )
    y_labels = {model.y_label for model, _custom, _color, _title, _index in items}
    secondary_label = next(
        (
            model.y_label
            for model, _custom, _color, _title, _index in items
            if model.y_label != base.y_label
        ),
        None,
    )

    combined: list[PlotSeries] = []
    for model, custom, color_id, _title, _index in items:
        shared_label = len({series.label for series in model.series}) == 1
        for series in model.series:
            label = series.label
            if custom:
                label = custom if shared_label else f"{custom}: {series.label}"
            axis: Literal["primary", "secondary"] = (
                "primary" if model.y_label == base.y_label else "secondary"
            )
            combined.append(
                replace(
                    series,
                    label=label,
                    axis=axis,
                    color_id=series.color_id if color_id is None else color_id,
                )
            )

    counts: dict[tuple[str, str, str], int] = {}
    unique: list[PlotSeries] = []
    for series in combined:
        key = (series.axis, series.quantity, series.label)
        count = counts.get(key, 0) + 1
        counts[key] = count
        label = series.label if count == 1 else f"{series.label} ({count})"
        unique.append(replace(series, label=label))
    default_title = (
        base.title
        if len({model.title for model, _custom, _color, _title, _index in items}) == 1
        else base.combined_title or base.title
    )
    title = next(
        (
            title
            for _model, _custom, _color, title, _index in items
            if title
        ),
        default_title,
    )
    return replace(
        base,
        series=tuple(unique),
        title=title,
        secondary_y_label=secondary_label if len(y_labels) > 1 else None,
        source_indices=tuple(dict.fromkeys(index for *_item, index in items)),
    )
