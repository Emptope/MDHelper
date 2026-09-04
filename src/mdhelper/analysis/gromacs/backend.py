"""Complete GROMACS analysis backend orchestration."""

from __future__ import annotations

from pathlib import Path
from threading import Event

import numpy as np
from numpy.typing import NDArray

from mdhelper.analysis.common import (
    analysis_directory,
    check_cancel,
)
from mdhelper.analysis.pipeline import AnalysisInput, BackendQuery
from mdhelper.analysis.radial import (
    FrameAudit,
    first_shell,
    first_shell_warnings,
    validate_frame_selection,
)
from mdhelper.core.analysis import AnalysisRequest, AnalysisResult, EnergyRequest
from mdhelper.core.errors import BackendError, FormatError
from mdhelper.core.integrations import IntegrationRunRecord, unique_run_records
from mdhelper.core.system import FrameRange
from mdhelper.integrations.gromacs import error_message
from mdhelper.integrations.manager import IntegrationManager

from .curves import _parse_curve
from .energy import EnergyAnalysis
from .inputs import (
    _request,
    _requested_indices,
    _requested_paths,
    _selection,
    _selection_records,
    _write_frame_index,
)
from .runs import _process_progress, _run_audit, _trajectory_frame_count

METHOD_VERSION = "1.0.0"


