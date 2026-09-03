"""Radial grids, histogram accumulation, and curve normalization."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray

from mdhelper.core.analysis import RadialRequest

from .frames import FrameAudit


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


@dataclass
class RadialAccumulator:
    grid: RadialGrid
    reference_count: int
    selection_count: int
    histogram: NDArray[np.float64] = field(init=False)
    density_sum: float = field(default=0.0, init=False)
    reference_observations: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self.histogram = np.zeros(self.grid.fine_bins, dtype=np.float64)

    def add_distances(self, distances: NDArray[np.float64]) -> None:
        self.histogram += _fine_histogram(distances, self.grid)

    def complete_frame(self, volume_nm3: float) -> None:
        self.density_sum += self.selection_count / volume_nm3
        self.reference_observations += self.reference_count

    def profile(
        self,
        reference: tuple[int, ...],
        selection: tuple[int, ...],
        possible_pairs: int,
        normalization_pairs: int,
        audit: FrameAudit,
        bin_width_nm: float,
    ) -> RadialProfile:
        rdf_histogram = _rdf_histogram(self.histogram, len(self.grid.radius_nm))
        normalization = (
            self.reference_count * self.grid.shell_volumes_nm3 * self.density_sum
        )
        rdf = np.divide(
            rdf_histogram,
            normalization,
            out=np.zeros_like(rdf_histogram),
            where=normalization > 0,
        )
        cumulative_histogram = _cumulative_histogram(
            self.histogram,
            len(self.grid.cumulative_radius_nm),
        )
        cumulative_number = (
            np.cumsum(cumulative_histogram) / self.reference_observations
        )
        return RadialProfile(
            self.grid.radius_nm,
            rdf,
            self.grid.cumulative_radius_nm,
            cumulative_number,
            reference,
            selection,
            possible_pairs,
            normalization_pairs,
            audit,
            bin_width_nm,
        )


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
    distances: NDArray[np.float64],
    grid: RadialGrid,
) -> NDArray[np.float64]:
    indices = np.floor(distances / grid.fine_width_nm).astype(np.int64)
    indices = indices[(indices >= 0) & (indices < grid.fine_bins)]
    return np.bincount(indices, minlength=grid.fine_bins).astype(np.float64)


def _rdf_histogram(
    histogram: NDArray[np.float64],
    bins: int,
) -> NDArray[np.float64]:
    result = np.zeros(bins, dtype=np.float64)
    result[0] = histogram[0]
    if bins > 1:
        lower = histogram[1 : 2 * bins - 1 : 2]
        upper = histogram[2 : 2 * bins : 2]
        result[1:] = lower + upper
    return result


def _cumulative_histogram(
    histogram: NDArray[np.float64],
    bins: int,
) -> NDArray[np.float64]:
    return histogram[: 2 * bins].reshape(bins, 2).sum(axis=1)
