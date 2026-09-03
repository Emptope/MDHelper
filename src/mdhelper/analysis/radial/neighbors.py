"""Bounded periodic neighbor searches for radial analyses."""

from __future__ import annotations

import math
from collections.abc import Callable, Iterator, Sequence
from itertools import product

import numpy as np
from numpy.typing import NDArray

from mdhelper.core.errors import BackendError, InputError
from mdhelper.core.system import Box, Coordinates, Frame

from .frames import box_matrix

DistanceSearch = Callable[
    [Frame, float, int],
    Iterator[NDArray[np.float64]],
]


def native_search(
    reference: tuple[int, ...],
    selection: tuple[int, ...],
) -> DistanceSearch:
    def distances(
        frame: Frame,
        max_distance_nm: float,
        max_pairs_per_chunk: int,
    ) -> Iterator[NDArray[np.float64]]:
        for _reference, _selection, values in iter_neighbor_pairs(
            frame.positions_nm,
            reference,
            selection,
            frame.box,
            max_distance_nm,
            max_pairs_per_chunk,
        ):
            yield values

    return distances


def mdanalysis_search(
    reference: tuple[int, ...],
    selection: tuple[int, ...],
) -> DistanceSearch:
    try:
        from MDAnalysis.lib.distances import capped_distance
        from MDAnalysis.lib.mdamath import triclinic_box
    except ImportError as exc:
        raise BackendError("MDAnalysis is required for the MDAnalysis RDF backend.") from exc

    reference_array = np.asarray(reference, dtype=np.int64)
    selection_array = np.asarray(selection, dtype=np.int64)

    def distances(
        frame: Frame,
        max_distance_nm: float,
        _max_pairs_per_chunk: int,
    ) -> Iterator[NDArray[np.float64]]:
        vectors = np.asarray(frame.box.vectors_nm, dtype=np.float64)
        dimensions = triclinic_box(vectors[0], vectors[1], vectors[2])
        pairs, values = capped_distance(
            frame.positions_nm[reference_array],
            frame.positions_nm[selection_array],
            max_distance_nm,
            box=dimensions,
            return_distances=True,
        )
        if len(pairs):
            keep = reference_array[pairs[:, 0]] != selection_array[pairs[:, 1]]
            yield np.asarray(values[keep], dtype=np.float64)

    return distances


def iter_neighbor_pairs(
    positions_nm: Coordinates,
    reference_indices: Sequence[int],
    selection_indices: Sequence[int],
    box: Box,
    max_distance_nm: float,
    max_pairs_per_chunk: int = 500_000,
) -> Iterator[tuple[NDArray[np.int64], NDArray[np.int64], NDArray[np.float64]]]:
    """Yield neighbor pair slots without materializing the full distance matrix."""

    coordinates = np.asarray(positions_nm, dtype=np.float64)
    ref_ids = np.asarray(reference_indices, dtype=np.int64)
    selection_ids = np.asarray(selection_indices, dtype=np.int64)
    if coordinates.ndim != 2 or coordinates.shape[1] != 3:
        raise InputError("Coordinates must have shape (n_atoms, 3).")
    matrix = box_matrix(box)
    squared_cutoff = max_distance_nm * max_distance_nm
    reference_slots = np.arange(len(ref_ids), dtype=np.int64)
    selection_slots = np.arange(len(selection_ids), dtype=np.int64)
    total_pairs = len(ref_ids) * len(selection_ids)
    lengths = _orthogonal_lengths(matrix)
    if lengths is not None and total_pairs > max_pairs_per_chunk:
        yield from _iter_orthogonal_pairs(
            coordinates,
            ref_ids,
            selection_ids,
            lengths,
            max_distance_nm,
            max_pairs_per_chunk,
        )
        return
    inverse = np.linalg.inv(matrix)
    cell_groups = _cell_groups(
        coordinates,
        ref_ids,
        selection_ids,
        inverse,
        max_distance_nm,
        total_pairs,
        max_pairs_per_chunk,
    )
    if cell_groups is None:
        yield from _iter_pair_blocks(
            coordinates,
            ref_ids,
            selection_ids,
            reference_slots,
            selection_slots,
            matrix,
            inverse,
            squared_cutoff,
            max_pairs_per_chunk,
        )
        return
    for grouped_reference, grouped_selection in cell_groups:
        yield from _iter_pair_blocks(
            coordinates,
            ref_ids,
            selection_ids,
            grouped_reference,
            grouped_selection,
            matrix,
            inverse,
            squared_cutoff,
            max_pairs_per_chunk,
        )


