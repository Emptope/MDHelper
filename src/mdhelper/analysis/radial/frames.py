"""Backend-neutral radial frame selection and audit records."""

from __future__ import annotations

from dataclasses import dataclass

from mdhelper.core.errors import InputError
from mdhelper.core.system import Frame, FrameRange


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
