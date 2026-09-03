"""Widget-independent state for interactive result plots."""

from __future__ import annotations

from dataclasses import dataclass, replace
from uuid import uuid4

from mdhelper.core.analysis import AnalysisRequest, AnalysisResult, EnergyRequest, RadialRequest
from mdhelper.core.plotting import (
    PLOT_COLORS,
    PlotAppearance,
    PlotLimits,
    PlotModel,
    PlotSelection,
    PlotState,
    results_plots,
)


@dataclass(frozen=True)
class PlotEntry:
    result: AnalysisResult
    label: str
    selection: str
    visible: bool = True
    color_id: int = 0
    series: str = ""
    group: str = ""
    title: str = ""


class PlotSession:
    def __init__(self) -> None:
        self.entries: tuple[PlotEntry, ...] = ()
        self.results: dict[str, AnalysisResult] = {}
        self.limits = PlotLimits()
        self.appearance = PlotAppearance()

    def add(self, result: AnalysisResult, label: str | None = None) -> tuple[int, ...]:
        if result.analysis_id in self.results:
            self.results[result.analysis_id] = result
            self.entries = tuple(
                replace(entry, result=result)
                if entry.result.analysis_id == result.analysis_id
                else entry
                for entry in self.entries
            )
            return ()
        self.results[result.analysis_id] = result
        start = len(self.entries)
        added = self._entries(result, label)
        self.entries = (*self.entries, *added)
        return tuple(range(start, len(self.entries)))

    def restore(
        self,
        state: PlotState,
        results: tuple[AnalysisResult, ...],
    ) -> None:
        state.validate()
        available = {result.analysis_id: result for result in results}
        entries: list[PlotEntry] = []
        self.entries = ()
        self.results = {}
        for selection in state.selections:
            result = available.get(selection.result_id)
            if result is None:
                continue
            self.results[result.analysis_id] = result
            entries.extend(
                self._entries(
                    result,
                    selection.label or None,
                    selection.visible,
                    selection.color_id,
                    selection.series or None,
                    selection.group,
                    selection.title,
                )
            )
        self.entries = tuple(entries)
        self.limits = state.limits
        self.appearance = state.appearance
        self.normalize()

    def clear(self) -> None:
        self.entries = ()
        self.results = {}

    def replace(self, entries: tuple[PlotEntry, ...]) -> None:
        if len(entries) != len(self.entries):
            raise RuntimeError("Plot entries do not match the displayed rows.")
        self.entries = entries

    def remove(self, rows: tuple[int, ...]) -> set[str]:
        removed = set(rows)
        self.entries = tuple(
            entry for index, entry in enumerate(self.entries) if index not in removed
        )
        used = {entry.result.analysis_id for entry in self.entries}
        self.results = {
            result_id: result
            for result_id, result in self.results.items()
            if result_id in used
        }
        self.normalize()
        return used

    def combine(self, rows: tuple[int, ...], current: int) -> bool:
        if len(rows) < 2 or not all(self.is_energy(row) for row in rows):
            return False
        ordered = (current, *rows) if current in rows else rows
        title = next((self.entries[row].title for row in ordered if self.entries[row].title), "")
        group = f"energy-{uuid4()}"
        selected = set(rows)
        self.entries = tuple(
            replace(entry, group=group, title=title) if index in selected else entry
            for index, entry in enumerate(self.entries)
        )
        self.normalize()
        return True

    def separate(self, rows: tuple[int, ...]) -> bool:
        if not rows:
            return False
        selected = set(rows)
        self.entries = tuple(
            replace(entry, group="") if index in selected else entry
            for index, entry in enumerate(self.entries)
        )
        self.normalize()
        return True

    def set_title(self, rows: tuple[int, ...], title: str) -> None:
        selected = set(rows)
        self.entries = tuple(
            replace(entry, title=title) if index in selected else entry
            for index, entry in enumerate(self.entries)
        )

    def normalize(self) -> bool:
        counts: dict[str, int] = {}
        for entry in self.entries:
            if entry.group:
                counts[entry.group] = counts.get(entry.group, 0) + 1
        normalized = tuple(
            replace(entry, group="")
            if entry.group and counts.get(entry.group) == 1
            else entry
            for entry in self.entries
        )
        changed = normalized != self.entries
        self.entries = normalized
        return changed

    def is_energy(self, row: int) -> bool:
        if row < 0 or row >= len(self.entries):
            return False
        entry = self.entries[row]
        return bool(entry.series) and entry.result.analysis_type == "energy"

    def visible(self) -> tuple[tuple[PlotEntry, int], ...]:
        return tuple(
            (entry, row) for row, entry in enumerate(self.entries) if entry.visible
        )

    def models(self) -> tuple[PlotModel, ...]:
        visible = self.visible()
        if not visible:
            return ()
        entries = tuple(entry for entry, _row in visible)
        return results_plots(
            tuple(entry.result for entry in entries),
            tuple(entry.label or None for entry in entries),
            tuple(entry.color_id for entry in entries),
            tuple(entry.series or None for entry in entries),
            tuple(entry.group or None for entry in entries),
            tuple(entry.title or None for entry in entries),
        )

    def rows(self, models: tuple[PlotModel, ...]) -> tuple[tuple[int, ...], ...]:
        visible = self.visible()
        return tuple(
            tuple(visible[source][1] for source in model.source_indices)
            for model in models
        )

    def group_labels(self) -> tuple[str, ...]:
        positions: dict[str, int] = {}
        labels: list[str] = []
        for row, entry in enumerate(self.entries):
            if not entry.series:
                labels.append("Automatic")
                continue
            key = entry.group or f"row-{row}"
            if key not in positions:
                positions[key] = len(positions) + 1
            suffix = " - Combined" if entry.group else ""
            labels.append(f"Plot {positions[key]}{suffix}")
        return tuple(labels)

    def state(self, scheme: str) -> PlotState:
        return PlotState(
            tuple(
                PlotSelection(
                    entry.result.analysis_id,
                    entry.label,
                    entry.visible,
                    entry.color_id,
                    entry.series,
                    entry.group,
                    entry.title,
                )
                for entry in self.entries
            ),
            scheme,
            self.limits,
            self.appearance,
        )

    def _entries(
        self,
        result: AnalysisResult,
        label: str | None,
        visible: bool = True,
        color_id: int | None = None,
        series: str | None = None,
        group: str = "",
        title: str = "",
    ) -> tuple[PlotEntry, ...]:
        request = AnalysisRequest.from_dict(result.request)
        if isinstance(request, RadialRequest):
            default = f"{request.reference}-{request.selection}"
        elif isinstance(request, EnergyRequest):
            default = ", ".join(request.energy_terms)
        else:
            return ()
        if result.analysis_type == "energy":
            values = result.data.get("series")
            if not isinstance(values, dict):
                return ()
            available = tuple(str(key) for key in values)
            keys = available if series is None else (series,)
            if any(key not in available for key in keys):
                return ()
        else:
            keys = ("",)
        entries: list[PlotEntry] = []
        for key in keys:
            selected = label
            if label and len(keys) > 1:
                selected = f"{label}: {key}"
            row = len(self.entries) + len(entries)
            entries.append(
                PlotEntry(
                    result,
                    selected or key or default,
                    key or default,
                    visible,
                    row % len(PLOT_COLORS) if color_id is None else color_id,
                    key,
                    group,
                    title,
                )
            )
        return tuple(entries)
