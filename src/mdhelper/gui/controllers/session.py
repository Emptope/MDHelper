"""GUI project-session state independent of Qt widgets."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from mdhelper.app import ApplicationService
from mdhelper.core.analysis import AnalysisRequest, AnalysisResult
from mdhelper.core.errors import ConfigurationError
from mdhelper.core.plotting import PlotState
from mdhelper.gui.controllers.session_state import SessionState
from mdhelper.project import Project


@dataclass
class ProjectSession:
    application: ApplicationService
    project: Project | None = None
    request: AnalysisRequest | None = None
    result: AnalysisResult | None = None
    state: SessionState = field(default_factory=SessionState)

    def reset(self) -> None:
        self.project = None
        self.request = None
        self.result = None
        self.state.reset()

    def create(
        self,
        root: str | Path,
        topology: str | Path,
        trajectory: str | Path,
        species_roles: dict[str, str],
        index_file: str | Path | None = None,
    ) -> Project:
        project = self.application.projects.create(
            root, topology, trajectory, species_roles, index_file
        )
        self.project = project
        self.request = None
        self.result = None
        self.state.ready()
        return project

    def open(self, root: str | Path) -> tuple[Project, dict[str, Path]]:
        project = self.application.projects.open(root)
        inputs = project.resolve_inputs()
        self.project = project
        self.request = None
        self.result = None
        self.state.ready()
        return project, inputs

    def ensure(
        self,
        root: str | Path,
        topology: str | Path,
        trajectory: str | Path,
        species_roles: dict[str, str],
        index_file: str | Path | None = None,
    ) -> tuple[Project, bool]:
        project, created = self.application.projects.ensure(
            root, topology, trajectory, species_roles, index_file
        )
        self.project = project
        self.request = None
        self.result = None
        self.state.ready()
        return project, created

    def start(self, request: AnalysisRequest) -> None:
        self.state.start()
        self.request = request
        self.result = None

    def complete(self, result: AnalysisResult) -> Path | None:
        output = None
        if self.project is not None and self.request is not None:
            output = self.application.projects.commit_result(self.project, self.request, result)
        self.result = result
        self.state.complete()
        return output

    def abort(self) -> None:
        self.result = None
        self.state.abort(self.project is not None)

    def set_species_roles(self, species_roles: dict[str, str]) -> None:
        if self.project is None:
            raise RuntimeError("A project session is not open.")
        self.application.projects.set_species_roles(self.project, species_roles)

    def plot_state(self) -> PlotState:
        if self.project is None:
            return PlotState()
        return self.application.projects.plot_state(self.project)

    def set_plot_state(self, state: PlotState) -> None:
        if self.project is None:
            return
        self.application.projects.set_plot_state(self.project, state)

    def load_plot_results(self, state: PlotState) -> tuple[AnalysisResult, ...]:
        if self.project is None:
            return ()
        loaded: list[AnalysisResult] = []
        identifiers: set[str] = set()
        for selection in state.selections:
            if selection.result_id in identifiers:
                continue
            try:
                loaded.append(
                    self.application.projects.load_result(
                        self.project, selection.result_id
                    )
                )
                identifiers.add(selection.result_id)
            except ConfigurationError:
                continue
        if loaded:
            self.result = loaded[-1]
            self.request = AnalysisRequest.from_dict(self.result.request)
            self.state.restore()
        return tuple(loaded)

    def list_results(self) -> tuple[dict[str, object], ...]:
        if self.project is None:
            return ()
        return self.application.projects.list_results(self.project)

    def load_result(self, analysis_id: str) -> tuple[AnalysisRequest, AnalysisResult]:
        if self.project is None:
            raise RuntimeError("A project session is not open.")
        result = self.application.projects.load_result(self.project, analysis_id)
        request = AnalysisRequest.from_dict(result.request)
        self.request = request
        self.result = result
        self.state.restore()
        return request, result
