"""Species role vocabulary and suggestions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .errors import InputError

SPECIES_ROLES = ("cation", "anion", "solvent")


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
    evidence: dict[str, Any]
    error: str | None = None

    def validate(self) -> None:
        if self.suggested_role is not None and (
            not isinstance(self.suggested_role, str)
            or self.suggested_role not in SPECIES_ROLES
        ):
            raise InputError(f"Unknown suggested species role: {self.suggested_role!r}.")
        if not isinstance(self.method, str) or not self.method.strip():
            raise InputError("A role suggestion requires an explainable method.")
        if not isinstance(self.evidence, dict):
            raise InputError("A role suggestion requires structured evidence.")
        if self.suggested_role is None:
            if not isinstance(self.error, str) or not self.error.strip():
                raise InputError("An unavailable role suggestion requires an error.")
        elif self.error is not None:
            raise InputError("An available role suggestion cannot contain an error.")
