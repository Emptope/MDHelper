"""Persisted plot selection and axis state contracts."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..errors import ConfigurationError
from .appearance import DEFAULT_PLOT_SCHEME, PlotAppearance, plot_color, plot_scheme

MAX_PLOT_TITLE_LENGTH = 120


@dataclass(frozen=True)
class PlotLimits:
    """Optional user-selected axis bounds; omitted values remain automatic."""

    x_min: float | None = None
    x_max: float | None = None
    y_min: float | None = None
    y_max: float | None = None
    y2_min: float | None = None
    y2_max: float | None = None

    def validate(self) -> None:
        values = (
            self.x_min,
            self.x_max,
            self.y_min,
            self.y_max,
            self.y2_min,
            self.y2_max,
        )
        if any(value is not None and not math.isfinite(value) for value in values):
            raise ConfigurationError("Plot axis limits must be finite numbers or automatic.")
        if self.x_min is not None and self.x_max is not None and self.x_min >= self.x_max:
            raise ConfigurationError("The X-axis minimum must be less than its maximum.")
        if self.y_min is not None and self.y_max is not None and self.y_min >= self.y_max:
            raise ConfigurationError("The primary Y-axis minimum must be less than its maximum.")
        if self.y2_min is not None and self.y2_max is not None and self.y2_min >= self.y2_max:
            raise ConfigurationError(
                "The secondary Y-axis minimum must be less than its maximum."
            )

    def to_dict(self) -> dict[str, float | None]:
        self.validate()
        return {
            "x_min": self.x_min,
            "x_max": self.x_max,
            "y_min": self.y_min,
            "y_max": self.y_max,
            "y2_min": self.y2_min,
            "y2_max": self.y2_max,
        }

    @classmethod
    def from_dict(cls, value: object) -> PlotLimits:
        if not isinstance(value, dict):
            raise ConfigurationError("Plot limits must be an object.")
        expected = {"x_min", "x_max", "y_min", "y_max", "y2_min", "y2_max"}
        if set(value) != expected:
            raise ConfigurationError("Plot limits contain missing or unknown fields.")
        try:
            limits = cls(**dict(value))
        except TypeError as exc:
            raise ConfigurationError("Plot limits are invalid.") from exc
        limits.validate()
        return limits


@dataclass(frozen=True)
class PlotSelection:
    result_id: str
    label: str = ""
    visible: bool = True
    color_id: int = 0
    series: str = ""
    group: str = ""
    title: str = ""

    def validate(self) -> None:
        if not isinstance(self.result_id, str) or not self.result_id.strip():
            raise ConfigurationError("A plot selection requires a result ID.")
        if not isinstance(self.label, str):
            raise ConfigurationError("A plot selection label must be a string.")
        if type(self.visible) is not bool:
            raise ConfigurationError("Plot selection visibility must be true or false.")
        plot_color(self.color_id)
        if not isinstance(self.series, str):
            raise ConfigurationError("A plot selection series must be a string.")
        if not isinstance(self.group, str):
            raise ConfigurationError("A plot selection group must be a string.")
        validate_plot_title(self.title)

    def to_dict(self) -> dict[str, object]:
        self.validate()
        return {
            "result_id": self.result_id,
            "label": self.label,
            "visible": self.visible,
            "color_id": self.color_id,
            "series": self.series,
            "group": self.group,
            "title": self.title,
        }

    @classmethod
    def from_dict(cls, value: object) -> PlotSelection:
        if not isinstance(value, dict):
            raise ConfigurationError("A plot selection must be an object.")
        expected = {
            "result_id",
            "label",
            "visible",
            "color_id",
            "series",
            "group",
            "title",
        }
        if set(value) != expected:
            raise ConfigurationError("A plot selection contains missing or unknown fields.")
        try:
            selection = cls(**dict(value))
        except TypeError as exc:
            raise ConfigurationError("A plot selection is invalid.") from exc
        selection.validate()
        return selection


@dataclass(frozen=True)
class PlotState:
    selections: tuple[PlotSelection, ...] = ()
    scheme: str = DEFAULT_PLOT_SCHEME
    limits: PlotLimits = PlotLimits()
    appearance: PlotAppearance = field(default_factory=PlotAppearance)
    schema_version: int = 1

    def validate(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ConfigurationError("Unsupported plot-state schema version.")
        if not isinstance(self.selections, tuple):
            raise ConfigurationError("Plot selections must be an array.")
        for selection in self.selections:
            if not isinstance(selection, PlotSelection):
                raise ConfigurationError("Plot selections contain an invalid item.")
            selection.validate()
        identifiers = [
            (selection.result_id, selection.series) for selection in self.selections
        ]
        if len(set(identifiers)) != len(identifiers):
            raise ConfigurationError("Plot selections contain duplicate result series.")
        group_titles: dict[str, set[str]] = {}
        for selection in self.selections:
            if selection.group and selection.title:
                group_titles.setdefault(selection.group, set()).add(selection.title)
        if any(len(titles) > 1 for titles in group_titles.values()):
            raise ConfigurationError("Grouped plot selections must use one title.")
        plot_scheme(self.scheme)
        self.limits.validate()
        if not isinstance(self.appearance, PlotAppearance):
            raise ConfigurationError("Plot appearance is invalid.")
        self.appearance.validate()

    def to_dict(self) -> dict[str, object]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "selections": [selection.to_dict() for selection in self.selections],
            "scheme": self.scheme,
            "limits": self.limits.to_dict(),
            "appearance": self.appearance.to_dict(),
        }

    @classmethod
    def from_dict(cls, value: object) -> PlotState:
        if not isinstance(value, dict):
            raise ConfigurationError("Plot state must be an object.")
        expected = {
            "schema_version",
            "selections",
            "scheme",
            "limits",
            "appearance",
        }
        if set(value) != expected:
            raise ConfigurationError("Plot state contains missing or unknown fields.")
        raw_selections = value.get("selections")
        if not isinstance(raw_selections, list):
            raise ConfigurationError("Plot selections must be an array.")
        selections = tuple(PlotSelection.from_dict(item) for item in raw_selections)
        state = cls(
            selections,
            value.get("scheme"),  # type: ignore[arg-type]
            PlotLimits.from_dict(value.get("limits")),
            PlotAppearance.from_dict(value.get("appearance")),
            value.get("schema_version"),  # type: ignore[arg-type]
        )
        state.validate()
        return state


def validate_plot_title(title: object) -> None:
    if not isinstance(title, str):
        raise ConfigurationError("A plot title must be a string.")
    if title != title.strip():
        raise ConfigurationError("A plot title cannot have surrounding whitespace.")
    if len(title) > MAX_PLOT_TITLE_LENGTH:
        raise ConfigurationError(
            f"A plot title cannot exceed {MAX_PLOT_TITLE_LENGTH} characters."
        )
    if any(not character.isprintable() for character in title):
        raise ConfigurationError("A plot title cannot contain control characters.")
