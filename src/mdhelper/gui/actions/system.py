"""Loaded-system and integration actions for the desktop GUI."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMainWindow, QMessageBox

from mdhelper.app import ApplicationService
from mdhelper.core.analysis import AnalysisRequest
from mdhelper.core.species import SpeciesRoleSuggestion, role_decision
from mdhelper.gui.controllers.integration_detection import IntegrationDetectionController
from mdhelper.gui.controllers.session import ProjectSession
from mdhelper.gui.controllers.system_state import InspectionState
from mdhelper.gui.dialogs.selection import SelectionHintDialog
from mdhelper.gui.dialogs.species import RoleHelpDialog, SuggestionDetailsDialog
from mdhelper.gui.pages.analysis import AnalysisPanel
from mdhelper.gui.pages.load import LoadPanel
from mdhelper.gui.windows import WindowManager


class SystemActions:
    def __init__(
        self,
        parent: QMainWindow,
        application: ApplicationService,
        session: ProjectSession,
        load: LoadPanel,
        analysis: AnalysisPanel,
        windows: WindowManager,
        project_ready: Callable[[str, bool], None],
        show_error: Callable[[BaseException], None],
    ):
        self.parent = parent
        self.application = application
        self.session = session
        self.load = load
        self.analysis = analysis
        self.windows = windows
        self.project_ready = project_ready
        self.show_error = show_error
        self.state = InspectionState()
        self.applying_roles = False
        self.suspend_auto_inspect = False
        self.gromacs_detected = False
        self.gromacs_capabilities: frozenset[str] = frozenset()
        self.timer = QTimer(parent)
        self.timer.setSingleShot(True)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self.auto_inspect)
        self.detection = IntegrationDetectionController(application, parent)

        load.inputs.system_changed.connect(self.system_input_changed)
        load.inputs.index_changed.connect(self.index_input_changed)
        load.species.suggestions_requested.connect(self.apply_role_suggestions)
        load.species.suggestions_cancelled.connect(self.cancel_role_suggestions)
        load.species.help_requested.connect(self.show_role_help)
        load.species.details_requested.connect(self.show_suggestion_details)
        load.species.role_edited.connect(self.role_edited)
        load.selection_inputs_changed.connect(analysis.parameters.set_selection_groups)
        analysis.selection_hint_requested.connect(self.show_selection_hint)
        analysis.parameters.energy_terms_requested.connect(self.load_energy_terms)
        analysis.parameters.analysis_backend_changed.connect(self.backend_changed)
        analysis.parameters.backend_requirements_changed.connect(
            self.sync_gromacs_availability
        )
        self.detection.completed.connect(self.integration_detected)
        self.detection.failed.connect(self.integration_detection_failed)

    @property
    def role_suggestions(self) -> dict[str, SpeciesRoleSuggestion]:
        return self.state.suggestions

    @role_suggestions.setter
    def role_suggestions(self, suggestions: dict[str, SpeciesRoleSuggestion]) -> None:
        self.state.suggestions = dict(suggestions)

    @property
    def role_provenance(self) -> dict[str, Any]:
        return self.state.provenance

    @role_provenance.setter
    def role_provenance(self, provenance: dict[str, Any]) -> None:
        self.state.provenance = dict(provenance)

    def load_energy_terms(self, path: str) -> None:
        backend = self.analysis.parameters.analysis_backend_value()
        self.parent.statusBar().showMessage("Reading energy terms...")
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
            self.show_error(exc)
            return
        self.parent.statusBar().showMessage(f"Loaded {len(terms)} energy terms", 10000)

    def backend_changed(self) -> None:
        parameters = self.analysis.parameters
        path = parameters.energy_file.edit.text().strip()
        parameters.set_energy_terms("", ())
        if Path(path).expanduser().is_file():
            self.load_energy_terms(path)

    def detect_gromacs(self) -> None:
        configured = self.application.integrations.is_configured("gromacs")
        self.analysis.parameters.set_gromacs_configured(configured)
        if not configured:
            self.gromacs_detected = False
            self.gromacs_capabilities = frozenset()
            self.analysis.parameters.set_gromacs_available(False)
            return
        self.analysis.parameters.set_gromacs_pending()
        self.detection.submit("gromacs")

    def integration_detected(self, name: str, status: object) -> None:
        if name != "gromacs":
            return
        capabilities = getattr(status, "capabilities", ())
        self.gromacs_detected = bool(getattr(status, "available", False))
        self.gromacs_capabilities = frozenset(
            str(capability) for capability in capabilities
        )
        self.sync_gromacs_availability()

    def integration_detection_failed(self, name: str, _error: object) -> None:
        if name != "gromacs":
            return
        self.gromacs_detected = False
        self.gromacs_capabilities = frozenset()
        self.sync_gromacs_availability()

    def sync_gromacs_availability(self) -> None:
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
            self.gromacs_detected
            and set(required).issubset(self.gromacs_capabilities)
        )

    def system_input_changed(self) -> None:
        if self.suspend_auto_inspect:
            return
        self.state.reset()
        self.load.species.clear()
        self.load.set_index_groups({})
        self.timer.start()

    def index_input_changed(self) -> None:
        if self.suspend_auto_inspect:
            return
        roles = self.load.species.roles()
        if roles:
            self.state.set_pending_roles(roles)
        self.timer.start()

    def auto_inspect(self) -> None:
        topology = self.load.inputs.topology.edit.text().strip()
        trajectory = self.load.inputs.trajectory.edit.text().strip()
        if not topology or not trajectory:
            self.parent.statusBar().showMessage("Select topology and trajectory files")
            return
        if not Path(topology).expanduser().is_file() or not Path(
            trajectory
        ).expanduser().is_file():
            self.parent.statusBar().showMessage(
                "Select existing topology and trajectory files"
            )
            return
        self.inspect(self.state.pending_roles, report_error=False)

    def inspect(
        self,
        existing_roles: dict[str, str] | None = None,
        report_error: bool = True,
    ) -> None:
        self.timer.stop()
        project = self.session.project
        source = existing_roles is None
        if existing_roles is None:
            existing_roles = project.manifest.get("species_roles", {}) if project else {}
        self.state.schedule(existing_roles)
        self.state.begin()
        try:
            summary = self.application.checks.inspect_system(
                self.load.inputs.topology.edit.text().strip(),
                self.load.inputs.trajectory.edit.text().strip(),
                self.load.inputs.index_value(),
                None if project is None else project.cache_dir,
            )
        except Exception as exc:
            self.state.fail()
            if report_error:
                self.show_error(exc)
            else:
                self.parent.statusBar().showMessage(
                    f"Could not load selected system: {exc}"
                )
            return
        if source:
            provenance = {
                species: role_decision(
                    role,
                    summary.role_suggestions[species],
                    "project_manifest",
                )
                for species, role in existing_roles.items()
                if species in summary.role_suggestions
            }
        else:
            provenance = {
                species: decision
                for species, decision in self.state.provenance.items()
                if species in summary.role_suggestions
            }
        self.state.complete(dict(summary.role_suggestions), provenance)
        self.applying_roles = True
        try:
            self.load.species.set_summary(summary, existing_roles)
            self.load.set_index_groups(summary.index_groups)
        finally:
            self.applying_roles = False
        self.state.set_pending_roles(self.load.species.roles())
        group_text = (
            f"; {len(summary.index_groups)} index groups"
            if summary.index_groups
            else ""
        )
        self.parent.statusBar().showMessage(
            f"Loaded {summary.n_atoms} atoms; backend: {summary.backend}{group_text}",
            10000,
        )

    def role_edited(self, species: str, role: str) -> None:
        if self.applying_roles:
            return
        decision = (
            None
            if not role
            else role_decision(role, self.state.suggestions[species], "role_editor")
        )
        self.state.edit_role(species, decision)

    def apply_role_suggestions(self) -> None:
        if not any(suggestion.available for suggestion in self.state.suggestions.values()):
            QMessageBox.information(
                self.parent,
                "Species Role Suggestions",
                "No suggestions available.",
            )
            return
        self.applying_roles = True
        try:
            decisions = self.load.species.apply_suggestions(self.state.suggestions)
        finally:
            self.applying_roles = False
        self.state.apply_roles(decisions, self.load.species.roles())
        self.save_roles()

    def cancel_role_suggestions(self) -> None:
        species = self.state.cancel_roles("suggestion_batch")
        if not species:
            return
        self.applying_roles = True
        try:
            self.load.species.clear_roles(species)
        finally:
            self.applying_roles = False
        self.state.set_pending_roles(self.load.species.roles())
        if self.session.project is not None:
            self.save_roles()
        else:
            self.parent.statusBar().showMessage("Role suggestions cleared", 10000)

    def save_roles(self) -> bool:
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
                self.project_ready(action, False)
            else:
                self.session.set_species_roles(roles)
        except Exception as exc:
            self.show_error(exc)
            return False
        self.parent.statusBar().showMessage("Confirmed species roles saved", 10000)
        return True

    def apply_request(self, request: AnalysisRequest) -> None:
        self.applying_roles = True
        self.suspend_auto_inspect = True
        try:
            self.load.apply_request(request, preserve_inputs=True)
            self.analysis.apply_request(request)
        finally:
            self.suspend_auto_inspect = False
            self.applying_roles = False
        decisions = request.parameter_provenance.get("species_roles", {})
        self.state.provenance = dict(decisions) if isinstance(decisions, dict) else {}

    def reset(self) -> None:
        self.timer.stop()
        self.state.reset()
        self.load.species.clear()
        self.load.set_index_groups({})

    def show_role_help(self) -> None:
        self.windows.show(RoleHelpDialog)

    def show_suggestion_details(self, suggestions: object) -> None:
        if not isinstance(suggestions, dict):
            return
        self.windows.show(
            SuggestionDetailsDialog,
            lambda dialog: dialog.set_suggestions(suggestions),
        )

    def show_selection_hint(self, backend: str) -> None:
        self.windows.show(
            SelectionHintDialog,
            lambda dialog: dialog.set_backend(backend),
        )

    def shutdown(self) -> None:
        self.timer.stop()
        self.detection.shutdown()
