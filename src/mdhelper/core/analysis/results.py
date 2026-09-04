"""Versioned analysis result contract."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from dataclasses import fields as dataclass_fields
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from ..errors import ConfigurationError
from .requests import AnalysisRequest, EnergyRequest
from .validation import json_issue


@dataclass
class AnalysisResult:
    data: dict[str, Any]
    parameters: dict[str, Any]
    units: dict[str, str]
    diagnostics: dict[str, Any]
    provenance: dict[str, Any]
    request: dict[str, Any]
    warnings: list[str] = field(default_factory=list)
    analysis_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    method_version: str = "1.0.0"
    schema_version: int = 1

    @property
    def analysis_type(self) -> str:
        value = self.request.get("analysis_type")
        return value if isinstance(value, str) else ""

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)

    def validate(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ConfigurationError(
                f"Analysis result schema version {self.schema_version} is not supported.",
                "Use schema_version = 1.",
            )
        if not isinstance(self.analysis_id, str) or not self.analysis_id.strip():
            raise ConfigurationError("An analysis result must have a non-empty analysis_id.")
        if not isinstance(self.method_version, str) or not self.method_version.strip():
            raise ConfigurationError("An analysis result must have a method version.")
        if not isinstance(self.created_at, str):
            raise ConfigurationError("An analysis result must have an ISO 8601 created_at value.")
        try:
            created = datetime.fromisoformat(self.created_at)
        except ValueError as exc:
            raise ConfigurationError(
                "An analysis result has an invalid created_at value."
            ) from exc
        if created.tzinfo is None or created.utcoffset() is None:
            raise ConfigurationError("An analysis result created_at value must include a timezone.")
        mappings = {
            "data": self.data,
            "parameters": self.parameters,
            "units": self.units,
            "diagnostics": self.diagnostics,
            "provenance": self.provenance,
        }
        for name, value in mappings.items():
            if not isinstance(value, dict):
                raise ConfigurationError(f"Analysis result field {name!r} must be an object.")
            issue = json_issue(value, name)
            if issue:
                raise ConfigurationError(issue)
        if any(
            not isinstance(key, str) or not isinstance(unit, str)
            for key, unit in self.units.items()
        ):
            raise ConfigurationError("Analysis result units must map string fields to strings.")
        if not isinstance(self.warnings, list) or any(
            not isinstance(warning, str) for warning in self.warnings
        ):
            raise ConfigurationError("Analysis result warnings must be an array of strings.")
        if not isinstance(self.request, dict) or not self.request:
            raise ConfigurationError(
                "The analysis result does not contain its versioned analysis request.",
                "This result cannot reconstruct the analysis configuration required by "
                "the current result schema.",
            )
        try:
            request = AnalysisRequest.from_dict(self.request)
        except ConfigurationError as exc:
            raise ConfigurationError(
                "The analysis result contains an invalid analysis request.",
                details={"exception": f"{type(exc).__name__}: {exc}"},
            ) from exc
        if isinstance(request, EnergyRequest):
            if set(self.data) != {"time_ps", "series"}:
                raise ConfigurationError(
                    "Energy result data contains missing or unknown fields."
                )
            time_ps = self.data["time_ps"]
            series = self.data["series"]
            if not isinstance(time_ps, list) or not time_ps:
                raise ConfigurationError("Energy result time_ps must be a non-empty array.")
            if not isinstance(series, dict) or not series:
                raise ConfigurationError("Energy result series must be a non-empty object.")
            if tuple(series) != request.energy_terms:
                raise ConfigurationError(
                    "Energy result series do not match the requested terms."
                )
            if any(
                not isinstance(values, list) or len(values) != len(time_ps)
                for values in series.values()
            ):
                raise ConfigurationError(
                    "Every energy result series must match the time axis length."
                )
        self.request = request.to_dict()

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> AnalysisResult:
        if not isinstance(value, dict):
            raise ConfigurationError("An analysis result must be a JSON object.")
        expected = {item.name for item in dataclass_fields(cls)}
        missing = sorted(expected - set(value))
        unknown = sorted(set(value) - expected)
        if missing and unknown:
            raise ConfigurationError(
                "The analysis result contains missing or unknown fields.",
                details={"missing_fields": missing, "unknown_fields": unknown},
            )
        if missing:
            raise ConfigurationError(
                "The analysis result contains missing fields.",
                details={"missing_fields": missing},
            )
        if unknown:
            raise ConfigurationError(
                "The analysis result contains unknown fields.",
                details={"unknown_fields": unknown},
            )
        try:
            result = cls(**value)
        except TypeError as exc:
            raise ConfigurationError(
                "The analysis result does not match the supported schema.",
                details={"exception": f"{type(exc).__name__}: {exc}"},
            ) from exc
        result.validate()
        return result
