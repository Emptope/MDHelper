"""Inspection and analysis CLI commands."""

from __future__ import annotations

import json
import signal
import sys
from dataclasses import replace
from pathlib import Path
from threading import Event
from typing import Any, Literal

from jsonargparse import Namespace

from mdhelper.app import ApplicationService
from mdhelper.cli.output import write_json
from mdhelper.core.analysis import AnalysisRequest, EnergyRequest, RadialRequest
from mdhelper.core.errors import ConfigurationError, InputError
from mdhelper.core.species import validate_species_roles
from mdhelper.core.system import FrameRange
from mdhelper.project import Project
from mdhelper.workflow.tasks import TaskService


def _frame_range(args: Namespace) -> FrameRange:
    return FrameRange(args.start, args.stop, args.stride)


def _resolve_inputs(
    args: Namespace, app: ApplicationService
) -> tuple[str, str, str | None, Project | None]:
    project: Project | None = None
    topology = args.topology
    trajectory = args.trajectory
    index_file = args.index
    if args.project:
        project = app.projects.open(args.project)
        inputs = project.resolve_inputs()
        topology = inputs["topology"]
        trajectory = inputs["trajectory"]
        if index_file is None and "index" in inputs:
            index_file = inputs["index"]
    if not topology or not trajectory:
        raise InputError("Provide --topology and --trajectory, or provide --project.")
    return (
        str(topology),
        str(trajectory),
        None if index_file is None else str(index_file),
        project,
    )


def _progress(json_progress: bool):
    def callback(current: int, total: int | None, message: str) -> None:
        event = {"event": "progress", "current": current, "total": total, "message": message}
        if json_progress or not sys.stderr.isatty():
            write_json(event, sys.stderr)
        else:
            total_text = "?" if total is None else str(total)
            sys.stderr.write(f"\r[{current}/{total_text}] {message:60.60s}")
            sys.stderr.flush()

    return callback


def _request(
    analysis: str,
    args: Namespace,
    topology: str,
    trajectory: str,
    index_file: str | None,
    species_roles: dict[str, str],
) -> AnalysisRequest:
    if analysis == "energy":
        return EnergyRequest(
            analysis_type="energy",
            energy_file=str(args.energy_file),
            energy_terms=tuple(args.terms),
            backend=args.backend,
        )
    common: dict[str, Any] = {
        "topology": topology,
        "trajectory": trajectory,
        "index_file": index_file,
        "frames": _frame_range(args),
        "backend": args.backend,
        "species_roles": species_roles,
    }
    analysis_type: Literal["rdf", "cumulative_rdf"]
    if analysis == "rdf":
        analysis_type = "rdf"
    elif analysis == "cumulative-rdf":
        analysis_type = "cumulative_rdf"
    else:
        raise InputError(f"Cannot build request for {analysis!r}.")
    return RadialRequest(
        analysis_type=analysis_type,
        reference=args.reference,
        selection=args.selection,
        r_max_nm=args.r_max,
        bin_width_nm=args.bin_width,
        **common,
    )


def _run(
    app: ApplicationService,
    request: AnalysisRequest,
    output: Path,
    include_figures: bool,
    json_progress: bool,
    project: Project | None,
) -> int:
    cancel_event = Event()
    previous_handler = signal.getsignal(signal.SIGINT)

    def request_cancel(_signum: int, _frame: Any) -> None:
        cancel_event.set()
        sys.stderr.write("\nCancellation requested; finishing the current frame...\n")
        sys.stderr.flush()

    signal.signal(signal.SIGINT, request_cancel)
    try:
        tasks = TaskService(app)
        try:
            cache_dir = None if project is None else project.cache_dir
            result = tasks.run_sync(
                request, _progress(json_progress), cancel_event, cache_dir
            )
        finally:
            tasks.shutdown()
    finally:
        signal.signal(signal.SIGINT, previous_handler)
    if sys.stderr.isatty() and not json_progress:
        sys.stderr.write("\n")
    exported = app.analyses.export(result, output, include_figures=include_figures)
    project_result = app.projects.commit_result(project, request, result) if project else None
    write_json(
        {
            "status": "completed",
            "analysis_id": result.analysis_id,
            "analysis_type": result.analysis_type,
            "method_version": result.method_version,
            "exports": [str(path) for path in exported],
            "project_result": None if project_result is None else str(project_result),
            "warnings": result.warnings,
        }
    )
    return 0


def _load_request(path: Path) -> AnalysisRequest:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigurationError(
            f"Could not load analysis request: {path}",
            details={"exception": f"{type(exc).__name__}: {exc}"},
        ) from exc
    if not isinstance(value, dict):
        raise ConfigurationError("An analysis request JSON document must be an object.")
    return AnalysisRequest.from_dict(value)


def inspect(args: Namespace, app: ApplicationService) -> int:
    topology, trajectory, index_file, project = _resolve_inputs(args, app)
    write_json(
        app.checks.inspect_system(
            topology,
            trajectory,
            index_file,
            None if project is None else project.cache_dir,
        ).to_dict()
    )
    return 0


def handle(args: Namespace, app: ApplicationService) -> int:
    analysis = args.analysis
    options = args[analysis]
    if analysis in {"rdf", "cumulative-rdf"}:
        topology, trajectory, index_file, project = _resolve_inputs(options, app)
        species_roles = dict(project.manifest.get("species_roles", {})) if project else {}
        validate_species_roles(options.roles)
        species_roles.update(options.roles)
        request = _request(
            analysis,
            options,
            topology,
            trajectory,
            index_file,
            species_roles,
        )
        return _run(
            app,
            request,
            options.output,
            options.figures,
            options.json_progress,
            project,
        )
    if analysis == "energy":
        project = (
            app.projects.open(options.project, verify_inputs=False)
            if options.project
            else None
        )
        request = _request(analysis, options, "", "", None, {})
        return _run(
            app,
            request,
            options.output,
            options.figures,
            options.json_progress,
            project,
        )
    if analysis == "request":
        request = _load_request(options.request)
        project = None
        if options.project:
            project = app.projects.open(options.project)
            inputs = project.resolve_inputs()
            replacement: dict[str, Any] = {}
            if isinstance(request, EnergyRequest):
                if "energy" in inputs:
                    replacement["energy_file"] = str(inputs["energy"])
            elif isinstance(request, RadialRequest):
                replacement.update(
                    {
                        "topology": str(inputs["topology"]),
                        "trajectory": str(inputs["trajectory"]),
                    }
                )
                if request.index_file is not None and "index" in inputs:
                    replacement["index_file"] = str(inputs["index"])
                species_roles = dict(project.manifest.get("species_roles", {}))
                species_roles.update(request.species_roles)
                replacement["species_roles"] = species_roles
            else:
                raise ConfigurationError("Unknown analysis request type.")
            request = replace(request, **replacement)
        return _run(
            app,
            request,
            options.output,
            options.figures,
            options.json_progress,
            project,
        )
    raise AssertionError(f"Unhandled analysis: {analysis}")
