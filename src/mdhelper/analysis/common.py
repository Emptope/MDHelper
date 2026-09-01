from __future__ import annotations

import math
import tempfile
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from threading import Event

import numpy as np
from numpy.typing import NDArray

from mdhelper.core.errors import BackendError, InputError, TaskCancelled
from mdhelper.core.progress import ProgressCallback
from mdhelper.core.system import Box, Coordinates, Frame, FrameRange


@dataclass
class FrameAudit:
    count: int = 0
    first_index: int | None = None
    last_index: int | None = None
    first_time_ps: float | None = None
    last_time_ps: float | None = None

    def observe(self, frame: Frame) -> None:
        if self.count == 0:
            self.first_index = frame.index
            self.first_time_ps = frame.time_ps
        self.count += 1
        self.last_index = frame.index
        self.last_time_ps = frame.time_ps

    def to_dict(self) -> dict[str, int | float | None]:
        return {
            "count": self.count,
            "first_index": self.first_index,
            "last_index": self.last_index,
            "first_time_ps": self.first_time_ps,
            "last_time_ps": self.last_time_ps,
        }


@contextmanager
def analysis_directory(cache_dir: Path | None, name: str) -> Iterator[Path]:
    if cache_dir is None:
        with tempfile.TemporaryDirectory(prefix=f"mdhelper-{name}-") as directory:
            yield Path(directory)
        return
    root = cache_dir.expanduser().resolve()
    try:
        root.mkdir(parents=True, exist_ok=True)
        directory = tempfile.mkdtemp(prefix=f"{name}-", dir=root)
    except OSError as exc:
        raise BackendError(
            f"Could not prepare analysis cache directory: {root}",
            details={"exception": f"{type(exc).__name__}: {exc}"},
        ) from exc
    yield Path(directory)


def preprocessing_record() -> dict[str, str]:
    return {
        "coordinate_source": "stored trajectory coordinates converted to nm",
        "selection_identity": "resolved once from static topology",
        "unwrapping": "none",
        "alignment": "none",
        "distance_pbc": "triclinic minimum image per pair and frame",
    }


def selected_frame_count(n_frames: int | None, frame_range: FrameRange) -> int | None:
    if n_frames is None and frame_range.stop is None:
        return None
    if n_frames is None:
        stop = frame_range.stop
    else:
        stop = n_frames if frame_range.stop is None else min(frame_range.stop, n_frames)
    assert stop is not None
    return len(range(frame_range.start, stop, frame_range.stride))


def validate_frame_selection(
    n_frames: int | None,
    frame_range: FrameRange,
) -> int | None:
    if (
        n_frames is not None
        and frame_range.stop is not None
        and frame_range.stop > n_frames
    ):
        raise InputError(
            "The frame stop exceeds the trajectory frame count.\n"
            f"Total frame count: {n_frames}",
            "Use a stop no greater than the reported total frame count.",
            {
                "stop_frame": frame_range.stop,
                "total_frames": n_frames,
            },
        )
    count = selected_frame_count(n_frames, frame_range)
    if count is None:
        return None
    stop = frame_range.stop
    if n_frames is not None:
        stop = n_frames if stop is None else min(stop, n_frames)
    assert stop is not None
    available = max(0, stop - frame_range.start)
    if available > 1 and count == 1:
        raise InputError(
            "The frame stride selects only one frame from a multi-frame range.",
            "Reduce the stride or explicitly select a one-frame range.",
            {
                "available_frames": available,
                "selected_frames": count,
                "stride_frames": frame_range.stride,
            },
        )
    return count


def report_progress(
    callback: ProgressCallback | None,
    current: int,
    total: int | None,
    message: str,
) -> None:
    if callback:
        callback(current, total, message)


def check_cancel(cancel_event: Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise TaskCancelled()


def _matrix(box: Box) -> NDArray[np.float64]:
    value = np.asarray(box.vectors_nm, dtype=np.float64)
    if value.shape != (3, 3):
        raise InputError("A periodic box must contain three three-dimensional vectors.")
    return value


def periodic_radius_limit_nm(box: Box) -> float:
    """Half the smallest perpendicular cell height.

    Distances beyond this limit do not have an unambiguous spherical-shell normalization
    under the minimum-image convention.
    """

    matrix = _matrix(box)
    try:
        inverse = np.linalg.inv(matrix)
    except np.linalg.LinAlgError as exc:
        raise InputError("The periodic-box matrix is singular.") from exc
    heights = 1.0 / np.linalg.norm(inverse, axis=0)
    return float(np.min(heights) / 2.0)


def validate_radius(radius_nm: float, box: Box, label: str) -> None:
    limit = periodic_radius_limit_nm(box)
    tolerance = max(1e-12, limit * 1e-10)
    if radius_nm > limit + tolerance:
        raise InputError(
            f"{label}={radius_nm:g} nm exceeds this frame's reliable "
            f"minimum-image limit of {limit:g} nm.",
            "Reduce the distance/cutoff or verify the trajectory box.",
            {"requested_nm": radius_nm, "limit_nm": limit},
        )


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
    matrix = _matrix(box)
    inverse = np.linalg.inv(matrix)
    squared_cutoff = max_distance_nm * max_distance_nm
    reference_slots = np.arange(len(ref_ids), dtype=np.int64)
    selection_slots = np.arange(len(selection_ids), dtype=np.int64)
    total_pairs = len(ref_ids) * len(selection_ids)
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
