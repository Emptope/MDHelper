"""Species-role actions for the desktop GUI."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtWidgets import QMainWindow, QMessageBox

from mdhelper.app import ApplicationService
from mdhelper.core.analysis import AnalysisRequest
from mdhelper.core.species import SpeciesRoleSuggestion, role_decision
from mdhelper.gui.actions.system.watching import FileWatchingActions
from mdhelper.gui.controllers.session import ProjectSession
from mdhelper.gui.pages.analysis import AnalysisPanel
from mdhelper.gui.pages.load import LoadPanel


class RoleActions(FileWatchingActions):
    def __init__(
        self,
        parent: QMainWindow,
        application: ApplicationService,
        session: ProjectSession,
        load: LoadPanel,
        analysis: AnalysisPanel,
        project_ready: Callable[[str, bool], None],
        show_error: Callable[[BaseException], None],
    ):
        super().__init__(
            parent,
            application,
            session,
            load,
            analysis,
            project_ready,
            show_error,
        )
        load.species.suggestions_requested.connect(self.apply_role_suggestions)
        load.species.suggestions_cancelled.connect(self.cancel_role_suggestions)
        load.species.role_edited.connect(self.role_edited)

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
