"""Shared synchronous and asynchronous analysis job execution."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event, Lock

from mdhelper.app import ApplicationService
from mdhelper.core.analysis import AnalysisRequest, AnalysisResult
from mdhelper.jobs.models import JobHandle, JobStatus


class JobRunner:
    def __init__(self, application: ApplicationService, max_workers: int = 1):
        self.application = application
        self.executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="mdhelper-job",
        )
        self._lock = Lock()
        self._jobs: dict[str, JobHandle] = {}

    def submit(
        self,
        request: AnalysisRequest,
        cache_dir: str | Path | None = None,
        on_progress: Callable[[JobHandle], None] | None = None,
        on_finished: Callable[[JobHandle], None] | None = None,
        name: str = "Analysis",
    ) -> JobHandle:
        handle = JobHandle(name=name.strip() or "Analysis")
        with self._lock:
            self._jobs[handle.job_id] = handle

        def progress(current: int, total: int | None, message: str) -> None:
            handle.update_progress(current, total, message)
            if on_progress:
                on_progress(handle)

        def work() -> AnalysisResult:
            handle.status = JobStatus.RUNNING
            try:
                result = self.application.analyses.run(
                    request, progress, handle.cancel_event, cache_dir
                )
                handle.result = result
                handle.status = JobStatus.COMPLETED
                return result
            except BaseException as exc:
                handle.error = exc
                handle.status = (
                    JobStatus.CANCELLED
                    if handle.cancel_event.is_set()
                    else JobStatus.FAILED
                )
                raise
            finally:
                if on_finished:
                    on_finished(handle)

        handle.future = self.executor.submit(work)
        return handle

    def run_sync(
        self,
        request: AnalysisRequest,
        progress: Callable[[int, int | None, str], None] | None = None,
        cancel_event: Event | None = None,
        cache_dir: str | Path | None = None,
    ) -> AnalysisResult:
        """Run through the same job boundary for synchronous adapters."""

        return self.application.analyses.run(request, progress, cancel_event, cache_dir)

    def get(self, job_id: str) -> JobHandle | None:
        with self._lock:
            return self._jobs.get(job_id)

    def shutdown(self, wait: bool = True) -> None:
        self.executor.shutdown(wait=wait, cancel_futures=False)
