"""Complete native analysis pipeline."""

from __future__ import annotations

from pathlib import Path

from mdhelper.analysis.pipeline import AnalysisInput, BackendQuery
from mdhelper.core.analysis import AnalysisRequest, AnalysisResult, RadialRequest
from mdhelper.core.errors import BackendError, InputError
from mdhelper.integrations.manager import IntegrationManager

from .cumulative_rdf import cumulative_result
from .radial import radial_profile
from .rdf import rdf_result


class NativeBackend:
    name = "native"
    display_name = "Native"
    analysis_types = frozenset(("rdf", "cumulative_rdf"))

    def auto_priority(
        self,
        query: BackendQuery,
        _integrations: IntegrationManager,
    ) -> int | None:
        if query.index_file is None or query.topology is None or query.trajectory is None:
            return None
        if (
            Path(query.topology).suffix.casefold() != ".gro"
            or Path(query.trajectory).suffix.casefold() != ".gro"
        ):
            return None
        return 10

    def required_capabilities(self, query: BackendQuery) -> tuple[str, ...]:
        del query
        return ()

    def validate_request(self, request: AnalysisRequest) -> None:
        if not isinstance(request, RadialRequest):
            raise BackendError("The Native backend requires a radial request.")
        if request.index_file is None:
            raise InputError(
                "The Native backend requires index groups.",
                "Select an .ndx file, or use Auto or MDAnalysis for selection expressions.",
            )

    def opens_trajectory(self, request: AnalysisRequest) -> bool:
        return isinstance(request, RadialRequest)

    def fingerprints_inputs(self, request: AnalysisRequest) -> bool:
        del request
        return True

    def run(self, inputs: AnalysisInput) -> AnalysisResult:
        request = inputs.request
        source = inputs.source
        if not isinstance(request, RadialRequest) or source is None:
            raise BackendError("The Native backend requires a radial request.")
        request.validate()
        profile = radial_profile(
            source,
            request,
            "Native radial analysis",
            inputs.progress,
            inputs.cancel_event,
            inputs.max_pairs_per_chunk,
        )
        if request.analysis_type == "rdf":
            return rdf_result(source, request, inputs.provenance, profile)
        return cumulative_result(source, request, inputs.provenance, profile)
