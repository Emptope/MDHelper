from __future__ import annotations

from threading import Event
from typing import cast

import pytest

from mdhelper.app import ApplicationService
from mdhelper.core.analysis import AnalysisRequest, AnalysisResult
from mdhelper.core.errors import JobCancelled
from mdhelper.jobs import JobHandle, JobRunner, JobStatus


class _Analyses:
    def __init__(self, result: AnalysisResult):
        self.result = result
        self.started = Event()
        self.release = Event()

    def run(
        self,
        _request: AnalysisRequest,
        progress: object,
        cancel_event: Event,
        _cache_dir: object,
    ) -> AnalysisResult:
        self.started.set()
        self.release.wait(2)
        if cancel_event.is_set():
            raise JobCancelled()
        if callable(progress):
            progress(1, 2, "Reading frame 1")
            progress(2, 2, "Reading frame 2")
        return self.result


class _Application:
    def __init__(self, analyses: _Analyses):
        self.analyses = analyses


def _runner(analyses: _Analyses) -> JobRunner:
    application = cast(ApplicationService, _Application(analyses))
    return JobRunner(application)


def test_job_runner_tracks_progress_and_completion() -> None:
    result = cast(AnalysisResult, object())
    analyses = _Analyses(result)
    runner = _runner(analyses)
    updates: list[tuple[int, int | None, str]] = []
    try:
        job = runner.submit(
            cast(AnalysisRequest, object()),
            on_progress=lambda handle: updates.append(
                (handle.current, handle.total, handle.message)
            ),
            name="CN: ion pair",
        )
        analyses.release.set()

        assert job.future is not None
        assert job.future.result(timeout=2) is result
        assert job.status == JobStatus.COMPLETED
        assert job.name == "CN: ion pair"
        assert runner.get(job.job_id) is job
        assert updates == [
            (1, 2, "Reading frame 1"),
            (2, 2, "Reading frame 2"),
        ]
        assert job.log_snapshot() == (
            "Reading frame 1",
            "Reading frame 2",
        )
    finally:
        runner.shutdown()


def test_job_runner_marks_cancelled_work() -> None:
    analyses = _Analyses(cast(AnalysisResult, object()))
    runner = _runner(analyses)
    try:
        job = runner.submit(cast(AnalysisRequest, object()))
        assert analyses.started.wait(1)
        job.cancel()
        analyses.release.set()

        assert job.future is not None
        with pytest.raises(JobCancelled):
            job.future.result(timeout=2)
        assert job.status == JobStatus.CANCELLED
    finally:
        runner.shutdown()


def test_job_log_collapses_only_consecutive_duplicate_messages() -> None:
    job = JobHandle()

    job.update_progress(1, 4, "Fingerprinting trajectory.xtc")
    job.update_progress(2, 4, "Fingerprinting trajectory.xtc")
    job.update_progress(3, 4, "Reading trajectory")
    job.update_progress(4, 4, "Fingerprinting trajectory.xtc")

    current, total, message, messages = job.progress_snapshot()
    assert (current, total, message) == (4, 4, "Fingerprinting trajectory.xtc")
    assert messages == (
        "Fingerprinting trajectory.xtc",
        "Reading trajectory",
        "Fingerprinting trajectory.xtc",
    )
