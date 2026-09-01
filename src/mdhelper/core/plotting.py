"""Backend-neutral plot contracts derived only from analysis results."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Any, Literal

from .analysis import AnalysisRequest, AnalysisResult, RadialRequest
from .errors import ConfigurationError
from .units import convert_distance

DEFAULT_PLOT_SCHEME = "residue_name"
SECONDARY_COLOR_FACTOR = 0.5
MAX_PLOT_TITLE_LENGTH = 120


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
        data = dict(value)
        try:
            limits = cls(**data)
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
        _validate_title(self.title)

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
        data = dict(value)
        try:
            selection = cls(**data)
        except TypeError as exc:
            raise ConfigurationError("A plot selection is invalid.") from exc
        selection.validate()
        return selection


@dataclass(frozen=True)
class PlotState:
    selections: tuple[PlotSelection, ...] = ()
    scheme: str = DEFAULT_PLOT_SCHEME
    limits: PlotLimits = PlotLimits()
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

    def to_dict(self) -> dict[str, object]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "selections": [selection.to_dict() for selection in self.selections],
            "scheme": self.scheme,
            "limits": self.limits.to_dict(),
        }

    @classmethod
    def from_dict(cls, value: object) -> PlotState:
        if not isinstance(value, dict):
            raise ConfigurationError("Plot state must be an object.")
        expected = {"schema_version", "selections", "scheme", "limits"}
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
            value.get("schema_version"),  # type: ignore[arg-type]
        )
        state.validate()
        return state


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

_CATEGORY_COLOR_IDS = (0, 1, 2, 3, 4, 5, 6, 7, 9, 10, 11, 12, 13, 14, 15, 16, 8)

_SCHEME_MAP = {scheme.key: scheme for scheme in PLOT_SCHEMES}
_COLOR_MAP = {color.color_id: color for color in PLOT_COLORS}


def plot_scheme(key: str) -> PlotScheme:
    try:
        return _SCHEME_MAP[key]
    except KeyError as exc:
        raise ConfigurationError(f"Unknown plot color scheme: {key!r}.") from exc


def plot_color(color_id: int) -> PlotColor:
    if type(color_id) is not int:
        raise ConfigurationError("A plot color ID must be an integer.")
    try:
        return _COLOR_MAP[color_id]
    except KeyError as exc:
        raise ConfigurationError(f"Unknown plot color ID: {color_id!r}.") from exc


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
            combined_title="RDF and Cumulative Coordination Number",
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
                    "N(r)",
                    color_key=selection,
                    residue_name_key=residue_key,
                ),
            ),
            r"$r$ ($\mathrm{\AA}$)",
            "Coordination number",
            "Cumulative Coordination Number",
            domain="radial_distance",
            axis_order=1,
            combined_title="RDF and Cumulative Coordination Number",
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
        _validate_title(title)
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


def _validate_title(title: object) -> None:
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


def _series_color_key(series: PlotSeries, method: str) -> str:
    if method == "residue_name":
        return series.residue_name_key or series.color_key or series.label
    raise ConfigurationError(f"Unknown categorical coloring method: {method!r}.")


def draw_plot(
    axis: object,
    model: PlotModel,
    scheme: str = DEFAULT_PLOT_SCHEME,
    limits: PlotLimits | None = None,
) -> None:
    """Render a plot model with a consistent publication style."""

    selected_limits = limits or PlotLimits()
    selected_limits.validate()
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
            color_id = _CATEGORY_COLOR_IDS[color_index % len(_CATEGORY_COLOR_IDS)]
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
                linewidth=1.8 if series.axis == "secondary" else 2.0,
            )
        elif model.kind == "step":
            target_axis.step(
                x,
                y,
                where="mid",
                color=color,
                label=_legend_text(series),
                linewidth=1.8,
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
            linewidth=1.0,
            linestyle="-",
            alpha=0.3,
            zorder=0,
        )
    axis.set_xlabel(model.x_label, fontsize=12)  # type: ignore[attr-defined]
    axis.set_ylabel(model.y_label, fontsize=12)  # type: ignore[attr-defined]
    if secondary_axis is not None and model.secondary_y_label is not None:
        secondary_axis.set_ylabel(model.secondary_y_label, fontsize=12)
        secondary_axis.tick_params(axis="y", colors="#202020", labelsize=10)
    axis.set_title(  # type: ignore[attr-defined]
        model.title,
        fontsize=14,
        fontweight="normal",
        pad=10,
        wrap=True,
    )
    axis.set_axisbelow(True)  # type: ignore[attr-defined]
    axis.tick_params(axis="both", labelsize=10)  # type: ignore[attr-defined]
    axis.grid(  # type: ignore[attr-defined]
        True,
        which="both",
        color="#b0b0b0",
        linestyle=":",
        linewidth=0.8,
        alpha=0.5,
    )
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
    if model.series:
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
            loc="upper left",
            fontsize=9,
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
