"""Main desktop window and GUI composition root."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QUrl
from PySide6.QtGui import QCloseEvent, QDesktopServices
from PySide6.QtWidgets import QApplication, QFileDialog, QMainWindow, QMessageBox

from mdhelper.app import ApplicationService
from mdhelper.core.analysis import AnalysisResult
from mdhelper.core.errors import ConfigurationError
from mdhelper.core.species import SpeciesRoleSuggestion
from mdhelper.gui.actions.analysis import AnalysisActions
from mdhelper.gui.actions.backend import BackendActions
from mdhelper.gui.actions.project import ProjectActions
from mdhelper.gui.actions.results import ResultActions
from mdhelper.gui.actions.system import SystemActions
from mdhelper.gui.controllers.analysis_jobs import AnalysisJobController
from mdhelper.gui.controllers.analysis_runs import RunCompletion
from mdhelper.gui.controllers.session import ProjectSession
from mdhelper.gui.dialogs.integrations import IntegrationsDialog
from mdhelper.gui.dialogs.projects import NewProjectDialog
from mdhelper.gui.dialogs.templates import TemplatesDialog
from mdhelper.gui.dialogs.tools import MakeIndexHelpDialog
from mdhelper.gui.fonts import configure_ui_font
from mdhelper.gui.formatting import error_text
from mdhelper.gui.menu import install_menu
from mdhelper.gui.pages.workspace import WorkspaceTabs
from mdhelper.gui.theme import theme_controller
from mdhelper.gui.windows import WindowManager
from mdhelper.gui.workflows import WorkflowActions
from mdhelper.jobs import JobHandle
from mdhelper.runtime.logging import configure_logging, record_error
from mdhelper.services.config import ThemeMode, save_config
from mdhelper.version import __version__

__all__ = ["MainWindow", "NewProjectDialog", "QFileDialog"]


class MainWindow(QMainWindow):
    """Compose desktop pages, actions, and application services."""

    # Construction

    def __init__(self):
        configure_logging()
        application = ApplicationService()
        qt_application = QApplication.instance()
        if isinstance(qt_application, QApplication):
            configure_ui_font(qt_application, application.config.gui.font_size)
        super().__init__()
        self.application = application
        self.theme = theme_controller()
        self.theme.apply(application.config.gui.theme)
        self.session = ProjectSession(application)
        self.windows = WindowManager(self)

        self.setWindowTitle(f"MDHelper {__version__}")
        self.setMinimumSize(760, 680)
        self.resize(860, 800)
        self.tabs = WorkspaceTabs(windows=self.windows)
        self.load = self.tabs.load
        self.analysis = self.tabs.analysis
        self.results = self.tabs.results
        self.setCentralWidget(self.tabs)
        status = self.statusBar()
        status.setSizeGripEnabled(False)
        status.showMessage("Ready")

        self.system_actions = SystemActions(
            self,
            application,
            self.session,
            self.load,
            self.analysis,
            self.windows,
            self._project_ready,
            self._show_error,
        )
        self.backend_actions = BackendActions(
            self,
            application,
            self.session,
            self.analysis,
            self._show_error,
        )
        self.analysis_actions = AnalysisActions(
            self,
            application,
            self.session,
            self.tabs,
            self.load,
            self.analysis,
            self.results,
            self.windows,
            lambda: dict(self.role_provenance),
            self._project_ready,
            self._refresh_project_results,
            self._show_error,
        )
        self.workflow_actions = WorkflowActions(
            self,
            application,
            self.load,
            self.analysis_actions,
            self.backend_actions,
            self.windows,
            self._open_settings,
        )
        self.project_actions = ProjectActions(
            self,
            application,
            self.session,
            self.tabs,
            self.load,
            self.analysis,
            self.results,
            self.system_actions,
            lambda candidates, parent: NewProjectDialog(candidates, parent),
            lambda: self._inspect(),
            lambda: self.job_controller.running,
            self.analysis_actions.controller.state.reset,
            self._show_error,
        )
        self.result_actions = ResultActions(
            self,
            application,
            self.session,
            self.results,
            self.windows,
            self._show_error,
        )
        self.menu_actions = install_menu(
            self,
            self._open_project,
            self._export_result,
            self._integrations,
            self._templates,
            self._open_terminal,
            self._run_workflow,
            self._make_index_file,
            self._open_settings,
            application.config.gui.theme,
            self._set_theme,
            self._open_document,
        )
        self.backend_actions.detect_gromacs()

    # System actions

    @property
    def role_suggestions(self) -> dict[str, SpeciesRoleSuggestion]:
        return self.system_actions.role_suggestions

    @role_suggestions.setter
    def role_suggestions(self, value: dict[str, SpeciesRoleSuggestion]) -> None:
        self.system_actions.role_suggestions = value

    @property
    def role_provenance(self) -> dict[str, Any]:
        return self.system_actions.role_provenance

    @role_provenance.setter
    def role_provenance(self, value: dict[str, Any]) -> None:
        self.system_actions.role_provenance = value

    @property
    def _inspection_timer(self):
        return self.system_actions.timer

    def _inspect(
        self,
        existing_roles: dict[str, str] | None = None,
        report_error: bool = True,
    ) -> None:
        self.system_actions.inspect(existing_roles, report_error)

    def _integration_detected(self, name: str, status: object) -> None:
        self.backend_actions.integration_detected(name, status)

    def _make_index_file(self) -> None:
        if not self.application.integrations.is_configured("gromacs"):
            self.windows.show(MakeIndexHelpDialog)
            return
        try:
            value = self.load.inputs.topology.edit.text().strip()
            source = self.application.integrations.validate_input_file(
                "gromacs",
                "make_ndx",
                "-f",
                value,
            )
            output = source.parent / "index.ndx"
            self.system_actions.watch_index_file(output)
            self.application.integrations.open_terminal(
                "gromacs",
                ["make_ndx", "-f", str(source), "-o", output.name],
                source.parent,
                required_capabilities=("make_ndx",),
            )
        except Exception as exc:
            self.system_actions.cancel_index_watch()
            self._show_error(exc)
            return
        self.statusBar().showMessage(f"Creating index file in {source.parent}", 10000)

    # Analysis actions

    @property
    def job_controller(self) -> AnalysisJobController:
        return self.analysis_actions.jobs

    def _run(self) -> None:
        self.analysis_actions.run()

    def _job_changed(self, job: JobHandle) -> None:
        self.analysis_actions.job_changed(job)

    def _job_completed(self, result: AnalysisResult) -> None:
        current = self.analysis_actions.controller.state.current
        if current is not None:
            self.analysis_actions.controller._completed(result)
            return
        self.session.result = result
        self.analysis_actions.present_result(RunCompletion(result, "", None, False))
        self.analysis_actions.finish()

    # Project actions

    def _open_project(self) -> None:
        self.project_actions.open()

    def _project_ready(self, action: str, restore: bool = True) -> None:
        self.project_actions.ready(action, restore)

    def _refresh_project_results(self, selected_id: str | None = None) -> None:
        self.project_actions.refresh_results(selected_id)

    # Result actions

    def _export_result(self) -> None:
        self.result_actions.export()

    def _save_project_figures(self) -> None:
        self.result_actions.save_project_figures()

    # Application actions

    def _open_terminal(self) -> None:
        from mdhelper.gui.main import start_tui

        if start_tui():
            self.statusBar().showMessage("Terminal interface opened", 10000)
            return
        QMessageBox.critical(
            self,
            "Terminal Interface",
            "The terminal interface could not be started.",
        )

    def _run_workflow(self) -> None:
        self.workflow_actions.open()

    def _integrations(self) -> None:
        IntegrationsDialog(self.application, self).exec()
        self.backend_actions.detect_gromacs()

    def _templates(self) -> None:
        TemplatesDialog(self.application, self).exec()

    def _open_settings(self) -> None:
        path = self.application.config_file
        try:
            if not path.is_file():
                save_config(self.application.config, path)
            opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
            if not opened:
                raise ConfigurationError(
                    f"Could not open the configuration file: {path}",
                    "Configure a default text application for TOML files and try again.",
                )
        except Exception as exc:
            self._show_error(exc)
            return
        self.statusBar().showMessage(f"Opened configuration: {path}", 10000)

    def _open_document(self, url: str) -> None:
        try:
            if not QDesktopServices.openUrl(QUrl(url)):
                raise ConfigurationError(
                    f"Could not open documentation: {url}",
                    "Configure a default web browser and try again.",
                )
        except Exception as exc:
            self._show_error(exc)

    def _set_theme(self, mode: ThemeMode) -> None:
        previous = self.application.config.gui.theme
        self.application.config.gui.theme = mode
        self.theme.apply(mode)
        try:
            save_config(self.application.config, self.application.config_file)
        except Exception as exc:
            self.application.config.gui.theme = previous
            self.theme.apply(previous)
            self.menu_actions.themes[previous].setChecked(True)
            self._show_error(exc)
            return
        self.statusBar().showMessage(f"Appearance: {mode}", 5000)

    # Error handling and lifecycle

    def _show_error(self, error: BaseException) -> None:
        record_error(error, "GUI operation")
        message = error_text(error)
        self.results.show_message(message)
        QMessageBox.critical(self, "MDHelper Error", message)

    def closeEvent(self, event: QCloseEvent) -> None:
        if event.spontaneous():
            message = (
                "Cancel the running analysis and quit MDHelper?"
                if self.job_controller.running
                else "Quit MDHelper?"
            )
            answer = QMessageBox.question(self, "Really Quit?", message)
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        if self.job_controller.running:
            self.analysis_actions.cancel()
        self.analysis_actions.shutdown()
        self.system_actions.shutdown()
        self.backend_actions.shutdown()
        self.windows.close_all()
        event.accept()
