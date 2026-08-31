from __future__ import annotations

from threading import Event

from mdhelper.core.analysis import AnalysisRequest, AnalysisResult
from mdhelper.core.trajectory import TrajectorySource
from mdhelper.services.selection import selection_resolution_record

from .common import ProgressCallback, preprocessing_record
from .radial import first_shell, first_shell_warnings, radial_profile

METHOD_VERSION = "1.0.0"


def run_cumulative_rdf(
    source: TrajectorySource,
    request: AnalysisRequest,
    provenance: dict[str, object],
    progress: ProgressCallback | None = None,
    cancel_event: Event | None = None,
    max_pairs_per_chunk: int = 500_000,
) -> AnalysisResult:
    request.validate()
    profile = radial_profile(
        source,
        request,
        "Cumulative RDF",
        progress,
        cancel_event,
        max_pairs_per_chunk,
    )
    shell = first_shell(profile.radius_nm, profile.rdf)
    minimum_index = shell.get("first_minimum_index")
    if type(minimum_index) is int:
        minimum = float(profile.radius_nm[minimum_index])
        cumulative_index = min(
            int(profile.cumulative_radius_nm.searchsorted(minimum)),
            len(profile.cumulative_radius_nm) - 1,
        )
        shell["coordination_number"] = float(
            profile.cumulative_number[cumulative_index]
        )
    return AnalysisResult(
        analysis_type="cumulative_rdf",
        method_version=METHOD_VERSION,
        data={
            "radius_nm": profile.cumulative_radius_nm.tolist(),
            "cumulative_number": profile.cumulative_number.tolist(),
        },
        parameters={
            "reference": request.reference,
            "selection": request.selection,
            "r_max_nm": request.r_max_nm,
            "bin_width_nm": profile.bin_width_nm,
            "requested_bin_width_nm": request.bin_width_nm,
            "frames": request.frames.__dict__,
            "definition": "mean selection atoms within radius per reference atom",
            "pbc": "triclinic minimum image",
            "trajectory_preprocessing": preprocessing_record(),
        },
        units={
            "radius_nm": "nm",
            "cumulative_number": "count",
        },
        uncertainty={},
        diagnostics={
            "n_frames": profile.audit.count,
            "selected_frame_time_range": profile.audit.to_dict(),
            "n_reference_atoms": len(profile.reference),
            "n_selection_atoms": len(profile.selection),
            "possible_ordered_pairs_per_frame": profile.possible_pairs,
            "normalization_ordered_pairs_per_frame": profile.normalization_pairs,
            "first_shell_suggestion": shell,
            "selection_resolution": {
                "reference": selection_resolution_record(
                    request.reference,
                    profile.reference,
                    source.atoms,
                    request.index_file,
                ),
                "selection": selection_resolution_record(
                    request.selection or "",
                    profile.selection,
                    source.atoms,
                    request.index_file,
                ),
            },
        },
        provenance=provenance,
        request=request.to_dict(),
        warnings=first_shell_warnings(shell),
    )
