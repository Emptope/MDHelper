"""Terminal analysis selection and parameter editing workflows."""

from __future__ import annotations

from typing import cast

from mdhelper.core.analysis import AnalysisBackend, AnalysisType, analysis_label
from mdhelper.core.errors import InputError
from mdhelper.core.system import FrameRange
from mdhelper.tui.controllers.execution import AnalysisExecutionController
from mdhelper.tui.formatting import draft_issues, setup_panel, task_label
from mdhelper.tui.model import AnalysisDraft, RadialTask


class AnalysisController(AnalysisExecutionController):
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
            self.terminal.heading("RDF + CN setup")
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
            self.terminal.heading(f"{analysis_label(draft.analysis_type)} setup")
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
            self.terminal.heading(f"{analysis_label(draft.analysis_type)} groups")
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
        start = self.terminal.integer(
            "First zero-based frame", draft.frames.start, minimum=0
        )
        stop = self.terminal.integer(
            "Exclusive zero-based frame stop (empty means end)",
            draft.frames.stop,
            minimum=0,
            allow_empty=True,
        )
        stride = self.terminal.integer(
            "Frame stride (frames)", draft.frames.stride, minimum=1
        )
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
        self.terminal.heading(f"{action} radial task")
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
            self.terminal.heading("Radial task queue")
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
