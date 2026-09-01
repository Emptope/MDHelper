"""Shared radial pair accumulation for RDF and cumulative RDF analyses."""

from __future__ import annotations

import math
from dataclasses import dataclass
from threading import Event

import numpy as np
from numpy.typing import NDArray

from mdhelper.core.analysis import RadialRequest
from mdhelper.core.errors import BackendError, InputError
from mdhelper.core.trajectory import TrajectorySource
from mdhelper.services.selection import resolve_selections

from .common import (
    FrameAudit,
    ProgressCallback,
    check_cancel,
    iter_neighbor_pairs,
    report_progress,
    selected_frame_count,
    validate_radius,
)


@dataclass(frozen=True)
class RadialProfile:
    radius_nm: NDArray[np.float64]
    rdf: NDArray[np.float64]
    cumulative_radius_nm: NDArray[np.float64]
    cumulative_number: NDArray[np.float64]
    reference: tuple[int, ...]
    selection: tuple[int, ...]
    possible_pairs: int
    normalization_pairs: int
    audit: FrameAudit
    bin_width_nm: float


@dataclass(frozen=True)
class RadialGrid:
    fine_width_nm: float
    fine_bins: int
    radius_nm: NDArray[np.float64]
    shell_volumes_nm3: NDArray[np.float64]
    cumulative_radius_nm: NDArray[np.float64]


def radial_grid(request: RadialRequest) -> RadialGrid:
    """Build the shared half-width histogram and radial output grids."""

    width = request.bin_width_nm
    fine_bins = request.radial_fine_bin_count()
    rdf_bins = request.radial_bin_count()
    cumulative_bins = request.cumulative_bin_count()
    radius = np.round(np.arange(rdf_bins, dtype=np.float64) * width, decimals=15)
    shell_edges = np.concatenate(
        (
            np.zeros(1, dtype=np.float64),
            (np.arange(rdf_bins, dtype=np.float64) + 0.5) * width,
        )
    )
    shell_volumes = (4.0 * math.pi / 3.0) * (
        shell_edges[1:] ** 3 - shell_edges[:-1] ** 3
    )
    cumulative_radius = np.round(
        (np.arange(cumulative_bins, dtype=np.float64) + 1.0) * width,
        decimals=15,
    )
    return RadialGrid(
        width / 2.0,
        fine_bins,
        radius,
        shell_volumes,
        cumulative_radius,
    )


def _fine_histogram(
    distances: NDArray[np.float64], grid: RadialGrid
) -> NDArray[np.float64]:
    indices = np.floor(distances / grid.fine_width_nm).astype(np.int64)
    indices = indices[(indices >= 0) & (indices < grid.fine_bins)]
    return np.bincount(indices, minlength=grid.fine_bins).astype(np.float64)


def _rdf_histogram(
    histogram: NDArray[np.float64], bins: int
) -> NDArray[np.float64]:
    result = np.zeros(bins, dtype=np.float64)
    result[0] = histogram[0]
    if bins > 1:
        lower = histogram[1 : 2 * bins - 1 : 2]
        upper = histogram[2 : 2 * bins : 2]
        result[1:] = lower + upper
    return result


def _cumulative_histogram(
    histogram: NDArray[np.float64], bins: int
) -> NDArray[np.float64]:
    return histogram[: 2 * bins].reshape(bins, 2).sum(axis=1)


def _smooth(values: NDArray[np.float64], window: int, order: int) -> NDArray[np.float64]:
    """Apply a local polynomial filter without importing the SciPy package."""

    half = window // 2
    result = np.empty_like(values)
    edge_x = np.arange(window, dtype=np.float64)
    edge_fit = np.linalg.pinv(np.vander(edge_x, order + 1, increasing=True))
    left = values[:window]
    right = values[-window:]
    result[:half] = (
        np.vander(edge_x[:half], order + 1, increasing=True) @ edge_fit @ left
    )
    result[-half:] = (
        np.vander(edge_x[-half:], order + 1, increasing=True) @ edge_fit @ right
    )

    local_x = np.arange(-half, half + 1, dtype=np.float64)
    local_fit = np.linalg.pinv(np.vander(local_x, order + 1, increasing=True))
    center = local_fit[0]
    for index in range(half, len(values) - half):
        result[index] = center @ values[index - half : index + half + 1]
    return result


