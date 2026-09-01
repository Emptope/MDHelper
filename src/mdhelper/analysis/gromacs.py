"""Complete GROMACS analysis pipeline."""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from pathlib import Path
from threading import Event

import numpy as np
from numpy.typing import NDArray

from mdhelper.analysis.common import (
    FrameAudit,
    analysis_directory,
    check_cancel,
    report_progress,
    selected_frame_count,
)
from mdhelper.analysis.radial import first_shell, first_shell_warnings
from mdhelper.core.analysis import AnalysisRequest, AnalysisResult, EnergyRequest, RadialRequest
from mdhelper.core.errors import BackendError, FormatError
from mdhelper.core.system import FrameRange
from mdhelper.core.trajectory import TrajectorySource
from mdhelper.integrations.gromacs import frame_progress, frame_progresses, output_message
from mdhelper.integrations.manager import IntegrationManager
from mdhelper.plugins.analysis import AnalysisInput, BackendQuery
from mdhelper.services.selection import resolve_selections, selection_resolution_record

from .energy import _GromacsEnergy


def _request(inputs: AnalysisInput) -> RadialRequest:
    request = inputs.request
    if not isinstance(request, RadialRequest):
        raise BackendError("The GROMACS RDF backend requires a radial request.")
    return request

METHOD_VERSION = "1.0.0"


def _write_frame_index(indices: Sequence[int], path: Path) -> None:
    try:
        with path.open("w", encoding="ascii", newline="\n") as handle:
            handle.write("[ frames ]\n")
            for start in range(0, len(indices), 15):
                handle.write(
                    " ".join(str(index + 1) for index in indices[start : start + 15])
                )
                handle.write("\n")
    except OSError as exc:
        raise BackendError(
            "Could not write the GROMACS RDF frame index.",
            details={"exception": f"{type(exc).__name__}: {exc}"},
        ) from exc


def _audit_frames(
    source: TrajectorySource,
    inputs: AnalysisInput,
) -> tuple[FrameAudit, tuple[float, ...], tuple[int, ...]]:
    audit = FrameAudit()
    times: list[float] = []
    indices: list[int] = []
    request = _request(inputs)
    for frame in source.iter_frames(request.frames):
        check_cancel(inputs.cancel_event)
        audit.observe(frame)
        times.append(frame.time_ps)
        indices.append(frame.index)
        report_progress(
            inputs.progress,
            audit.count,
            selected_frame_count(source.n_frames, request.frames),
            f"Selecting GROMACS RDF frame {frame.index}",
        )
    return audit, tuple(times), tuple(indices)


def _audit_bounds(
    source: TrajectorySource,
    inputs: AnalysisInput,
) -> tuple[FrameAudit, tuple[float, ...], tuple[int, ...]]:
    n_frames = source.n_frames
    if n_frames is None:
        return _audit_frames(source, inputs)
    request = _request(inputs)
    count = selected_frame_count(n_frames, request.frames)
    assert count is not None
    if count == 0:
        raise BackendError("The selected GROMACS RDF frame range is empty.")
    frame_range = request.frames
    stop = n_frames if frame_range.stop is None else min(frame_range.stop, n_frames)
    indices = tuple(range(frame_range.start, stop, frame_range.stride))
    first_index = indices[0]
    last_index = indices[-1]
    first = next(source.iter_frames(type(frame_range)(first_index, first_index + 1)))
    last = (
        first
        if last_index == first_index
        else next(source.iter_frames(type(frame_range)(last_index, last_index + 1)))
    )
    audit = FrameAudit(
        count=count,
        first_index=first.index,
        last_index=last.index,
        first_time_ps=first.time_ps,
        last_time_ps=last.time_ps,
    )
    report_progress(
        inputs.progress,
        count,
        count,
        f"Selected {count} GROMACS RDF frames",
    )
    times = (first.time_ps,) if count == 1 else (first.time_ps, last.time_ps)
    return audit, times, indices


def _frame_args(
    source: TrajectorySource,
    inputs: AnalysisInput,
    times: tuple[float, ...],
) -> list[str] | None:
    frame_range = _request(inputs).frames
    arguments = [
        "-f",
        str(source.trajectory_path),
        "-s",
        str(source.topology_path),
    ]
    if frame_range.start == 0 and frame_range.stop is None and frame_range.stride == 1:
        return arguments
    if frame_range.stride != 1:
        return None
    if len(times) == 1:
        return [*arguments, "-b", str(times[0]), "-e", str(times[0])]
    if np.any(np.diff(np.asarray(times, dtype=np.float64)) <= 0):
        return None
    return [*arguments, "-b", str(times[0]), "-e", str(times[-1])]


