"""Loaded-system inspection actions for the desktop GUI."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMainWindow

from mdhelper.app import ApplicationService
from mdhelper.core.species import role_decision
from mdhelper.gui.controllers.session import ProjectSession
from mdhelper.gui.controllers.system_state import InspectionState
from mdhelper.gui.pages.analysis import AnalysisPanel
from mdhelper.gui.pages.load import LoadPanel


class SystemInspectionActions:
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
        self.parent = parent
        self.application = application
        self.session = session
        self.load = load
        self.analysis = analysis
        self.project_ready = project_ready
        self.show_error = show_error
        self.state = InspectionState()
        self.applying_roles = False
        self.suspend_auto_inspect = False
        self.timer = QTimer(parent)
        self.timer.setSingleShot(True)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self.auto_inspect)

        load.inputs.system_changed.connect(self.system_input_changed)
        load.selection_inputs_changed.connect(analysis.parameters.set_selection_groups)

    def system_input_changed(self) -> None:
        if self.suspend_auto_inspect:
            return
        self.state.reset()
        self.load.species.clear()
        self.load.set_index_groups({})
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

    def reset(self) -> None:
        self.timer.stop()
        self.state.reset()
        self.load.species.clear()
        self.load.set_index_groups({})

    def shutdown(self) -> None:
        self.timer.stop()
