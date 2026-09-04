"""Versioned analysis request contracts."""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from dataclasses import fields as dataclass_fields
from typing import Any, Literal

from ..errors import ConfigurationError, InputError
from ..species import validate_species_roles
from ..system import FrameRange
from .validation import json_issue

AnalysisType = Literal["rdf", "cumulative_rdf", "energy"]
AnalysisBackend = Literal["auto", "mdanalysis", "gromacs"]

ANALYSIS_LABELS: dict[str, str] = {
    "rdf": "Radial Distribution Function (RDF)",
    "cumulative_rdf": "Cumulative Number RDF",
    "energy": "Energy Analysis",
}


def analysis_label(analysis_type: str) -> str:
    """Return the shared user-facing name for a stable analysis identifier."""

    return ANALYSIS_LABELS.get(analysis_type, analysis_type.replace("_", " ").title())


@dataclass(frozen=True, kw_only=True)
class AnalysisRequest(ABC):
    analysis_type: AnalysisType
    analysis_backend: AnalysisBackend = "auto"
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
        if self.analysis_backend not in {"auto", "mdanalysis", "gromacs"}:
            raise InputError(f"Unknown analysis backend: {self.analysis_backend!r}.")
        if not isinstance(self.parameter_provenance, dict):
            raise InputError("parameter_provenance must be an object.")
        issue = json_issue(self.parameter_provenance, "parameter_provenance")
        if issue:
            raise InputError(issue)
        if "species_roles" in self.parameter_provenance:
            raise InputError(
                "Species-role suggestions cannot be stored in parameter_provenance.",
                "Store only confirmed roles in species_roles.",
            )

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
    analysis_backend: AnalysisBackend = "auto"
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
    analysis_backend: AnalysisBackend = "auto"
    energy_file: str
    energy_terms: tuple[str, ...]

    def validate(self) -> None:
        super().validate()
        if self.analysis_type != "energy":
            raise InputError(f"Unknown energy analysis type: {self.analysis_type}")
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