def _requested_paths(request: RadialRequest) -> tuple[Path, Path]:
    return (
        Path(request.topology).expanduser().resolve(),
        Path(request.trajectory).expanduser().resolve(),
    )


def _requested_indices(frame_range: FrameRange) -> tuple[int, ...]:
    if frame_range.stop is None:
        raise BackendError("An open-ended sampled frame range requires trajectory metadata.")
    indices = tuple(range(frame_range.start, frame_range.stop, frame_range.stride))
    if not indices:
        raise BackendError("The selected GROMACS RDF frame range is empty.")
    return indices


def _run_audit(
    stdout: str,
    stderr: str,
    indices: tuple[int, ...] = (),
) -> FrameAudit:
    values = frame_progresses(stdout, stderr)
    if indices:
        count = len(indices)
        first_index = indices[0]
        last_index = indices[-1]
    elif values:
        count = values[-1][0] + 1
        first_index = 0
        last_index = values[-1][0]
    else:
        count = 0
        first_index = None
        last_index = None
    return FrameAudit(
        count=count,
        first_index=first_index,
        last_index=last_index,
        first_time_ps=values[0][1] if values else None,
        last_time_ps=values[-1][1] if values else None,
    )


def _parse_curve(path: Path, label: str) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    rows: list[tuple[float, float]] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        raise FormatError(
            f"Could not read GROMACS {label} output: {path}",
            details={"exception": f"{type(exc).__name__}: {exc}"},
        ) from exc
    for line_number, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line or line.startswith(("#", "@")):
            continue
        fields = line.split()
        if len(fields) != 2:
            raise FormatError(
                f"GROMACS {label} output has an unexpected column count.",
                details={"line": line_number, "columns": len(fields)},
            )
        try:
            radius, value = (float(field) for field in fields)
        except ValueError as exc:
            raise FormatError(
                f"GROMACS {label} output contains a non-numeric row.",
                details={"line": line_number},
            ) from exc
        if not math.isfinite(radius) or not math.isfinite(value):
            raise FormatError(
                f"GROMACS {label} output contains a non-finite value.",
                details={"line": line_number},
            )
        rows.append((radius, value))
    if not rows:
        raise FormatError(f"GROMACS {label} output contains no numeric samples.")
    values = np.asarray(rows, dtype=np.float64)
    if len(values) > 1 and np.any(np.diff(values[:, 0]) <= 0):
        raise FormatError(f"GROMACS {label} radii are not strictly increasing.")
    return values[:, 0], values[:, 1]


def _selection(value: str, index_file: str | None) -> str:
    if index_file is None:
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'group "{escaped}"'


def _selection_records(
    source: TrajectorySource | None,
    inputs: AnalysisInput,
) -> tuple[dict[str, object], int | None, int | None, int | None]:
    request = _request(inputs)
    if request.index_file is None:
        records: dict[str, object] = {
            "reference": {
                "expression": request.reference,
                "source": "gromacs_selection",
                "language": "GROMACS selection",
            },
            "selection": {
                "expression": request.selection or "",
                "source": "gromacs_selection",
                "language": "GROMACS selection",
            },
        }
        return records, None, None, None
    if source is None:
        records = {
            "reference": {
                "expression": request.reference,
                "source": "gromacs_index",
                "language": "GROMACS index group",
            },
            "selection": {
                "expression": request.selection or "",
                "source": "gromacs_index",
                "language": "GROMACS index group",
            },
        }
        return records, None, None, None
    reference, selection = resolve_selections(
        source.atoms,
        (request.reference, request.selection or ""),
        index_file=request.index_file,
    )
    overlap = len(set(reference).intersection(selection))
    possible_pairs = len(reference) * len(selection) - overlap
    records = {
        "reference": selection_resolution_record(
            request.reference, reference, source.atoms, request.index_file
        ),
        "selection": selection_resolution_record(
            request.selection or "", selection, source.atoms, request.index_file
        ),
    }
    return records, len(reference), len(selection), possible_pairs


def _process_progress(
    inputs: AnalysisInput,
    total: int | None,
) -> Callable[[float, str, str], None]:
    def update(_elapsed: float, stdout: str, stderr: str) -> None:
        message = output_message(stdout, stderr)
        if message is None:
            return
        parsed = frame_progress(stdout, stderr)
        if parsed is None:
            report_progress(inputs.progress, 0, total, message)
            return
        frame, _time_ps = parsed
        current = frame + 1 if total is None else min(frame + 1, total)
        report_progress(
            inputs.progress,
            current,
            total,
            message,
        )

    return update


