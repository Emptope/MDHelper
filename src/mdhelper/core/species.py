"""Species role vocabulary and explainable role suggestions."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

from .errors import InputError

SPECIES_ROLES = ("cation", "anion", "solvent", "additive", "polymer", "surface", "other")

# Role labels are project metadata used to describe how a species is used in a
# workflow. They never alter selections or the numerical analysis algorithm.
SPECIES_ROLE_DESCRIPTIONS: dict[str, str] = {
    "cation": "Positively charged species, commonly used as a central atom set.",
    "anion": "Negatively charged species, commonly used as a counterion set.",
    "solvent": "Neutral solvent component used to describe the chemical environment.",
    "additive": "Neutral or minor component tracked separately from the solvent.",
    "polymer": "Polymeric component or macromolecular environment.",
    "surface": "Solid or interfacial component used as a structural reference.",
    "other": "A confirmed component with no more specific domain role.",
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
    candidates: tuple[str, ...]
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
        if (
            not isinstance(self.candidates, tuple)
            or not self.candidates
            or any(role not in SPECIES_ROLES for role in self.candidates)
        ):
            raise InputError("A role suggestion must contain valid candidate roles.")
        if len(set(self.candidates)) != len(self.candidates):
            raise InputError("A role suggestion contains duplicate candidate roles.")
        if self.suggested_role is not None and self.suggested_role not in self.candidates:
            raise InputError("The suggested role must also appear in the candidate roles.")
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
            "candidates": list(self.candidates),
            "available": self.available,
        }


def role_decision(
    selected_role: str,
    suggestion: SpeciesRoleSuggestion,
    source: str = "user",
) -> dict[str, Any]:
    """Build the auditable record for one explicit role confirmation."""

    validate_species_roles({"species": selected_role})
    suggestion.validate()
    if not isinstance(source, str) or not source.strip():
        raise InputError("A role decision requires a non-empty source.")
    decision = (
        "accepted"
        if suggestion.available and selected_role == suggestion.suggested_role
        else "overridden"
        if suggestion.available
        else "confirmed_without_suggestion"
    )
    return {
        "decision": decision,
        "selected_role": selected_role,
        "source": source,
        "suggestion": suggestion.to_dict(),
    }
