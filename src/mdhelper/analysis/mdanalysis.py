"""Complete MDAnalysis analysis pipeline."""

from __future__ import annotations

from pathlib import Path
from threading import Event

from mdhelper.analysis.pipeline import AnalysisInput, BackendQuery
from mdhelper.core.analysis import AnalysisRequest, AnalysisResult, EnergyRequest, RadialRequest
from mdhelper.core.errors import BackendError
from mdhelper.integrations.manager import IntegrationManager

from .cumulative_rdf import cumulative_result
from .energy import _MDAnalysisEnergy
from .radial import mdanalysis_radial_profile
from .rdf import rdf_result


class MDAnalysisBackend:
    name = "mdanalysis"
    display_name = "MDAnalysis"
    analysis_types = frozenset(("rdf", "cumulative_rdf", "energy"))

    def __init__(self) -> None:
        self._energy = _MDAnalysisEnergy()

    def auto_priority(
        self,
        _query: BackendQuery,
        _integrations: IntegrationManager,
    ) -> int:
        return 20

    def required_capabilities(self, query: BackendQuery) -> tuple[str, ...]:
        del query
        return ()

    def validate_request(self, request: AnalysisRequest) -> None:
        request.validate()

    def opens_trajectory(self, request: AnalysisRequest) -> bool:
        return isinstance(request, RadialRequest)

    def fingerprints_inputs(self, request: AnalysisRequest) -> bool:
        del request
        return True

    def terms(
        self,
        integrations: IntegrationManager,
        energy_file: str | Path,
        cancel_event: Event | None = None,
        cache_dir: Path | None = None,
    ) -> tuple[str, ...]:
        return self._energy.terms(integrations, energy_file, cancel_event, cache_dir)

    def run(self, inputs: AnalysisInput) -> AnalysisResult:
        request = inputs.request
        if isinstance(request, EnergyRequest):
            return self._energy.run(inputs)
        source = inputs.source
        if not isinstance(request, RadialRequest) or source is None:
            raise BackendError("The MDAnalysis backend requires a supported request.")
        request.validate()
        profile = mdanalysis_radial_profile(
            source,
            request,
            "MDAnalysis RDF",
            inputs.progress,
            inputs.cancel_event,
            inputs.max_pairs_per_chunk,
        )
        if request.analysis_type == "rdf":
            return rdf_result(source, request, inputs.provenance, profile)
        return cumulative_result(source, request, inputs.provenance, profile)
