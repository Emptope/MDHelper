"""Qt-facing controller for asynchronous analysis tasks."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from threading import Lock
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal

from mdhelper.app import ApplicationService
from mdhelper.core.analysis import AnalysisRequest, AnalysisResult
from mdhelper.workflow.tasks import TaskHandle, TaskService, TaskStatus

_DETECTION_EXECUTOR = ThreadPoolExecutor(
    max_workers=2,
    thread_name_prefix="mdhelper-detection",
)


class DetectionTasks(QObject):
    completed = Signal(str, object)
    failed = Signal(str, object)

    def __init__(self, application: ApplicationService, parent: QObject | None = None):
        super().__init__(parent)
        self.application = application
        self._lock = Lock()
        self._generation = 0
        self._future: Future[Any] | None = None
        self._closed = False

    def submit(self, name: str) -> None:
        config = self.application.config.integration(name)
        with self._lock:
            if self._closed:
                return
            self._generation += 1
            generation = self._generation
            previous = self._future
            future = _DETECTION_EXECUTOR.submit(
                self.application.integrations.detect,
                name,
                None,
                config,
            )
            self._future = future
        if previous is not None:
            previous.cancel()
        future.add_done_callback(
            lambda result: self._finished(name, generation, result)
        )

    def _finished(
        self,
        name: str,
        generation: int,
        future: Future[Any],
    ) -> None:
        with self._lock:
            current = not self._closed and generation == self._generation
        if not current or future.cancelled():
            return
        try:
            status = future.result()
        except BaseException as exc:
            self.failed.emit(name, exc)
            return
        self.completed.emit(name, status)

    def shutdown(self) -> None:
        with self._lock:
            self._closed = True
            future = self._future
        if future is not None:
            future.cancel()


class AnalysisTasks(QObject):
    progress = Signal(int, object, str)
    completed = Signal(object)
    failed = Signal(object)
    running_changed = Signal(bool)

    def __init__(self, application: ApplicationService, parent: QObject | None = None):
        super().__init__(parent)
        self.service = TaskService(application)
        self.current: TaskHandle | None = None
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.poll)

    @property
    def running(self) -> bool:
        return self.current is not None and self.current.status in {
            TaskStatus.PENDING,
            TaskStatus.RUNNING,
        }

    def submit(
        self, request: AnalysisRequest, cache_dir: str | Path | None = None
    ) -> None:
        if self.running:
            raise RuntimeError("An analysis task is already running.")
        self.current = self.service.submit(request, cache_dir)
        self.running_changed.emit(True)
        self.timer.start()

    def poll(self) -> None:
        task = self.current
        if task is None:
            return
        self.progress.emit(task.current, task.total, task.message or task.status.value)
        if task.status in {TaskStatus.PENDING, TaskStatus.RUNNING}:
            return
        self.timer.stop()
        self.current = None
        self.running_changed.emit(False)
        if task.status == TaskStatus.COMPLETED and task.result is not None:
            result: AnalysisResult = task.result
            self.completed.emit(result)
        elif task.error is not None:
            self.failed.emit(task.error)

    def cancel(self) -> None:
        if self.current is not None:
            self.current.cancel()

    def shutdown(self) -> None:
        self.timer.stop()
        self.service.shutdown(wait=False)
