"""Terminal analysis navigation and setup orchestration."""

from __future__ import annotations

from typing import cast

from mdhelper.core.analysis import AnalysisType, analysis_label
from mdhelper.core.errors import InputError
from mdhelper.tui.controllers.analysis.queue import AnalysisQueueController
from mdhelper.tui.formatting import setup_panel
from mdhelper.tui.model import AnalysisDraft


class AnalysisController(AnalysisQueueController):
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
                    (f"Run task queue ({len(draft.queue)})", "1"),
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
