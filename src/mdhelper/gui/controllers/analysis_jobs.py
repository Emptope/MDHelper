"""Qt-facing controller for asynchronous analysis jobs."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from mdhelper.app import ApplicationService
from mdhelper.core.analysis import AnalysisRequest, AnalysisResult
from mdhelper.jobs import JobHandle, JobRunner, JobStatus


class AnalysisJobController(QObject):
    progress = Signal(int, object, str)
    completed = Signal(object)
    failed = Signal(object)
    running_changed = Signal(bool)
    job_changed = Signal(object)

    def __init__(self, application: ApplicationService, parent: QObject | None = None):
        super().__init__(parent)
        self.runner = JobRunner(application)
        self.current: JobHandle | None = None
        self.latest: JobHandle | None = None
        self._message_count = 0
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.poll)

    @property
    def running(self) -> bool:
        return self.current is not None and self.current.status in {
            JobStatus.PENDING,
            JobStatus.RUNNING,
        }

    def submit(
        self,
        request: AnalysisRequest,
        cache_dir: str | Path | None = None,
        name: str = "Analysis",
    ) -> None:
        if self.running:
            raise RuntimeError("An analysis job is already running.")
        self.current = self.runner.submit(request, cache_dir, name=name)
        self.latest = self.current
        self._message_count = 0
        self.job_changed.emit(self.current)
        self.running_changed.emit(True)
        self.timer.start()

    def poll(self) -> None:
        job = self.current
        if job is None:
            return
        current, total, message, messages = job.progress_snapshot()
        self.progress.emit(current, total, message or job.status.value)
        if len(messages) != self._message_count:
            self._message_count = len(messages)
            self.job_changed.emit(job)
        if job.status in {JobStatus.PENDING, JobStatus.RUNNING}:
            return
        self.timer.stop()
        self.current = None
        self.running_changed.emit(False)
        if job.status == JobStatus.COMPLETED and job.result is not None:
            result: AnalysisResult = job.result
            self.completed.emit(result)
        elif job.error is not None:
            self.failed.emit(job.error)

    def cancel(self) -> None:
        if self.current is not None:
            self.current.cancel()

    def shutdown(self) -> None:
        self.timer.stop()
        self.runner.shutdown(wait=False)
