"""Versioned analysis request and result contracts.

The serialized contracts contain only Python scalars, lists and dictionaries. Third-party
backend objects are deliberately excluded so projects remain portable across backends.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
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
AnalysisBackend = Literal["auto", "native", "mdanalysis", "gromacs"]
RadialBackend = Literal["auto", "native", "mdanalysis", "gromacs"]
EnergyBackend = Literal["auto", "mdanalysis", "gromacs"]

ANALYSIS_LABELS: dict[str, str] = {
    "rdf": "Radial Distribution Function (RDF)",
    "cumulative_rdf": "Cumulative Coordination Number (CN)",
    "energy": "Energy Analysis",
}


def analysis_label(analysis_type: str) -> str:
    """Return the shared user-facing name for a stable analysis identifier."""

    return ANALYSIS_LABELS.get(analysis_type, analysis_type.replace("_", " ").title())


@dataclass(frozen=True, kw_only=True)
class AnalysisRequest(ABC):
    analysis_type: AnalysisType
    analysis_backend: AnalysisBackend = "native"
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
        if self.analysis_backend not in {"auto", "native", "mdanalysis", "gromacs"}:
            raise InputError(f"Unknown analysis backend: {self.analysis_backend!r}.")
        if not isinstance(self.parameter_provenance, dict):
            raise InputError("parameter_provenance must be an object.")
        issue = _json_issue(self.parameter_provenance, "parameter_provenance")
        if issue:
            raise InputError(issue)

    @abstractmethod
    def to_dict(self) -> dict[str, Any]:
        """Return the strict analysis-specific JSON object."""

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> AnalysisRequest:
        if not isinstance(value, dict):
            raise ConfigurationError("An analysis request must be a JSON object.")
        data = dict(value)
        analysis_type = data.get("analysis_type")
        common = {"analysis_type", "analysis_backend", "schema_version"}
        optional = {"parameter_provenance"}
        if analysis_type in {"rdf", "cumulative_rdf"}:
            required = common | {
                "topology",
                "trajectory",
                "reference",
                "selection",
                "r_max_nm",
                "bin_width_nm",
                "frames",
            }
            optional |= {"index_file", "species_roles"}
        elif analysis_type == "energy":
            required = common | {"energy_file", "energy_terms"}
        else:
            raise ConfigurationError(
                "The analysis request does not match the supported schema.",
                details={"analysis_type": analysis_type},
            )
        missing = sorted(required - set(data))
        unknown = sorted(set(data) - required - optional)
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
        data.setdefault("parameter_provenance", {})
        if analysis_type == "energy":
            energy_terms = data["energy_terms"]
            if not isinstance(energy_terms, (list, tuple)) or any(
                not isinstance(item, str) for item in energy_terms
            ):
                raise ConfigurationError(
                    "Analysis request field 'energy_terms' must be an array of strings."
                )
            data["energy_terms"] = tuple(energy_terms)
        else:
            frames = data["frames"]
            if not isinstance(frames, dict):
                raise ConfigurationError("Analysis request field 'frames' must be an object.")
            frame_fields = {item.name for item in dataclass_fields(FrameRange)}
            if set(frames) != frame_fields:
                raise ConfigurationError(
                    "Analysis request field 'frames' contains missing or unknown fields."
                )
            data["frames"] = FrameRange(**frames)
        try:
            request_type = EnergyRequest if analysis_type == "energy" else RadialRequest
            request = request_type(**data)
            request.validate()
        except (InputError, TypeError, ValueError) as exc:
            raise ConfigurationError(
                "The analysis request does not match the supported schema.",
                details={"exception": f"{type(exc).__name__}: {exc}"},
            ) from exc
        return request


@dataclass(frozen=True, kw_only=True)
class RadialRequest(AnalysisRequest):
    analysis_backend: RadialBackend = "auto"
    topology: str
    trajectory: str
    reference: str
    selection: str
    index_file: str | None = None
    r_max_nm: float = 1.0
    bin_width_nm: float = 0.002
    frames: FrameRange = field(default_factory=FrameRange)
    species_roles: dict[str, str] = field(default_factory=dict)

    def validate(self) -> None:
        super().validate()
        if self.analysis_backend not in {"auto", "native", "mdanalysis", "gromacs"}:
            raise InputError(
                "RDF and CN require Auto, Native, MDAnalysis, or GROMACS."
            )
        if self.analysis_type not in {"rdf", "cumulative_rdf"}:
            raise InputError(f"Unknown radial analysis type: {self.analysis_type}")
        for name, value in (
            ("topology", self.topology),
            ("trajectory", self.trajectory),
            ("reference", self.reference),
            ("selection", self.selection),
        ):
            if not isinstance(value, str) or not value.strip():
                raise InputError(f"{name} must be a non-empty string.")
        if self.index_file is not None and (
            not isinstance(self.index_file, str) or not self.index_file.strip()
        ):
            raise InputError(
                "index_file cannot be empty when GROMACS index-group selection is requested."
            )
        if not isinstance(self.frames, FrameRange):
            raise InputError("frames must be a FrameRange object.")
        self.frames.validate()
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
        validate_species_roles(self.species_roles)

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        value: dict[str, Any] = {
            "analysis_type": self.analysis_type,
            "topology": self.topology,
            "trajectory": self.trajectory,
            "reference": self.reference,
            "selection": self.selection,
            "r_max_nm": self.r_max_nm,
            "bin_width_nm": self.bin_width_nm,
            "frames": asdict(self.frames),
            "analysis_backend": self.analysis_backend,
            "schema_version": self.schema_version,
        }
        if self.index_file is not None:
            value["index_file"] = self.index_file
        if self.species_roles:
            value["species_roles"] = self.species_roles
        if self.parameter_provenance:
            value["parameter_provenance"] = self.parameter_provenance
        return value

    def radial_bin_count(self) -> int:
        return (self.radial_fine_bin_count() + 1) // 2

    def cumulative_bin_count(self) -> int:
        return self.radial_fine_bin_count() // 2

    def radial_fine_bin_count(self) -> int:
        ratio = 2.0 * self.r_max_nm / self.bin_width_nm
        return max(1, math.floor(ratio + 0.5))


@dataclass(frozen=True, kw_only=True)
class EnergyRequest(AnalysisRequest):
    analysis_backend: EnergyBackend = "auto"
    energy_file: str
    energy_terms: tuple[str, ...]

    def validate(self) -> None:
        super().validate()
        if self.analysis_type != "energy":
            raise InputError(f"Unknown energy analysis type: {self.analysis_type}")
        if self.analysis_backend not in {"auto", "gromacs", "mdanalysis"}:
            raise InputError(
                "Energy analysis requires the GROMACS or MDAnalysis backend."
            )
        if not isinstance(self.energy_file, str) or not self.energy_file.strip():
            raise InputError("Energy analysis requires a non-empty energy_file.")
        if not isinstance(self.energy_terms, tuple) or any(
            not isinstance(term, str) or not term.strip() for term in self.energy_terms
        ):
            raise InputError("energy_terms must contain non-empty strings.")
        if not self.energy_terms:
            raise InputError("Energy analysis requires at least one energy term.")
        if len(set(self.energy_terms)) != len(self.energy_terms):
            raise InputError("energy_terms cannot contain duplicates.")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        value: dict[str, Any] = {
            "analysis_type": self.analysis_type,
            "energy_file": self.energy_file,
            "energy_terms": list(self.energy_terms),
            "analysis_backend": self.analysis_backend,
            "schema_version": self.schema_version,
        }
        if self.parameter_provenance:
            value["parameter_provenance"] = self.parameter_provenance
        return value


@dataclass
class AnalysisResult:
    analysis_type: str
    data: dict[str, Any]
    parameters: dict[str, Any]
    units: dict[str, str]
    diagnostics: dict[str, Any]
    provenance: dict[str, Any]
    artifacts: dict[str, str] = field(default_factory=dict)
    request: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    analysis_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    method_version: str = "1.0.0"
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)

    def validate(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ConfigurationError(
                f"Analysis result schema version {self.schema_version} is not supported.",
                "Use schema_version = 1.",
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
        if not isinstance(self.artifacts, dict):
            raise ConfigurationError("Analysis result artifacts must be an object.")
        for name, content in self.artifacts.items():
            if (
                not isinstance(name, str)
                or not name
                or name != name.strip()
                or name in {".", ".."}
                or "/" in name
                or "\\" in name
                or "\x00" in name
            ):
                raise ConfigurationError(
                    "Analysis result artifact names must be plain file names."
                )
            if not isinstance(content, str):
                raise ConfigurationError(
                    "Analysis result artifact contents must be strings."
                )
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
            if not isinstance(request, EnergyRequest):
                raise ConfigurationError(
                    "Energy result does not contain an energy request."
                )
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
