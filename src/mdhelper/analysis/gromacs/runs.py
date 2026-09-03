"""External-run progress and audit helpers for the GROMACS pipeline."""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Callable
from pathlib import Path

from mdhelper.analysis.common import report_progress
from mdhelper.analysis.pipeline import AnalysisInput
from mdhelper.analysis.radial import FrameAudit
from mdhelper.core.errors import BackendError
from mdhelper.core.integrations import IntegrationRunRecord
from mdhelper.integrations.gromacs import (
    frame_count,
    frame_progress,
    frame_progresses,
    output_message,
)


def _run_audit(
    stdout: str,
    stderr: str,
    indices: tuple[int, ...] = (),
) -> FrameAudit:
    values = frame_progresses(stdout, stderr)
    if indices:
        count = len(indices)
        first_index = indices[0]
        last_index = indices[-1]
    elif values:
        count = values[-1][0] + 1
        first_index = 0
        last_index = values[-1][0]
    else:
        count = 0
        first_index = None
        last_index = None
    return FrameAudit(
        count=count,
        first_index=first_index,
        last_index=last_index,
        first_time_ps=values[0][1] if values else None,
        last_time_ps=values[-1][1] if values else None,
    )


def _process_progress(
    inputs: AnalysisInput,
    total: int | None,
    indices: tuple[int, ...] = (),
) -> Callable[[float, str, str], None]:
    def update(_elapsed: float, stdout: str, stderr: str) -> None:
        message = output_message(stdout, stderr)
        if message is None:
            return
        parsed = frame_progress(stdout, stderr)
        if parsed is None:
            report_progress(inputs.progress, 0, total, message)
            return
        frame, _time_ps = parsed
        current = bisect_right(indices, frame) if indices else frame + 1
        if total is not None:
            current = min(current, total)
        report_progress(
            inputs.progress,
            current,
            total,
            message,
        )

    return update


def _trajectory_frame_count(
    inputs: AnalysisInput,
    trajectory: Path,
    root: Path,
) -> tuple[int, IntegrationRunRecord]:
    record = inputs.integrations.run(
        "gromacs",
        ["check", "-f", str(trajectory)],
        root,
        cancel_event=inputs.cancel_event,
        process_progress=_process_progress(inputs, None),
        required_capabilities=("check",),
    )
    if record.status != "completed":
        raise BackendError(
            f"GROMACS trajectory inspection exited with code {record.exit_code}.",
            details={"integration_run": record.to_dict()},
        )
    count = frame_count(record.stdout, record.stderr)
    if count is None:
        raise BackendError(
            "GROMACS did not report the trajectory frame count.",
            details={"integration_run": record.to_dict()},
        )
    return count, record
