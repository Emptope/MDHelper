"""Periodic neighbor search for MDAnalysis radial analyses."""

from __future__ import annotations

from collections.abc import Callable, Iterator

import numpy as np
from numpy.typing import NDArray

from mdhelper.core.errors import BackendError
from mdhelper.core.system import Frame

DistanceSearch = Callable[
    [Frame, float],
    Iterator[NDArray[np.float64]],
]


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
