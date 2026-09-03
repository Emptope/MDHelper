"""Terminal analysis request execution and batch completion."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from mdhelper.app import default_plot_exports
from mdhelper.core.analysis import AnalysisRequest, AnalysisResult, analysis_label
from mdhelper.core.errors import InputError
from mdhelper.tui.controllers.base import ControllerContext
from mdhelper.tui.formatting import draft_issues, result_text
from mdhelper.tui.model import AnalysisDraft


class AnalysisExecutionController(ControllerContext):
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
                "Use Add task to configure at least one RDF or cumulative RDF task.",
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
            self.terminal.write(
                f"Task {number}/{len(requests)}: {analysis_label(request.analysis_type)}"
            )
            result = self.job_runner.run_sync(
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
        paths = self.application.exports.export_bundle(plots, output)
        if any(len(plot.items) > 1 for plot in plots):
            paths.extend(self.application.exports.save_plots(plots, output))
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
        self.terminal.heading("Analysis completed", blank_before=True)
        for result in results:
            self.terminal.write(result_text(result))
        self.terminal.write()
        self.terminal.write("Exported files:")
        for path in paths:
            self.terminal.write(f"  {path}")
        if project_paths:
            self.terminal.write()
        for path in project_paths:
            self.terminal.write(f"Project result: {path}")
