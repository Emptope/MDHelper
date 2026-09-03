"""Terminal result history, export, and plot workflows."""

from __future__ import annotations

from mdhelper.app import default_plot_exports
from mdhelper.core.analysis import AnalysisResult
from mdhelper.core.errors import InputError
from mdhelper.tui.controllers.execution import AnalysisExecutionController
from mdhelper.tui.formatting import result_text


class ResultController(AnalysisExecutionController):
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
        self.terminal.heading("Current result")
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
        paths = self.application.exports.save_plots(
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
