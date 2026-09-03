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
)

from mdhelper.app import ApplicationService
from mdhelper.app.exports import PlotExport, plot_exports, result_exports
from mdhelper.core.analysis import (
    AnalysisRequest,
    AnalysisResult,
    RadialRequest,
    analysis_label,
)
from mdhelper.core.errors import ConfigurationError
from mdhelper.core.plotting import PlotSize
from mdhelper.core.species import SpeciesRoleSuggestion, role_decision
from mdhelper.gui.controllers.analysis_jobs import AnalysisJobController
from mdhelper.gui.controllers.integration_detection import IntegrationDetectionController
from mdhelper.gui.controllers.session import ProjectSession
from mdhelper.gui.dialogs.integrations import IntegrationsDialog
from mdhelper.gui.dialogs.log import JobLogDialog
from mdhelper.gui.dialogs.plot import PlotSettingsDialog
from mdhelper.gui.dialogs.projects import NewProjectDialog
from mdhelper.gui.dialogs.results import ResultDetailsDialog
from mdhelper.gui.dialogs.selection import SelectionHintDialog
from mdhelper.gui.dialogs.species import RoleHelpDialog, SuggestionDetailsDialog
from mdhelper.gui.dialogs.templates import TemplatesDialog
from mdhelper.gui.dialogs.tools import MakeIndexHelpDialog
from mdhelper.gui.fonts import configure_ui_font
from mdhelper.gui.formatting import (
    error_text,
)
from mdhelper.gui.menu import install_menu
from mdhelper.gui.pages.workspace import WorkspaceTabs
from mdhelper.gui.theme import theme_controller
from mdhelper.gui.windows import WindowManager
from mdhelper.jobs import JobHandle
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
        self.job_controller = AnalysisJobController(self.application, self)
        self.integration_detection = IntegrationDetectionController(self.application, self)
        self.windows = WindowManager(self)
        self.role_suggestions: dict[str, SpeciesRoleSuggestion] = {}
        self.role_provenance: dict[str, Any] = {}
        self._applying_roles = False
        self._pending_jobs: list[tuple[AnalysisRequest, str]] = []
        self._active_label = ""
        self._batch_total = 0
        self._pending_roles: dict[str, str] = {}
        self._suspend_auto_inspect = False
        self._gromacs_detected = False
        self._gromacs_capabilities: frozenset[str] = frozenset()
        self._inspection_timer = QTimer(self)
        self._inspection_timer.setSingleShot(True)
        self._inspection_timer.setInterval(250)
        self._inspection_timer.timeout.connect(self._auto_inspect)

        self.setWindowTitle(f"MDHelper {__version__}")
        self.setMinimumSize(760, 680)
        self.resize(860, 800)
        tabs = WorkspaceTabs(windows=self.windows)
        self.load = tabs.load
        self.analysis = tabs.analysis
        self.results = tabs.results
        self.analysis.parameters.set_gromacs_configured(
            self.application.integrations.is_configured("gromacs")
        )
        self._connect_panels()
        self.menu_actions = install_menu(
            self,
            self._open_project,
            self._export_result,
            self._integrations,
            self._templates,
            self._open_terminal,
            self._make_index_file,
            self._open_settings,
            self.application.config.gui.theme,
            self._set_theme,
        )
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
            self.application.integrations.open_terminal(
                "gromacs",
                ["make_ndx", "-f", str(source), "-o", "index.ndx"],
                source.parent,
                required_capabilities=("make_ndx",),
            )
        except Exception as exc:
            self._show_error(exc)
            return
        self.statusBar().showMessage(f"Creating index file in {source.parent}", 10000)

    def _connect_panels(self) -> None:
        self.load.inputs.system_changed.connect(self._system_input_changed)
        self.load.inputs.index_changed.connect(self._index_input_changed)
        self.load.species.suggestions_requested.connect(self._apply_role_suggestions)
        self.load.species.suggestions_cancelled.connect(self._cancel_role_suggestions)
        self.load.species.help_requested.connect(self._show_role_help)
        self.load.species.details_requested.connect(self._show_suggestion_details)
        self.load.selection_inputs_changed.connect(self.analysis.parameters.set_selection_groups)
        self.analysis.run_requested.connect(self._run)
        self.analysis.cancel_requested.connect(self._cancel)
        self.analysis.details_requested.connect(self._show_job_log)
        self.analysis.selection_hint_requested.connect(self._show_selection_hint)
        self.analysis.parameters.energy_terms_requested.connect(self._load_energy_terms)
        self.analysis.parameters.analysis_backend_changed.connect(self._backend_changed)
        self.analysis.parameters.backend_requirements_changed.connect(
            self._sync_gromacs_availability
        )
        self.load.species.role_edited.connect(self._role_edited)
        self.results.load_requested.connect(self._load_project_result)
        self.results.save_project_requested.connect(self._save_project_figures)
        self.results.export_requested.connect(self._export_result)
        self.results.details_requested.connect(self._show_result_details)
        self.results.advanced_plot_requested.connect(self._show_plot_settings)
        self.results.state_changed.connect(self._save_plot_state)
        self.job_controller.progress.connect(self._job_progress)
        self.job_controller.completed.connect(self._job_completed)
        self.job_controller.failed.connect(self._job_failed)
        self.job_controller.running_changed.connect(self.analysis.set_running)
        self.job_controller.job_changed.connect(self._job_changed)
        self.integration_detection.completed.connect(self._integration_detected)
        self.integration_detection.failed.connect(self._integration_detection_failed)

    def _load_energy_terms(self, path: str) -> None:
        backend = self.analysis.parameters.analysis_backend_value()
        self.statusBar().showMessage("Reading energy terms...")
        try:
            terms = self.application.analyses.energy_terms(
                path,
                backend,
                cache_dir=(
                    None
                    if self.session.project is None
                    else self.session.project.cache_dir
                ),
            )
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
        configured = self.application.integrations.is_configured("gromacs")
        self.analysis.parameters.set_gromacs_configured(configured)
        if not configured:
            self._gromacs_detected = False
            self._gromacs_capabilities = frozenset()
            self.analysis.parameters.set_gromacs_available(False)
            return
        self.analysis.parameters.set_gromacs_pending()
        self.integration_detection.submit("gromacs")

    def _integration_detected(self, name: str, status: object) -> None:
        if name == "gromacs":
            capabilities = getattr(status, "capabilities", ())
            self._gromacs_detected = bool(getattr(status, "available", False))
            self._gromacs_capabilities = frozenset(
                str(capability) for capability in capabilities
            )
            self._sync_gromacs_availability()

    def _integration_detection_failed(self, name: str, _error: object) -> None:
        if name == "gromacs":
            self._gromacs_detected = False
            self._gromacs_capabilities = frozenset()
            self._sync_gromacs_availability()

    def _sync_gromacs_availability(self) -> None:
        parameters = self.analysis.parameters
        analysis_type = parameters.analysis_type_value()
        try:
            frames = None if analysis_type == "energy" else parameters.frame_range()
        except ValueError:
            parameters.set_gromacs_available(False)
            return
        required = self.application.analyses.backend_capabilities(
            "gromacs",
            analysis_type,
            frames,
        )
        parameters.set_gromacs_available(
            self._gromacs_detected
            and set(required).issubset(self._gromacs_capabilities)
        )

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
                species: role_decision(
                    role, summary.role_suggestions[species], "project_manifest"
                )
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

    def _show_role_help(self) -> None:
        self.windows.show(RoleHelpDialog)

    def _show_suggestion_details(self, suggestions: object) -> None:
        if not isinstance(suggestions, dict):
            return
        self.windows.show(
            SuggestionDetailsDialog,
            lambda dialog: dialog.set_suggestions(suggestions),
        )

    def _show_selection_hint(self, backend: str) -> None:
        self.windows.show(
            SelectionHintDialog,
            lambda dialog: dialog.set_backend(backend),
        )

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
        self._applying_roles = True
        try:
            self.role_provenance.update(self.load.species.apply_suggestions(self.role_suggestions))
        finally:
            self._applying_roles = False
        self._pending_roles = self.load.species.roles()
        self._save_roles()

    def _cancel_role_suggestions(self) -> None:
        species = {
            name
            for name, decision in self.role_provenance.items()
            if isinstance(decision, dict) and decision.get("source") == "suggestion_batch"
        }
        if not species:
            return
        self._applying_roles = True
        try:
            self.load.species.clear_roles(species)
        finally:
            self._applying_roles = False
        for name in species:
            self.role_provenance.pop(name, None)
        self._pending_roles = self.load.species.roles()
        if self.session.project is not None:
            self._save_roles()
        else:
            self.statusBar().showMessage("Role suggestions cleared", 10000)

    def _save_roles(self) -> bool:
        roles = self.load.species.roles()
        try:
            if self.session.project is None:
                topology = Path(
                    self.load.inputs.topology.edit.text().strip()
                ).expanduser().resolve()
                trajectory = Path(
                    self.load.inputs.trajectory.edit.text().strip()
                ).expanduser().resolve()
                _project, created = self.session.ensure(
                    trajectory.parent,
                    topology,
                    trajectory,
                    roles,
                    self.load.inputs.index_value(),
                )
                action = "created automatically" if created else "opened automatically"
                self._project_ready(action, restore=False)
            else:
                self.session.set_species_roles(roles)
        except Exception as exc:
            self._show_error(exc)
            return False
        self.statusBar().showMessage("Confirmed species roles saved", 10000)
        return True

    def _run(self) -> None:
        if (
            self.analysis.parameters.requires_selections()
            and self.analysis.parameters.analysis_backend_value() == "native"
            and self.load.inputs.index_value() is None
        ):
            answer = QMessageBox.question(
                self,
                "Native Requires Index File",
                "No .ndx file was provided. Use MDAnalysis selection expressions instead?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                self.statusBar().showMessage("Select a GROMACS index file to continue.", 10000)
                return
            self.analysis.parameters.set_analysis_backend("mdanalysis")
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
        self._pending_jobs = runs
        self._batch_total = len(runs)
        self.results.begin_batch(runs[0][0].analysis_type)
        self._submit_next()

    def _submit_next(self) -> None:
        if not self._pending_jobs:
            return
        request, self._active_label = self._pending_jobs.pop(0)
        self.session.start(request)
        cache_dir = None if self.session.project is None else self.session.project.cache_dir
        name = analysis_label(request.analysis_type)
        if self._active_label:
            name = f"{name}: {self._active_label}"
        self.job_controller.submit(request, cache_dir, name=name)
        current = self._batch_total - len(self._pending_jobs)
        self.statusBar().showMessage(f"Running plot series {current} of {self._batch_total}...")

    def _job_progress(self, current: int, total: object, message: str) -> None:
        self.analysis.set_progress(current, total if isinstance(total, int) else None)
        self.statusBar().showMessage(message)

    def _job_changed(self, job: JobHandle) -> None:
        self.analysis.set_details_available(True)
        dialog = self.windows.get(JobLogDialog)
        if dialog is not None:
            dialog.set_content(
                job.job_id,
                job.name,
                job.log_snapshot(),
            )

    def _show_job_log(self) -> None:
        job = self.job_controller.latest
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

    def _show_result_details(self) -> None:
        result = self.results.result
        if result is None:
            return
        self.windows.show(
            ResultDetailsDialog,
            lambda dialog: dialog.set_content(self.results.context_name(), result),
        )

    def _show_plot_settings(self) -> None:
        self.windows.show(
            PlotSettingsDialog,
            lambda dialog: dialog.begin(self.results.plot_appearance()),
            setup=self._connect_plot_settings,
        )

    def _connect_plot_settings(self, dialog: PlotSettingsDialog) -> None:
        dialog.applied.connect(self.results.apply_plot_appearance)
        dialog.reverted.connect(self.results.apply_plot_appearance)

    def _job_completed(self, result: AnalysisResult) -> None:
        try:
            if self.session.complete(result) is not None:
                self._refresh_project_results(result.analysis_id)
        except Exception as exc:
            self._pending_jobs.clear()
            self._show_error(exc)
            return
        job = self.job_controller.latest
        context_name = job.name if job is not None and job.result is result else None
        self.results.show_result(result, self._active_label or None, context_name)
        if self._pending_jobs:
            self._submit_next()
            return
        self.tabs.setCurrentWidget(self.results)
        self.results.open_plot_window()
        self.statusBar().showMessage("Analysis completed", 10000)

    def _job_failed(self, error: BaseException) -> None:
        self._pending_jobs.clear()
        self._show_error(error)

    def _cancel(self) -> None:
        if self.job_controller.running:
            self._pending_jobs.clear()
            self.job_controller.cancel()
            self.statusBar().showMessage("Cancellation requested...")

    def _open_project(self) -> None:
        if self.job_controller.running:
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
        _project, created = self.session.ensure(
            directory,
            topology,
            trajectory,
            {},
            index_file,
        )
        self._inspect()
        action = "created" if created else "opened"
        self._project_ready(action, restore=False)

    def _open_existing_project(self, directory: str) -> None:
        _, inputs = self.session.open(directory)
        self.load.inputs.topology.edit.setText(str(inputs["topology"]))
        self.load.inputs.trajectory.edit.setText(str(inputs["trajectory"]))
        self.load.inputs.index_file.edit.setText(str(inputs.get("index", "")))
        self._inspect()
        self._project_ready("opened")

    def _reset_workspace(self) -> None:
        self.session.reset()
        self.role_suggestions.clear()
        self.role_provenance.clear()
        self._pending_jobs.clear()
        self.load.inputs.clear()
        self.load.species.clear()
        self.load.set_index_groups({})
        self.analysis.reset()
        self.results.clear_result()
        self.results.set_history(())
        self.results.set_project(False)
        self.setWindowTitle(f"MDHelper {__version__}")
        self.tabs.setCurrentWidget(self.load)
        self.statusBar().showMessage("New project workspace", 10000)

    def _project_ready(self, action: str, restore: bool = True) -> None:
        assert self.session.project is not None
        self.setWindowTitle(f"MDHelper {__version__} - {self.session.project.root.name}")
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
        plots = self._plot_exports()
        sizes = self._plot_export_sizes(len(plots))
        try:
            paths = self.application.analyses.export_bundle(
                plots,
                directory,
                self.results.plot_scheme(),
                self.results.plot_limits(),
                sizes,
                self.results.plot_appearance(),
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
        plots = self._plot_exports()
        sizes = self._plot_export_sizes(len(plots))
        directory = self.session.project.root / "figures"
        try:
            paths = self.application.analyses.save_plots(
                plots,
                directory,
                self.results.plot_scheme(),
                self.results.plot_limits(),
                sizes,
                self.results.plot_appearance(),
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

    def _plot_exports(self) -> tuple[PlotExport, ...]:
        visible = self.results.plot_results()
        if visible:
            return plot_exports(
                visible,
                series_keys=self.results.plot_series_keys(),
                labels=self.results.plot_labels(),
                color_ids=self.results.plot_color_ids(),
                group_ids=self.results.plot_group_ids(),
                titles=self.results.plot_titles(),
            )
        assert self.session.result is not None
        items = result_exports(self.session.result)
        return plot_exports(tuple(item.result for item in items))

    def _plot_export_sizes(self, count: int) -> tuple[PlotSize, ...]:
        sizes = self.results.plot_sizes()
        if len(sizes) == count:
            return sizes
        size = self.results.plot_size()
        return tuple(size for _index in range(count))

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
                if self.job_controller.running
                else "Quit MDHelper?"
            )
            answer = QMessageBox.question(self, "Really Quit?", message)
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        if self.job_controller.running:
            self.job_controller.cancel()
        self.job_controller.shutdown()
        self.integration_detection.shutdown()
        self.windows.close_all()
        event.accept()
