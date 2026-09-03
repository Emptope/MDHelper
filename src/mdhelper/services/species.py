"""Project include-topology species-role suggestions."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from mdhelper.core.species import SpeciesRoleSuggestion
from mdhelper.io.itp import discover_molecule_types

CHARGE_ZERO_TOLERANCE_E = 1e-6


@dataclass(frozen=True)
class SpeciesRoleInspection:
    suggestions: dict[str, SpeciesRoleSuggestion]
    system_charge_e: float | None


def _role(charge_e: float) -> str:
    if abs(charge_e) <= CHARGE_ZERO_TOLERANCE_E:
        return "solvent"
    return "cation" if charge_e > 0 else "anion"


def inspect_species_roles(
    project_root: str | Path,
    species: Mapping[str, int],
) -> SpeciesRoleInspection:
    root = Path(project_root).expanduser().resolve()
    definitions = discover_molecule_types(root)
    suggestions: dict[str, SpeciesRoleSuggestion] = {}
    charge_terms: list[float] = []
    charge_complete = True
    for name in sorted(species):
        record = definitions.get(name)
        if record is None:
            charge_complete = False
            suggestions[name] = SpeciesRoleSuggestion(
                None,
                "project include-topology molecular net charge",
                "unavailable",
                {
                    "project_directory": str(root),
                    "matched_molecule_type": False,
                },
                reason=(
                    "No project .itp file defines a matching molecule type, so the role "
                    "requires manual selection."
                ),
            )
            continue
        charge_terms.append(record.charge_e * species[name])
        role = _role(record.charge_e)
        suggestions[name] = SpeciesRoleSuggestion(
            role,
            "project include-topology molecular net charge",
            "high",
            {
                "atom_count": record.atom_count,
                "molecule_charge_e": record.charge_e,
                "zero_tolerance_e": CHARGE_ZERO_TOLERANCE_E,
                "source_file": record.path.relative_to(root).as_posix(),
            },
            reason=(
                "The role follows the sign of the summed [ atoms ] charges; values within "
                "the zero tolerance are neutral."
            ),
        )
    return SpeciesRoleInspection(
        suggestions,
        math.fsum(charge_terms) if charge_complete else None,
    )
