"""Project creation, persistence, and result-history use cases."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from mdhelper.core.analysis import AnalysisRequest, AnalysisResult
from mdhelper.core.errors import InputFileError
from mdhelper.core.plotting import PlotState
from mdhelper.core.trajectory import TOPOLOGY_SUFFIXES, TRAJECTORY_SUFFIXES
from mdhelper.project import Project
from mdhelper.project.manifests import ManifestRepository

INDEX_SUFFIX = ".ndx"


@dataclass(frozen=True)
class InputCandidates:
    root: Path
    topology: tuple[Path, ...]
    trajectory: tuple[Path, ...]
    index: tuple[Path, ...]


def discover_inputs(root: str | Path) -> InputCandidates:
    directory = Path(root).expanduser().resolve()
    if not directory.is_dir():
        raise InputFileError(
            "The selected project location is not a directory.",
            "Select a directory containing the simulation input files.",
            {"path": str(directory)},
        )
    try:
        files = tuple(
            sorted(
                (path for path in directory.iterdir() if path.is_file()),
                key=lambda path: (path.name.casefold(), path.name),
            )
        )
    except OSError as exc:
        raise InputFileError(
            "The selected project directory could not be inspected.",
            "Confirm that the directory is readable and try again.",
            {"path": str(directory), "reason": str(exc)},
        ) from exc
    topology = tuple(
        path for path in files if path.suffix.casefold() in TOPOLOGY_SUFFIXES
    )
    trajectory = tuple(
        path for path in files if path.suffix.casefold() in TRAJECTORY_SUFFIXES
    )
    index = tuple(path for path in files if path.suffix.casefold() == INDEX_SUFFIX)
    missing = []
    if not topology:
        missing.append("topology")
    if not trajectory:
        missing.append("trajectory")
    if missing:
        raise InputFileError(
            f"No supported {' or '.join(missing)} files were found in the selected directory.",
            "Select a directory containing supported topology and trajectory files.",
            {
                "path": str(directory),
                "missing": missing,
                "topology_suffixes": TOPOLOGY_SUFFIXES,
                "trajectory_suffixes": TRAJECTORY_SUFFIXES,
            },
        )
    return InputCandidates(directory, topology, trajectory, index)


class ProjectUseCases:
    def exists(self, root: str | Path) -> bool:
        directory = Path(root).expanduser().resolve()
        return ManifestRepository(directory).path.is_file()

    def discover_inputs(self, root: str | Path) -> InputCandidates:
        return discover_inputs(root)

    def create(
        self,
        root: str | Path,
        topology: str | Path,
        trajectory: str | Path,
        species_roles: dict[str, str] | None = None,
        index_file: str | Path | None = None,
    ) -> Project:
        return Project.create(root, topology, trajectory, species_roles, index_file)

    def ensure(
        self,
        root: str | Path,
        topology: str | Path,
        trajectory: str | Path,
        species_roles: dict[str, str] | None = None,
        index_file: str | Path | None = None,
    ) -> tuple[Project, bool]:
        project_root = Path(root).expanduser().resolve()
        if ManifestRepository(project_root).path.is_file():
            project = Project.open(project_root)
            project.verify_input_set(topology, trajectory, index_file)
            return project, False
        return (
            Project.create(
                project_root,
                topology,
                trajectory,
                species_roles,
                index_file,
                allow_nonempty=True,
            ),
            True,
        )

    def open(self, root: str | Path, verify_inputs: bool = True) -> Project:
        return Project.open(root, verify_inputs)

    def commit_result(
        self, project: Project, request: AnalysisRequest, result: AnalysisResult
    ) -> Path:
        return project.commit_result(request, result)

    def set_species_roles(self, project: Project, species_roles: dict[str, str]) -> None:
        project.set_species_roles(species_roles)

    def plot_state(self, project: Project) -> PlotState:
        return project.plot_state()

    def set_plot_state(self, project: Project, state: PlotState) -> None:
        project.set_plot_state(state)

    def list_results(self, project: Project) -> tuple[dict[str, object], ...]:
        return project.list_results()

    def load_result(self, project: Project, analysis_id: str) -> AnalysisResult:
        return project.load_result(analysis_id)
