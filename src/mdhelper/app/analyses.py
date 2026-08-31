"""Analysis execution and result-export use cases."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from threading import Event

from mdhelper.analysis.common import check_cancel
from mdhelper.app.context import ApplicationContext
from mdhelper.core.analysis import AnalysisRequest, AnalysisResult
from mdhelper.core.errors import BackendError, ConfigurationError, FormatError, InputError
from mdhelper.core.plotting import DEFAULT_PLOT_SCHEME, PlotLimits
from mdhelper.core.progress import ProgressCallback
from mdhelper.core.species import role_decision, role_policy
from mdhelper.io.export import export_comparison_figures, export_figures, export_result
from mdhelper.plugins.analysis import AnalysisInput
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
    ) -> tuple[str, ...]:
        if backend_name == "native":
            raise InputError("The native GRO backend cannot read EDR files.")
        names = self._energy_backend_names(backend_name)
        last_error: BackendError | FormatError | None = None
        for name in names:
            backend = self.context.analysis_registry.get("energy", name)
            discover = getattr(backend, "terms", None)
            if not callable(discover):
                raise ConfigurationError(
                    f"Analysis backend {name!r} cannot discover energy terms."
                )
            try:
                terms: tuple[str, ...] = discover(
                    self.context.integrations,
                    energy_file,
                    cancel_event,
                )
                return terms
            except (BackendError, FormatError) as exc:
                last_error = exc
                if backend_name != "auto":
                    raise
        assert last_error is not None
        raise last_error

    def _energy_backend_names(self, backend_name: str) -> tuple[str, ...]:
        if backend_name != "auto":
            return (backend_name,)
        names = ["mdanalysis"]
        status = self.context.integrations.status("gromacs")
        if status.available and "energy" in status.capabilities:
            names.append("gromacs")
        return tuple(names)

    def _run_file_analysis(
        self,
        request: AnalysisRequest,
        backend_name: str,
        progress: ProgressCallback | None,
        cancel_event: Event | None,
    ) -> AnalysisResult:
        backend = self.context.analysis_registry.get(request.analysis_type, backend_name)
        assert request.energy_file is not None
        provenance = input_provenance(
            {"energy": Path(request.energy_file)},
            backend.name,
            {
                "user_config": str(self.context.config_file),
                "backend": "analysis_request",
            },
            parameter_provenance=request.parameter_provenance,
            cancel_event=cancel_event,
            progress=progress,
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
            )
        )
        result.validate()
        if result.analysis_type != request.analysis_type or result.request != request.to_dict():
            raise ConfigurationError(
                "The analysis backend returned a result that does not match its request.",
                details={"backend": backend.name},
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
        if request.analysis_type == "energy":
            last_error: BackendError | FormatError | None = None
            for backend_name in self._energy_backend_names(request.backend):
                try:
                    return self._run_file_analysis(
                        request, backend_name, progress, cancel_event
                    )
                except (BackendError, FormatError) as exc:
                    last_error = exc
                    if request.backend != "auto":
                        raise
            assert last_error is not None
            raise last_error
        backend_name = (
            "gromacs"
            if request.backend == "gromacs"
            and request.analysis_type in {"rdf", "cumulative_rdf"}
            else "native"
        )
        backend = self.context.analysis_registry.get(request.analysis_type, backend_name)
        direct_gmx = (
            request.backend == "gromacs"
            and request.analysis_type in {"rdf", "cumulative_rdf"}
        )
        source_backend = "auto" if direct_gmx else request.backend
        with trajectory_cache(cache_dir):
            source = self.context.trajectory_loader(
                request.topology,
                request.trajectory,
                source_backend,
            )
        check_cancel(cancel_event)
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
            source.topology_path,
            source.trajectory_path,
            request.backend if direct_gmx else source.backend_name,
            {
                "user_config": str(self.context.config_file),
                "backend": "analysis_request",
            },
            additional_inputs=(
                {"index": Path(request.index_file)} if request.index_file else None
            ),
            species_roles=request.species_roles,
            parameter_provenance=request.parameter_provenance,
            cancel_event=cancel_event,
            progress=progress,
        )
        provenance["analysis_backend"] = {
            "name": backend.name,
            "display_name": backend.display_name,
        }
        provenance["trajectory_backend"] = {
            "name": source.backend_name,
            "display_name": source.backend_display_name,
        }
        check_cancel(cancel_event)
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
