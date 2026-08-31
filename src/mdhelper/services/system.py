"""Backend-independent system inspection services."""

from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import cast

from mdhelper.backends.trajectory import load_trajectory
from mdhelper.core.errors import BackendError
from mdhelper.core.species import SpeciesRoleSuggestion
from mdhelper.core.system import Atom, SystemSummary
from mdhelper.core.trajectory import TrajectorySource
from mdhelper.integrations.manager import IntegrationManager

_TRAJECTORY_CACHE: ContextVar[str | Path | None] = ContextVar(
    "mdhelper_trajectory_cache", default=None
)


@contextmanager
def trajectory_cache(path: str | Path | None):
    """Set the cache used by the default trajectory loader in this context."""

    token = _TRAJECTORY_CACHE.set(path)
    try:
        yield
    finally:
        _TRAJECTORY_CACHE.reset(token)


def load_source(
    topology: str,
    trajectory: str,
    backend: str,
    integrations: IntegrationManager | None = None,
) -> TrajectorySource:
    """Load a trajectory behind the application-facing service boundary."""

    def convert(topology_path: Path, trajectory_path: Path, output: Path) -> dict[str, object]:
        if integrations is None:
            raise BackendError(
                "The GROMACS trajectory backend requires the GROMACS integration."
            )
        record = integrations.run(
            "gromacs",
            [
                "trjconv",
                "-s",
                str(topology_path),
                "-f",
                str(trajectory_path),
                "-o",
                str(output),
                "-ndec",
                "6",
            ],
            output.parent,
            output_files=[output],
            input_text="0\n",
            required_capabilities=("trjconv",),
        )
        if record.status != "completed":
            raise BackendError(
                f"GROMACS trajectory conversion exited with code {record.exit_code}.",
                details={"integration_run": record.to_dict()},
            )
        return record.to_dict()

    return load_trajectory(
        topology,
        trajectory,
        backend,
        _TRAJECTORY_CACHE.get(),
        convert if integrations is not None else None,
    )


def summarize_source(source: TrajectorySource) -> SystemSummary:
    molecules_by_species: dict[str, dict[str, list[Atom]]] = {}
    atom_names: Counter[str] = Counter()
    for atom in source.atoms:
        molecules_by_species.setdefault(atom.residue_name, {}).setdefault(
            atom.molecule_id, []
        ).append(atom)
        atom_names[atom.name] += 1
    return SystemSummary(
        topology=str(source.topology_path),
        trajectory=str(source.trajectory_path),
        n_atoms=len(source.atoms),
        n_frames=source.n_frames,
        species={key: len(value) for key, value in sorted(molecules_by_species.items())},
        atom_names=dict(sorted(atom_names.items())),
        backend=source.backend_name,
        role_suggestions=_role_suggestions(molecules_by_species),
    )


def _role_suggestions(
    molecules_by_species: dict[str, dict[str, list[Atom]]],
) -> dict[str, SpeciesRoleSuggestion]:
    """Build explainable role suggestions without residue-name special cases."""

    tolerance = 0.25
    suggestions: dict[str, SpeciesRoleSuggestion] = {}
    neutral: list[tuple[str, int]] = []
    records: dict[str, dict[str, object]] = {}
    for species, molecules in sorted(molecules_by_species.items()):
        sizes = sorted({len(atoms) for atoms in molecules.values()})
        charges: list[float] = []
        complete = True
        for atoms in molecules.values():
            if any(atom.charge_e is None for atom in atoms):
                complete = False
                break
            charges.append(sum(cast(float, atom.charge_e) for atom in atoms))
        evidence: dict[str, object] = {
            "molecule_count": len(molecules),
            "atoms_per_molecule": sizes,
            "complete_topology_charges": complete,
            "charge_tolerance_e": tolerance,
        }
        if complete and charges:
            evidence["molecule_charge_range_e"] = [min(charges), max(charges)]
            evidence["mean_molecule_charge_e"] = sum(charges) / len(charges)
        records[species] = evidence
        if complete and charges and all(charge > tolerance for charge in charges):
            suggestions[species] = SpeciesRoleSuggestion(
                "cation", ("cation",), "consistent topology-derived molecular net-charge sign",
                "high", evidence,
                reason="Every molecule has a positive net charge above the stated tolerance.",
            )
        elif complete and charges and all(charge < -tolerance for charge in charges):
            suggestions[species] = SpeciesRoleSuggestion(
                "anion", ("anion",), "consistent topology-derived molecular net-charge sign",
                "high", evidence,
                reason="Every molecule has a negative net charge below the stated tolerance.",
            )
        elif complete and charges and all(abs(charge) <= tolerance for charge in charges):
            neutral.append((species, len(molecules)))
        else:
            suggestions[species] = SpeciesRoleSuggestion(
                None,
                ("cation", "anion", "solvent", "additive", "polymer", "surface", "other"),
                "topology composition and molecular net-charge assessment",
                "unavailable",
                evidence,
                reason=(
                    "The topology does not provide complete, consistently signed molecular "
                    "charges, so a role cannot be inferred safely."
                ),
            )
    if neutral:
        largest_count = max(count for _, count in neutral)
        largest = [species for species, count in neutral if count == largest_count]
        for species, _ in neutral:
            evidence = records[species]
            if len(largest) == 1 and species == largest[0]:
                suggestions[species] = SpeciesRoleSuggestion(
                    "solvent", ("solvent", "additive", "other"),
                    "neutral-species population dominance heuristic", "low", evidence,
                    reason=(
                        "This is the most populous neutral species, but population alone cannot "
                        "distinguish solvent, additive, or another neutral component."
                    ),
                )
            else:
                suggestions[species] = SpeciesRoleSuggestion(
                    None, ("solvent", "additive", "polymer", "surface", "other"),
                    "neutral-species population assessment", "unavailable", evidence,
                    reason=(
                        "A neutral species role cannot be determined uniquely from topology and "
                        "population evidence."
                    ),
                )
    return suggestions
