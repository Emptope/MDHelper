"""Project workspace actions for the desktop GUI."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtWidgets import QDialog, QFileDialog, QMainWindow, QMessageBox, QTabWidget

from mdhelper.app import ApplicationService
from mdhelper.gui.actions.system import SystemActions
from mdhelper.gui.controllers.session import ProjectSession
from mdhelper.gui.pages.analysis import AnalysisPanel
from mdhelper.gui.pages.load import LoadPanel
from mdhelper.gui.pages.results import ResultPanel
from mdhelper.runtime.logging import record_error
from mdhelper.version import __version__


class ProjectActions:
    def __init__(
        self,
        parent: QMainWindow,
        application: ApplicationService,
        session: ProjectSession,
        tabs: QTabWidget,
        load: LoadPanel,
        analysis: AnalysisPanel,
        results: ResultPanel,
        system: SystemActions,
        dialog_factory: Callable[[Any, QMainWindow], Any],
        inspect_system: Callable[[], None],
        analysis_running: Callable[[], bool],
        reset_analysis: Callable[[], None],
        show_error: Callable[[BaseException], None],
    ):
        self.parent = parent
        self.application = application
        self.session = session
        self.tabs = tabs
        self.load = load
        self.analysis = analysis
        self.results = results
        self.system = system
        self.dialog_factory = dialog_factory
        self.inspect_system = inspect_system
        self.analysis_running = analysis_running
        self.reset_analysis = reset_analysis
        self.show_error = show_error

        results.load_requested.connect(self.load_result)
        results.state_changed.connect(self.save_plot_state)

    def open(self) -> None:
        if self.analysis_running():
            QMessageBox.information(
                self.parent,
                "Open Project",
                "Cancel the running analysis before opening another project.",
            )
            return
        directory = QFileDialog.getExistingDirectory(self.parent, "Open MDHelper Project")
        if not directory:
            return
        try:
            if self.application.projects.exists(directory):
                self._open_existing(directory)
                return
            self._prepare(directory)
        except Exception as exc:
            self.show_error(exc)

    def reset(self) -> None:
        self.session.reset()
        self.reset_analysis()
        self.system.suspend_auto_inspect = True
        try:
            self.load.inputs.clear()
        finally:
            self.system.suspend_auto_inspect = False
        self.system.reset()
        self.analysis.reset()
        self.results.clear_result()
        self.results.set_history(())
        self.results.set_project(False)
        self.parent.setWindowTitle(f"MDHelper {__version__}")
        self.tabs.setCurrentWidget(self.load)
        self.parent.statusBar().showMessage("New project workspace", 10000)

    def ready(self, action: str, restore: bool = True) -> None:
        if self.session.project is None:
            raise RuntimeError("A project session is not open.")
        self.parent.setWindowTitle(
            f"MDHelper {__version__} - {self.session.project.root.name}"
        )
        if self.session.result is None:
            self.results.clear_result()
        self.results.set_project(True)
        self.refresh_results()
        if restore:
            self.restore_plot_state()
        self.parent.statusBar().showMessage(
            f"Project {action}: {self.session.project.root}", 10000
        )

    def refresh_results(self, selected_id: str | None = None) -> None:
        self.results.set_history(self.session.list_results(), selected_id)

    def restore_plot_state(self) -> None:
        try:
            state = self.session.plot_state()
            loaded = self.session.load_plot_results(state)
            self.results.restore_state(state, loaded)
            if loaded and self.session.request is not None:
                self.system.apply_request(self.session.request)
            elif self.results.current_id() is not None:
                self.load_result()
        except Exception as exc:
            self.show_error(exc)

    def save_plot_state(self) -> None:
        if self.session.project is None:
            return
        try:
            self.session.set_plot_state(self.results.plot_state())
        except Exception as exc:
            record_error(exc, "Save plot state")
            self.parent.statusBar().showMessage(
                f"Could not save plot selection: {exc}", 10000
            )

    def load_result(self) -> None:
        analysis_id = self.results.current_id()
        if self.session.project is None or analysis_id is None:
            return
        try:
            request, result = self.session.load_result(analysis_id)
        except Exception as exc:
            self.show_error(exc)
            return
        self.system.apply_request(request)
        self.results.show_result(result)
        self.parent.statusBar().showMessage(
            f"Loaded result {result.analysis_id}", 10000
        )

    def _prepare(self, directory: str) -> None:
        candidates = self.application.projects.discover_inputs(directory)
        dialog = self.dialog_factory(candidates, self.parent)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.reset()
        self._set_inputs(
            str(dialog.topology_path),
            str(dialog.trajectory_path),
            "" if dialog.index_path is None else str(dialog.index_path),
        )
        _project, created = self.session.ensure(
            directory,
            dialog.topology_path,
            dialog.trajectory_path,
            {},
            dialog.index_path,
        )
        self.inspect_system()
        self.ready("created" if created else "opened", restore=False)

    def _open_existing(self, directory: str) -> None:
        _, inputs = self.session.open(directory)
        self._set_inputs(
            str(inputs["topology"]),
            str(inputs["trajectory"]),
            str(inputs.get("index", "")),
        )
        self.inspect_system()
        self.ready("opened")

    def _set_inputs(self, topology: str, trajectory: str, index_file: str) -> None:
        self.system.suspend_auto_inspect = True
        try:
            self.load.inputs.topology.edit.setText(topology)
            self.load.inputs.trajectory.edit.setText(trajectory)
            self.load.inputs.index_file.edit.setText(index_file)
        finally:
            self.system.suspend_auto_inspect = False
