"""Request and selection preparation for the GROMACS pipeline."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from mdhelper.analysis.pipeline import AnalysisInput
from mdhelper.core.analysis import RadialRequest
from mdhelper.core.errors import BackendError
from mdhelper.core.system import FrameRange
from mdhelper.core.trajectory import TrajectorySource
from mdhelper.services.selection import resolve_selections, selection_resolution_record


def _request(inputs: AnalysisInput) -> RadialRequest:
    request = inputs.request
    if not isinstance(request, RadialRequest):
        raise BackendError("The GROMACS RDF backend requires a radial request.")
    return request

def _write_frame_index(indices: Sequence[int], path: Path) -> None:
    try:
        with path.open("w", encoding="ascii", newline="\n") as handle:
            handle.write("[ frames ]\n")
            for start in range(0, len(indices), 15):
                handle.write(
                    " ".join(str(index + 1) for index in indices[start : start + 15])
                )
                handle.write("\n")
    except OSError as exc:
        raise BackendError(
            "Could not write the GROMACS RDF frame index.",
            details={"exception": f"{type(exc).__name__}: {exc}"},
        ) from exc


def _requested_paths(request: RadialRequest) -> tuple[Path, Path]:
    return (
        Path(request.topology).expanduser().resolve(),
        Path(request.trajectory).expanduser().resolve(),
    )


def _requested_indices(
    frame_range: FrameRange,
    n_frames: int | None = None,
) -> tuple[int, ...]:
    stop = frame_range.stop
    if stop is None and n_frames is None:
        raise BackendError("An open-ended non-default frame range requires trajectory metadata.")
    if stop is None:
        stop = n_frames
    elif n_frames is not None:
        stop = min(stop, n_frames)
    assert stop is not None
    indices = tuple(range(frame_range.start, stop, frame_range.stride))
    if not indices:
        raise BackendError("The selected GROMACS RDF frame range is empty.")
    return indices


def _selection(value: str, index_file: str | None) -> str:
    if index_file is None:
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'group "{escaped}"'


def _selection_records(
    source: TrajectorySource | None,
    inputs: AnalysisInput,
) -> tuple[dict[str, object], int | None, int | None, int | None]:
    request = _request(inputs)
    if request.index_file is None:
        records: dict[str, object] = {
            "reference": {
                "expression": request.reference,
                "source": "gromacs_selection",
                "language": "GROMACS selection",
            },
            "selection": {
                "expression": request.selection or "",
                "source": "gromacs_selection",
                "language": "GROMACS selection",
            },
        }
        return records, None, None, None
    if source is None:
        records = {
            "reference": {
                "expression": request.reference,
                "source": "gromacs_index",
                "language": "GROMACS index group",
            },
            "selection": {
                "expression": request.selection or "",
                "source": "gromacs_index",
                "language": "GROMACS index group",
            },
        }
        return records, None, None, None
    reference, selection = resolve_selections(
        source.atoms,
        (request.reference, request.selection or ""),
        index_file=request.index_file,
    )
    overlap = len(set(reference).intersection(selection))
    possible_pairs = len(reference) * len(selection) - overlap
    records = {
        "reference": selection_resolution_record(
            request.reference, reference, source.atoms, request.index_file
        ),
        "selection": selection_resolution_record(
            request.selection or "", selection, source.atoms, request.index_file
        ),
    }
    return records, len(reference), len(selection), possible_pairs
