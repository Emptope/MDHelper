from __future__ import annotations

from mdhelper.core.analysis import AnalysisResult, RadialRequest
from mdhelper.core.trajectory import TrajectorySource
from mdhelper.services.selection import selection_resolution_record

from .radial import (
    RadialProfile,
    first_shell,
    first_shell_warnings,
    preprocessing_record,
)

METHOD_VERSION = "1.0.0"


def rdf_result(
    source: TrajectorySource,
    request: RadialRequest,
    provenance: dict[str, object],
    profile: RadialProfile,
) -> AnalysisResult:
    suggestion = first_shell(profile.radius_nm, profile.rdf)
    warnings = first_shell_warnings(suggestion)

    return AnalysisResult(
        analysis_type="rdf",
        method_version=METHOD_VERSION,
        data={
            "radius_nm": profile.radius_nm.tolist(),
            "g_r": profile.rdf.tolist(),
        },
        parameters={
            "bin_width_nm": profile.bin_width_nm,
            "normalization": (
                "average pair count / reference count / shell volume / "
                "average selection number density"
            ),
            "pbc": "triclinic minimum image",
            "trajectory_preprocessing": preprocessing_record(),
        },
        units={
            "radius_nm": "nm",
            "g_r": "dimensionless",
        },
        diagnostics={
            "n_frames": profile.audit.count,
            "selected_frame_time_range": profile.audit.to_dict(),
            "n_reference_atoms": len(profile.reference),
            "n_selection_atoms": len(profile.selection),
            "possible_ordered_pairs_per_frame": profile.possible_pairs,
            "normalization_ordered_pairs_per_frame": profile.normalization_pairs,
            "first_shell_suggestion": suggestion,
            "selection_resolution": {
                "reference": selection_resolution_record(
                    request.reference, profile.reference, source.atoms, request.index_file
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
        warnings=warnings,
    )
