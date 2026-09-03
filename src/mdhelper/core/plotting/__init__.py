"""Backend-neutral plotting API."""

from .appearance import (
    DEFAULT_LEGEND_LOCATION,
    DEFAULT_PLOT_SCHEME,
    MAX_PLOT_FONT_SIZE,
    MAX_PLOT_LINE_WIDTH,
    MIN_PLOT_FONT_SIZE,
    MIN_PLOT_LINE_WIDTH,
    PLOT_COLORS,
    PLOT_LEGEND_LOCATIONS,
    PLOT_SCHEMES,
    PlotAppearance,
    PlotColor,
    PlotLegendLocation,
    PlotScheme,
    plot_color,
    plot_legend_location,
    plot_scheme,
)
from .builders import result_plot, results_plot, results_plots
from .models import DEFAULT_PLOT_SIZE, PlotModel, PlotSeries, PlotSize
from .rendering import draw_plot
from .state import MAX_PLOT_TITLE_LENGTH, PlotLimits, PlotSelection, PlotState

__all__ = [
    "DEFAULT_LEGEND_LOCATION",
    "DEFAULT_PLOT_SCHEME",
    "DEFAULT_PLOT_SIZE",
    "MAX_PLOT_FONT_SIZE",
    "MAX_PLOT_LINE_WIDTH",
    "MAX_PLOT_TITLE_LENGTH",
    "MIN_PLOT_FONT_SIZE",
    "MIN_PLOT_LINE_WIDTH",
    "PLOT_COLORS",
    "PLOT_LEGEND_LOCATIONS",
    "PLOT_SCHEMES",
    "PlotAppearance",
    "PlotColor",
    "PlotLegendLocation",
    "PlotLimits",
    "PlotModel",
    "PlotScheme",
    "PlotSelection",
    "PlotSeries",
    "PlotSize",
    "PlotState",
    "draw_plot",
    "plot_color",
    "plot_legend_location",
    "plot_scheme",
    "result_plot",
    "results_plot",
    "results_plots",
]