class GromacsBackend:
    name = "gromacs"
    display_name = "GROMACS"
    analysis_types = frozenset(("rdf", "cumulative_rdf", "energy"))

    def __init__(self) -> None:
        self._energy = EnergyAnalysis()

    def auto_priority(
        self,
        query: BackendQuery,
        integrations: IntegrationManager,
    ) -> int | None:
        if query.analysis_type != "energy" and query.index_file is None:
            return None
        capabilities = self.required_capabilities(query)
        status = integrations.status("gromacs")
        if not status.available or not set(capabilities).issubset(status.capabilities):
            return None
        return 30

    def required_capabilities(self, query: BackendQuery) -> tuple[str, ...]:
        if query.analysis_type == "energy":
            return ("energy",)
        if query.frames is not None and query.frames != FrameRange():
            return ("rdf", "trjconv", "check")
        return ("rdf",)

    def validate_request(self, request: AnalysisRequest) -> None:
        request.validate()

    def opens_trajectory(self, request: AnalysisRequest) -> bool:
        del request
        return False

    def fingerprints_inputs(self, request: AnalysisRequest) -> bool:
        del request
        return False

    def terms(
        self,
        integrations: IntegrationManager,
        energy_file: str | Path,
        cancel_event: Event | None = None,
        cache_dir: Path | None = None,
    ) -> tuple[str, ...]:
        return self._energy.terms(integrations, energy_file, cancel_event, cache_dir)

    def run(self, inputs: AnalysisInput) -> AnalysisResult:
        if isinstance(inputs.request, EnergyRequest):
            return self._energy.run(inputs)
        request = _request(inputs)
        request.validate()
        topology_path, trajectory_path = _requested_paths(request)
        with analysis_directory(inputs.cache_dir, "gromacs-rdf") as root:
            subset = root / "selected.xtc"
            frame_index = root / "frames.ndx"
            rdf_output = root / "rdf.xvg"
            cumulative_output = root / "rdf_cn.xvg"
            cumulative_radius: NDArray[np.float64] | None = None
            cumulative: NDArray[np.float64] | None = None
            metadata_record: IntegrationRunRecord | None = None
            indices: tuple[int, ...]
            if request.frames == FrameRange():
                audit = FrameAudit()
                indices = ()
                frame_args = [
                    "-f",
                    str(trajectory_path),
                    "-s",
                    str(topology_path),
                ]
            else:
                n_frames, metadata_record = _trajectory_frame_count(
                    inputs,
                    trajectory_path,
                    root,
                )
                validate_frame_selection(n_frames, request.frames)
                indices = _requested_indices(request.frames, n_frames)
                audit = FrameAudit(
                    count=len(indices),
                    first_index=indices[0],
                    last_index=indices[-1],
                )
                frame_args = None
            direct_source = frame_args is not None
            conversion_record = None
            if frame_args is None:
                _write_frame_index(indices, frame_index)
                conversion_arguments = [
                    "trjconv",
                    "-f",
                    str(trajectory_path),
                    "-s",
                    str(topology_path),
                    "-fr",
                    str(frame_index),
                    "-o",
                    str(subset),
                ]
                conversion_record = inputs.integrations.run(
                    "gromacs",
                    conversion_arguments,
                    root,
                    cancel_event=inputs.cancel_event,
                    output_files=[subset],
                    input_text="0\n",
                    process_progress=_process_progress(inputs, audit.count, indices),
                    required_capabilities=("trjconv",),
                )
                if conversion_record.status != "completed" or not subset.is_file():
                    raise BackendError(
                        "GROMACS did not produce the selected RDF trajectory.",
                        details={"integration_run": conversion_record.to_dict()},
                    )
                frame_args = [
                    "-f",
                    str(subset),
                    "-s",
                    str(topology_path),
                ]
            arguments = ["rdf"]
            arguments.extend(frame_args)
            if request.index_file is not None:
                arguments.extend(("-n", str(Path(request.index_file).expanduser().resolve())))
            arguments.extend(
                (
                    "-ref",
                    _selection(request.reference, request.index_file),
                    "-sel",
                    _selection(request.selection or "", request.index_file),
                    "-o",
                    str(rdf_output),
                )
            )
            output_files: list[str | Path] = [rdf_output]
            if request.analysis_type == "cumulative_rdf":
                arguments.extend(("-cn", str(cumulative_output)))
                output_files.append(cumulative_output)
            arguments.extend(
                (
                    "-bin",
                    str(request.bin_width_nm),
                    "-rmax",
                    str(request.r_max_nm),
                    "-xvg",
                    "none",
                )
            )
            total = audit.count or None
            record = inputs.integrations.run(
                "gromacs",
                arguments,
                root,
                cancel_event=inputs.cancel_event,
                output_files=output_files,
                process_progress=_process_progress(inputs, total),
                required_capabilities=("rdf",),
            )
            if record.status != "completed":
                raise BackendError(
                    f"GROMACS RDF exited with code {record.exit_code}.",
                    error_message(record.stdout, record.stderr) or "",
                    details={"integration_run": record.to_dict()},
                )
            if audit.count == 0:
                audit = _run_audit(record.stdout, record.stderr)
            elif audit.first_time_ps is None:
                audit = _run_audit(record.stdout, record.stderr, indices)
            rdf_radius, rdf = _parse_curve(rdf_output, "RDF")
            if request.analysis_type == "cumulative_rdf":
                cumulative_radius, cumulative = _parse_curve(
                    cumulative_output, "cumulative RDF"
                )
        check_cancel(inputs.cancel_event)
        shell = first_shell(rdf_radius, rdf)
        if request.analysis_type == "cumulative_rdf" and shell.get("available"):
            assert cumulative_radius is not None
            assert cumulative is not None
            raw_minimum = shell.get("first_minimum_nm")
            if isinstance(raw_minimum, bool) or not isinstance(raw_minimum, (int, float)):
                raise FormatError("The GROMACS RDF shell diagnostic has no numeric minimum.")
            minimum = float(raw_minimum)
            index = min(
                int(np.searchsorted(cumulative_radius, minimum)),
                len(cumulative_radius) - 1,
            )
            shell["coordination_number"] = float(cumulative[index])
        records, n_reference, n_selection, possible_pairs = _selection_records(
            inputs.source, inputs
        )
        width_values = np.diff(rdf_radius)
        actual_width = (
            float(np.median(width_values)) if len(width_values) else request.bin_width_nm
        )
        provenance = dict(inputs.provenance)
        runs = provenance.get("integration_runs")
        integration_runs = list(runs) if isinstance(runs, list) else []
        if metadata_record is not None:
            integration_runs.append(metadata_record.to_dict())
        if conversion_record is not None:
            integration_runs.append(conversion_record.to_dict())
        integration_runs.append(record.to_dict())
        provenance["integration_runs"] = unique_run_records(integration_runs)
        common_parameters = {
            "bin_width_nm": actual_width,
            "pbc": "GROMACS gmx rdf default periodic handling",
            "trajectory_preprocessing": {
                "source": (
                    "original trajectory"
                    if direct_source
                    else "GROMACS exact-frame XTC subset"
                ),
                "analysis": "gmx rdf",
            },
        }
        diagnostics = {
            "n_frames": audit.count,
            "selected_frame_time_range": audit.to_dict(),
            "n_reference_atoms": n_reference,
            "n_selection_atoms": n_selection,
            "possible_ordered_pairs_per_frame": possible_pairs,
            "normalization_ordered_pairs_per_frame": (
                None
                if n_reference is None or n_selection is None
                else n_reference * n_selection
            ),
            "first_shell_suggestion": shell,
            "selection_resolution": records,
        }
        if request.analysis_type == "rdf":
            data = {"radius_nm": rdf_radius.tolist(), "g_r": rdf.tolist()}
            units = {"radius_nm": "nm", "g_r": "dimensionless"}
            parameters = {
                **common_parameters,
                "normalization": "GROMACS gmx rdf norm=rdf",
            }
        else:
            assert cumulative_radius is not None
            assert cumulative is not None
            data = {
                "radius_nm": cumulative_radius.tolist(),
                "cumulative_number": cumulative.tolist(),
            }
            units = {"radius_nm": "nm", "cumulative_number": "count"}
            parameters = {
                **common_parameters,
                "definition": "GROMACS gmx rdf -cn cumulative number RDF",
            }
        return AnalysisResult(
            method_version=METHOD_VERSION,
            data=data,
            parameters=parameters,
            units=units,
            diagnostics=diagnostics,
            provenance=provenance,
            request=request.to_dict(),
            warnings=first_shell_warnings(shell),
        )
