from __future__ import annotations

import math
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from threading import Event

import numpy as np
from numpy.typing import NDArray

from mdhelper.core.errors import InputError, TaskCancelled
from mdhelper.core.progress import ProgressCallback
from mdhelper.core.system import Box, Frame, FrameRange


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


def preprocessing_record() -> dict[str, str]:
    return {
        "coordinate_source": "stored trajectory coordinates converted to nm",
        "selection_identity": "resolved once from static topology",
        "unwrapping": "none",
        "alignment": "none",
        "distance_pbc": "triclinic minimum image per pair and frame",
    }


def selected_frame_count(n_frames: int | None, frame_range: FrameRange) -> int | None:
    if n_frames is None:
        return None
    stop = n_frames if frame_range.stop is None else min(frame_range.stop, n_frames)
    return len(range(frame_range.start, stop, frame_range.stride))


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
    positions_nm: Sequence[Sequence[float]],
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
    selection_chunk = max(
        1, min(len(selection_ids), int(math.sqrt(max_pairs_per_chunk)))
    )
    reference_chunk = max(1, max_pairs_per_chunk // selection_chunk)
    squared_cutoff = max_distance_nm * max_distance_nm
    for ref_start in range(0, len(ref_ids), reference_chunk):
        ref_stop = min(ref_start + reference_chunk, len(ref_ids))
        ref_block_ids = ref_ids[ref_start:ref_stop]
        ref_coordinates = coordinates[ref_block_ids]
        for selection_start in range(0, len(selection_ids), selection_chunk):
            selection_stop = min(selection_start + selection_chunk, len(selection_ids))
            selection_block_ids = selection_ids[selection_start:selection_stop]
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
                    local_ref.astype(np.int64, copy=False) + ref_start,
                    local_selection.astype(np.int64, copy=False) + selection_start,
                    np.sqrt(distance_squared[local_ref, local_selection]),
                )
