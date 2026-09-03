"""Species role vocabulary and explainable role suggestions."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

from .errors import InputError

SPECIES_ROLES = ("cation", "anion", "solvent")

# Role labels are project metadata used to describe how a species is used in a
# workflow. They never alter selections or the numerical analysis algorithm.
SPECIES_ROLE_DESCRIPTIONS: dict[str, str] = {
    "cation": "Positively charged species, commonly used as a central atom set.",
    "anion": "Negatively charged species, commonly used as a counterion set.",
    "solvent": "Neutral solvent component used to describe the chemical environment.",
}

SPECIES_ROLE_POLICY: dict[str, object] = {
    "purpose": "Descriptive chemical context stored with projects and analysis provenance.",
    "affects": ("project metadata", "analysis provenance", "result interpretation"),
    "does_not_affect": ("atom selections", "analysis parameters", "numerical algorithms"),
    "confirmation": "Every suggested or manually chosen role requires user confirmation.",
}


def role_description(role: str) -> str:
    """Return the explanatory text for a validated species role."""

    return SPECIES_ROLE_DESCRIPTIONS.get(role, "Role metadata for this species.")


def role_policy() -> dict[str, Any]:
    """Return the JSON-ready policy shared by inspection and provenance."""

    return {
        key: list(value) if isinstance(value, tuple) else value
        for key, value in SPECIES_ROLE_POLICY.items()
    }


def validate_species_roles(species_roles: dict[str, str]) -> None:
    if not isinstance(species_roles, dict):
        raise InputError("species_roles must be an object.")
    for species, role in species_roles.items():
        if not isinstance(species, str) or not species.strip():
            raise InputError("A species-role mapping contains an empty species name.")
        if role not in SPECIES_ROLES:
            raise InputError(
                f"Unknown role {role!r} for species {species!r}.",
                f"Choose one of: {', '.join(SPECIES_ROLES)}.",
            )


@dataclass(frozen=True)
class SpeciesRoleSuggestion:
    suggested_role: str | None
    method: str
    confidence: Literal["high", "medium", "low", "unavailable"]
    evidence: dict[str, Any]
    requires_user_confirmation: bool = True
    reason: str = ""

    @property
    def available(self) -> bool:
        return self.suggested_role is not None

    def validate(self) -> None:
        if self.suggested_role is not None and (
            not isinstance(self.suggested_role, str)
            or self.suggested_role not in SPECIES_ROLES
        ):
            raise InputError(f"Unknown suggested species role: {self.suggested_role!r}.")
        if not isinstance(self.method, str) or not self.method.strip():
            raise InputError("A role suggestion requires an explainable method.")
        if self.confidence not in {"high", "medium", "low", "unavailable"}:
            raise InputError("A role suggestion has an invalid confidence level.")
        if (self.suggested_role is None) != (self.confidence == "unavailable"):
            raise InputError("Role availability and confidence are inconsistent.")
        if not isinstance(self.evidence, dict):
            raise InputError("A role suggestion requires structured evidence.")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise InputError("A role suggestion requires an explainable reason.")
        if self.requires_user_confirmation is not True:
            raise InputError("Species role suggestions must require user confirmation.")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            **asdict(self),
            "available": self.available,
        }
