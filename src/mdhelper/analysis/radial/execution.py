"""Radial analysis orchestration over interchangeable neighbor searches."""

from __future__ import annotations

from collections.abc import Callable
from threading import Event

from mdhelper.core.analysis import RadialRequest
from mdhelper.core.errors import BackendError, InputError
from mdhelper.core.progress import ProgressCallback
from mdhelper.core.trajectory import TrajectorySource
from mdhelper.services.selection import resolve_selections

from .curves import RadialAccumulator, RadialProfile, radial_grid
from .frames import RadialFrames
from .neighbors import DistanceSearch, mdanalysis_search

SearchFactory = Callable[[tuple[int, ...], tuple[int, ...]], DistanceSearch]


def mdanalysis_radial_profile(
    source: TrajectorySource,
    request: RadialRequest,
    progress_name: str,
    progress: ProgressCallback | None = None,
    cancel_event: Event | None = None,
) -> RadialProfile:
    if source.backend_name != "mdanalysis":
        raise BackendError("The MDAnalysis analysis backend requires MDAnalysis input.")
    return _run_profile(
        source,
        request,
        progress_name,
        mdanalysis_search,
        progress,
        cancel_event,
    )


def _run_profile(
    source: TrajectorySource,
    request: RadialRequest,
    progress_name: str,
    search_factory: SearchFactory,
    progress: ProgressCallback | None,
    cancel_event: Event | None,
) -> RadialProfile:
    raw_reference, raw_selection = resolve_selections(
        source.atoms,
        (request.reference, request.selection or ""),
        index_file=request.index_file,
    )
    reference = tuple(raw_reference)
    selection = tuple(raw_selection)
    overlap = len(set(reference).intersection(selection))
    possible_pairs = len(reference) * len(selection) - overlap
    normalization_pairs = len(reference) * len(selection)
    if possible_pairs <= 0:
        raise InputError("The selections contain no non-self atom pairs.")

    accumulator = RadialAccumulator(radial_grid(request), len(reference), len(selection))
    frames = RadialFrames(
        source,
        request.frames,
        request.r_max_nm,
        progress_name,
        progress,
        cancel_event,
    )
    search = search_factory(reference, selection)
    for frame in frames:
        for distances in search(frame, request.r_max_nm):
            accumulator.add_distances(distances)
        accumulator.complete_frame(frame.box.volume_nm3)
    return accumulator.profile(
        reference,
        selection,
        possible_pairs,
        normalization_pairs,
        frames.audit,
        request.bin_width_nm,
    )