def _peak_indices(values: NDArray[np.float64]) -> NDArray[np.int64]:
    """Return local peak indices, selecting the middle of a flat peak."""

    peaks: list[int] = []
    index = 1
    while index < len(values) - 1:
        if values[index] <= values[index - 1]:
            index += 1
            continue
        end = index
        while end + 1 < len(values) and values[end + 1] == values[index]:
            end += 1
        if end < len(values) - 1 and values[end] > values[end + 1]:
            peaks.append((index + end) // 2)
        index = end + 1
    return np.asarray(peaks, dtype=np.int64)


def _prominences(
    values: NDArray[np.float64], peaks: NDArray[np.int64]
) -> NDArray[np.float64]:
    """Measure peak prominence against the higher surrounding base."""

    result = np.empty(len(peaks), dtype=np.float64)
    for position, raw_peak in enumerate(peaks):
        peak = int(raw_peak)
        height = values[peak]
        left_base = height
        for index in range(peak - 1, -1, -1):
            if values[index] > height:
                break
            left_base = min(left_base, values[index])
        right_base = height
        for index in range(peak + 1, len(values)):
            if values[index] > height:
                break
            right_base = min(right_base, values[index])
        result[position] = height - max(left_base, right_base)
    return result


def _prominent_peaks(
    values: NDArray[np.float64], floor: float
) -> tuple[NDArray[np.int64], NDArray[np.float64]]:
    peaks = _peak_indices(values)
    prominence = _prominences(values, peaks)
    accepted = prominence >= floor
    return peaks[accepted], prominence[accepted]


def first_shell(radii: NDArray[np.float64], rdf: NDArray[np.float64]) -> dict[str, object]:
    """Resolve the first RDF peak and its following minimum."""

    if len(rdf) < 11 or not np.any(np.isfinite(rdf)):
        return {"available": False, "reason": "insufficient_data"}
    finite = np.nan_to_num(rdf, nan=0.0, posinf=0.0, neginf=0.0)
    window = min(11, len(finite) if len(finite) % 2 else len(finite) - 1)
    window = max(window, 5)
    smooth = _smooth(finite, window, min(3, window - 2))
    prominence_floor = max(0.05, float(np.max(smooth)) * 0.05)
    peaks, prominences = _prominent_peaks(smooth, prominence_floor)
    eligible = np.nonzero(peaks >= max(2, window // 2))[0]
    if not len(eligible):
        return {"available": False, "reason": "no_resolved_first_peak"}
    peak_position = int(eligible[0])
    peak_index = int(peaks[peak_position])
    minima, _ = _prominent_peaks(-smooth, max(0.02, prominence_floor / 2.0))
    minima = minima[minima > peak_index + 1]
    if not len(minima):
        return {
            "available": False,
            "reason": "no_resolved_minimum_after_peak",
            "first_peak_index": peak_index,
            "first_peak_nm": float(radii[peak_index]),
        }
    minimum_index = int(minima[0])
    peak_value = float(smooth[peak_index])
    minimum_value = float(smooth[minimum_index])
    contrast = peak_value - minimum_value
    confidence = "high" if contrast >= 0.5 else "medium" if contrast >= 0.2 else "low"
    return {
        "available": True,
        "method": "Savitzky-Golay smoothing + first prominent peak/minimum",
        "first_peak_index": peak_index,
        "first_peak_nm": float(radii[peak_index]),
        "first_peak_g_r": float(rdf[peak_index]),
        "first_peak_prominence": float(prominences[peak_position]),
        "first_minimum_index": minimum_index,
        "first_minimum_nm": float(radii[minimum_index]),
        "first_minimum_g_r": float(rdf[minimum_index]),
        "confidence": confidence,
        "requires_user_confirmation": True,
    }


def first_shell_warnings(shell: dict[str, object]) -> list[str]:
    if shell.get("confidence") == "low":
        return [
            "The RDF first-shell boundary has low confidence; inspect the RDF before use."
        ]
    if not shell.get("available"):
        return [
            "No reliable RDF first minimum was found; no first-shell boundary was reported."
        ]
    return []


def radial_profile(
    source: TrajectorySource,
    request: RadialRequest,
    progress_name: str,
    progress: ProgressCallback | None = None,
    cancel_event: Event | None = None,
    max_pairs_per_chunk: int = 500_000,
) -> RadialProfile:
    reference, selection = resolve_selections(
        source.atoms,
        (request.reference, request.selection or ""),
        index_file=request.index_file,
    )
    grid = radial_grid(request)
    histogram = np.zeros(grid.fine_bins, dtype=np.float64)
    density_sum = 0.0
    total_reference_observations = 0
    overlap = len(set(reference).intersection(selection))
    possible_pairs = len(reference) * len(selection) - overlap
    normalization_pairs = len(reference) * len(selection)
    if possible_pairs <= 0:
        raise InputError("The selections contain no non-self atom pairs.")

    audit = FrameAudit()
    total = selected_frame_count(source.n_frames, request.frames)

    for frame in source.iter_frames(request.frames):
        check_cancel(cancel_event)
        validate_radius(request.r_max_nm, frame.box, "r_max_nm")
        for _, _, distances in iter_neighbor_pairs(
            frame.positions_nm,
            reference,
            selection,
            frame.box,
            request.r_max_nm,
            max_pairs_per_chunk,
        ):
            histogram += _fine_histogram(distances, grid)
        density_sum += len(selection) / frame.box.volume_nm3
        total_reference_observations += len(reference)
        audit.observe(frame)
        report_progress(progress, audit.count, total, f"{progress_name} frame {frame.index}")

    rdf_histogram = _rdf_histogram(histogram, len(grid.radius_nm))
    normalization = len(reference) * grid.shell_volumes_nm3 * density_sum
    rdf = np.divide(
        rdf_histogram,
        normalization,
        out=np.zeros_like(rdf_histogram),
        where=normalization > 0,
    )
    cumulative_histogram = _cumulative_histogram(
        histogram, len(grid.cumulative_radius_nm)
    )
    cumulative_number = (
        np.cumsum(cumulative_histogram) / total_reference_observations
    )
    return RadialProfile(
        grid.radius_nm,
        rdf,
        grid.cumulative_radius_nm,
        cumulative_number,
        tuple(reference),
        tuple(selection),
        possible_pairs,
        normalization_pairs,
        audit,
        request.bin_width_nm,
    )


def mdanalysis_radial_profile(
    source: TrajectorySource,
    request: RadialRequest,
    progress_name: str,
    progress: ProgressCallback | None = None,
    cancel_event: Event | None = None,
    _max_pairs_per_chunk: int = 500_000,
) -> RadialProfile:
    if source.backend_name != "mdanalysis":
        raise BackendError("The MDAnalysis analysis backend requires MDAnalysis input.")
    try:
        from MDAnalysis.lib.distances import capped_distance
        from MDAnalysis.lib.mdamath import triclinic_box
    except ImportError as exc:
        raise BackendError("MDAnalysis is required for the MDAnalysis RDF backend.") from exc

    reference, selection = resolve_selections(
        source.atoms,
        (request.reference, request.selection or ""),
        index_file=request.index_file,
    )
    grid = radial_grid(request)
    histogram = np.zeros(grid.fine_bins, dtype=np.float64)
    density_sum = 0.0
    total_reference_observations = 0
    reference_array = np.asarray(reference, dtype=np.int64)
    selection_array = np.asarray(selection, dtype=np.int64)
    overlap = len(set(reference).intersection(selection))
    possible_pairs = len(reference) * len(selection) - overlap
    normalization_pairs = len(reference) * len(selection)
    if possible_pairs <= 0:
        raise InputError("The selections contain no non-self atom pairs.")

    audit = FrameAudit()
    total = selected_frame_count(source.n_frames, request.frames)
    for frame in source.iter_frames(request.frames):
        check_cancel(cancel_event)
        validate_radius(request.r_max_nm, frame.box, "r_max_nm")
        vectors = np.asarray(frame.box.vectors_nm, dtype=np.float64)
        dimensions = triclinic_box(vectors[0], vectors[1], vectors[2])
        pairs, distances = capped_distance(
            frame.positions_nm[reference_array],
            frame.positions_nm[selection_array],
            request.r_max_nm,
            box=dimensions,
            return_distances=True,
        )
        if len(pairs):
            keep = reference_array[pairs[:, 0]] != selection_array[pairs[:, 1]]
            histogram += _fine_histogram(
                np.asarray(distances[keep], dtype=np.float64), grid
            )
        density_sum += len(selection) / frame.box.volume_nm3
        total_reference_observations += len(reference)
        audit.observe(frame)
        report_progress(progress, audit.count, total, f"{progress_name} frame {frame.index}")

    rdf_histogram = _rdf_histogram(histogram, len(grid.radius_nm))
    normalization = len(reference) * grid.shell_volumes_nm3 * density_sum
    rdf = np.divide(
        rdf_histogram,
        normalization,
        out=np.zeros_like(rdf_histogram),
        where=normalization > 0,
    )
    cumulative_histogram = _cumulative_histogram(
        histogram, len(grid.cumulative_radius_nm)
    )
    cumulative_number = np.cumsum(cumulative_histogram) / total_reference_observations
    return RadialProfile(
        grid.radius_nm,
        rdf,
        grid.cumulative_radius_nm,
        cumulative_number,
        tuple(reference),
        tuple(selection),
        possible_pairs,
        normalization_pairs,
        audit,
        request.bin_width_nm,
    )
