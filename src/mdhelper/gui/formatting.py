"""GUI-safe formatting of domain values and failures."""

from __future__ import annotations

import json
from collections.abc import Mapping
from html import escape
from typing import Any

from mdhelper.app.reports import (
    local_time,
    report_for,
    result_analysis_label,
)
from mdhelper.core.analysis import AnalysisResult
from mdhelper.core.errors import MDHelperError
from mdhelper.core.species import SpeciesRoleSuggestion

__all__ = (
    "error_dict",
    "error_text",
    "result_analysis_label",
    "result_details_html",
    "result_label",
    "result_summary_html",
    "role_suggestions_html",
)
def error_dict(error: BaseException) -> dict[str, Any]:
    if isinstance(error, MDHelperError):
        return error.to_dict()
    return {
        "error": "internal_error",
        "message": str(error),
        "details": {"exception_type": type(error).__name__},
    }


def error_text(error: BaseException) -> str:
    value = error_dict(error)
    lines = [str(value.get("message", error))]
    hint = str(value.get("hint", "")).strip()
    if hint:
        lines.extend(("", hint))
    return "\n".join(lines)


def _evidence_label(name: str) -> tuple[str, str]:
    for suffix, unit in (("_e", "e"), ("_nm", "nm"), ("_ps", "ps")):
        if name.endswith(suffix):
            return name[: -len(suffix)].replace("_", " ").capitalize(), unit
    return name.replace("_", " ").capitalize(), ""


def _evidence_value(value: object, unit: str) -> str:
    if isinstance(value, bool):
        text = "Yes" if value else "No"
    elif isinstance(value, float):
        text = f"{value:.6g}"
    elif isinstance(value, (dict, list, tuple)):
        text = json.dumps(value, sort_keys=True, ensure_ascii=True)
    elif value is None:
        text = "Unavailable"
    else:
        text = str(value)
    if unit and isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{text} {unit}"
    return text


def role_suggestions_html(suggestions: Mapping[str, SpeciesRoleSuggestion]) -> str:
    """Render complete role suggestions as readable rich text."""

    parts: list[str] = []
    for species, item in suggestions.items():
        fields = [
            ("Suggested role", item.suggested_role or "Unavailable"),
            ("Method", item.method),
        ]
        if item.error:
            fields.append(("Error", item.error))
        parts.append(f"<h3>{escape(species)}</h3><table cellspacing='5'>")
        parts.extend(
            f"<tr><td><b>{escape(key)}</b></td><td>{escape(value)}</td></tr>"
            for key, value in fields
        )
        parts.append("</table><h4>Evidence</h4><table cellspacing='5'>")
        parts.extend(
            f"<tr><td><b>{escape(label)}</b></td>"
            f"<td>{escape(_evidence_value(value, unit))}</td></tr>"
            for name, value in item.evidence.items()
            for label, unit in (_evidence_label(name),)
        )
        parts.append("</table>")
    return "".join(parts)


def result_label(entry: Mapping[str, object]) -> str:
    analysis_type = result_analysis_label(str(entry.get("analysis_type", "analysis")))
    request = entry.get("request")
    selection = ""
    if isinstance(request, dict):
        reference_value = request.get("reference")
        selected_value = request.get("selection")
        reference = reference_value.strip() if isinstance(reference_value, str) else ""
        selected = selected_value.strip() if isinstance(selected_value, str) else ""
        if selected:
            selection = f" | {reference}-{selected}"
        elif reference:
            selection = f" | {reference}"
    return f"{local_time(entry.get('committed_at'))} | {analysis_type}{selection}"


def _result_html(result: AnalysisResult, include_technical: bool) -> str:
    """Render the shared result report as compact, selectable rich text."""

    report = report_for(result)
    parts = [f"<h3>{escape(report.title)}</h3>"]
    for heading, rows in report.sections():
        parts.append(f"<h4>{escape(heading)}</h4><table cellspacing='4'>")
        for key, value in rows:
            parts.append(
                f"<tr><td><b>{escape(key)}</b></td><td>{escape(value)}</td></tr>"
            )
        parts.append("</table>")
    if result.warnings:
        parts.append("<h4>Warnings and review items</h4><ul>")
        parts.extend(f"<li>{escape(warning)}</li>" for warning in result.warnings)
        parts.append("</ul>")
    if include_technical:
        parts.append("<h4>Technical details</h4><table cellspacing='4'>")
        for key, value in report.technical_rows():
            parts.append(
                f"<tr><td><b>{escape(key)}</b></td><td>{escape(value)}</td></tr>"
            )
        parts.append("</table>")
    return "".join(parts)


def result_summary_html(result: AnalysisResult) -> str:
    """Render result highlights without reproduction metadata."""

    return _result_html(result, include_technical=False)


def result_details_html(result: AnalysisResult) -> str:
    """Render the complete readable result and reproduction metadata."""

    return _result_html(result, include_technical=True)
