"""Render backend-neutral plot models on Matplotlib-compatible axes."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

from ..errors import ConfigurationError
from .appearance import (
    CATEGORY_COLOR_IDS,
    DEFAULT_PLOT_SCHEME,
    SECONDARY_COLOR_FACTOR,
    PlotAppearance,
    plot_color,
    plot_legend_location,
    plot_scheme,
)
from .models import PlotModel, PlotSeries
from .state import PlotLimits


def _series_color_key(series: PlotSeries, method: str) -> str:
    if method == "residue_name":
        return series.residue_name_key or series.color_key or series.label
    raise ConfigurationError(f"Unknown categorical coloring method: {method!r}.")


def draw_plot(
    axis: object,
    model: PlotModel,
    scheme: str = DEFAULT_PLOT_SCHEME,
    limits: PlotLimits | None = None,
    appearance: PlotAppearance | None = None,
) -> None:
    """Render a plot model with a consistent publication style."""

    selected_limits = limits or PlotLimits()
    selected_limits.validate()
    selected_appearance = appearance or PlotAppearance()
    selected_appearance.validate()
    auto_x = _common_x_range(model)
    x_range = _x_range(auto_x, selected_limits)
    method = plot_scheme(scheme)
    labels: dict[str, int] = {}
    if method.key != "fixed":
        for series in model.series:
            key = _series_color_key(series, method.key)
            if key not in labels:
                labels[key] = len(labels)
    secondary = [series for series in model.series if series.axis == "secondary"]
    secondary_axis = axis.twinx() if secondary else None  # type: ignore[attr-defined]
    if secondary_axis is not None:
        # twinx shares the radial-distance coordinate but owns an independent
        # Y scale. Keep its patch transparent so it cannot cover RDF lines.
        secondary_axis.patch.set_visible(False)
        secondary_axis.set_zorder(axis.get_zorder())  # type: ignore[attr-defined]
    visible_y: dict[str, list[float]] = {"primary": [], "secondary": []}
    for series in model.series:
        if method.key == "fixed":
            color = plot_color(series.color_id).value
        else:
            key = _series_color_key(series, method.key)
            color_index = labels[key]
            color_id = CATEGORY_COLOR_IDS[color_index % len(CATEGORY_COLOR_IDS)]
            color = plot_color(color_id).value
        if series.axis == "secondary":
            color = _shade(color, SECONDARY_COLOR_FACTOR)
        target_axis: Any = secondary_axis if series.axis == "secondary" else axis
        assert target_axis is not None
        x, y, _y_error = _visible_values(series, x_range)
        visible_y[series.axis].extend(y)
        if model.kind == "line":
            target_axis.plot(
                x,
                y,
                color=color,
                label=_legend_text(series),
                linestyle="--" if series.axis == "secondary" else "-",
                linewidth=(
                    selected_appearance.line_width * 0.9
                    if series.axis == "secondary"
                    else selected_appearance.line_width
                ),
            )
        elif model.kind == "step":
            target_axis.step(
                x,
                y,
                where="mid",
                color=color,
                label=_legend_text(series),
                linewidth=selected_appearance.line_width,
            )
            target_axis.scatter(
                x,
                y,
                color=color,
                edgecolors="white",
                linewidths=0.5,
                s=24,
                zorder=3,
            )
        else:
            raise ConfigurationError(f"Unknown plot kind: {model.kind}")
    if model.reference_y is not None:
        axis.axhline(  # type: ignore[attr-defined]
            model.reference_y,
            color="#666666",
            linewidth=selected_appearance.line_width * 0.5,
            linestyle="-",
            alpha=0.3,
            zorder=0,
        )
    axis.set_xlabel(  # type: ignore[attr-defined]
        model.x_label,
        fontsize=selected_appearance.label_font_size,
    )
    axis.set_ylabel(  # type: ignore[attr-defined]
        model.y_label,
        fontsize=selected_appearance.label_font_size,
    )
    if secondary_axis is not None and model.secondary_y_label is not None:
        secondary_axis.set_ylabel(
            model.secondary_y_label,
            fontsize=selected_appearance.label_font_size,
        )
        secondary_axis.tick_params(
            axis="y",
            colors="#202020",
            labelsize=selected_appearance.tick_font_size,
        )
    axis.set_title(  # type: ignore[attr-defined]
        model.title,
        fontsize=selected_appearance.title_font_size,
        fontweight="normal",
        pad=10,
        wrap=True,
    )
    axis.set_axisbelow(True)  # type: ignore[attr-defined]
    axis.tick_params(  # type: ignore[attr-defined]
        axis="both",
        labelsize=selected_appearance.tick_font_size,
    )
    if selected_appearance.grid_visible:
        axis.grid(  # type: ignore[attr-defined]
            True,
            which="both",
            color="#b0b0b0",
            linestyle=":",
            linewidth=0.8,
            alpha=0.5,
        )
    else:
        axis.grid(False)  # type: ignore[attr-defined]
    if x_range is not None:
        axis.set_xlim(*x_range)  # type: ignore[attr-defined]
    elif selected_limits.x_min is not None or selected_limits.x_max is not None:
        axis.set_xlim(  # type: ignore[attr-defined]
            left=selected_limits.x_min,
            right=selected_limits.x_max,
        )
    if model.domain == "radial_distance":
        primary_values = visible_y["primary"]
        if model.reference_y is not None:
            primary_values.append(model.reference_y)
        axis.set_ylim(0, _positive_top(primary_values))  # type: ignore[attr-defined]
        if secondary_axis is not None:
            secondary_axis.set_ylim(0, _positive_top(visible_y["secondary"]))
    if selected_limits.y_min is not None or selected_limits.y_max is not None:
        axis.set_ylim(  # type: ignore[attr-defined]
            bottom=selected_limits.y_min,
            top=selected_limits.y_max,
        )
    if secondary_axis is not None and (
        selected_limits.y2_min is not None or selected_limits.y2_max is not None
    ):
        secondary_axis.set_ylim(
            bottom=selected_limits.y2_min,
            top=selected_limits.y2_max,
        )
    if model.series and selected_appearance.legend_visible:
        handles, legend_labels = axis.get_legend_handles_labels()  # type: ignore[attr-defined]
        if secondary_axis is not None:
            secondary_handles, secondary_labels = (
                secondary_axis.get_legend_handles_labels()
            )
            handles += secondary_handles
            legend_labels += secondary_labels
        legend = axis.legend(  # type: ignore[attr-defined]
            handles,
            legend_labels,
            frameon=True,
            fancybox=False,
            framealpha=0.96,
            facecolor="white",
            edgecolor="#a8a8a8",
            loc=plot_legend_location(selected_appearance.legend_location).value,
            fontsize=selected_appearance.legend_font_size,
            handlelength=2.6,
            handletextpad=0.7,
            borderpad=0.55,
            labelspacing=0.4,
        )
        legend.get_frame().set_linewidth(0.7)
        legend.set_zorder(10)


def _legend_text(series: PlotSeries) -> str:
    return " ".join(part for part in (series.quantity, series.label) if part)


def _shade(color: str, factor: float) -> str:
    value = color.removeprefix("#")
    if len(value) != 6:
        raise ConfigurationError(f"Plot color must use six-digit hexadecimal form: {color}")
    try:
        channels = tuple(int(value[offset : offset + 2], 16) for offset in (0, 2, 4))
    except ValueError as exc:
        raise ConfigurationError(f"Plot color is invalid: {color}") from exc
    scaled = (round(channel * factor) for channel in channels)
    return "#" + "".join(f"{channel:02x}" for channel in scaled)


def _common_x_range(model: PlotModel) -> tuple[float, float] | None:
    if model.domain != "radial_distance" or not model.series:
        return None
    ranges: list[tuple[float, float]] = []
    for series in model.series:
        values = [float(value) for value in series.x if isinstance(value, (int, float))]
        if len(values) != len(series.x) or not values:
            return None
        ranges.append((min(values), max(values)))
    lower = max(value[0] for value in ranges)
    upper = min(value[1] for value in ranges)
    if lower >= upper:
        return None
    return (min(0.0, lower), upper)


def _x_range(
    automatic: tuple[float, float] | None,
    limits: PlotLimits,
) -> tuple[float, float] | None:
    if automatic is None:
        if limits.x_min is None or limits.x_max is None:
            return None
        return (limits.x_min, limits.x_max)
    left = automatic[0] if limits.x_min is None else limits.x_min
    right = automatic[1] if limits.x_max is None else limits.x_max
    return (left, right)


def _visible_values(
    series: PlotSeries,
    x_range: tuple[float, float] | None,
) -> tuple[tuple[float | str, ...], tuple[float, ...], tuple[float, ...] | None]:
    if x_range is None:
        return series.x, series.y, series.y_error
    selected = tuple(
        index
        for index, value in enumerate(series.x)
        if isinstance(value, (int, float)) and x_range[0] <= float(value) <= x_range[1]
    )
    x = tuple(series.x[index] for index in selected)
    y = tuple(series.y[index] for index in selected)
    error = (
        None
        if series.y_error is None
        else tuple(series.y_error[index] for index in selected)
    )
    return x, y, error


def _positive_top(values: Sequence[float]) -> float:
    maximum = max((value for value in values if math.isfinite(value)), default=0.0)
    return 1.0 if maximum <= 0.0 else maximum * 1.05