def _orthogonal_lengths(matrix: NDArray[np.float64]) -> NDArray[np.float64] | None:
    lengths = np.diag(matrix)
    if np.any(lengths <= 0.0) or np.count_nonzero(matrix - np.diag(lengths)):
        return None
    return lengths


def _iter_orthogonal_pairs(
    coordinates: NDArray[np.float64],
    ref_ids: NDArray[np.int64],
    selection_ids: NDArray[np.int64],
    lengths: NDArray[np.float64],
    cutoff: float,
    max_pairs_per_chunk: int,
) -> Iterator[tuple[NDArray[np.int64], NDArray[np.int64], NDArray[np.float64]]]:
    from scipy.spatial import cKDTree

    reference = np.mod(coordinates[ref_ids], lengths)
    selection = np.mod(coordinates[selection_ids], lengths)
    for selection_start in range(0, len(selection), max_pairs_per_chunk):
        selection_stop = min(selection_start + max_pairs_per_chunk, len(selection))
        selection_block = selection[selection_start:selection_stop]
        selection_tree = cKDTree(selection_block, boxsize=lengths)
        counts = np.asarray(
            selection_tree.query_ball_point(reference, cutoff, return_length=True),
            dtype=np.int64,
        )
        for reference_start, reference_stop in _count_blocks(
            counts, max_pairs_per_chunk
        ):
            reference_tree = cKDTree(
                reference[reference_start:reference_stop], boxsize=lengths
            )
            pairs = reference_tree.sparse_distance_matrix(
                selection_tree,
                cutoff,
                output_type="coo_matrix",
            )
            local_reference = np.asarray(pairs.row, dtype=np.int64)
            local_selection = np.asarray(pairs.col, dtype=np.int64)
            reference_slots = local_reference + reference_start
            selection_slots = local_selection + selection_start
            keep = ref_ids[reference_slots] != selection_ids[selection_slots]
            if np.any(keep):
                yield (
                    reference_slots[keep],
                    selection_slots[keep],
                    np.asarray(pairs.data[keep], dtype=np.float64),
                )


def _count_blocks(
    counts: NDArray[np.int64], limit: int
) -> Iterator[tuple[int, int]]:
    start = 0
    total = 0
    for stop, value in enumerate(counts, start=1):
        count = int(value)
        if total and total + count > limit:
            yield start, stop - 1
            start = stop - 1
            total = 0
        total += count
        if total == limit:
            yield start, stop
            start = stop
            total = 0
    if start < len(counts):
        yield start, len(counts)


