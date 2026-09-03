"""Terminal radial task queue editing workflows."""

from __future__ import annotations

from typing import cast

from mdhelper.core.analysis import AnalysisType, analysis_label
from mdhelper.core.errors import InputError
from mdhelper.tui.controllers.analysis.parameters import AnalysisParameterController
from mdhelper.tui.formatting import draft_issues, task_label
from mdhelper.tui.model import AnalysisDraft, RadialTask


class AnalysisQueueController(AnalysisParameterController):
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
