"""Analysis execution and result-export use cases."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from threading import Event

from mdhelper.analysis.common import check_cancel
from mdhelper.app.context import ApplicationContext
from mdhelper.core.analysis import (
    AnalysisRequest,
    AnalysisResult,
    EnergyRequest,
    RadialRequest,
)
from mdhelper.core.errors import (
    BackendError,
    ConfigurationError,
    FormatError,
    InputError,
    MDHelperError,
    TaskCancelled,
)
from mdhelper.core.plotting import DEFAULT_PLOT_SCHEME, PlotLimits
from mdhelper.core.progress import ProgressCallback
from mdhelper.core.species import role_decision, role_policy
from mdhelper.core.trajectory import TrajectorySource
from mdhelper.io.export import export_comparison_figures, export_figures, export_result
from mdhelper.plugins.analysis import AnalysisInput, BackendAdapter, BackendQuery
from mdhelper.services.provenance import analysis_provenance, input_provenance
from mdhelper.services.system import summarize_source, trajectory_cache


class AnalysisUseCases:
    def __init__(self, context: ApplicationContext):
        self.context = context

    def export(
        self,
        result: AnalysisResult,
        output_directory: str | Path,
        include_figures: bool = True,
        scheme: str = DEFAULT_PLOT_SCHEME,
        limits: PlotLimits | None = None,
    ) -> list[Path]:
        return export_result(result, output_directory, include_figures, scheme, limits)

    def export_figures(
        self,
        result: AnalysisResult,
        output_directory: str | Path,
        stem: str | None = None,
        scheme: str = DEFAULT_PLOT_SCHEME,
        limits: PlotLimits | None = None,
    ) -> list[Path]:
        return export_figures(result, output_directory, stem, scheme, limits)

    def export_comparison_figures(
        self,
        results: Sequence[AnalysisResult],
        output_directory: str | Path,
        stem: str = "comparison",
        labels: Sequence[str | None] | None = None,
        color_ids: Sequence[int] | None = None,
        series_keys: Sequence[str | None] | None = None,
        group_ids: Sequence[str | None] | None = None,
        titles: Sequence[str | None] | None = None,
        scheme: str = DEFAULT_PLOT_SCHEME,
        limits: PlotLimits | None = None,
    ) -> list[Path]:
        return export_comparison_figures(
            results,
            output_directory,
            stem,
            labels,
            color_ids,
            series_keys,
            group_ids,
            titles,
            scheme,
            limits,
        )

    def energy_terms(
        self,
        energy_file: str | Path,
        backend_name: str = "auto",
        cancel_event: Event | None = None,
        cache_dir: str | Path | None = None,
    ) -> tuple[str, ...]:
        backends = self._analysis_backends(backend_name, BackendQuery("energy"))
        last_error: BackendError | FormatError | None = None
        for backend in backends:
            discover = getattr(backend, "terms", None)
            if not callable(discover):
                raise ConfigurationError(
                    f"Analysis backend {backend.name!r} cannot discover energy terms."
                )
            try:
                terms: tuple[str, ...] = discover(
                    self.context.integrations,
                    energy_file,
                    cancel_event,
                    None
                    if cache_dir is None
                    else Path(cache_dir).expanduser().resolve(),
                )
                return terms
            except (BackendError, FormatError) as exc:
                last_error = exc
                if backend_name != "auto":
                    raise
        assert last_error is not None
        raise last_error

    def _analysis_backends(
        self,
        backend_name: str,
        query: BackendQuery,
    ) -> tuple[BackendAdapter, ...]:
        if backend_name != "auto":
            return (
                self.context.analysis_registry.get(
                    backend_name,
                    query.analysis_type,
                ),
            )
        backends = self.context.analysis_registry.auto(
            query,
            self.context.integrations,
        )
        if backends:
            return backends
        raise BackendError(
            f"No complete backend is available for {query.analysis_type!r}.",
            "Install or configure a backend that supports the selected inputs.",
        )

    def _run_file_analysis(
        self,
        request: EnergyRequest,
        backend: BackendAdapter,
        progress: ProgressCallback | None,
        cancel_event: Event | None,
        cache_dir: Path | None,
    ) -> AnalysisResult:
        backend.validate_request(request)
        provenance = input_provenance(
            {"energy": Path(request.energy_file)},
            {
                "user_config": str(self.context.config_file),
                "analysis_backend": "analysis_request",
            },
            parameter_provenance=request.parameter_provenance,
            cancel_event=cancel_event,
            progress=progress,
            fingerprint_inputs=backend.fingerprints_inputs(request),
        )
        provenance["analysis_backend"] = {
            "name": backend.name,
            "display_name": backend.display_name,
        }
        result = backend.run(
            AnalysisInput(
                request,
                None,
                provenance,
                self.context.integrations,
                progress,
                cancel_event,
                self.context.config.resources.max_pairs_per_chunk,
                cache_dir,
            )
        )
        result.validate()
        if result.analysis_type != request.analysis_type or result.request != request.to_dict():
            raise ConfigurationError(
                "The analysis backend returned a result that does not match its request.",
                details={"backend": backend.name},
            )
        return result

    def _load_radial_source(
        self,
        request: RadialRequest,
        backend: BackendAdapter,
        cache_dir: str | Path | None,
        cancel_event: Event | None,
        progress: ProgressCallback | None,
    ) -> TrajectorySource:
        backend.validate_request(request)
        with trajectory_cache(cache_dir):
            return self.context.trajectory_loader(
                request.topology,
                request.trajectory,
                backend.name,
                cancel_event,
                progress,
            )

    def _run_radial_analysis(
        self,
        request: RadialRequest,
        backend: BackendAdapter,
        source: TrajectorySource | None,
        progress: ProgressCallback | None,
        cancel_event: Event | None,
        cache_dir: Path | None,
    ) -> AnalysisResult:
        if source is not None and source.backend_name != backend.name:
            raise ConfigurationError(
                "The analysis backend and input pipeline do not match.",
                details={
                    "analysis_backend": backend.name,
                    "input_backend": source.backend_name,
                },
            )
        check_cancel(cancel_event)
        unmapped_species: list[str] = []
        decisions: dict[str, object] = {}
        if source is not None:
            system_species = {atom.residue_name for atom in source.atoms}
            unknown_species = sorted(set(request.species_roles) - system_species)
            if unknown_species:
                raise InputError(
                    "The species-role mapping contains names absent from the loaded topology.",
                    "Inspect the system and confirm roles using the reported species names.",
                    {"unknown_species": unknown_species},
                )
            unmapped_species = sorted(system_species - set(request.species_roles))
            suggestions = summarize_source(source).role_suggestions
            decisions = {
                species: role_decision(role, suggestions[species], "analysis_request")
                for species, role in request.species_roles.items()
            }
        provenance = analysis_provenance(
            (
                source.topology_path
                if source is not None
                else Path(request.topology).expanduser().resolve()
            ),
            (
                source.trajectory_path
                if source is not None
                else Path(request.trajectory).expanduser().resolve()
            ),
            {
                "user_config": str(self.context.config_file),
                "analysis_backend": "analysis_request",
            },
            additional_inputs=(
                {"index": Path(request.index_file)} if request.index_file else None
            ),
            species_roles=request.species_roles,
            parameter_provenance=request.parameter_provenance,
            cancel_event=cancel_event,
            progress=progress,
            fingerprint_inputs=backend.fingerprints_inputs(request),
        )
        provenance["analysis_backend"] = {
            "name": backend.name,
            "display_name": backend.display_name,
        }
        provenance["species_mapping"]["status"] = (
            "not_provided"
            if not request.species_roles
            else "partial"
            if unmapped_species
            else "confirmed"
        )
        provenance["species_mapping"]["unmapped_species"] = unmapped_species
        provenance["species_mapping"]["decisions"] = decisions
        provenance["species_mapping"]["policy"] = role_policy()
        integration_run = getattr(source, "integration_run", None)
        if isinstance(integration_run, dict):
            provenance["integration_runs"] = [integration_run]
        result = backend.run(
            AnalysisInput(
                request,
                source,
                provenance,
                self.context.integrations,
                progress,
                cancel_event,
                self.context.config.resources.max_pairs_per_chunk,
                cache_dir,
            )
        )
        result.validate()
        if result.analysis_type != request.analysis_type or result.request != request.to_dict():
            raise ConfigurationError(
                "The analysis backend returned a result that does not match its request.",
                details={
                    "backend": backend.name,
                    "request_analysis_type": request.analysis_type,
                    "result_analysis_type": result.analysis_type,
                },
            )
        if unmapped_species:
            result.warnings.append(
                "Species roles are incomplete; confirm the unmapped species before drawing "
                "role-dependent conclusions."
            )
        return result

    def run(
        self,
        request: AnalysisRequest,
        progress: ProgressCallback | None = None,
        cancel_event: Event | None = None,
        cache_dir: str | Path | None = None,
    ) -> AnalysisResult:
        request.validate()
        check_cancel(cancel_event)
        resolved_cache = (
            None if cache_dir is None else Path(cache_dir).expanduser().resolve()
        )
        if isinstance(request, EnergyRequest):
            last_error: BackendError | FormatError | None = None
            query = BackendQuery(request.analysis_type)
            for backend in self._analysis_backends(request.analysis_backend, query):
                try:
                    return self._run_file_analysis(
                        request, backend, progress, cancel_event, resolved_cache
                    )
                except (BackendError, FormatError) as exc:
                    last_error = exc
                    if request.analysis_backend != "auto":
                        raise
            assert last_error is not None
            raise last_error
        if not isinstance(request, RadialRequest):
            raise InputError("Trajectory analysis requires a radial request.")
        attempts: list[dict[str, str]] = []
        query = BackendQuery(
            request.analysis_type,
            request.topology,
            request.trajectory,
            request.index_file,
        )
        for backend in self._analysis_backends(request.analysis_backend, query):
            backend.validate_request(request)
            if not backend.opens_trajectory(request):
                return self._run_radial_analysis(
                    request,
                    backend,
                    None,
                    progress,
                    cancel_event,
                    resolved_cache,
                )
            try:
                source = self._load_radial_source(
                    request,
                    backend,
                    resolved_cache,
                    cancel_event,
                    progress,
                )
            except TaskCancelled:
                raise
            except MDHelperError as exc:
                attempts.append(
                    {
                        "backend": backend.name,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
                if request.analysis_backend != "auto":
                    raise
                continue
            try:
                return self._run_radial_analysis(
                    request,
                    backend,
                    source,
                    progress,
                    cancel_event,
                    resolved_cache,
                )
            finally:
                source.close()
        raise BackendError(
            "No complete radial-analysis backend could read the selected inputs.",
            "Inspect the backend attempts or select a compatible backend explicitly.",
            {"attempts": attempts},
        )
