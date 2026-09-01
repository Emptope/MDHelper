"""GROMACS RDF and cumulative RDF backend."""

from __future__ import annotations

import math
import tempfile
from collections.abc import Sequence
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from mdhelper.analysis.common import (
    FrameAudit,
    check_cancel,
    report_progress,
    selected_frame_count,
)
from mdhelper.analysis.radial import first_shell, first_shell_warnings
from mdhelper.core.analysis import AnalysisResult, RadialRequest
from mdhelper.core.errors import BackendError, FormatError
from mdhelper.core.trajectory import TrajectorySource
from mdhelper.plugins.analysis import AnalysisInput
from mdhelper.services.selection import resolve_selections, selection_resolution_record


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
    source: TrajectorySource,
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


class GmxRdf:
    name = "gromacs"
    display_name = "GROMACS"
    needs_trajectory = True

    def run(self, inputs: AnalysisInput) -> AnalysisResult:
        request = _request(inputs)
        request.validate()
        if inputs.source is None:
            raise BackendError("The GROMACS RDF backend requires trajectory metadata.")
        with tempfile.TemporaryDirectory(prefix="mdhelper-gromacs-rdf-") as directory:
            root = Path(directory)
            subset = root / "selected.xtc"
            frame_index = root / "frames.ndx"
            rdf_output = root / "rdf.xvg"
            cn_output = root / "cn.xvg"
            audit, times, indices = _audit_bounds(inputs.source, inputs)
            frame_args = _frame_args(inputs.source, inputs, times)
            direct_source = frame_args is not None
            conversion_record = None
            if frame_args is None:
                _write_frame_index(indices, frame_index)
                report_progress(
                    inputs.progress,
                    0,
                    None,
                    "Running GROMACS trajectory conversion",
                )
                conversion_record = inputs.integrations.run(
                    "gromacs",
                    [
                        "trjconv",
                        "-f",
                        str(inputs.source.trajectory_path),
                        "-s",
                        str(inputs.source.topology_path),
                        "-fr",
                        str(frame_index),
                        "-o",
                        str(subset),
                    ],
                    root,
                    cancel_event=inputs.cancel_event,
                    output_files=[subset],
                    input_text="0\n",
                    required_capabilities=("trjconv",),
                )
                if conversion_record.status != "completed" or not subset.is_file():
                    raise BackendError(
                        "GROMACS did not produce the selected RDF trajectory.",
                        details={"integration_run": conversion_record.to_dict()},
                    )
                report_progress(
                    inputs.progress,
                    audit.count,
                    audit.count,
                    "Prepared GROMACS RDF frames",
                )
                frame_args = [
                    "-f",
                    str(subset),
                    "-s",
                    str(inputs.source.topology_path),
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
                    "-cn",
                    str(cn_output),
                    "-bin",
                    str(request.bin_width_nm),
                    "-rmax",
                    str(request.r_max_nm),
                    "-xvg",
                    "none",
                )
            )
            report_progress(inputs.progress, 0, None, "Running GROMACS RDF")
            record = inputs.integrations.run(
                "gromacs",
                arguments,
                root,
                cancel_event=inputs.cancel_event,
                output_files=[rdf_output, cn_output],
                required_capabilities=("rdf",),
            )
            if record.status != "completed":
                raise BackendError(
                    f"GROMACS RDF exited with code {record.exit_code}.",
                    details={"integration_run": record.to_dict()},
                )
            report_progress(
                inputs.progress,
                audit.count,
                audit.count,
                "Completed GROMACS RDF",
            )
            rdf_radius, rdf = _parse_curve(rdf_output, "RDF")
            cn_radius, cumulative = _parse_curve(cn_output, "cumulative RDF")
        check_cancel(inputs.cancel_event)
        shell = first_shell(rdf_radius, rdf)
        if request.analysis_type == "cumulative_rdf" and shell.get("available"):
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
            data = {
                "radius_nm": cn_radius.tolist(),
                "cumulative_number": cumulative.tolist(),
            }
            units = {"radius_nm": "nm", "cumulative_number": "count"}
            parameters = {
                **common_parameters,
                "definition": "GROMACS gmx rdf -cn cumulative number RDF",
            }
        return AnalysisResult(
            analysis_type=request.analysis_type,
            method_version=METHOD_VERSION,
            data=data,
            parameters=parameters,
            units=units,
            diagnostics=diagnostics,
            provenance=provenance,
            request=request.to_dict(),
            warnings=first_shell_warnings(shell),
        )
