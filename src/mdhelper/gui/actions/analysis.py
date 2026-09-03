"""Analysis actions for the desktop GUI."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtWidgets import QMainWindow, QTabWidget

from mdhelper.app import ApplicationService
from mdhelper.core.analysis import AnalysisRequest, RadialRequest
from mdhelper.gui.components.parameters import ParameterPanel
from mdhelper.gui.controllers.analysis_jobs import AnalysisJobController
from mdhelper.gui.controllers.analysis_runs import AnalysisRunController, RunCompletion
from mdhelper.gui.controllers.session import ProjectSession
from mdhelper.gui.dialogs.log import JobLogDialog
from mdhelper.gui.pages.analysis import AnalysisPanel
from mdhelper.gui.pages.load import LoadPanel
from mdhelper.gui.pages.results import ResultPanel
from mdhelper.gui.windows import WindowManager
from mdhelper.jobs import JobHandle


class AnalysisActions:
    def __init__(
        self,
        parent: QMainWindow,
        application: ApplicationService,
        session: ProjectSession,
        tabs: QTabWidget,
        load: LoadPanel,
        analysis: AnalysisPanel,
        results: ResultPanel,
        windows: WindowManager,
        role_provenance: Callable[[], dict[str, object]],
        project_ready: Callable[[str, bool], None],
        refresh_results: Callable[[str | None], None],
        show_error: Callable[[BaseException], None],
    ):
        self.parent = parent
        self.session = session
        self.tabs = tabs
        self.load = load
        self.analysis = analysis
        self.results = results
        self.windows = windows
        self.role_provenance = role_provenance
        self.project_ready = project_ready
        self.refresh_results = refresh_results
        self.show_error = show_error
        self.controller = AnalysisRunController(application, session, parent)

        analysis.run_requested.connect(self.run)
        analysis.cancel_requested.connect(self.cancel)
        analysis.details_requested.connect(self.show_job_log)
        self.controller.batch_started.connect(results.begin_batch)
        self.controller.run_started.connect(self._run_started)
        self.controller.progress.connect(self._progress)
        self.controller.job_changed.connect(self.job_changed)
        self.controller.running_changed.connect(analysis.set_running)
        self.controller.result_ready.connect(self.present_result)
        self.controller.completed.connect(self.finish)
        self.controller.failed.connect(self._failed)

    @property
    def jobs(self) -> AnalysisJobController:
        return self.controller.jobs

    def run(self) -> None:
        parameters = self.analysis.parameters
        try:
            items = self.analysis.request_series(self._common(parameters))
        except Exception as exc:
            self.show_error(exc)
            return
        self.start(items)

    def request_items(
        self, parameters: ParameterPanel
    ) -> tuple[tuple[AnalysisRequest, str], ...]:
        return parameters.request_series(self._common(parameters))

    def _common(self, parameters: ParameterPanel) -> dict[str, object]:
        return self.load.common(
            self.role_provenance(),
            parameters.frame_range(),
            parameters.requires_selections(),
        )

    def start(self, items: tuple[tuple[AnalysisRequest, str], ...]) -> None:
        try:
            request = next(
                (item[0] for item in items if isinstance(item[0], RadialRequest)),
                items[0][0],
            )
            self._ensure_project(request)
            self.controller.start(items)
        except Exception as exc:
            self.show_error(exc)

    def cancel(self) -> None:
        if not self.jobs.running:
            return
        self.controller.cancel()
        self.parent.statusBar().showMessage("Cancellation requested...")

    def job_changed(self, job: JobHandle) -> None:
        self.analysis.set_details_available(True)
        dialog = self.windows.get(JobLogDialog)
        if dialog is not None:
            dialog.set_content(job.job_id, job.name, job.log_snapshot())

    def show_job_log(self) -> None:
        job = self.jobs.latest
        if job is None:
            return
        self.windows.show(
            JobLogDialog,
            lambda dialog: dialog.set_content(
                job.job_id,
                job.name,
                job.log_snapshot(),
            ),
        )

    def present_result(self, completion: RunCompletion) -> None:
        if completion.committed:
            self.refresh_results(completion.result.analysis_id)
        self.results.show_result(
            completion.result,
            completion.label or None,
            completion.context_name,
        )

    def finish(self) -> None:
        self.tabs.setCurrentWidget(self.results)
        self.results.open_plot_window()
        self.parent.statusBar().showMessage("Analysis completed", 10000)

    def shutdown(self) -> None:
        self.controller.shutdown()

    def _ensure_project(self, request: object) -> None:
        if self.session.project is not None or not isinstance(request, RadialRequest):
            return
        root = Path(request.trajectory).expanduser().resolve().parent
        _project, created = self.session.ensure(
            root,
            request.topology,
            request.trajectory,
            request.species_roles,
            request.index_file,
        )
        action = "created automatically" if created else "opened automatically"
        self.project_ready(action, False)

    def _run_started(self, current: int, total: int, _name: str) -> None:
        self.parent.statusBar().showMessage(
            f"Running plot series {current} of {total}..."
        )

    def _progress(self, current: int, total: object, message: str) -> None:
        self.analysis.set_progress(current, total if isinstance(total, int) else None)
        self.parent.statusBar().showMessage(message)

    def _failed(self, error: BaseException) -> None:
        self.show_error(error)
