"""Base contract and shared fields for readable result reports."""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from mdhelper.core.analysis import AnalysisRequest, AnalysisResult, analysis_label

ReportRows = tuple[tuple[str, str], ...]
ReportSections = tuple[tuple[str, ReportRows], ...]

RESULT_ANALYSIS_LABELS = {
    "rdf": "RDF",
    "cumulative_rdf": "CN",
    "energy": "Energy",
}


@dataclass(frozen=True)
class Report(ABC):
    result: AnalysisResult

    @property
    def request(self) -> AnalysisRequest:
        return AnalysisRequest.from_dict(self.result.request)

    @property
    def title(self) -> str:
        return f"{result_analysis_label(self.result.analysis_type)} completed"

    @property
    def frame_count(self) -> str:
        frames = self.result.diagnostics.get("n_frames")
        return "unknown" if frames is None else number(frames)

    @property
    def frame_range(self) -> str:
        value = self.result.diagnostics.get("selected_frame_time_range")
        if not isinstance(value, dict):
            return ""
        first = value.get("first_time_ps")
        last = value.get("last_time_ps")
        if first is None or last is None:
            return ""
        return f"{number(first)} to {number(last)} ps"

    @abstractmethod
    def result_rows(self) -> ReportRows:
        """Return analysis-specific result fields."""

    @abstractmethod
    def configuration_rows(self) -> ReportRows:
        """Return analysis-specific configuration fields."""

    def sections(self) -> ReportSections:
        return (
            ("Results", self.result_rows()),
            ("Configuration", self.configuration_rows()),
        )

    def technical_rows(self) -> ReportRows:
        provenance = self.result.provenance
        rows: list[tuple[str, str]] = [
            (
                "Method",
                f"{result_analysis_label(self.result.analysis_type)} "
                f"{self.result.method_version}",
            ),
            (
                "Analysis backend",
                component_name(
                    provenance.get("analysis_backend"),
                    self.request.backend,
                ),
            ),
        ]
        trajectory = provenance.get("trajectory_backend")
        if trajectory is not None:
            rows.append(("Trajectory backend", component_name(trajectory, "Unknown")))
        raw_runs = provenance.get("integration_runs")
        runs = (
            tuple(item for item in raw_runs if isinstance(item, dict))
            if isinstance(raw_runs, list)
            else ()
        )
        for index, run in enumerate(runs, start=1):
            suffix = "" if len(runs) == 1 else f" {index}"
            rows.extend(
                (
                    (f"External software{suffix}", component_name(run, "Unknown")),
                    (f"Software version{suffix}", str(run.get("version", "Unknown"))),
                    (f"Executable{suffix}", str(run.get("path", "Unknown"))),
                    (f"Command{suffix}", integration_command(run)),
                )
            )
        rows.extend(
            (
                ("Created", local_time(self.result.created_at)),
                ("Analysis ID", self.result.analysis_id),
            )
        )
        return tuple(rows)

    def text(self) -> str:
        lines = [self.title]
        for heading, rows in self.sections():
            lines.extend(("", heading))
            lines.extend(f"  {key}: {value}" for key, value in rows)
        if self.result.warnings:
            lines.extend(("", "Warnings"))
            lines.extend(f"  - {warning}" for warning in self.result.warnings)
        lines.extend(("", "Technical details"))
        lines.extend(f"  {key}: {value}" for key, value in self.technical_rows())
        return "\n".join(lines)


def result_analysis_label(analysis_type: str) -> str:
    return RESULT_ANALYSIS_LABELS.get(analysis_type, analysis_label(analysis_type))


def local_time(value: object) -> str:
    if not isinstance(value, str):
        return "Unknown time"
    try:
        parsed = datetime.fromisoformat(value).astimezone()
    except ValueError:
        return value
    return parsed.strftime("%Y-%m-%d %H:%M:%S")


def number(value: object, digits: int = 6) -> str:
    if isinstance(value, float):
        return f"{value:.{digits}g}"
    return str(value)


def scalar(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    converted = float(value)
    return converted if math.isfinite(converted) else None


def series(value: object) -> tuple[float, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    numbers = tuple(scalar(item) for item in value)
    if any(item is None for item in numbers):
        return ()
    return tuple(item for item in numbers if item is not None)


def component_name(value: object, fallback: str) -> str:
    if isinstance(value, dict):
        display = value.get("display_name")
        if isinstance(display, str) and display.strip():
            return display.strip()
        name = value.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


def integration_command(run: Mapping[str, object]) -> str:
    arguments = run.get("arguments")
    if not isinstance(arguments, list) or not arguments:
        return "Unknown"
    command = arguments[0]
    return str(command) if isinstance(command, str) and command else "Unknown"
