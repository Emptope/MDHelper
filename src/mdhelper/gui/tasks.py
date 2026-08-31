"""Qt-facing controller for asynchronous analysis tasks."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from mdhelper.app import ApplicationService
from mdhelper.core.analysis import AnalysisRequest, AnalysisResult
from mdhelper.workflow.tasks import TaskHandle, TaskService, TaskStatus


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
