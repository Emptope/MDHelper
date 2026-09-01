"""Project aggregate coordinating specialized repositories."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mdhelper.core.analysis import AnalysisRequest, AnalysisResult
from mdhelper.core.errors import ConfigurationError
from mdhelper.core.plotting import PlotState
from mdhelper.core.species import validate_species_roles
from mdhelper.project.inputs import InputRecord, InputRepository
from mdhelper.project.manifests import ManifestRepository
from mdhelper.project.results import ResultRepository
from mdhelper.project.runs import RunRepository
from mdhelper.project.schema import PROJECT_SCHEMA_VERSION
from mdhelper.version import __version__


@dataclass
class Project:
    root: Path
    manifest: dict[str, Any]
    _manifests: ManifestRepository = field(init=False, repr=False)
    _inputs: InputRepository = field(init=False, repr=False)
    _runs: RunRepository = field(init=False, repr=False)
    _results: ResultRepository = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._manifests = ManifestRepository(self.root)
        self._inputs = InputRepository(self.root)
        self._runs = RunRepository(self.root)
        self._results = ResultRepository(
            self.root, self._manifests, self._inputs, self._runs
        )

    @property
    def manifest_path(self) -> Path:
        return self._manifests.path

    @property
    def cache_dir(self) -> Path:
        return self.root / "cache"

    @classmethod
    def create(
        cls,
        root: str | Path,
        topology: str | Path,
        trajectory: str | Path,
        species_roles: dict[str, str] | None = None,
        index_file: str | Path | None = None,
        allow_nonempty: bool = False,
    ) -> Project:
        roles = dict(species_roles or {})
        validate_species_roles(roles)
        project_root = Path(root).expanduser().resolve()
        manifests = ManifestRepository(project_root)
        inputs = InputRepository(project_root)
        records: dict[str, InputRecord] = {
            "topology": inputs.record(topology),
            "trajectory": inputs.record(trajectory),
        }
        if index_file is not None:
            records["index"] = inputs.record(index_file)
        manifest: dict[str, Any] = {
            "schema_version": PROJECT_SCHEMA_VERSION,
            "mdhelper_version": __version__,
            "created_at": datetime.now(UTC).isoformat(),
            "inputs": records,
            "species_roles": roles,
            "integration_preferences": {},
            "integration_runs": [],
            "analyses": [],
            "plot": PlotState().to_dict(),
        }
        return cls(project_root, manifests.create(manifest, allow_nonempty))

    @classmethod
    def open(cls, root: str | Path, verify_inputs: bool = True) -> Project:
        project_root = Path(root).expanduser().resolve()
        expected = ManifestRepository(project_root.parent).path
        if project_root == expected:
            project_root = project_root.parent
        elif project_root.exists() and not project_root.is_dir():
            raise ConfigurationError(
                f"The selected file is not an MDHelper project manifest: {project_root}",
                f"Select {expected.name} or its containing directory.",
            )
        manifests = ManifestRepository(project_root)
        manifest = manifests.load()
        manifests.ensure_layout()
        project = cls(project_root, manifest)
        project._runs.verify(manifest["integration_runs"])
        if verify_inputs:
            project.resolve_inputs(verify_fingerprints=True)
        return project

    def _commit(self, updated: dict[str, Any]) -> None:
        self.manifest = self._manifests.commit(updated)

    def resolve_inputs(self, verify_fingerprints: bool = True) -> dict[str, Path]:
        return self._inputs.resolve_all(self.manifest["inputs"], verify_fingerprints)

    def verify_input_set(
        self,
        topology: str | Path,
        trajectory: str | Path,
        index_file: str | Path | None = None,
    ) -> None:
        """Reject accidental reuse of a project for different simulation inputs."""

        requested = {
            "topology": self._inputs.record(topology),
            "trajectory": self._inputs.record(trajectory),
        }
        if index_file is not None:
            requested["index"] = self._inputs.record(index_file)
        mismatched = {
            role: {
                "project_sha256": self.manifest["inputs"][role]["sha256"],
                "selected_sha256": record["sha256"],
            }
            for role, record in requested.items()
            if role in self.manifest["inputs"]
            and self.manifest["inputs"][role]["sha256"] != record["sha256"]
        }
        if mismatched:
            raise ConfigurationError(
                "The existing project belongs to different simulation inputs.",
                "Open that project explicitly or place the new inputs in a separate directory.",
                {"mismatched_inputs": mismatched},
            )

    def relocate_input(self, role: str, new_path: str | Path) -> None:
        relocated = self._inputs.relocate(role, self.manifest["inputs"], new_path)
        self._commit(
            {
                **self.manifest,
                "inputs": {**self.manifest["inputs"], role: relocated},
            }
        )

    def set_species_roles(self, species_roles: dict[str, str]) -> None:
        roles = dict(species_roles)
        validate_species_roles(roles)
        self._commit({**self.manifest, "species_roles": roles})

    def plot_state(self) -> PlotState:
        return PlotState.from_dict(self.manifest["plot"])

    def set_plot_state(self, state: PlotState) -> None:
        state.validate()
        self._commit({**self.manifest, "plot": state.to_dict()})

    def set_integration_preference(
        self,
        logical_name: str,
        preferred: bool,
        required_capabilities: tuple[str, ...] = (),
    ) -> None:
        name = logical_name.strip().casefold()
        if not name:
            raise ConfigurationError("A project tool preference requires a tool name.")
        preference = {
            "preferred": preferred,
            "required_capabilities": list(required_capabilities),
        }
        self._commit(
            {
                **self.manifest,
                "integration_preferences": {
                    **self.manifest["integration_preferences"],
                    name: preference,
                },
            }
        )

    def record_integration_run(self, record: dict[str, Any]) -> None:
        records, paths = self._runs.store((record,))
        try:
            self._commit(
                {
                    **self.manifest,
                    "integration_runs": [
                        *self.manifest.get("integration_runs", []),
                        records[0],
                    ],
                }
            )
        except BaseException:
            self._runs.remove(paths)
            raise

    def commit_result(self, request: AnalysisRequest, result: AnalysisResult) -> Path:
        self.manifest, path = self._results.commit(self.manifest, request, result)
        return path

    def list_results(self) -> tuple[dict[str, object], ...]:
        return self._results.list(self.manifest)

    def load_result(self, analysis_id: str) -> AnalysisResult:
        return self._results.load(self.manifest, analysis_id)
