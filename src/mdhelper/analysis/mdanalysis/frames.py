"""Frame iteration and periodic-box validation for the MDAnalysis pipeline."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from threading import Event

import numpy as np
from numpy.typing import NDArray

from mdhelper.analysis.common import check_cancel, report_progress
from mdhelper.analysis.radial import FrameAudit, validate_frame_selection
from mdhelper.core.errors import InputError
from mdhelper.core.progress import ProgressCallback
from mdhelper.core.system import Box, Frame, FrameRange
from mdhelper.core.trajectory import TrajectorySource


@dataclass
class RadialFrames:
    source: TrajectorySource
    frame_range: FrameRange
    radius_nm: float
    progress_name: str
    progress: ProgressCallback | None = None
    cancel_event: Event | None = None
    audit: FrameAudit = field(default_factory=FrameAudit, init=False)

    def __iter__(self) -> Iterator[Frame]:
        total = validate_frame_selection(self.source.n_frames, self.frame_range)
        for frame in self.source.iter_frames(self.frame_range):
            check_cancel(self.cancel_event)
            validate_radius(self.radius_nm, frame.box, "r_max_nm")
            yield frame
            self.audit.observe(frame)
            report_progress(
                self.progress,
                self.audit.count,
                total,
                f"{self.progress_name} frame {frame.index}",
            )


def preprocessing_record() -> dict[str, str]:
    return {
        "coordinate_source": "stored trajectory coordinates converted to nm",
        "selection_identity": "resolved once from static topology",
        "unwrapping": "none",
        "alignment": "none",
        "distance_pbc": "triclinic minimum image per pair and frame",
    }


def box_matrix(box: Box) -> NDArray[np.float64]:
    value = np.asarray(box.vectors_nm, dtype=np.float64)
    if value.shape != (3, 3):
        raise InputError("A periodic box must contain three three-dimensional vectors.")
    return value


def periodic_radius_limit_nm(box: Box) -> float:
    """Return half the smallest perpendicular cell height."""

    matrix = box_matrix(box)
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
