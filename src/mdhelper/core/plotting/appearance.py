"""Plot appearance contracts and shared value catalogs."""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..errors import ConfigurationError

DEFAULT_PLOT_SCHEME = "residue_name"
DEFAULT_LEGEND_LOCATION = "upper_left"
SECONDARY_COLOR_FACTOR = 0.5
MIN_PLOT_LINE_WIDTH = 0.1
MAX_PLOT_LINE_WIDTH = 10.0
MIN_PLOT_FONT_SIZE = 6.0
MAX_PLOT_FONT_SIZE = 48.0


@dataclass(frozen=True)
class PlotScheme:
    """A reusable coloring method exposed to presentation adapters."""

    key: str
    label: str


@dataclass(frozen=True)
class PlotColor:
    """One indexed color shared by categorical and fixed coloring."""

    color_id: int
    label: str
    value: str


@dataclass(frozen=True)
class PlotLegendLocation:
    """One supported legend placement with a presentation label."""

    key: str
    label: str
    value: str


@dataclass(frozen=True)
class PlotAppearance:
    """User-selected presentation settings shared by previews and exports."""

    legend_visible: bool = True
    legend_location: str = DEFAULT_LEGEND_LOCATION
    grid_visible: bool = True
    line_width: float = 2.0
    title_font_size: float = 14.0
    label_font_size: float = 12.0
    tick_font_size: float = 10.0
    legend_font_size: float = 9.0

    def validate(self) -> None:
        if type(self.legend_visible) is not bool:
            raise ConfigurationError("Plot legend visibility must be true or false.")
        if type(self.grid_visible) is not bool:
            raise ConfigurationError("Plot grid visibility must be true or false.")
        plot_legend_location(self.legend_location)
        _validate_plot_number(
            self.line_width,
            "line width",
            MIN_PLOT_LINE_WIDTH,
            MAX_PLOT_LINE_WIDTH,
        )
        for name, value in (
            ("title font size", self.title_font_size),
            ("axis label font size", self.label_font_size),
            ("tick font size", self.tick_font_size),
            ("legend font size", self.legend_font_size),
        ):
            _validate_plot_number(value, name, MIN_PLOT_FONT_SIZE, MAX_PLOT_FONT_SIZE)

    def to_dict(self) -> dict[str, object]:
        self.validate()
        return {
            "legend_visible": self.legend_visible,
            "legend_location": self.legend_location,
            "grid_visible": self.grid_visible,
            "line_width": self.line_width,
            "title_font_size": self.title_font_size,
            "label_font_size": self.label_font_size,
            "tick_font_size": self.tick_font_size,
            "legend_font_size": self.legend_font_size,
        }

    @classmethod
    def from_dict(cls, value: object) -> PlotAppearance:
        if not isinstance(value, dict):
            raise ConfigurationError("Plot appearance must be an object.")
        expected = {
            "legend_visible",
            "legend_location",
            "grid_visible",
            "line_width",
            "title_font_size",
            "label_font_size",
            "tick_font_size",
            "legend_font_size",
        }
        if set(value) != expected:
            raise ConfigurationError("Plot appearance contains missing or unknown fields.")
        try:
            appearance = cls(**dict(value))
        except TypeError as exc:
            raise ConfigurationError("Plot appearance is invalid.") from exc
        appearance.validate()
        return appearance


PLOT_SCHEMES = (
    PlotScheme("residue_name", "Residue name"),
    PlotScheme("fixed", "Fixed color"),
)

PLOT_COLORS = (
    PlotColor(0, "Blue", "#4040ff"),
    PlotColor(1, "Red", "#ff0000"),
    PlotColor(2, "Gray", "#595959"),
    PlotColor(3, "Orange", "#cc8033"),
    PlotColor(4, "Yellow", "#cccc00"),
    PlotColor(5, "Tan", "#808033"),
    PlotColor(6, "Silver", "#999999"),
    PlotColor(7, "Green", "#33b333"),
    PlotColor(8, "White", "#ffffff"),
    PlotColor(9, "Pink", "#ff9999"),
    PlotColor(10, "Cyan", "#40bfbf"),
    PlotColor(11, "Purple", "#a64da6"),
    PlotColor(12, "Lime", "#80e666"),
    PlotColor(13, "Mauve", "#e666b3"),
    PlotColor(14, "Ochre", "#804d00"),
    PlotColor(15, "Ice blue", "#80bfbf"),
    PlotColor(16, "Black", "#000000"),
)

PLOT_LEGEND_LOCATIONS = (
    PlotLegendLocation("best", "Best fit", "best"),
    PlotLegendLocation("upper_left", "Upper left", "upper left"),
    PlotLegendLocation("upper_right", "Upper right", "upper right"),
    PlotLegendLocation("lower_left", "Lower left", "lower left"),
    PlotLegendLocation("lower_right", "Lower right", "lower right"),
    PlotLegendLocation("center_left", "Center left", "center left"),
    PlotLegendLocation("center_right", "Center right", "center right"),
)

CATEGORY_COLOR_IDS = (0, 1, 2, 3, 4, 5, 6, 7, 9, 10, 11, 12, 13, 14, 15, 16, 8)

_SCHEME_MAP = {scheme.key: scheme for scheme in PLOT_SCHEMES}
_COLOR_MAP = {color.color_id: color for color in PLOT_COLORS}
_LEGEND_LOCATION_MAP = {
    location.key: location for location in PLOT_LEGEND_LOCATIONS
}


def plot_scheme(key: str) -> PlotScheme:
    try:
        return _SCHEME_MAP[key]
    except KeyError as exc:
        raise ConfigurationError(f"Unknown plot color scheme: {key!r}.") from exc


def plot_legend_location(key: str) -> PlotLegendLocation:
    try:
        return _LEGEND_LOCATION_MAP[key]
    except (KeyError, TypeError) as exc:
        raise ConfigurationError(f"Unknown plot legend location: {key!r}.") from exc


def plot_color(color_id: int) -> PlotColor:
    if type(color_id) is not int:
        raise ConfigurationError("A plot color ID must be an integer.")
    try:
        return _COLOR_MAP[color_id]
    except KeyError as exc:
        raise ConfigurationError(f"Unknown plot color ID: {color_id!r}.") from exc


def _validate_plot_number(
    value: object,
    name: str,
    minimum: float,
    maximum: float,
) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not minimum <= value <= maximum
    ):
        raise ConfigurationError(
            f"Plot {name} must be between {minimum:g} and {maximum:g}."
        )
