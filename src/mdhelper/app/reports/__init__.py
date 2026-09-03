"""Analysis-specific readable result reports."""

from __future__ import annotations

from mdhelper.core.analysis import AnalysisResult
from mdhelper.core.errors import ConfigurationError

from .base import (
    Report,
    ReportRows,
    ReportSections,
    local_time,
    result_analysis_label,
)
from .energy import EnergyReport
from .radial import CumulativeRdfReport, RdfReport

REPORT_TYPES: dict[str, type[Report]] = {
    "rdf": RdfReport,
    "cumulative_rdf": CumulativeRdfReport,
    "energy": EnergyReport,
}

__all__ = (
    "CumulativeRdfReport",
    "EnergyReport",
    "RdfReport",
    "Report",
    "ReportRows",
    "ReportSections",
    "local_time",
    "report_for",
    "result_analysis_label",
    "result_summary",
)


def report_for(result: AnalysisResult) -> Report:
    try:
        report_type = REPORT_TYPES[result.analysis_type]
    except KeyError as exc:
        raise ConfigurationError(
            f"No result report is defined for {result.analysis_type!r}."
        ) from exc
    return report_type(result)


def result_summary(result: AnalysisResult) -> str:
    return report_for(result).text()
