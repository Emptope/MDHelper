"""Terminal input, project, and species-role workflows."""

from __future__ import annotations

from pathlib import Path

from mdhelper.app import InputCandidates
from mdhelper.core.errors import InputError
from mdhelper.core.species import SPECIES_ROLES
from mdhelper.core.trajectory import TOPOLOGY_SUFFIXES, TRAJECTORY_SUFFIXES
from mdhelper.tui.controllers.base import ControllerContext
from mdhelper.tui.formatting import roles_text, summary_text


class WorkspaceController(ControllerContext):
    def _workspace(self) -> None:
        while True:
            choice = self.terminal.menu(
                "System and project",
                (
                    ("Open a new project", "1"),
                    ("Create a project from current inputs", "2"),
                    ("Show current system summary", "3"),
                    ("Save confirmed species roles", "4"),
                    ("Detach project but keep loaded inputs", "5"),
                    ("Reset the current session", "6"),
                ),
            )
            if choice is None:
                return
            if choice == "1":
                self._open_project()
                return
            if choice == "2":
                self._create_project()
                return
            if choice == "3":
                self._show_summary()
            elif choice == "4":
                self._save_roles()
            elif choice == "5":
                self.workspace.project = None
                self.terminal.write("Project detached; loaded inputs remain available.")
            elif choice == "6" and self.terminal.confirm(
                "Clear inputs, project state, drafts, and the in-memory result?"
            ):
                self.workspace.clear()
                self.terminal.write("Session reset.")

    def _load_inputs(self, topology: str | None = None) -> None:
        if topology is None:
            topology = self.terminal.ask(
                f"Topology path ({', '.join(TOPOLOGY_SUFFIXES)})"
            )
        trajectory = self.terminal.ask(
            f"Trajectory path ({', '.join(TRAJECTORY_SUFFIXES)})"
        )
        index_file = self.terminal.ask(
            "GROMACS index path (leave empty for selection expressions)",
            allow_empty=True,
        )
        self.workspace.clear()
        self.workspace.topology = topology
        self.workspace.trajectory = trajectory
        self.workspace.index_file = index_file or None
        self._inspect()

    def _inspect(self) -> None:
        if not self.workspace.loaded:
            raise InputError(
                "No topology and trajectory are loaded.",
                "Choose 'Open a new project' first.",
            )
        summary = self.application.checks.inspect_system(
            self.workspace.topology,
            self.workspace.trajectory,
            self.workspace.index_file,
            None if self.workspace.project is None else self.workspace.project.cache_dir,
            None if self.workspace.project is None else self.workspace.project.root,
        )
        self.workspace.summary = summary
        species = set(summary.species)
        self.workspace.roles = {
            name: role for name, role in self.workspace.roles.items() if name in species
        }
        self.terminal.heading("System inspection")
        self.terminal.write(summary_text(summary))
        if set(self.workspace.roles) != set(summary.species):
            self.terminal.write("Choose a role for each species before running an analysis.")
            self._roles()
            if (
                self.workspace.project is not None
                and set(self.workspace.roles) == set(summary.species)
            ):
                self.application.projects.set_species_roles(
                    self.workspace.project,
                    self.workspace.roles,
                )
        elif self.workspace.project is not None:
            self.terminal.write("Species roles loaded from the project.")

    def _show_summary(self) -> None:
        if self.workspace.summary is None:
            raise InputError("The current inputs have not been inspected.")
        self.terminal.heading("Current system")
        self.terminal.write(summary_text(self.workspace.summary))

    def _open_project(self, root: str | Path | None = None) -> None:
        if root is None:
            root = self.terminal.ask("Project directory")
        if self.application.projects.exists(root):
            self._open_existing_project(root)
            return
        self._prepare_project(root)

    def _prepare_project(self, root: str | Path) -> None:
        candidates = self.application.projects.discover_inputs(root)
        topology, trajectory, index_file = self._select_project_inputs(candidates)
        self.workspace.clear()
        self.workspace.topology = str(topology)
        self.workspace.trajectory = str(trajectory)
        self.workspace.index_file = None if index_file is None else str(index_file)
        project, created = self.application.projects.ensure(
            root,
            topology,
            trajectory,
            {},
            index_file,
        )
        self.workspace.project = project
        self._inspect()
        action = "created" if created else "opened"
        self.terminal.write(f"Project {action}: {project.root}")

    def _select_project_inputs(
        self,
        candidates: InputCandidates,
    ) -> tuple[Path, Path, Path | None]:
        topology = self.terminal.choose(
            "Topology file",
            tuple((path.name, path) for path in candidates.topology),
        )
        trajectory = self.terminal.choose(
            "Trajectory file",
            tuple((path.name, path) for path in candidates.trajectory),
        )
        index_options: tuple[tuple[str, Path | None], ...] = (
            ("Do not use an index file", None),
            *((path.name, path) for path in candidates.index),
        )
        index_default = candidates.index[0] if len(candidates.index) == 1 else None
        index_file = self.terminal.choose("Index file", index_options, index_default)
        return topology, trajectory, index_file

    def _open_existing_project(self, root: str | Path) -> None:
        project = self.application.projects.open(root)
        inputs = project.resolve_inputs()
        self.workspace.clear()
        self.workspace.project = project
        self.workspace.topology = str(inputs["topology"])
        self.workspace.trajectory = str(inputs["trajectory"])
        self.workspace.index_file = str(inputs["index"]) if "index" in inputs else None
        self.workspace.roles = dict(project.manifest.get("species_roles", {}))
        self._inspect()
        self.terminal.write(f"Project opened: {project.root}")

    def _create_project(self) -> None:
        self._require_confirmed_roles()
        root = self.terminal.ask("New project directory")
        project = self.application.projects.create(
            root,
            self.workspace.topology,
            self.workspace.trajectory,
            self.workspace.roles,
            self.workspace.index_file,
        )
        self.workspace.project = project
        self.terminal.write(f"Project created: {project.root}")

    def _save_roles(self) -> None:
        self._require_confirmed_roles()
        if self.workspace.project is None:
            raise InputError(
                "No project is open.", "Create or open a project before saving roles."
            )
        self.application.projects.set_species_roles(
            self.workspace.project,
            self.workspace.roles,
        )
        self.terminal.write("Confirmed species roles saved to the project.")

    def _roles(self) -> None:
        summary = self.workspace.summary
        if summary is None:
            raise InputError(
                "The system has not been inspected.", "Inspect the current inputs first."
            )
        while True:
            self.terminal.heading("Species and roles", blank_before=True)
            self.terminal.write(roles_text(self.workspace))
            choice = self.terminal.menu(
                "Role actions",
                (
                    ("Review and confirm every species", "1"),
                    ("Review and apply all available suggestions", "2"),
                    ("Change one species role", "3"),
                ),
            )
            if choice is None:
                return
            if choice == "1":
                for species in summary.species:
                    self._choose_role(species)
                return
            if choice == "2":
                self._apply_role_suggestions()
                if set(self.workspace.roles) == set(summary.species):
                    return
            elif choice == "3":
                species = self.terminal.choose(
                    "Select species",
                    tuple((name, name) for name in summary.species),
                )
                self._choose_role(species)

    def _choose_role(self, species: str) -> None:
        assert self.workspace.summary is not None
        suggestion = self.workspace.summary.role_suggestions[species]
        self.terminal.heading(f"Choose role: {species}")
        self.terminal.write(f"Numbers:  {self.workspace.summary.species[species]}")
        self.terminal.write(f"Suggestion: {suggestion.suggested_role or 'unavailable'}")
        self.terminal.write(f"Method:     {suggestion.method}")
        if suggestion.error:
            self.terminal.write(f"Error:      {suggestion.error}")
        current = self.workspace.roles.get(species) or suggestion.suggested_role
        role = self.terminal.choose(
            "Confirm a role",
            tuple((name, name) for name in SPECIES_ROLES),
            current,
        )
        self.workspace.roles[species] = role

    def _apply_role_suggestions(self) -> None:
        assert self.workspace.summary is not None
        suggestions = {
            name: item
            for name, item in self.workspace.summary.role_suggestions.items()
            if item.suggested_role is not None
        }
        if not suggestions:
            self.terminal.write("No role has a safe automatic suggestion.")
            return
        self.terminal.write("Suggestions to apply:")
        for species, suggestion in suggestions.items():
            self.terminal.write(f"  {species}: {suggestion.suggested_role}")
        if not self.terminal.confirm("Apply these suggestions?", default=True):
            return
        for species, suggestion in suggestions.items():
            assert suggestion.suggested_role is not None
            self.workspace.roles[species] = suggestion.suggested_role

    def _require_confirmed_roles(self) -> None:
        if not self.workspace.loaded or self.workspace.summary is None:
            raise InputError(
                "No inspected system is available.", "Load and inspect input files first."
            )
        missing = sorted(set(self.workspace.summary.species) - set(self.workspace.roles))
        if missing:
            raise InputError(
                "Every detected species needs an explicitly confirmed role.",
                "Review the automatic suggestions in the species-role menu.",
                {"unconfirmed_species": missing},
            )