def _iter_pair_blocks(
    coordinates: NDArray[np.float64],
    ref_ids: NDArray[np.int64],
    selection_ids: NDArray[np.int64],
    reference_slots: NDArray[np.int64],
    selection_slots: NDArray[np.int64],
    matrix: NDArray[np.float64],
    inverse: NDArray[np.float64],
    squared_cutoff: float,
    max_pairs_per_chunk: int,
) -> Iterator[tuple[NDArray[np.int64], NDArray[np.int64], NDArray[np.float64]]]:
    selection_chunk = max(
        1, min(len(selection_slots), int(math.sqrt(max_pairs_per_chunk)))
    )
    reference_chunk = max(1, max_pairs_per_chunk // selection_chunk)
    for ref_start in range(0, len(reference_slots), reference_chunk):
        ref_stop = min(ref_start + reference_chunk, len(reference_slots))
        ref_block_slots = reference_slots[ref_start:ref_stop]
        ref_block_ids = ref_ids[ref_block_slots]
        ref_coordinates = coordinates[ref_block_ids]
        for selection_start in range(0, len(selection_slots), selection_chunk):
            selection_stop = min(selection_start + selection_chunk, len(selection_slots))
            selection_block_slots = selection_slots[selection_start:selection_stop]
            selection_block_ids = selection_ids[selection_block_slots]
            selection_coordinates = coordinates[selection_block_ids]
            delta = selection_coordinates[None, :, :] - ref_coordinates[:, None, :]
            fractional = delta @ inverse
            fractional -= np.rint(fractional)
            delta = fractional @ matrix
            distance_squared = np.einsum("ijk,ijk->ij", delta, delta)
            not_self = ref_block_ids[:, None] != selection_block_ids[None, :]
            mask = not_self & (distance_squared <= squared_cutoff)
            local_ref, local_selection = np.nonzero(mask)
            if local_ref.size:
                yield (
                    ref_block_slots[local_ref],
                    selection_block_slots[local_selection],
                    np.sqrt(distance_squared[local_ref, local_selection]),
                )


def _cell_groups(
    coordinates: NDArray[np.float64],
    ref_ids: NDArray[np.int64],
    selection_ids: NDArray[np.int64],
    inverse: NDArray[np.float64],
    cutoff: float,
    total_pairs: int,
    max_pairs_per_chunk: int,
) -> Iterator[tuple[NDArray[np.int64], NDArray[np.int64]]] | None:
    if cutoff <= 0.0 or total_pairs <= max_pairs_per_chunk:
        return None
    fractional_limit = cutoff * np.linalg.norm(inverse, axis=0)
    if np.any(fractional_limit <= 0.0):
        return None
    raw_cell_counts = np.floor(1.0 / fractional_limit)
    max_axis_cells = max(1, len(ref_ids) + len(selection_ids))
    cell_counts = np.asarray(
        [
            max(1, min(max_axis_cells, int(value)))
            if math.isfinite(float(value))
            else max_axis_cells
            for value in raw_cell_counts
        ],
        dtype=np.int64,
    )
    while math.prod(int(value) for value in cell_counts) > np.iinfo(np.int64).max:
        axis = int(np.argmax(cell_counts))
        cell_counts[axis] = max(1, int(cell_counts[axis]) // 2)
    cell_ranges = np.ceil(fractional_limit * cell_counts).astype(np.int64)
    neighbor_counts = np.minimum(cell_counts, 2 * cell_ranges + 1)
    cell_total = math.prod(int(value) for value in cell_counts)
    neighbor_total = math.prod(int(value) for value in neighbor_counts)
    if neighbor_total * 2 >= cell_total:
        return None
    estimated_candidates = math.ceil(total_pairs * neighbor_total / cell_total)
    search_work = len(ref_ids) + len(selection_ids) + estimated_candidates
    if search_work * 2 >= total_pairs:
        return None

    reference_fractional = coordinates[ref_ids] @ inverse
    reference_fractional -= np.floor(reference_fractional)
    selection_fractional = coordinates[selection_ids] @ inverse
    selection_fractional -= np.floor(selection_fractional)
    reference_cells = _cell_keys(reference_fractional, cell_counts)
    selection_cells = _cell_keys(selection_fractional, cell_counts)
    reference_groups = _group_slots(reference_cells)
    selection_groups = dict(_group_slots(selection_cells))
    offsets = tuple(
        product(
            range(-int(cell_ranges[0]), int(cell_ranges[0]) + 1),
            range(-int(cell_ranges[1]), int(cell_ranges[1]) + 1),
            range(-int(cell_ranges[2]), int(cell_ranges[2]) + 1),
        )
    )

    def iter_groups() -> Iterator[tuple[NDArray[np.int64], NDArray[np.int64]]]:
        yz = int(cell_counts[1]) * int(cell_counts[2])
        z_count = int(cell_counts[2])
        for key, grouped_reference in reference_groups:
            x = key // yz
            remainder = key % yz
            y = remainder // z_count
            z = remainder % z_count
            grouped: list[NDArray[np.int64]] = []
            seen: set[int] = set()
            for offset_x, offset_y, offset_z in offsets:
                cell_x = (x + offset_x) % int(cell_counts[0])
                cell_y = (y + offset_y) % int(cell_counts[1])
                cell_z = (z + offset_z) % z_count
                neighbor = cell_x * yz + cell_y * z_count + cell_z
                if neighbor in seen:
                    continue
                seen.add(neighbor)
                slots = selection_groups.get(neighbor)
                if slots is not None:
                    grouped.append(slots)
            if grouped:
                yield grouped_reference, np.concatenate(grouped)

    return iter_groups()


def _cell_keys(
    fractional: NDArray[np.float64], cell_counts: NDArray[np.int64]
) -> NDArray[np.int64]:
    cells = np.floor(fractional * cell_counts).astype(np.int64)
    cells %= cell_counts
    return np.asarray(
        cells[:, 0] * cell_counts[1] * cell_counts[2]
        + cells[:, 1] * cell_counts[2]
        + cells[:, 2],
        dtype=np.int64,
    )


def _group_slots(
    keys: NDArray[np.int64],
) -> tuple[tuple[int, NDArray[np.int64]], ...]:
    order = np.argsort(keys, kind="stable")
    ordered = keys[order]
    boundaries = np.flatnonzero(np.diff(ordered)) + 1
    starts = np.concatenate((np.zeros(1, dtype=np.int64), boundaries))
    stops = np.concatenate((boundaries, np.asarray([len(order)], dtype=np.int64)))
    return tuple(
        (int(ordered[start]), order[start:stop])
        for start, stop in zip(starts, stops, strict=True)
    )
