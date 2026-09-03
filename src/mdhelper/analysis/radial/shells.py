"""First-shell diagnostics derived from radial distribution curves."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


def _unavailable(reason: str, **evidence: object) -> dict[str, object]:
    return {
        "available": False,
        "reason": reason,
        **evidence,
    }


def first_shell(
    radii: NDArray[np.float64],
    rdf: NDArray[np.float64],
) -> dict[str, object]:
    """Resolve the first RDF peak and its following minimum."""

    if len(rdf) < 11 or not np.any(np.isfinite(rdf)):
        return _unavailable("insufficient_data")
    finite = np.nan_to_num(rdf, nan=0.0, posinf=0.0, neginf=0.0)
    window = min(11, len(finite) if len(finite) % 2 else len(finite) - 1)
    window = max(window, 5)
    smooth = _smooth(finite, window, min(3, window - 2))
    prominence_floor = max(0.05, float(np.max(smooth)) * 0.05)
    peaks, prominences = _prominent_peaks(smooth, prominence_floor)
    eligible = np.nonzero(peaks >= max(2, window // 2))[0]
    if not len(eligible):
        return _unavailable("no_resolved_first_peak")
    peak_position = int(eligible[0])
    peak_index = int(peaks[peak_position])
    minima, _ = _prominent_peaks(-smooth, max(0.02, prominence_floor / 2.0))
    minima = minima[minima > peak_index + 1]
    if not len(minima):
        return _unavailable(
            "no_resolved_minimum_after_peak",
            first_peak_index=peak_index,
            first_peak_nm=float(radii[peak_index]),
        )
    minimum_index = int(minima[0])
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
        "requires_user_confirmation": True,
    }


def first_shell_warnings(shell: dict[str, object]) -> list[str]:
    if not shell.get("available"):
        return [
            "No reliable RDF first minimum was found; no first-shell boundary was reported."
        ]
    return []


def _smooth(
    values: NDArray[np.float64],
    window: int,
    order: int,
) -> NDArray[np.float64]:
    """Apply a local polynomial filter without an optional numerical dependency."""

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
    values: NDArray[np.float64],
    peaks: NDArray[np.int64],
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
    values: NDArray[np.float64],
    floor: float,
) -> tuple[NDArray[np.int64], NDArray[np.float64]]:
    peaks = _peak_indices(values)
    prominence = _prominences(values, peaks)
    accepted = prominence >= floor
    return peaks[accepted], prominence[accepted]
