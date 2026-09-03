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


def _brute_pairs(
    positions: np.ndarray,
    reference: tuple[int, ...],
    selection: tuple[int, ...],
    box: Box,
    cutoff: float,
) -> dict[tuple[int, int], float]:
    matrix = np.asarray(box.vectors_nm, dtype=np.float64)
    inverse = np.linalg.inv(matrix)
    result: dict[tuple[int, int], float] = {}
    for reference_slot, reference_id in enumerate(reference):
        for selection_slot, selection_id in enumerate(selection):
            if reference_id == selection_id:
                continue
            delta = positions[selection_id] - positions[reference_id]
            fractional = delta @ inverse
            delta = (fractional - np.rint(fractional)) @ matrix
            distance = float(np.linalg.norm(delta))
            if distance <= cutoff:
                result[(reference_slot, selection_slot)] = distance
    return result


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


def test_orthogonal_search_matches_bounded_periodic_pairs() -> None:
    rng = np.random.default_rng(29)
    lengths = np.asarray((4.0, 5.0, 6.0))
    positions = rng.random((240, 3)) * lengths
    positions[:12] += np.asarray((4.0, -5.0, 6.0))
    reference = tuple(range(140))
    selection = tuple(range(50, 240))
    box = Box(((4.0, 0.0, 0.0), (0.0, 5.0, 0.0), (0.0, 0.0, 6.0)))

    expected = _brute_pairs(positions, reference, selection, box, 0.7)
    actual, largest = _pairs(
        positions,
        reference,
        selection,
        box,
        cutoff=0.7,
        chunk=128,
    )

    assert actual.keys() == expected.keys()
    assert actual == pytest.approx(expected)
    assert largest <= 128
