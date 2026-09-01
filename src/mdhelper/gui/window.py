"""Main GUI window coordinating reusable panels and application services."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QCloseEvent, QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QTabWidget,
)

from mdhelper.app import ApplicationService
from mdhelper.core.analysis import AnalysisRequest, AnalysisResult, RadialRequest
from mdhelper.core.errors import ConfigurationError
from mdhelper.core.species import SpeciesRoleSuggestion, role_decision
from mdhelper.gui.analysis import AnalysisPanel
from mdhelper.gui.dialogs import IntegrationsDialog
from mdhelper.gui.fonts import configure_ui_font
from mdhelper.gui.formatting import (
    error_text,
    role_suggestions_text,
)
from mdhelper.gui.load import LoadPanel
from mdhelper.gui.menu import install_menu
from mdhelper.gui.projects import NewProjectDialog
from mdhelper.gui.results import ResultPanel
from mdhelper.gui.session import ProjectSession
from mdhelper.gui.tasks import AnalysisTasks, DetectionTasks
from mdhelper.gui.templates import TemplatesDialog
from mdhelper.gui.theme import theme_controller
from mdhelper.runtime.logging import configure_logging, record_error
from mdhelper.services.config import ThemeMode, save_config
from mdhelper.version import __version__


class MainWindow(QMainWindow):
    """Coordinate GUI events and application services for the main window."""

    def __init__(self):
        configure_logging()
        application = ApplicationService()
        qt_application = QApplication.instance()
        if isinstance(qt_application, QApplication):
            configure_ui_font(
                qt_application,
                application.config.gui.font_size,
            )
        super().__init__()
        self.application = application
        self.theme = theme_controller()
        self.theme.apply(self.application.config.gui.theme)
        self.session = ProjectSession(self.application)
        self.task_controller = AnalysisTasks(self.application, self)
        self.detection_tasks = DetectionTasks(self.application, self)
        self.role_suggestions: dict[str, SpeciesRoleSuggestion] = {}
        self.role_provenance: dict[str, Any] = {}
        self._applying_roles = False
        self._pending_runs: list[tuple[AnalysisRequest, str]] = []
        self._active_label = ""
        self._batch_total = 0
        self._pending_roles: dict[str, str] = {}
        self._suspend_auto_inspect = False
        self._inspection_timer = QTimer(self)
        self._inspection_timer.setSingleShot(True)
        self._inspection_timer.setInterval(250)
        self._inspection_timer.timeout.connect(self._auto_inspect)

        self.setWindowTitle(f"MDHelper {__version__}")
        self.setMinimumSize(760, 680)
        self.resize(860, 800)
        self.load = LoadPanel()
        self.analysis = AnalysisPanel()
        self.results = ResultPanel()
        self.load.inputs.set_gromacs_pending()
        self._connect_panels()
        self.menu_actions = install_menu(
            self,
            self._open_project,
            self._export_result,
            self._integrations,
            self._templates,
            self._open_terminal,
            self._open_settings,
            self.application.config.gui.theme,
            self._set_theme,
        )
        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        tabs.setMovable(False)
        tabs.addTab(self.load, "Load")
        tabs.addTab(self.analysis, "Analysis Settings")
        tabs.addTab(self.results, "Result")
        self.tabs = tabs
        self.setCentralWidget(tabs)
        status = self.statusBar()
        status.setSizeGripEnabled(False)
        status.showMessage("Ready")
        self._detect_gromacs_availability()

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

    def _connect_panels(self) -> None:
        self.load.inputs.system_changed.connect(self._system_input_changed)
        self.load.inputs.index_changed.connect(self._index_input_changed)
        self.load.species.suggestions_requested.connect(self._apply_role_suggestions)
        self.load.species.save_requested.connect(self._save_roles)
        self.load.selection_source_changed.connect(self.analysis.parameters.set_selection_source)
        self.analysis.run_requested.connect(self._run)
        self.analysis.cancel_requested.connect(self._cancel)
        self.analysis.parameters.energy_terms_requested.connect(self._load_energy_terms)
        self.load.inputs.backend.currentIndexChanged.connect(self._backend_changed)
        self.load.species.role_edited.connect(self._role_edited)
        self.results.load_requested.connect(self._load_project_result)
        self.results.save_project_requested.connect(self._save_project_figures)
        self.results.export_requested.connect(self._export_result)
        self.results.state_changed.connect(self._save_plot_state)
        self.task_controller.progress.connect(self._task_progress)
        self.task_controller.completed.connect(self._task_completed)
        self.task_controller.failed.connect(self._task_failed)
        self.task_controller.running_changed.connect(self.analysis.set_running)
        self.detection_tasks.completed.connect(self._integration_detected)
        self.detection_tasks.failed.connect(self._integration_detection_failed)

    def _load_energy_terms(self, path: str) -> None:
        backend = self.load.inputs.backend_value()
        self.statusBar().showMessage("Reading energy terms...")
        try:
            terms = self.application.analyses.energy_terms(path, backend)
            self.analysis.parameters.set_energy_terms(path, terms)
        except Exception as exc:
            self._show_error(exc)
            return
        self.statusBar().showMessage(
            f"Loaded {len(terms)} energy terms",
            10000,
        )

    def _backend_changed(self) -> None:
        parameters = self.analysis.parameters
        path = parameters.energy_file.edit.text().strip()
        parameters.set_energy_terms("", ())
        if Path(path).expanduser().is_file():
            self._load_energy_terms(path)

    def _detect_gromacs_availability(self) -> None:
        self.load.inputs.set_gromacs_pending()
        self.detection_tasks.submit("gromacs")

    def _integration_detected(self, name: str, status: object) -> None:
        if name == "gromacs":
            self.load.inputs.set_gromacs_available(bool(getattr(status, "available", False)))

    def _integration_detection_failed(self, name: str, _error: object) -> None:
        if name == "gromacs":
            self.load.inputs.set_gromacs_available(False)

    def _system_input_changed(self) -> None:
        if self._suspend_auto_inspect:
            return
        self._pending_roles = {}
        self.role_suggestions.clear()
        self.role_provenance.clear()
        self.load.species.clear()
        self.load.set_index_groups({})
        self._inspection_timer.start()

    def _index_input_changed(self) -> None:
        if self._suspend_auto_inspect:
            return
        roles = self.load.species.roles()
        if roles:
            self._pending_roles = roles
        self.load.set_index_groups({})
        self._inspection_timer.start()

    def _auto_inspect(self) -> None:
        topology = self.load.inputs.topology.edit.text().strip()
        trajectory = self.load.inputs.trajectory.edit.text().strip()
        if not topology or not trajectory:
            self.statusBar().showMessage("Select topology and trajectory files")
            return
        if not Path(topology).expanduser().is_file() or not Path(trajectory).expanduser().is_file():
            self.statusBar().showMessage("Select existing topology and trajectory files")
            return
        self._inspect(self._pending_roles, report_error=False)

    def _inspect(
        self,
        existing_roles: dict[str, str] | None = None,
        report_error: bool = True,
    ) -> None:
        self._inspection_timer.stop()
        try:
            summary = self.application.checks.inspect_system(
                self.load.inputs.topology.edit.text().strip(),
                self.load.inputs.trajectory.edit.text().strip(),
                self.load.inputs.index_value(),
                None if self.session.project is None else self.session.project.cache_dir,
            )
        except Exception as exc:
            if report_error:
                self._show_error(exc)
            else:
                self.statusBar().showMessage(f"Could not load selected system: {exc}")
            return
        if existing_roles is None:
            project = self.session.project
            existing_roles = project.manifest.get("species_roles", {}) if project else {}
            self.role_provenance = {
                species: {
                    "decision": "loaded_from_project",
                    "selected_role": role,
                    "suggestion": summary.role_suggestions[species].to_dict(),
                }
                for species, role in existing_roles.items()
                if species in summary.role_suggestions
            }
        else:
            self.role_provenance = {
                species: decision
                for species, decision in self.role_provenance.items()
                if species in summary.role_suggestions
            }
        self.role_suggestions = dict(summary.role_suggestions)
        self._applying_roles = True
        try:
            self.load.species.set_summary(summary, existing_roles)
            self.load.set_index_groups(summary.index_groups)
        finally:
            self._applying_roles = False
        self._pending_roles = self.load.species.roles()
        project = self.session.project
        self.load.species.save_button.setEnabled(project is not None)
        group_text = f"; {len(summary.index_groups)} index groups" if summary.index_groups else ""
        self.statusBar().showMessage(
            f"Loaded {summary.n_atoms} atoms; backend: {summary.backend}{group_text}", 10000
        )

    def _role_edited(self, species: str, role: str) -> None:
        if self._applying_roles:
            return
        if not role:
            self.role_provenance.pop(species, None)
            return
        suggestion = self.role_suggestions[species]
        self.role_provenance[species] = role_decision(role, suggestion, "role_editor")

    def _apply_role_suggestions(self) -> None:
        available = {
            species: suggestion
            for species, suggestion in self.role_suggestions.items()
            if suggestion.available
        }
        if not available:
            QMessageBox.information(
                self,
                "Species Role Suggestions",
                "No suggestions available.",
            )
            return
        answer = QMessageBox.question(
            self,
            "Apply Role Suggestions",
            role_suggestions_text(available),
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._applying_roles = True
        try:
            self.role_provenance.update(self.load.species.apply_suggestions(self.role_suggestions))
        finally:
            self._applying_roles = False

    def _save_roles(self) -> None:
        if self.session.project is None:
            QMessageBox.information(self, "Project", "Create or open a project first.")
            return
        try:
            self.session.set_species_roles(self.load.species.roles(require_all=True))
        except Exception as exc:
            self._show_error(exc)
            return
        self.statusBar().showMessage("Confirmed species roles saved", 10000)

    def _run(self) -> None:
        if (
            self.analysis.parameters.requires_selections()
            and self.load.inputs.selection_source.currentData() == "index"
            and not self.load.inputs.index_path()
        ):
            answer = QMessageBox.question(
                self,
                "No GROMACS Index File",
                "No .ndx file was provided. Use MDAnalysis selection expressions instead?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                self.statusBar().showMessage("Select a GROMACS index file to continue.", 10000)
                return
            self.load.inputs.selection_source.setCurrentIndex(1)
        try:
            runs = list(
                self.analysis.request_series(
                    self.load.common(
                        self.role_provenance,
                        self.analysis.parameters.frame_range(),
                        self.analysis.parameters.requires_selections(),
                    ),
                )
            )
        except Exception as exc:
            self._show_error(exc)
            return
        if self.session.project is None:
            request = runs[0][0]
            if isinstance(request, RadialRequest):
                root = Path(request.trajectory).expanduser().resolve().parent
                try:
                    _project, created = self.session.ensure(
                        root,
                        request.topology,
                        request.trajectory,
                        request.species_roles,
                        request.index_file,
                    )
                except Exception as exc:
                    self._show_error(exc)
                    return
                action = "created automatically" if created else "opened automatically"
                self._project_ready(action, restore=False)
        self._pending_runs = runs
        self._batch_total = len(runs)
        self.results.begin_batch(runs[0][0].analysis_type)
        self._submit_next()

    def _submit_next(self) -> None:
        if not self._pending_runs:
            return
        request, self._active_label = self._pending_runs.pop(0)
        self.session.start(request)
        cache_dir = None if self.session.project is None else self.session.project.cache_dir
        self.task_controller.submit(request, cache_dir)
        current = self._batch_total - len(self._pending_runs)
        self.statusBar().showMessage(f"Running plot series {current} of {self._batch_total}...")

    def _task_progress(self, current: int, total: object, message: str) -> None:
        self.analysis.set_progress(current, total if isinstance(total, int) else None)
        self.statusBar().showMessage(message)

    def _task_completed(self, result: AnalysisResult) -> None:
        try:
            if self.session.complete(result) is not None:
                self._refresh_project_results(result.analysis_id)
        except Exception as exc:
            self._pending_runs.clear()
            self._show_error(exc)
            return
        self.results.show_result(result, self._active_label or None)
        if self._pending_runs:
            self._submit_next()
            return
        self.tabs.setCurrentWidget(self.results)
        self.results.open_plot_window()
        self.statusBar().showMessage("Analysis completed", 10000)

    def _task_failed(self, error: BaseException) -> None:
        self._pending_runs.clear()
        self._show_error(error)

    def _cancel(self) -> None:
        if self.task_controller.running:
            self._pending_runs.clear()
            self.task_controller.cancel()
            self.statusBar().showMessage("Cancellation requested...")

    def _open_project(self) -> None:
        if self.task_controller.running:
            QMessageBox.information(
                self,
                "Open Project",
                "Cancel the running analysis before opening another project.",
            )
            return
        directory = QFileDialog.getExistingDirectory(self, "Open MDHelper Project")
        if not directory:
            return
        try:
            if self.application.projects.exists(directory):
                self._open_existing_project(directory)
                return
            self._prepare_project(directory)
        except Exception as exc:
            self._show_error(exc)

    def _prepare_project(self, directory: str) -> None:
        candidates = self.application.projects.discover_inputs(directory)
        dialog = NewProjectDialog(candidates, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        topology = dialog.topology_path
        trajectory = dialog.trajectory_path
        index_file = dialog.index_path
        self._reset_workspace()
        self.load.inputs.topology.edit.setText(str(topology))
        self.load.inputs.trajectory.edit.setText(str(trajectory))
        self.load.inputs.index_file.edit.setText("" if index_file is None else str(index_file))
        self.load.inputs.set_backend("auto")
        self._inspect()

    def _open_existing_project(self, directory: str) -> None:
        _, inputs = self.session.open(directory)
        self.load.inputs.topology.edit.setText(str(inputs["topology"]))
        self.load.inputs.trajectory.edit.setText(str(inputs["trajectory"]))
        self.load.inputs.index_file.edit.setText(str(inputs.get("index", "")))
        self.load.inputs.selection_source.setCurrentIndex(0 if "index" in inputs else 1)
        self._inspect()
        self._project_ready("opened")

    def _reset_workspace(self) -> None:
        self.session.reset()
        self.role_suggestions.clear()
        self.role_provenance.clear()
        self._pending_runs.clear()
        self.load.inputs.clear()
        self.load.species.clear()
        self.load.set_index_groups({})
        self.analysis.reset()
        self.results.clear_result()
        self.results.close_plot_windows()
        self.results.set_history(())
        self.results.set_project(False)
        self.setWindowTitle(f"MDHelper {__version__}")
        self.tabs.setCurrentWidget(self.load)
        self.statusBar().showMessage("New project workspace", 10000)

    def _project_ready(self, action: str, restore: bool = True) -> None:
        assert self.session.project is not None
        self.setWindowTitle(f"MDHelper {__version__} - {self.session.project.root.name}")
        self.load.species.save_button.setEnabled(True)
        if self.session.result is None:
            self.results.clear_result()
        self.results.set_project(True)
        self._refresh_project_results()
        if restore:
            self._restore_plot_state()
        self.statusBar().showMessage(f"Project {action}: {self.session.project.root}", 10000)

    def _refresh_project_results(self, selected_id: str | None = None) -> None:
        self.results.set_history(self.session.list_results(), selected_id)

    def _restore_plot_state(self) -> None:
        try:
            state = self.session.plot_state()
            loaded = self.session.load_plot_results(state)
            self.results.restore_state(state, loaded)
            if loaded and self.session.request is not None:
                self._apply_request(self.session.request)
            elif self.results.current_id() is not None:
                self._load_project_result()
        except Exception as exc:
            self._show_error(exc)

    def _save_plot_state(self) -> None:
        if self.session.project is None:
            return
        try:
            self.session.set_plot_state(self.results.plot_state())
        except Exception as exc:
            record_error(exc, "Save plot state")
            self.statusBar().showMessage(f"Could not save plot selection: {exc}", 10000)

    def _load_project_result(self) -> None:
        analysis_id = self.results.current_id()
        if self.session.project is None or analysis_id is None:
            return
        try:
            request, result = self.session.load_result(analysis_id)
        except Exception as exc:
            self._show_error(exc)
            return
        self._apply_request(request)
        self.results.show_result(result)
        self.statusBar().showMessage(f"Loaded result {result.analysis_id}", 10000)

    def _apply_request(self, request: AnalysisRequest) -> None:
        self._applying_roles = True
        self._suspend_auto_inspect = True
        try:
            self.load.apply_request(request, preserve_inputs=True)
            self.analysis.apply_request(request)
        finally:
            self._suspend_auto_inspect = False
            self._applying_roles = False
        role_decisions = request.parameter_provenance.get("species_roles", {})
        self.role_provenance = dict(role_decisions) if isinstance(role_decisions, dict) else {}

    def _export_result(self) -> None:
        if self.session.result is None:
            QMessageBox.information(self, "Export", "No completed result is available.")
            return
        directory = QFileDialog.getExistingDirectory(self, "Export analysis result")
        if not directory:
            return
        visible = self.results.plot_results()
        plotted = visible or (self.session.result,)
        labels = self.results.plot_labels() if visible else (None,)
        color_ids = self.results.plot_color_ids() if visible else None
        series_keys = self.results.plot_series_keys() if visible else None
        group_ids = self.results.plot_group_ids() if visible else None
        titles = self.results.plot_titles() if visible else None
        try:
            paths = []
            unique = tuple({result.analysis_id: result for result in plotted}.values())
            for result in unique:
                output = (
                    Path(directory)
                    if len(unique) == 1
                    else Path(directory) / f"{result.analysis_type}-{result.analysis_id}"
                )
                paths.extend(
                    self.application.analyses.export(
                        result,
                        output,
                        include_figures=False,
                    )
                )
            paths.extend(
                self.application.analyses.export_comparison_figures(
                    plotted,
                    directory,
                    "plot",
                    labels,
                    color_ids,
                    series_keys,
                    group_ids,
                    titles,
                    self.results.plot_scheme(),
                    self.results.plot_limits(),
                )
            )
        except Exception as exc:
            self._show_error(exc)
            return
        QMessageBox.information(self, "Export Complete", f"Exported {len(paths)} files.")

    def _save_project_figures(self) -> None:
        if self.session.project is None or self.session.result is None:
            QMessageBox.information(
                self, "Project Figures", "Open a project and complete an analysis first."
            )
            return
        visible = self.results.plot_results()
        plotted = visible or (self.session.result,)
        labels = self.results.plot_labels() if visible else (None,)
        color_ids = self.results.plot_color_ids() if visible else None
        series_keys = self.results.plot_series_keys() if visible else None
        group_ids = self.results.plot_group_ids() if visible else None
        titles = self.results.plot_titles() if visible else None
        directory = self.session.project.root / "figures"
        try:
            paths = self.application.analyses.export_comparison_figures(
                plotted,
                directory,
                "plot",
                labels,
                color_ids,
                series_keys,
                group_ids,
                titles,
                self.results.plot_scheme(),
                self.results.plot_limits(),
            )
        except Exception as exc:
            self._show_error(exc)
            return
        self.statusBar().showMessage(f"Saved {len(paths)} figures to {directory}", 10000)
        QMessageBox.information(
            self,
            "Project Figures Saved",
            f"Saved PNG, SVG, and PDF to:\n{directory}",
        )

    def _integrations(self) -> None:
        IntegrationsDialog(self.application, self).exec()
        self._detect_gromacs_availability()

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

    def _show_error(self, error: BaseException) -> None:
        record_error(error, "GUI operation")
        message = error_text(error)
        self.results.show_message(message)
        QMessageBox.critical(self, "MDHelper Error", message)

    def closeEvent(self, event: QCloseEvent) -> None:
        if event.spontaneous():
            message = (
                "Cancel the running analysis and quit MDHelper?"
                if self.task_controller.running
                else "Quit MDHelper?"
            )
            answer = QMessageBox.question(self, "Really Quit?", message)
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        if self.task_controller.running:
            self.task_controller.cancel()
        self.task_controller.shutdown()
        self.detection_tasks.shutdown()
        self.results.close_plot_windows()
        event.accept()
