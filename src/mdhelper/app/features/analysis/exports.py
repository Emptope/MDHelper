"""Result and figure export feature."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from mdhelper.core.analysis import AnalysisResult
from mdhelper.core.errors import ConfigurationError
from mdhelper.core.plotting import (
    DEFAULT_PLOT_SCHEME,
    PlotAppearance,
    PlotLimits,
    PlotModel,
    PlotSize,
)
from mdhelper.io.export import (
    export_comparison_figures,
    export_figures,
    export_plot_model,
    export_result,
)

from .plans import (
    PlotExport,
    ResultExport,
    SourceAxis,
    _source_axis,
    _source_plot,
    _unique_name,
    export_directories,
)


class ExportFeature:
    def export(
        self,
        result: AnalysisResult,
        output_directory: str | Path,
        include_figures: bool = True,
        scheme: str = DEFAULT_PLOT_SCHEME,
        limits: PlotLimits | None = None,
        size: PlotSize | None = None,
        appearance: PlotAppearance | None = None,
    ) -> list[Path]:
        paths = export_result(result, output_directory)
        if include_figures:
            paths.extend(
                export_figures(
                    result,
                    output_directory,
                    scheme=scheme,
                    limits=limits,
                    size=size,
                    appearance=appearance,
                )
            )
        return paths

    def export_figures(
        self,
        result: AnalysisResult,
        output_directory: str | Path,
        stem: str | None = None,
        scheme: str = DEFAULT_PLOT_SCHEME,
        limits: PlotLimits | None = None,
        size: PlotSize | None = None,
        appearance: PlotAppearance | None = None,
    ) -> list[Path]:
        return export_figures(
            result,
            output_directory,
            stem,
            scheme,
            limits,
            size,
            appearance,
        )

    def export_comparison_figures(
        self,
        results: Sequence[AnalysisResult],
        output_directory: str | Path,
        stem: str = "comparison",
        labels: Sequence[str | None] | None = None,
        color_ids: Sequence[int] | None = None,
        series_keys: Sequence[str | None] | None = None,
        group_ids: Sequence[str | None] | None = None,
        titles: Sequence[str | None] | None = None,
        scheme: str = DEFAULT_PLOT_SCHEME,
        limits: PlotLimits | None = None,
        size: PlotSize | None = None,
        appearance: PlotAppearance | None = None,
    ) -> list[Path]:
        return export_comparison_figures(
            results,
            output_directory,
            stem,
            labels,
            color_ids,
            series_keys,
            group_ids,
            titles,
            scheme,
            limits,
            size,
            appearance,
        )

    def export_plot_model(
        self,
        model: PlotModel,
        output_directory: str | Path,
        stem: str,
        scheme: str = DEFAULT_PLOT_SCHEME,
        limits: PlotLimits | None = None,
        size: PlotSize | None = None,
        appearance: PlotAppearance | None = None,
    ) -> list[Path]:
        return export_plot_model(
            model,
            output_directory,
            stem,
            scheme,
            limits,
            size,
            appearance,
        )

    def export_bundle(
        self,
        plots: Sequence[PlotExport],
        output_directory: str | Path,
        scheme: str = DEFAULT_PLOT_SCHEME,
        limits: PlotLimits | None = None,
        sizes: Sequence[PlotSize | None] | None = None,
        appearance: PlotAppearance | None = None,
    ) -> list[Path]:
        return export_bundle(
            plots,
            output_directory,
            scheme,
            limits,
            sizes,
            appearance,
        )

    def save_plots(
        self,
        plots: Sequence[PlotExport],
        output_directory: str | Path,
        scheme: str = DEFAULT_PLOT_SCHEME,
        limits: PlotLimits | None = None,
        sizes: Sequence[PlotSize | None] | None = None,
        appearance: PlotAppearance | None = None,
    ) -> list[Path]:
        return save_plots(
            plots,
            output_directory,
            scheme,
            limits,
            sizes,
            appearance,
        )


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
        paths.extend(export_result(item.result, output))
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
