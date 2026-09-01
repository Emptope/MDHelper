"""Multi-level interactive terminal workflow built on application services."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import cast

from mdhelper.app import ApplicationService
from mdhelper.app.exports import default_plot_exports
from mdhelper.core.analysis import (
    AnalysisBackend,
    AnalysisRequest,
    AnalysisResult,
    AnalysisType,
    analysis_label,
)
from mdhelper.core.errors import InputError, MDHelperError
from mdhelper.core.species import SPECIES_ROLES, role_decision
from mdhelper.core.system import FrameRange
from mdhelper.core.trajectory import TOPOLOGY_SUFFIXES, TRAJECTORY_SUFFIXES
from mdhelper.runtime.logging import record_error
from mdhelper.tui.formatting import (
    draft_issues,
    error_text,
    result_text,
    roles_text,
    setup_panel,
    summary_text,
    task_label,
)
from mdhelper.tui.model import AnalysisDraft, RadialTask, Workspace
from mdhelper.tui.terminal import EndOfInput, Terminal
from mdhelper.version import DEVELOPER, __version__
from mdhelper.workflow.tasks import TaskService


class Tui:
    """Stateful numbered-menu adapter suitable for Windows and POSIX terminals."""

    def __init__(self, application: ApplicationService, terminal: Terminal):
        self.application = application
        self.terminal = terminal
        self.workspace = Workspace()
        self.tasks = TaskService(application)

    def run(self) -> int:
        self._banner()
        try:
            while True:
                choice = self._main_choice() if self.workspace.loaded else self._load_choice()
                if choice == "q":
                    return 0
                if self.workspace.loaded:
                    self._action(choice)
                else:
                    self._load_action(choice)
        except EndOfInput:
            self.terminal.write("\nInput closed; exiting MDHelper.")
            return 0
        except KeyboardInterrupt:
            self.terminal.write("\nOperation interrupted; incomplete results were not committed.")
            return 7
        finally:
            self.tasks.shutdown()

    def _banner(self) -> None:
        self.terminal.rule()
        self.terminal.write(f"MDHelper {__version__} interactive terminal")
        self.terminal.write(f"Developer: {DEVELOPER}")
        self.terminal.write("Press Ctrl+C to interrupt an operation and to exit the program.")
        self.terminal.rule()

    def _load_choice(self) -> str | None:
        self._write_context()
        return self.terminal.menu(
            "Load",
            (
                ("Load topology and trajectory", "1"),
                ("Open an existing project", "2"),
                ("Quit", "q"),
            ),
            back=False,
        )

    def _main_choice(self) -> str | None:
        self._write_context()
        return self.terminal.menu(
            "Main menu",
            (
                ("Analysis", "1"),
                ("Results and export", "2"),
                ("Input files and inspection", "3"),
                ("Project", "4"),
                ("Species roles", "5"),
                ("Tools", "6"),
                ("Quit", "q"),
            ),
            back=False,
        )

    def _write_context(self) -> None:
        project = (
            "none" if self.workspace.project is None else str(self.workspace.project.root)
        )
        self.terminal.write()
        self.terminal.write(f"Current project: {project}")

    def _load_action(self, choice: str | None) -> None:
        actions = {
            "1": self._load_inputs,
            "2": self._open_project,
        }
        self._perform(actions.get(choice or ""))

    def _action(self, choice: str | None) -> None:
        actions = {
            "1": self._analyses,
            "2": self._results,
            "3": self._inputs,
            "4": self._projects,
            "5": self._roles,
            "6": self._tools,
        }
        self._perform(actions.get(choice or ""))

    def _perform(self, action: Callable[[], None] | None) -> None:
        if action is None:
            return
        try:
            action()
        except EndOfInput:
            raise
        except (MDHelperError, OSError, ValueError) as exc:
            record_error(exc, "TUI operation")
            self.terminal.rule("Action could not be completed")
            self.terminal.write(error_text(exc))
        except Exception as exc:
            record_error(exc, "TUI operation")
            self.terminal.rule("Unexpected internal error")
            self.terminal.write(error_text(exc))

    def _tools(self) -> None:
        while True:
            choice = self.terminal.menu(
                "Tools",
                (
                    ("Integrations", "1"),
                    ("Templates", "2"),
                    ("Configuration summary", "3"),
                ),
            )
            if choice is None:
                return
            if choice == "1":
                self._integrations()
            elif choice == "2":
                self._templates()
            else:
                self._config()

    def _inputs(self) -> None:
        while True:
            choice = self.terminal.menu(
                "Input files and inspection",
                (
                    ("Load topology and trajectory", "1"),
                    ("Inspect current inputs", "2"),
                    ("Show current system summary", "3"),
                    ("Reset the current session", "4"),
                ),
            )
            if choice is None:
                return
            if choice == "1":
                self._load_inputs()
                return
            if choice == "2":
                self._inspect()
            elif choice == "3":
                self._show_summary()
            elif choice == "4" and self.terminal.confirm(
                "Clear inputs, project state, drafts, and the in-memory result?"
            ):
                self.workspace.clear()
                self.terminal.write("Session reset.")

    def _load_inputs(self) -> None:
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
                "Choose 'Load topology and trajectory' first.",
            )
        summary = self.application.checks.inspect_system(
            self.workspace.topology,
            self.workspace.trajectory,
            self.workspace.index_file,
            None if self.workspace.project is None else self.workspace.project.cache_dir,
        )
        self.workspace.summary = summary
        species = set(summary.species)
        self.workspace.roles = {
            name: role for name, role in self.workspace.roles.items() if name in species
        }
        self.workspace.role_decisions = {
            name: value
            for name, value in self.workspace.role_decisions.items()
            if name in species
        }
        if self.workspace.project is not None:
            for name, role in self.workspace.roles.items():
                self.workspace.role_decisions.setdefault(
                    name,
                    {
                        "decision": "loaded_from_project",
                        "selected_role": role,
                        "suggestion": summary.role_suggestions[name].to_dict(),
                    },
                )
        self.terminal.rule("System inspection")
        self.terminal.write(summary_text(summary))
        if set(self.workspace.roles) != set(summary.species):
            self.terminal.write("Choose a role for each species before running an analysis.")
            self._roles()
        elif self.workspace.project is not None:
            self.terminal.write("Species roles loaded from the project.")

    def _show_summary(self) -> None:
        if self.workspace.summary is None:
            raise InputError("The current inputs have not been inspected.")
        self.terminal.rule("Current system")
        self.terminal.write(summary_text(self.workspace.summary))

    def _projects(self) -> None:
        while True:
            project_label = (
                "none" if self.workspace.project is None else str(self.workspace.project.root)
            )
            self.terminal.write(f"Current project: {project_label}")
            choice = self.terminal.menu(
                "Project",
                (
                    ("Open an existing project", "1"),
                    ("Create a project from current inputs", "2"),
                    ("Save confirmed species roles", "3"),
                    ("Detach project but keep loaded inputs", "4"),
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
                self._save_roles()
            elif choice == "4":
                self.workspace.project = None
                self.terminal.write("Project detached; loaded inputs remain available.")

    def _open_project(self) -> None:
        root = self.terminal.ask("Project directory")
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
            self.workspace.project, self.workspace.roles
        )
        self.terminal.write("Confirmed species roles saved to the project.")

    def _roles(self) -> None:
        summary = self.workspace.summary
        if summary is None:
            raise InputError(
                "The system has not been inspected.", "Inspect the current inputs first."
            )
        while True:
            self.terminal.rule("Species roles")
            self.terminal.write(roles_text(self.workspace))
            choice = self.terminal.menu(
                "Role actions",
                (
                    ("Review and confirm every species", "1"),
                    ("Review and apply all available suggestions", "2"),
                    ("Change one species role", "3"),
                    ("Save confirmed roles to the current project", "4"),
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
            elif choice == "4":
                self._save_roles()
                return

    def _choose_role(self, species: str) -> None:
        assert self.workspace.summary is not None
        suggestion = self.workspace.summary.role_suggestions[species]
        self.terminal.rule(f"Choose role: {species}")
        self.terminal.write(f"Numbers:  {self.workspace.summary.species[species]}")
        self.terminal.write(
            f"Suggestion: {suggestion.suggested_role or 'unavailable'} "
            f"({suggestion.confidence} confidence)"
        )
        self.terminal.write(f"Method:     {suggestion.method}")
        if suggestion.reason:
            self.terminal.write(f"Reason:     {suggestion.reason}")
        current = self.workspace.roles.get(species) or suggestion.suggested_role
        role = self.terminal.choose(
            "Confirm a role",
            tuple((name, name) for name in SPECIES_ROLES),
            current,
        )
        self.workspace.roles[species] = role
        self.workspace.role_decisions[species] = role_decision(
            role, suggestion, "role_editor"
        )

    def _apply_role_suggestions(self) -> None:
        assert self.workspace.summary is not None
        suggestions = {
            name: item
            for name, item in self.workspace.summary.role_suggestions.items()
            if item.available and item.suggested_role is not None
        }
        if not suggestions:
            self.terminal.write("No role has a safe automatic suggestion.")
            return
        self.terminal.write("Suggestions to apply:")
        for species, suggestion in suggestions.items():
            self.terminal.write(
                f"  {species}: {suggestion.suggested_role} "
                f"({suggestion.confidence}; {suggestion.method})"
            )
        if not self.terminal.confirm("Apply these suggestions?"):
            return
        for species, suggestion in suggestions.items():
            assert suggestion.suggested_role is not None
            self.workspace.roles[species] = suggestion.suggested_role
            self.workspace.role_decisions[species] = role_decision(
                suggestion.suggested_role, suggestion, "suggestion_batch"
            )

    def _require_confirmed_roles(self) -> None:
        if not self.workspace.loaded or self.workspace.summary is None:
            raise InputError(
                "No inspected system is available.", "Load and inspect input files first."
            )
        missing = sorted(set(self.workspace.summary.species) - set(self.workspace.roles))
        if missing:
            raise InputError(
                "Every detected species needs an explicitly confirmed role.",
                "Use the species-role menu; choose 'other' when no domain role applies.",
                {"unconfirmed_species": missing},
            )

    def _analyses(self) -> None:
        if not self.workspace.loaded:
            raise InputError(
                "No topology and trajectory are loaded.", "Load input files first."
            )
        while True:
            options = [
                (analysis_label("rdf"), "1"),
                (analysis_label("cumulative_rdf"), "2"),
                ("RDF + CN Combined Plot", "3"),
                (analysis_label("energy"), "4"),
            ]
            choice = self.terminal.menu(
                "Choose analysis",
                tuple(options),
            )
            if choice is None:
                return
            if choice == "3":
                self._rdf_cn_setup()
                continue
            analysis_type = cast(
                AnalysisType,
                {
                    "1": "rdf",
                    "2": "cumulative_rdf",
                    "4": "energy",
                }[choice],
            )
            self._analysis_setup(self.workspace.draft(analysis_type))

    def _rdf_cn_setup(self) -> None:
        draft = self.workspace.rdf_cn()
        self._prepare_setup(draft, edit_groups=False)
        while True:
            self.terminal.rule("RDF + CN setup")
            self.terminal.write(setup_panel(draft, self.workspace))
            choice = self.terminal.menu(
                "Options",
                (
                    (
                        f"Run task queue ({len(draft.queue)})",
                        "1",
                    ),
                    ("Change groups", "2"),
                    ("Change frames", "3"),
                    ("Change parameters", "4"),
                    ("Change export folder", "5"),
                    ("Change analysis backend", "6"),
                    self._task_option(draft),
                    ("Manage task queue", "8"),
                ),
            )
            if choice is None:
                return
            if choice == "1":
                if self._run_rdf_cn(draft):
                    return
            elif choice == "2":
                self._edit_selections(draft)
            elif choice == "3":
                self._edit_sampling(draft)
            elif choice == "4":
                self._edit_parameters(draft)
            elif choice == "5":
                draft.output = self.terminal.ask("Export directory", draft.output)
            elif choice == "6":
                self._edit_backend(draft)
            elif choice == "7":
                self._edit_task(draft, mixed=True)
            elif choice == "8":
                self._manage_tasks(draft)

    def _analysis_setup(self, draft: AnalysisDraft) -> None:
        initialized = self._prepare_setup(draft)
        if initialized:
            self._add_task(draft)
        while True:
            self.terminal.rule(f"{analysis_label(draft.analysis_type)} setup")
            self.terminal.write(setup_panel(draft, self.workspace))
            options: list[tuple[str, str]] = [
                (
                    "Run current setup"
                    if draft.analysis_type == "energy"
                    else f"Run task queue ({len(draft.queue)})",
                    "1",
                ),
            ]
            if draft.analysis_type != "energy":
                options.extend((("Change groups", "2"), ("Change frames", "3")))
            options.extend(
                (
                    ("Change parameters", "4"),
                    ("Change export folder", "5"),
                    ("Change analysis backend", "6"),
                )
            )
            if draft.analysis_type != "energy":
                options.extend(
                    (
                        self._task_option(draft),
                        ("Manage task queue", "8"),
                    )
                )
            choice = self.terminal.menu("Options", options)
            if choice is None:
                return
            if choice == "1":
                if self._run_analysis(draft):
                    return
            elif choice == "2":
                self._edit_selections(draft)
            elif choice == "3":
                self._edit_sampling(draft)
            elif choice == "4":
                self._edit_parameters(draft)
            elif choice == "5":
                self._edit_output(draft)
            elif choice == "6":
                self._edit_backend(draft)
            elif choice == "7":
                self._edit_task(draft)
            elif choice == "8":
                self._manage_tasks(draft)

    def _prepare_setup(
        self,
        draft: AnalysisDraft,
        *,
        edit_groups: bool = True,
    ) -> bool:
        summary = self.workspace.summary
        if summary is not None and set(self.workspace.roles) != set(summary.species):
            self._roles()
            self._require_confirmed_roles()
        if draft.analysis_type == "energy":
            if draft.analysis_backend == "gromacs":
                self._require_gromacs("energy", "GROMACS Energy")
            if not draft.energy_file or not draft.energy_terms:
                self._edit_parameters(draft)
            return False
        if edit_groups and (
            not draft.reference.strip() or not draft.selection.strip()
        ):
            self.terminal.rule(f"{analysis_label(draft.analysis_type)} groups")
            self.terminal.write("Choose the groups to analyze.")
            self._edit_selections(draft)
            return True
        return False

    def _selection(self, title: str, current: str = "") -> str:
        summary = self.workspace.summary
        if self.workspace.index_file:
            if summary is None or not summary.index_groups:
                raise InputError(
                    "No valid index groups are available.",
                    "Inspect the index file or reload inputs without an index file.",
                )
            options = tuple(
                (f"{name} ({count} atoms)", name)
                for name, count in summary.index_groups.items()
            )
            default = current if current in summary.index_groups else None
            return self.terminal.choose(title, options, default)
        return self.terminal.ask(title, current or None)

    def _edit_selections(self, draft: AnalysisDraft) -> None:
        draft.reference = self._selection("Reference", draft.reference)
        draft.selection = self._selection("Selection", draft.selection)

    def _edit_sampling(self, draft: AnalysisDraft) -> None:
        start = self.terminal.integer("First zero-based frame", draft.frames.start, minimum=0)
        stop = self.terminal.integer(
            "Exclusive zero-based frame stop (empty means end)",
            draft.frames.stop,
            minimum=0,
            allow_empty=True,
        )
        stride = self.terminal.integer("Frame stride (frames)", draft.frames.stride, minimum=1)
        assert start is not None and stride is not None
        frames = FrameRange(start, stop, stride)
        frames.validate()
        draft.frames = frames

    def _edit_parameters(self, draft: AnalysisDraft) -> None:
        if draft.analysis_type in {"rdf", "cumulative_rdf"}:
            radius = self.terminal.number(
                "Maximum radius (nm)", draft.r_max_nm, minimum=0.001
            )
            bin_width = self.terminal.number(
                "Bin width (nm)", draft.bin_width_nm, minimum=0.000001
            )
            draft.r_max_nm = radius
            draft.bin_width_nm = bin_width
            self._manual_parameter(draft, "r_max_nm", radius)
            self._manual_parameter(draft, "bin_width_nm", bin_width)
        else:
            if draft.analysis_backend == "gromacs":
                self._require_gromacs("energy", "GROMACS Energy")
            energy_file = self.terminal.ask(
                "GROMACS energy file", draft.energy_file or None
            )
            terms = self.application.analyses.energy_terms(
                energy_file,
                draft.analysis_backend,
                cache_dir=(
                    None
                    if self.workspace.project is None
                    else self.workspace.project.cache_dir
                ),
            )
            selected = self.terminal.select_many(
                "Energy terms",
                tuple((term, term) for term in terms),
                draft.energy_terms,
            )
            draft.energy_file = energy_file
            draft.energy_terms = list(selected)

    @staticmethod
    def _task_option(draft: AnalysisDraft) -> tuple[str, str]:
        return ("Update task" if draft.queue_index is not None else "Add task", "7")

    def _edit_task(self, draft: AnalysisDraft, *, mixed: bool = False) -> None:
        action = "Update" if draft.queue_index is not None else "Add"
        self.terminal.rule(f"{action} radial task")
        if mixed:
            selected = self.terminal.choose(
                "Analysis type",
                (
                    (analysis_label("rdf"), "rdf"),
                    (analysis_label("cumulative_rdf"), "cumulative_rdf"),
                ),
                draft.analysis_type,
            )
            draft.analysis_type = cast(AnalysisType, selected)
        self._edit_selections(draft)
        self._edit_parameters(draft)
        self._add_task(draft)

    def _add_task(self, draft: AnalysisDraft) -> None:
        issues = draft_issues(draft, self.workspace)
        if issues:
            raise InputError(
                "The current setup cannot be queued.",
                "Complete every item shown under 'Missing'.",
                {"required_decisions": issues},
            )
        draft.request(self.workspace)
        task = RadialTask.from_draft(draft)
        index = draft.queue_index
        if index is None:
            index = next(
                (
                    number
                    for number, queued in enumerate(draft.queue)
                    if (
                        queued.analysis_type,
                        queued.reference,
                        queued.selection,
                    )
                    == (task.analysis_type, task.reference, task.selection)
                ),
                None,
            )
        if index is None:
            draft.queue.append(task)
            index = len(draft.queue) - 1
            action = "Added"
        else:
            draft.queue[index] = task
            action = "Updated"
        draft.queue_index = None
        self.terminal.write(f"{action} task {index + 1}: {task_label(task)}")

    def _manage_tasks(self, draft: AnalysisDraft) -> None:
        if not draft.queue:
            self.terminal.write("The task queue is empty.")
            return
        while draft.queue:
            self.terminal.rule("Radial task queue")
            for number, task in enumerate(draft.queue, 1):
                self.terminal.write(f"  {number}. {task_label(task)}")
            choice = self.terminal.menu(
                "Queue actions",
                (
                    ("Load a task for editing", "1"),
                    ("Remove a task", "2"),
                    ("Clear the task queue", "3"),
                ),
            )
            if choice is None:
                return
            if choice == "3":
                if self.terminal.confirm("Clear every queued task?"):
                    draft.queue.clear()
                    draft.queue_index = None
                    self.terminal.write("Task queue cleared.")
                return
            index = self.terminal.choose(
                "Queued tasks",
                tuple(
                    (task_label(task), number)
                    for number, task in enumerate(draft.queue)
                ),
            )
            if choice == "1":
                draft.queue[index].load(draft)
                draft.queue_index = index
                self.terminal.write(f"Loaded task {index + 1} for editing.")
                return
            draft.queue.pop(index)
            if draft.queue_index == index:
                draft.queue_index = None
            elif draft.queue_index is not None and draft.queue_index > index:
                draft.queue_index -= 1
            self.terminal.write(f"Removed task {index + 1}.")

    def _edit_backend(self, draft: AnalysisDraft) -> None:
        choices: list[tuple[str, str]] = [
            ("Automatic selection", "auto"),
            ("MDAnalysis", "mdanalysis"),
        ]
        configured = self.application.integrations.is_configured("gromacs")
        if draft.analysis_type != "energy":
            if self.workspace.index_file:
                choices.insert(1, ("Native", "native"))
            gromacs = configured and self._gromacs_supports(
                draft.analysis_type,
                draft.frames,
            )
        else:
            gromacs = configured and self._gromacs_supports("energy")
        if gromacs:
            choices.append(("GROMACS (local gmx)", "gromacs"))
        selected = self.terminal.choose(
            "Analysis backend",
            tuple(choices),
            draft.analysis_backend,
        )
        draft.analysis_backend = cast(AnalysisBackend, selected)

    def _gromacs_supports(
        self,
        analysis_type: str,
        frames: FrameRange | None = None,
    ) -> bool:
        required = self.application.analyses.backend_capabilities(
            "gromacs",
            analysis_type,
            frames,
        )
        return self.application.integrations.supports("gromacs", *required)

    def _require_gromacs(self, analysis_type: str, feature: str) -> None:
        if self._gromacs_supports(analysis_type):
            return
        required = self.application.analyses.backend_capabilities(
            "gromacs",
            analysis_type,
        )
        raise InputError(
            f"{feature} is unavailable because no compatible GROMACS executable was detected.",
            "Configure or detect GROMACS under Tools > Integrations.",
            {"required_capabilities": list(required)},
        )

    @staticmethod
    def _manual_parameter(draft: AnalysisDraft, name: str, value: int | float) -> None:
        existing = draft.parameter_provenance.get(name)
        draft.parameter_provenance[name] = {
            **(existing if isinstance(existing, dict) else {}),
            "decision": "overridden" if existing else "manual",
            "selected_value": value,
        }

    def _edit_output(self, draft: AnalysisDraft) -> None:
        draft.output = self.terminal.ask("Export directory", draft.output or None)

    def _run_analysis(self, draft: AnalysisDraft) -> bool:
        runs = (draft,) if draft.analysis_type == "energy" else self._radial_runs(draft)
        requests = self._requests(runs)
        results = self._run_requests(requests)
        self._complete_batch(results, draft.output)
        return True

    def _run_rdf_cn(self, draft: AnalysisDraft) -> bool:
        runs = self._radial_runs(draft)
        requests = self._requests(runs)
        results = self._run_requests(requests)
        self._complete_batch(results, draft.output)
        return True

    def _radial_runs(
        self,
        draft: AnalysisDraft,
    ) -> tuple[AnalysisDraft, ...]:
        if not draft.queue:
            raise InputError(
                "The task queue is empty.",
                "Use Add task to configure at least one RDF or CN task.",
            )
        runs: list[AnalysisDraft] = []
        for task in draft.queue:
            item = replace(
                draft,
                analysis_type=task.analysis_type,
                queue=[],
                queue_index=None,
            )
            task.load(item)
            runs.append(item)
        return tuple(runs)

    def _requests(self, drafts: tuple[AnalysisDraft, ...]) -> tuple[AnalysisRequest, ...]:
        issues: list[str] = []
        for number, draft in enumerate(drafts, 1):
            issues.extend(
                f"task {number}: {issue}"
                for issue in draft_issues(draft, self.workspace)
            )
        if issues:
            raise InputError(
                "Setup is incomplete.",
                "Complete every item shown under 'Missing'.",
                {"required_decisions": issues},
            )
        return tuple(draft.request(self.workspace) for draft in drafts)

    def _run_requests(
        self,
        requests: tuple[AnalysisRequest, ...],
    ) -> tuple[AnalysisResult, ...]:
        cache_dir = (
            None if self.workspace.project is None else self.workspace.project.cache_dir
        )
        results: list[AnalysisResult] = []
        for number, request in enumerate(requests, 1):
            self.terminal.rule(
                f"Task {number}/{len(requests)}: {analysis_label(request.analysis_type)}"
            )
            result = self.tasks.run_sync(
                request,
                self.terminal.progress,
                cache_dir=cache_dir,
            )
            self.terminal.finish_progress()
            results.append(result)
        return tuple(results)

    def _export_batch(
        self,
        results: tuple[AnalysisResult, ...],
        output: str | Path,
    ) -> list[Path]:
        plots = default_plot_exports(results)
        paths = self.application.analyses.export_bundle(plots, output)
        if any(len(plot.items) > 1 for plot in plots):
            paths.extend(self.application.analyses.save_plots(plots, output))
        return paths

    def _complete_batch(
        self,
        results: tuple[AnalysisResult, ...],
        output: str | Path,
    ) -> None:
        self.workspace.result = results[-1]
        self.workspace.plot_results = results
        paths = self._export_batch(results, output)
        project = self.workspace.project
        project_paths: list[Path] = []
        if project is not None:
            for result in results:
                project_paths.append(
                    self.application.projects.commit_result(
                        project,
                        AnalysisRequest.from_dict(result.request),
                        result,
                    )
                )
        self.terminal.rule("Analysis completed")
        for result in results:
            self.terminal.write(result_text(result))
        self.terminal.write("Exported files:")
        for path in paths:
            self.terminal.write(f"  {path}")
        for path in project_paths:
            self.terminal.write(f"Project result: {path}")

    def _results(self) -> None:
        while True:
            choice = self.terminal.menu(
                "Results and export",
                (
                    ("Show the current in-memory result", "1"),
                    ("Save the current plot to the project", "2"),
                    ("Export the current analysis results", "3"),
                    ("Load a completed result from the current project", "4"),
                ),
            )
            if choice is None:
                return
            if choice == "1":
                self._show_result()
            elif choice == "2":
                self._save_project_figures()
            elif choice == "3":
                self._export_result()
            elif choice == "4":
                self._load_result()

    def _require_result(self) -> AnalysisResult:
        if self.workspace.result is None:
            raise InputError(
                "No completed result is loaded.",
                "Run an analysis or load a saved project result first.",
            )
        return self.workspace.result

    def _show_result(self) -> None:
        self.terminal.rule("Current result")
        self.terminal.write(result_text(self._require_result()))

    def _current_plots(self) -> tuple[AnalysisResult, ...]:
        result = self._require_result()
        return self.workspace.plot_results or (result,)

    def _save_project_figures(self) -> None:
        project = self.workspace.project
        if project is None:
            raise InputError(
                "No project is open.",
                "Open a project before saving plots to its figures directory.",
            )
        directory = project.root / "figures"
        paths = self.application.analyses.save_plots(
            default_plot_exports(self._current_plots()),
            directory,
        )
        self.terminal.write(f"Saved {len(paths)} figure file(s) to {directory}.")

    def _export_result(self) -> None:
        output = self.terminal.ask("Export directory")
        paths = self._export_batch(self._current_plots(), output)
        self.terminal.write(f"Exported {len(paths)} file(s) to {output}.")

    def _load_result(self) -> None:
        project = self.workspace.project
        if project is None:
            raise InputError(
                "No project is open.", "Open a project before loading its result history."
            )
        entries = tuple(
            entry
            for entry in self.application.projects.list_results(project)
            if entry.get("available", True) is not False
        )
        if not entries:
            self.terminal.write("The project has no available completed results.")
            return
        options = tuple((self._result_label(entry), str(entry["analysis_id"])) for entry in entries)
        analysis_id = self.terminal.choose("Completed project results", options)
        self.workspace.result = self.application.projects.load_result(project, analysis_id)
        self.workspace.plot_results = (self.workspace.result,)
        self._show_result()

    @staticmethod
    def _result_label(entry: dict[str, object]) -> str:
        analysis_type = str(entry.get("analysis_type", "analysis")).upper()
        committed = str(entry.get("committed_at", "unknown time"))
        request = entry.get("request")
        selection = ""
        if isinstance(request, dict):
            reference = request.get("reference", "")
            selected = request.get("selection", "")
            selection = f" | {reference}" + (f"-{selected}" if selected else "")
        return f"{committed} | {analysis_type}{selection}"

    def _integrations(self) -> None:
        names = self.application.integrations.names()
        while True:
            options = tuple(
                (f"Detect {name}", str(number))
                for number, name in enumerate(names, 1)
            )
            choice = self.terminal.menu("Integrations", options)
            if choice is None:
                return
            name = names[int(choice) - 1]
            status = self.application.integrations.detect(name)
            self.terminal.rule(f"{name} detection")
            availability = "available" if status.available else "unavailable"
            self.terminal.write(
                f"{status.path or 'not found'} | {availability} | "
                f"{status.version or 'unknown'}"
            )
            if status.capabilities:
                self.terminal.write(f"  capabilities: {', '.join(status.capabilities)}")
            if status.error:
                self.terminal.write(f"  {status.error}")

    def _templates(self) -> None:
        while True:
            templates = self.application.templates.list()
            choice = self.terminal.menu(
                "Templates",
                tuple(
                    (f"{item.category} / {item.title}", str(number))
                    for number, item in enumerate(templates, 1)
                ),
            )
            if choice is None:
                return
            template = templates[int(choice) - 1]
            self.terminal.rule(template.title)
            self.terminal.write(template.content)

    def _config(self) -> None:
        config = self.application.config
        self.terminal.rule("Resolved configuration")
        self.terminal.write(f"Path: {self.application.config_file}")
        self.terminal.write(f"Maximum pairs per chunk: {config.resources.max_pairs_per_chunk}")
        self.terminal.write(f"GUI theme: {config.gui.theme}")
        self.terminal.write(f"GUI font size: {config.gui.font_size:g} pt")
        self.terminal.write("Configured integrations:")
        for name, item in sorted(config.integrations.items()):
            self.terminal.write(
                f"  {name}: {'enabled' if item.enabled else 'disabled'}, "
                f"path={item.path or 'automatic detection'}"
            )
