"""MDAnalysis adapter for topology-static atom selection expressions."""

from __future__ import annotations

import re
from collections.abc import Sequence

import numpy as np

from mdhelper.core.errors import BackendError, SelectionError
from mdhelper.core.system import Atom

SELECTION_LANGUAGE = "MDAnalysis Atom Selection Language"
SELECTION_LANGUAGE_VERSION = "2.x-static-topology-1"

_DYNAMIC_KEYWORDS = frozenset(
    {"around", "sphzone", "sphlayer", "isolayer", "cyzone", "cylayer", "point", "prop"}
)


def _validate_static(expression: str) -> None:
    tokens = {
        token.casefold()
        for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", expression)
    }
    dynamic = sorted(tokens.intersection(_DYNAMIC_KEYWORDS))
    if dynamic or re.search(r"\bsame\s+[xyz]\s+as\b", expression, flags=re.IGNORECASE):
        raise SelectionError(
            "Coordinate-dependent atom selections are not supported.",
            "Use a topology-stable MDAnalysis selection. Dynamic spatial identity would "
            "change by frame and requires a separately versioned analysis method.",
            {"expression": expression, "coordinate_dependent_tokens": dynamic},
        )


class MDAnalysisSelectionEngine:
    """Adapt MDAnalysis' parser without exposing its objects outside this module."""

    language = SELECTION_LANGUAGE
    language_version = SELECTION_LANGUAGE_VERSION

    @staticmethod
    def _universe(atoms: Sequence[Atom]):
        try:
            import MDAnalysis as mda
        except ImportError as exc:
            raise BackendError(
                "MDAnalysis is required to parse atom selections.",
                "Install the declared project dependencies with 'uv sync'.",
            ) from exc
        if not atoms:
            raise SelectionError("Cannot resolve a selection against an empty topology.")
        residue_slots: dict[str, int] = {}
        residue_names: list[str] = []
        residue_ids: list[int] = []
        atom_resindex: list[int] = []
        for atom in atoms:
            if atom.molecule_id not in residue_slots:
                residue_slots[atom.molecule_id] = len(residue_slots)
                residue_names.append(atom.residue_name)
                residue_ids.append(atom.residue_id)
            atom_resindex.append(residue_slots[atom.molecule_id])
        universe = mda.Universe.empty(
            len(atoms),
            n_residues=len(residue_slots),
            atom_resindex=np.asarray(atom_resindex, dtype=np.int64),
            trajectory=True,
        )
        universe.add_TopologyAttr("names", [atom.name for atom in atoms])
        universe.add_TopologyAttr("types", [atom.element for atom in atoms])
        universe.add_TopologyAttr("elements", [atom.element for atom in atoms])
        universe.add_TopologyAttr("resnames", residue_names)
        universe.add_TopologyAttr("resids", residue_ids)
        universe.atoms.positions = np.zeros((len(atoms), 3), dtype=np.float32)
        return universe

    def resolve_many(
        self, atoms: Sequence[Atom], expressions: Sequence[str]
    ) -> tuple[tuple[int, ...], ...]:
        if not expressions:
            return ()
        for expression in expressions:
            if not expression.strip():
                raise SelectionError("An atom selection expression cannot be empty.")
            _validate_static(expression)
        universe = self._universe(atoms)
        resolved: list[tuple[int, ...]] = []
        for expression in expressions:
            try:
                indices = tuple(int(index) for index in universe.select_atoms(expression).indices)
            except Exception as exc:
                raise SelectionError(
                    f"Invalid {self.language} expression: {expression!r}",
                    "See docs/SELECTIONS.md. Available attributes depend on the topology; "
                    "common selectors include name, type, element, resname, resid, index, "
                    "and bynum, with and/or/not and parentheses.",
                    {
                        "expression": expression,
                        "language": self.language,
                        "language_version": self.language_version,
                        "parser_exception": f"{type(exc).__name__}: {exc}",
                    },
                ) from exc
            if not indices:
                raise SelectionError(
                    f"Selection {expression!r} did not match any atoms.",
                    "Run 'mdhelper inspect' to see available residue and atom names.",
                    {
                        "expression": expression,
                        "language": self.language,
                        "available_resnames": sorted({atom.residue_name for atom in atoms})[:50],
                        "available_atom_names": sorted({atom.name for atom in atoms})[:50],
                    },
                )
            resolved.append(indices)
        return tuple(resolved)
