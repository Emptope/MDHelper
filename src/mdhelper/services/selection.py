"""Selection orchestration and provenance over interchangeable engines."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from pathlib import Path

from mdhelper.backends.mdanalysis import (
    SELECTION_LANGUAGE,
    SELECTION_LANGUAGE_VERSION,
    MDAnalysisSelectionEngine,
)
from mdhelper.core.errors import SelectionError
from mdhelper.core.selection import SelectionEngine
from mdhelper.core.system import Atom
from mdhelper.io.files import sha256_file
from mdhelper.io.ndx import (
    NDX_SELECTION_LANGUAGE,
    NDX_SELECTION_LANGUAGE_VERSION,
    NdxSelectionEngine,
    load_groups,
)

DEFAULT_SELECTION_ENGINE: SelectionEngine = MDAnalysisSelectionEngine()


def resolve_selections(
    atoms: Sequence[Atom],
    expressions: Sequence[str],
    engine: SelectionEngine | None = None,
    *,
    index_file: str | Path | None = None,
) -> tuple[tuple[int, ...], ...]:
    if engine is not None and index_file is not None:
        raise SelectionError("Specify either a selection engine or a GROMACS index file, not both.")
    selected_engine = NdxSelectionEngine(index_file) if index_file is not None else engine
    return (selected_engine or DEFAULT_SELECTION_ENGINE).resolve_many(atoms, expressions)


def resolve_selection(
    atoms: Sequence[Atom],
    expression: str,
    engine: SelectionEngine | None = None,
    *,
    index_file: str | Path | None = None,
) -> tuple[int, ...]:
    return resolve_selections(atoms, (expression,), engine, index_file=index_file)[0]


def selection_resolution_record(
    expression: str,
    indices: Sequence[int],
    atoms: Sequence[Atom],
    index_file: str | Path | None = None,
) -> dict[str, object]:
    digest = hashlib.sha256(",".join(str(index) for index in indices).encode("ascii")).hexdigest()
    record: dict[str, object] = {
        "expression": expression,
        "n_atoms": len(indices),
        "zero_based_indices_sha256": digest,
        "atom_names": sorted({atoms[index].name for index in indices}),
        "residue_names": sorted({atoms[index].residue_name for index in indices}),
    }
    if index_file is None:
        record.update(
            {
                "source": "expression",
                "language": SELECTION_LANGUAGE,
                "language_version": SELECTION_LANGUAGE_VERSION,
            }
        )
    else:
        path = Path(index_file).expanduser().resolve()
        record.update(
            {
                "source": "gromacs_index",
                "group": expression,
                "language": NDX_SELECTION_LANGUAGE,
                "language_version": NDX_SELECTION_LANGUAGE_VERSION,
                "index_file": str(path),
                "index_file_sha256": sha256_file(path),
            }
        )
    return record


def index_group_sizes(index_file: str | Path, n_atoms: int) -> dict[str, int]:
    """Return ordered group sizes for inspection without exposing parser internals."""

    _, groups = load_groups(index_file, n_atoms)
    return {name: len(indices) for name, indices in groups.items()}


__all__ = [
    "NDX_SELECTION_LANGUAGE",
    "NDX_SELECTION_LANGUAGE_VERSION",
    "SELECTION_LANGUAGE",
    "SELECTION_LANGUAGE_VERSION",
    "MDAnalysisSelectionEngine",
    "NdxSelectionEngine",
    "index_group_sizes",
    "resolve_selection",
    "resolve_selections",
    "selection_resolution_record",
]
