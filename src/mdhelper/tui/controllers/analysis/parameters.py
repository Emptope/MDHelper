"""Terminal analysis parameter editing workflows."""

from __future__ import annotations

from typing import cast

from mdhelper.core.analysis import AnalysisBackend
from mdhelper.core.errors import InputError
from mdhelper.core.system import FrameRange
from mdhelper.tui.controllers.execution import AnalysisExecutionController
from mdhelper.tui.model import AnalysisDraft


class AnalysisParameterController(AnalysisExecutionController):
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
            return
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
