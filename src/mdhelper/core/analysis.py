"""Versioned analysis request and result contracts.

The serialized contracts contain only Python scalars, lists and dictionaries. Third-party
backend objects are deliberately excluded so projects remain portable across backends.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from dataclasses import fields as dataclass_fields
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from .errors import ConfigurationError, InputError
from .species import validate_species_roles
from .system import FrameRange


def _json_issue(value: object, path: str) -> str | None:
    if value is None or isinstance(value, (bool, int, str)):
        return None
    if isinstance(value, float):
        return None if math.isfinite(value) else f"{path} contains a non-finite number."
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                return f"{path} contains a non-string object key."
            issue = _json_issue(item, f"{path}.{key}")
            if issue:
                return issue
        return None
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            issue = _json_issue(item, f"{path}[{index}]")
            if issue:
                return issue
        return None
    return f"{path} contains a non-JSON value of type {type(value).__name__}."


AnalysisType = Literal["rdf", "cumulative_rdf", "energy"]

ANALYSIS_LABELS: dict[str, str] = {
    "rdf": "Radial Distribution Function (RDF)",
    "cumulative_rdf": "Cumulative Coordination Number (CN)",
    "energy": "Energy Analysis",
}


def analysis_label(analysis_type: str) -> str:
    """Return the shared user-facing name for a stable analysis identifier."""

    return ANALYSIS_LABELS.get(analysis_type, analysis_type.replace("_", " ").title())


@dataclass(frozen=True)
class AnalysisRequest:
    analysis_type: AnalysisType
    topology: str
    trajectory: str
    reference: str
    index_file: str | None = None
    selection: str | None = None
    r_max_nm: float = 1.0
    bin_width_nm: float = 0.002
    energy_file: str | None = None
    energy_terms: tuple[str, ...] = ()
    frames: FrameRange = field(default_factory=FrameRange)
    backend: Literal["auto", "native", "mdanalysis", "gromacs"] = "auto"
    species_roles: dict[str, str] = field(default_factory=dict)
    parameter_provenance: dict[str, Any] = field(default_factory=dict)
    schema_version: int = 1

    def validate(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise InputError(
                f"Analysis request schema version {self.schema_version} is not supported.",
                "Use schema_version = 1.",
            )
        if self.analysis_type not in {"rdf", "cumulative_rdf", "energy"}:
            raise InputError(f"Unknown analysis type: {self.analysis_type}")
        if not isinstance(self.topology, str):
            raise InputError("topology must be a string.")
        if not isinstance(self.trajectory, str):
            raise InputError("trajectory must be a string.")
        if not isinstance(self.reference, str):
            raise InputError("reference must be a string.")
        if self.analysis_type != "energy":
            if not self.topology.strip():
                raise InputError("A non-empty topology path is required.")
            if not self.trajectory.strip():
                raise InputError("Both topology and trajectory are required.")
            if not self.reference.strip():
                raise InputError("The reference selection cannot be empty.")
        if self.index_file is not None and (
            not isinstance(self.index_file, str) or not self.index_file.strip()
        ):
            raise InputError(
                "index_file cannot be empty when GROMACS index-group selection is requested."
            )
        if not isinstance(self.frames, FrameRange):
            raise InputError("frames must be a FrameRange object.")
        self.frames.validate()
        if self.backend not in {"auto", "native", "mdanalysis", "gromacs"}:
            raise InputError(f"Unknown backend: {self.backend!r}.")
        if self.selection is not None and not isinstance(self.selection, str):
            raise InputError("selection must be a string or null.")
        if (
            isinstance(self.r_max_nm, bool)
            or not isinstance(self.r_max_nm, (int, float))
            or not math.isfinite(self.r_max_nm)
            or self.r_max_nm <= 0
        ):
            raise InputError("r_max_nm must be positive.")
        if (
            isinstance(self.bin_width_nm, bool)
            or not isinstance(self.bin_width_nm, (int, float))
            or not math.isfinite(self.bin_width_nm)
            or self.bin_width_nm <= 0
            or self.bin_width_nm > self.r_max_nm
        ):
            raise InputError(
                "bin_width_nm must be positive and no larger than r_max_nm."
            )
        if self.radial_bin_count() > 1_000_000:
            raise InputError(
                "The radial grid exceeds one million bins.",
                "Increase bin_width_nm or reduce r_max_nm.",
            )
        if self.energy_file is not None and (
            not isinstance(self.energy_file, str) or not self.energy_file.strip()
        ):
            raise InputError("energy_file must be a non-empty string or null.")
        if not isinstance(self.energy_terms, tuple) or any(
            not isinstance(term, str) or not term.strip() for term in self.energy_terms
        ):
            raise InputError("energy_terms must contain non-empty strings.")
        if len(set(self.energy_terms)) != len(self.energy_terms):
            raise InputError("energy_terms cannot contain duplicates.")
        if not isinstance(self.parameter_provenance, dict):
            raise InputError("parameter_provenance must be an object.")
        issue = _json_issue(self.parameter_provenance, "parameter_provenance")
        if issue:
            raise InputError(issue)
        validate_species_roles(self.species_roles)
        if self.analysis_type == "rdf":
            if not isinstance(self.selection, str) or not self.selection.strip():
                raise InputError("RDF analysis requires a selection.")
        elif self.analysis_type == "cumulative_rdf":
            if not isinstance(self.selection, str) or not self.selection.strip():
                raise InputError("Cumulative RDF analysis requires a selection.")
        elif self.analysis_type == "energy":
            if self.backend not in {"auto", "gromacs", "mdanalysis"}:
                raise InputError(
                    "Energy analysis requires the GROMACS or MDAnalysis backend."
                )
            if self.energy_file is None:
                raise InputError("Energy analysis requires energy_file.")
            if not self.energy_terms:
                raise InputError("Energy analysis requires at least one energy term.")
            if self.selection is not None:
                raise InputError("Energy analysis does not accept atom selections.")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        value = asdict(self)
        value["energy_terms"] = list(self.energy_terms)
        return value

    def radial_bin_count(self) -> int:
        """Return the number of integer-centered RDF samples."""

        return (self.radial_fine_bin_count() + 1) // 2

    def cumulative_bin_count(self) -> int:
        """Return the number of edge-aligned cumulative samples."""

        return self.radial_fine_bin_count() // 2

    def radial_fine_bin_count(self) -> int:
        """Return the shared half-width histogram size."""

        ratio = 2.0 * self.r_max_nm / self.bin_width_nm
        return max(1, math.floor(ratio + 0.5))

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> AnalysisRequest:
        if not isinstance(value, dict):
            raise ConfigurationError("An analysis request must be a JSON object.")
        data = dict(value)
        expected = {item.name for item in dataclass_fields(cls)}
        missing = sorted(expected - set(data))
        unknown = sorted(set(data) - expected)
        if missing and unknown:
            raise ConfigurationError(
                "The analysis request contains missing or unknown fields.",
                details={"missing_fields": missing, "unknown_fields": unknown},
            )
        if missing:
            raise ConfigurationError(
                "The analysis request contains missing fields.",
                details={"missing_fields": missing},
            )
        if unknown:
            raise ConfigurationError(
                "The analysis request contains unknown fields.",
                details={"unknown_fields": unknown},
            )
        frames = data["frames"]
        energy_terms = data["energy_terms"]
        if not isinstance(frames, dict):
            raise ConfigurationError("Analysis request field 'frames' must be an object.")
        frame_fields = {item.name for item in dataclass_fields(FrameRange)}
        if set(frames) != frame_fields:
            raise ConfigurationError(
                "Analysis request field 'frames' contains missing or unknown fields."
            )
        if not isinstance(energy_terms, (list, tuple)) or any(
            not isinstance(item, str) for item in energy_terms
        ):
            raise ConfigurationError(
                "Analysis request field 'energy_terms' must be an array of strings."
            )
        try:
            data["frames"] = FrameRange(**frames)
            data["energy_terms"] = tuple(energy_terms)
            request = cls(**data)
            request.validate()
        except (InputError, TypeError, ValueError) as exc:
            raise ConfigurationError(
                "The analysis request does not match the supported schema.",
                details={"exception": f"{type(exc).__name__}: {exc}"},
            ) from exc
        return request


@dataclass
class AnalysisResult:
    analysis_type: str
    data: dict[str, Any]
    parameters: dict[str, Any]
    units: dict[str, str]
    uncertainty: dict[str, Any]
    diagnostics: dict[str, Any]
    provenance: dict[str, Any]
    request: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    analysis_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    method_version: str = "1.0.0"
    schema_version: int = 1
    status: Literal["completed"] = "completed"

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)

    def validate(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ConfigurationError(
                f"Analysis result schema version {self.schema_version} is not supported.",
                "Use schema_version = 1.",
            )
        if self.status != "completed":
            raise ConfigurationError(
                f"Analysis result status {self.status!r} is not loadable as a completed result."
            )
        if self.analysis_type not in {"rdf", "cumulative_rdf", "energy"}:
            raise ConfigurationError(
                f"Unknown result analysis type: {self.analysis_type!r}."
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
            "uncertainty": self.uncertainty,
            "diagnostics": self.diagnostics,
            "provenance": self.provenance,
        }
        for name, value in mappings.items():
            if not isinstance(value, dict):
                raise ConfigurationError(f"Analysis result field {name!r} must be an object.")
            issue = _json_issue(value, name)
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
                "MDHelper 0.1.0.",
            )
        try:
            request = AnalysisRequest.from_dict(self.request)
        except (ConfigurationError, TypeError, InputError) as exc:
            raise ConfigurationError(
                "The analysis result contains an invalid analysis request.",
                details={"exception": f"{type(exc).__name__}: {exc}"},
            ) from exc
        if request.analysis_type != self.analysis_type:
            raise ConfigurationError(
                "The result analysis type does not match its embedded request.",
                details={
                    "result_analysis_type": self.analysis_type,
                    "request_analysis_type": request.analysis_type,
                },
            )
        if self.analysis_type == "energy":
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
