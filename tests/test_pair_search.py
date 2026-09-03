from __future__ import annotations

import numpy as np
import pytest

from mdhelper.analysis.radial.neighbors import iter_neighbor_pairs
from mdhelper.core.system import Box


def _pairs(
    positions: np.ndarray,
    reference: tuple[int, ...],
    selection: tuple[int, ...],
    box: Box,
    cutoff: float,
    chunk: int,
) -> tuple[dict[tuple[int, int], float], int]:
    result: dict[tuple[int, int], float] = {}
    largest = 0
    for reference_slots, selection_slots, distances in iter_neighbor_pairs(
        positions,
        reference,
        selection,
        box,
        cutoff,
        chunk,
    ):
        largest = max(largest, len(distances))
        for reference_slot, selection_slot, distance in zip(
            reference_slots, selection_slots, distances, strict=True
        ):
            key = (int(reference_slot), int(selection_slot))
            assert key not in result
            result[key] = float(distance)
    return result, largest


def test_periodic_cell_search_matches_direct_triclinic_pairs() -> None:
    rng = np.random.default_rng(17)
    matrix = np.asarray(
        (
            (4.0, 0.0, 0.0),
            (1.2, 3.5, 0.0),
            (0.4, 0.7, 3.8),
        )
    )
    fractional = rng.random((160, 3))
    fractional[:8] += np.asarray((1.0, -1.0, 0.0))
    positions = fractional @ matrix
    reference = tuple(range(100))
    selection = tuple(range(50, 160))
    box = Box(tuple(tuple(float(value) for value in row) for row in matrix))

    direct, _ = _pairs(
        positions,
        reference,
        selection,
        box,
        cutoff=0.4,
        chunk=len(reference) * len(selection),
    )
    cells, largest = _pairs(
        positions,
        reference,
        selection,
        box,
        cutoff=0.4,
        chunk=64,
    )

    assert cells.keys() == direct.keys()
    assert cells == pytest.approx(direct)
    assert largest <= 64
    assert all(reference[ref] != selection[sel] for ref, sel in cells)
