"""Matplotlib figure export."""

from __future__ import annotations

import os
from collections.abc import Sequence
from functools import cache
from pathlib import Path
from typing import Any

from mdhelper.core.analysis import AnalysisResult
from mdhelper.core.errors import BackendError
from mdhelper.core.plotting import (
    DEFAULT_PLOT_SCHEME,
    DEFAULT_PLOT_SIZE,
    PlotAppearance,
    PlotLimits,
    PlotModel,
    PlotSize,
    draw_plot,
    results_plots,
)

from .paths import output_directory

_FIGURE_STYLE = {
    "font.family": "sans-serif",
    "font.size": 10.0,
    "axes.labelsize": 10.0,
    "axes.titlesize": 12.0,
    "xtick.labelsize": 9.0,
    "ytick.labelsize": 9.0,
    "savefig.facecolor": "white",
    "savefig.edgecolor": "white",
}


def export_figures(
    result: AnalysisResult,
    destination: str | Path,
    stem: str | None = None,
    scheme: str = DEFAULT_PLOT_SCHEME,
    limits: PlotLimits | None = None,
    size: PlotSize | None = None,
    appearance: PlotAppearance | None = None,
) -> list[Path]:
    """Export only plot files, optionally under a result-specific filename."""

    return _write_figures(
        (result,),
        output_directory(destination),
        stem,
        scheme=scheme,
        limits=limits,
        size=size,
        appearance=appearance,
    )


def export_plot_model(
    model: PlotModel,
    destination: str | Path,
    stem: str,
    scheme: str = DEFAULT_PLOT_SCHEME,
    limits: PlotLimits | None = None,
    size: PlotSize | None = None,
    appearance: PlotAppearance | None = None,
) -> list[Path]:
    """Export one prepared plot model without changing its grouping or labels."""

    matplotlib, _figure_type, _canvas_type = _load_matplotlib()
    output = output_directory(destination)
    panel_size = DEFAULT_PLOT_SIZE if size is None else size
    panel_size.validate()
    with matplotlib.rc_context(_FIGURE_STYLE):
        figure = _figure(panel_size)
        axis = figure.add_subplot(1, 1, 1)
        axis.set_facecolor("white")
        draw_plot(axis, model, scheme, limits, appearance)
        try:
            return _save_figure(figure, output, _safe_stem(stem))
        finally:
            figure.clear()


def _safe_stem(value: str) -> str:
    stem = "".join(
        character if character.isalnum() or character in "-_." else "_"
        for character in value
    )
    return stem.strip("._") or "analysis"


@cache
def _load_matplotlib() -> tuple[Any, Any, Any]:
    try:
        import matplotlib
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        from matplotlib.figure import Figure
    except ImportError as exc:
        raise BackendError("Matplotlib is required for figure export.") from exc
    return matplotlib, Figure, FigureCanvasAgg


def _figure(size: PlotSize, panels: int = 1) -> Any:
    _matplotlib, figure_type, canvas_type = _load_matplotlib()
    figure = figure_type(
        figsize=(size.width, size.height * panels),
        constrained_layout=True,
    )
    canvas_type(figure)
    figure.set_facecolor("white")
    return figure


def _save_figure(figure: Any, output: Path, filename: str) -> list[Path]:
    paths: list[Path] = []
    temporary: Path | None = None
    try:
        figure.draw_without_rendering()
        figure.set_layout_engine("none")
        for suffix in ("png", "svg", "pdf"):
            path = output / f"{filename}.{suffix}"
            temporary = path.with_name(f".{path.name}.tmp")
            figure.savefig(
                temporary,
                dpi=300 if suffix == "png" else None,
                format=suffix,
            )
            os.replace(temporary, path)
            paths.append(path)
    except OSError as exc:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise BackendError(
            f"Could not export analysis figure to {output}.",
            details={"exception": f"{type(exc).__name__}: {exc}"},
        ) from exc
    return paths


def _write_figures(
    results: Sequence[AnalysisResult],
    output: Path,
    stem: str | None = None,
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
    matplotlib, _figure_type, _canvas_type = _load_matplotlib()
    filename = _safe_stem(results[0].analysis_type if stem is None else stem)
    with matplotlib.rc_context(_FIGURE_STYLE):
        models = results_plots(
            results,
            labels,
            color_ids,
            series_keys,
            group_ids,
            titles,
        )
        panel_size = DEFAULT_PLOT_SIZE if size is None else size
        panel_size.validate()
        figure = _figure(panel_size, len(models))
        for index, model in enumerate(models, start=1):
            axis = figure.add_subplot(len(models), 1, index)
            axis.set_facecolor("white")
            draw_plot(axis, model, scheme, limits, appearance)
        try:
            return _save_figure(figure, output, filename)
        finally:
            figure.clear()
