"""Backend-neutral plot data models."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from ..errors import ConfigurationError


@dataclass(frozen=True)
class PlotSize:
    """Physical size of one plot panel in inches."""

    width: float = 8.8
    height: float = 6.2

    def validate(self) -> None:
        if not math.isfinite(self.width) or not math.isfinite(self.height):
            raise ConfigurationError("Plot dimensions must be finite numbers.")
        if self.width <= 0.0 or self.height <= 0.0:
            raise ConfigurationError("Plot dimensions must be positive.")


DEFAULT_PLOT_SIZE = PlotSize()


@dataclass(frozen=True)
class PlotSeries:
    """One labelled data series and its optional pointwise uncertainty."""

    x: tuple[float | str, ...]
    y: tuple[float, ...]
    label: str
    y_error: tuple[float, ...] | None = None
    quantity: str = ""
    axis: Literal["primary", "secondary"] = "primary"
    color_key: str = ""
    residue_name_key: str = ""
    color_id: int = 0


@dataclass(frozen=True)
class PlotModel:
    """A complete, presentation-independent description of one set of axes."""

    kind: str
    series: tuple[PlotSeries, ...]
    x_label: str
    y_label: str
    title: str
    reference_y: float | None = None
    secondary_y_label: str | None = None
    domain: str = ""
    axis_order: int = 0
    combined_title: str | None = None
    source_indices: tuple[int, ...] = ()
