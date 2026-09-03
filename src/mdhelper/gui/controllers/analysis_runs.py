"""Analysis batch controller independent of desktop widgets."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal

from mdhelper.app import ApplicationService
from mdhelper.core.analysis import AnalysisResult, analysis_label
from mdhelper.gui.controllers.analysis_jobs import AnalysisJobController
from mdhelper.gui.controllers.analysis_state import AnalysisBatch, RunItem
from mdhelper.gui.controllers.session import ProjectSession


@dataclass(frozen=True)
class RunCompletion:
    result: AnalysisResult
    label: str
    context_name: str | None
    committed: bool


class AnalysisRunController(QObject):
    batch_started = Signal(str)
    run_started = Signal(int, int, str)
    progress = Signal(int, object, str)
    job_changed = Signal(object)
    running_changed = Signal(bool)
    result_ready = Signal(object)
    completed = Signal()
    failed = Signal(object)

    def __init__(
        self,
        application: ApplicationService,
        session: ProjectSession,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self.session = session
        self.state = AnalysisBatch()
        self.jobs = AnalysisJobController(application, self)
        self.jobs.progress.connect(self.progress)
        self.jobs.job_changed.connect(self.job_changed)
        self.jobs.running_changed.connect(self.running_changed)
        self.jobs.completed.connect(self._completed)
        self.jobs.failed.connect(self._failed)

    def start(self, items: tuple[RunItem, ...]) -> None:
        self.state.start(items)
        self.batch_started.emit(items[0][0].analysis_type)
        self._submit_next()

    def cancel(self) -> None:
        if self.state.current is None:
            return
        self.state.cancel()
        self.jobs.cancel()

    def shutdown(self) -> None:
        self.state.cancel()
        self.jobs.shutdown()

    def _submit_next(self) -> None:
        request, label = self.state.take_next()
        try:
            self.session.start(request)
            cache_dir = (
                None if self.session.project is None else self.session.project.cache_dir
            )
            name = analysis_label(request.analysis_type)
            if label:
                name = f"{name}: {label}"
            self.jobs.submit(request, cache_dir, name=name)
        except Exception as exc:
            self.state.fail()
            self.session.abort()
            self.failed.emit(exc)
            return
        self.run_started.emit(self.state.position, self.state.total, name)

    def _completed(self, result: AnalysisResult) -> None:
        current = self.state.current
        if current is None:
            self.failed.emit(RuntimeError("Completed analysis has no active batch request."))
            return
        _, label = current
        try:
            committed = self.session.complete(result) is not None
        except Exception as exc:
            self.state.fail()
            self.session.abort()
            self.failed.emit(exc)
            return
        job = self.jobs.latest
        context_name = job.name if job is not None and job.result is result else None
        finished = self.state.complete_current()
        self.result_ready.emit(RunCompletion(result, label, context_name, committed))
        if finished:
            self.completed.emit()
            return
        self._submit_next()

    def _failed(self, error: BaseException) -> None:
        self.state.fail()
        self.session.abort()
        self.failed.emit(error)