class GromacsBackend:
    name = "gromacs"
    display_name = "GROMACS"
    analysis_types = frozenset(("rdf", "cumulative_rdf", "energy"))

    def __init__(self) -> None:
        self._energy = _GromacsEnergy()

    def auto_priority(
        self,
        query: BackendQuery,
        integrations: IntegrationManager,
    ) -> int | None:
        if query.analysis_type != "energy" and query.index_file is None:
            return None
        capabilities = ("energy",) if query.analysis_type == "energy" else ("rdf",)
        status = integrations.status("gromacs")
        if not status.available or not set(capabilities).issubset(status.capabilities):
            return None
        return 30

    def validate_request(self, request: AnalysisRequest) -> None:
        request.validate()

    def opens_trajectory(self, request: AnalysisRequest) -> bool:
        return (
            isinstance(request, RadialRequest)
            and request.frames.stop is None
            and request.frames != FrameRange()
        )

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
            cn_output = root / "cn.xvg"
            cn_radius: NDArray[np.float64] | None = None
            cumulative: NDArray[np.float64] | None = None
            raw_cn: str | None = None
            if inputs.source is not None:
                audit, times, indices = _audit_bounds(inputs.source, inputs)
                frame_args = _frame_args(inputs.source, inputs, times)
            elif request.frames == FrameRange():
                audit = FrameAudit()
                indices = ()
                frame_args = [
                    "-f",
                    str(trajectory_path),
                    "-s",
                    str(topology_path),
                ]
            else:
                indices = _requested_indices(request.frames)
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
                    process_progress=_process_progress(inputs, audit.count),
                    required_capabilities=("trjconv",),
                )
                if conversion_record.status != "completed" or not subset.is_file():
                    raise BackendError(
                        "GROMACS did not produce the selected RDF trajectory.",
                        details={"integration_run": conversion_record.to_dict()},
                    )
                if audit.first_time_ps is None:
                    audit = _run_audit(
                        conversion_record.stdout,
                        conversion_record.stderr,
                        indices,
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
                arguments.extend(("-cn", str(cn_output)))
                output_files.append(cn_output)
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
                    details={"integration_run": record.to_dict()},
                )
            if audit.count == 0:
                audit = _run_audit(record.stdout, record.stderr)
            elif audit.first_time_ps is None:
                audit = _run_audit(record.stdout, record.stderr, indices)
            rdf_radius, rdf = _parse_curve(rdf_output, "RDF")
            with rdf_output.open(
                "r", encoding="utf-8", errors="replace", newline=""
            ) as handle:
                raw_rdf = handle.read()
            if request.analysis_type == "cumulative_rdf":
                cn_radius, cumulative = _parse_curve(cn_output, "cumulative RDF")
                with cn_output.open(
                    "r", encoding="utf-8", errors="replace", newline=""
                ) as handle:
                    raw_cn = handle.read()
        check_cancel(inputs.cancel_event)
        shell = first_shell(rdf_radius, rdf)
        if request.analysis_type == "cumulative_rdf" and shell.get("available"):
            assert cn_radius is not None
            assert cumulative is not None
            raw_minimum = shell.get("first_minimum_nm")
            if isinstance(raw_minimum, bool) or not isinstance(raw_minimum, (int, float)):
                raise FormatError("The GROMACS RDF shell diagnostic has no numeric minimum.")
            minimum = float(raw_minimum)
            index = min(int(np.searchsorted(cn_radius, minimum)), len(cn_radius) - 1)
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
        if conversion_record is not None:
            integration_runs.append(conversion_record.to_dict())
        integration_runs.append(record.to_dict())
        provenance["integration_runs"] = integration_runs
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
            assert cn_radius is not None
            assert cumulative is not None
            data = {
                "radius_nm": cn_radius.tolist(),
                "cumulative_number": cumulative.tolist(),
            }
            units = {"radius_nm": "nm", "cumulative_number": "count"}
            parameters = {
                **common_parameters,
                "definition": "GROMACS gmx rdf -cn cumulative number RDF",
            }
        artifacts = {"gromacs-rdf.xvg": raw_rdf}
        if raw_cn is not None:
            artifacts["gromacs-cn.xvg"] = raw_cn
        return AnalysisResult(
            analysis_type=request.analysis_type,
            method_version=METHOD_VERSION,
            data=data,
            parameters=parameters,
            units=units,
            diagnostics=diagnostics,
            provenance=provenance,
            artifacts=artifacts,
            request=request.to_dict(),
            warnings=first_shell_warnings(shell),
        )
