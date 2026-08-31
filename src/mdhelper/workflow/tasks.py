"""Shared task lifecycle, progress, cancellation, and worker execution."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from threading import Event, Lock
from uuid import uuid4

from mdhelper.app import ApplicationService
from mdhelper.core.analysis import AnalysisRequest, AnalysisResult


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskHandle:
    task_id: str = field(default_factory=lambda: str(uuid4()))
    status: TaskStatus = TaskStatus.PENDING
    current: int = 0
    total: int | None = None
    message: str = ""
    result: AnalysisResult | None = None
    error: BaseException | None = None
    cancel_event: Event = field(default_factory=Event)
    future: Future[AnalysisResult] | None = None

    def cancel(self) -> None:
        self.cancel_event.set()


class TaskService:
    def __init__(self, application: ApplicationService, max_workers: int = 1):
        self.application = application
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="mdhelper")
        self._lock = Lock()
        self._tasks: dict[str, TaskHandle] = {}

    def submit(
        self,
        request: AnalysisRequest,
        cache_dir: str | Path | None = None,
        on_progress: Callable[[TaskHandle], None] | None = None,
        on_finished: Callable[[TaskHandle], None] | None = None,
    ) -> TaskHandle:
        handle = TaskHandle()
        with self._lock:
            self._tasks[handle.task_id] = handle

        def progress(current: int, total: int | None, message: str) -> None:
            handle.current = current
            handle.total = total
            handle.message = message
            if on_progress:
                on_progress(handle)

        def work() -> AnalysisResult:
            handle.status = TaskStatus.RUNNING
            try:
                result = self.application.analyses.run(
                    request, progress, handle.cancel_event, cache_dir
                )
                handle.result = result
                handle.status = TaskStatus.COMPLETED
                return result
            except BaseException as exc:
                handle.error = exc
                handle.status = (
                    TaskStatus.CANCELLED if handle.cancel_event.is_set() else TaskStatus.FAILED
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
        """Run through the same task boundary for synchronous presentation adapters."""

        return self.application.analyses.run(request, progress, cancel_event, cache_dir)

    def get(self, task_id: str) -> TaskHandle | None:
        with self._lock:
            return self._tasks.get(task_id)

    def shutdown(self, wait: bool = True) -> None:
        self.executor.shutdown(wait=wait, cancel_futures=False)
