"""Project workspace actions for the desktop GUI."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtWidgets import QDialog, QFileDialog, QMainWindow, QMessageBox

from mdhelper.app import ApplicationService
from mdhelper.gui.actions.system import SystemActions
from mdhelper.gui.controllers.session import ProjectSession
from mdhelper.gui.pages.analysis import AnalysisPanel
from mdhelper.gui.pages.load import LoadPanel
from mdhelper.gui.pages.results import ResultPanel
from mdhelper.gui.pages.workspace import WorkspaceTabs
from mdhelper.runtime.logging import record_error
from mdhelper.version import __version__


class ProjectActions:
    def __init__(
        self,
        parent: QMainWindow,
        application: ApplicationService,
        session: ProjectSession,
        tabs: WorkspaceTabs,
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
        self._selecting = False

        results.load_requested.connect(self.load_result)
        results.state_changed.connect(self.save_plot_state)
        tabs.tabBarClicked.connect(self._tab_clicked)
        tabs.editor.open_requested.connect(self.open)

    def open(self) -> None:
        directory = QFileDialog.getExistingDirectory(self.parent, "Open MDHelper Project")
        if not directory:
            return
        try:
            if not self.tabs.editor.set_root(directory):
                return
            self.tabs.setCurrentWidget(self.tabs.editor)
            self.parent.statusBar().showMessage(f"Folder opened: {directory}", 10000)
        except Exception as exc:
            self.show_error(exc)

    def _reset_session(self) -> None:
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

    def _tab_clicked(self, index: int) -> None:
        if self.tabs.widget(index) == self.load:
            # Defer until the tab bar has finished its own selection change.
            from PySide6.QtCore import QTimer

            QTimer.singleShot(0, self._enter_load)

    def _enter_load(self) -> None:
        if self.tabs.currentWidget() is not self.load or self.analysis_running():
            return
        selected = all(row.edit.text().strip() for row in (
            self.load.inputs.topology, self.load.inputs.trajectory,
        ))
        if selected:
            return
        self.select_inputs()

    def change_inputs(self) -> None:
        if self.tabs.editor.root is None:
            self.open()
        if self.tabs.editor.root is not None:
            self.tabs.setCurrentWidget(self.load)
            self.select_inputs()

    def select_inputs(self) -> None:
        if self._selecting:
            return
        self._selecting = True
        try:
            self._select_inputs()
        finally:
            self._selecting = False

    def _select_inputs(self) -> None:
        directory = self.tabs.editor.root
        if directory is None:
            return
        if self.analysis_running():
            QMessageBox.information(
                self.parent, "Inputs", "Cancel the running analysis before changing inputs."
            )
            return
        current = self.session.project
        switching = current is None or current.root != directory
        try:
            candidates = self.application.projects.discover_inputs(
                directory, require_complete=False,
            )
            inputs: dict[str, Path] = {}
            project = current if not switching else None
            if project is None and self.application.projects.exists(directory):
                project = self.application.projects.open(directory, verify_inputs=False)
                inputs = project.resolve_inputs(verify_fingerprints=False)
            elif not switching or current is None:
                for role, row in (
                    ("topology", self.load.inputs.topology),
                    ("trajectory", self.load.inputs.trajectory),
                    ("index", self.load.inputs.index_file),
                ):
                    value = row.edit.text().strip()
                    if value:
                        inputs[role] = Path(value).expanduser().resolve()
            dialog = self.dialog_factory(candidates, self.parent)
            dialog.set_inputs(inputs)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            if project is None:
                project, created = self.application.projects.ensure(
                    directory, dialog.topology_path, dialog.trajectory_path, {}, dialog.index_path
                )
            else:
                project.verify_input_set(
                    dialog.topology_path, dialog.trajectory_path, dialog.index_path
                )
                created = False
            if switching:
                self._reset_session()
                self.session.project = project
                self.session.state.ready()
            self._set_inputs(
                str(dialog.topology_path), str(dialog.trajectory_path),
                "" if dialog.index_path is None else str(dialog.index_path),
            )
            self.inspect_system()
            self.ready("created" if created else "opened", restore=switching and not created)
        except Exception as exc:
            self.show_error(exc)

    def _set_inputs(self, topology: str, trajectory: str, index_file: str) -> None:
        self.system.suspend_auto_inspect = True
        try:
            self.load.inputs.topology.set_path(topology)
            self.load.inputs.trajectory.set_path(trajectory)
            self.load.inputs.index_file.set_path(index_file)
        finally:
            self.system.suspend_auto_inspect = False
