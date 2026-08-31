"""Inspection and analysis CLI commands."""

from __future__ import annotations

import argparse
import json
import signal
import sys
from dataclasses import replace
from pathlib import Path
from threading import Event
from typing import Any

from mdhelper.app import ApplicationService
from mdhelper.cli.output import write_json
from mdhelper.core.analysis import AnalysisRequest
from mdhelper.core.errors import ConfigurationError, InputError
from mdhelper.core.system import FrameRange
from mdhelper.project import Project
from mdhelper.workflow.tasks import TaskService


def _frame_range(args: argparse.Namespace) -> FrameRange:
    return FrameRange(args.start, args.stop, args.stride)


def _resolve_inputs(
    args: argparse.Namespace, app: ApplicationService
) -> tuple[str, str, str | None, Project | None]:
    project: Project | None = None
    topology = getattr(args, "topology", None)
    trajectory = getattr(args, "trajectory", None)
    index_file = getattr(args, "index", None)
    if getattr(args, "project", None):
        project = app.projects.open(args.project)
        inputs = project.resolve_inputs()
        topology = str(inputs["topology"])
        trajectory = str(inputs["trajectory"])
        if index_file is None and "index" in inputs:
            index_file = str(inputs["index"])
    if not topology or not trajectory:
        raise InputError("Provide --topology and --trajectory, or provide --project.")
    return topology, trajectory, index_file, project


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
    args: argparse.Namespace,
    topology: str,
    trajectory: str,
    index_file: str | None,
    species_roles: dict[str, str],
) -> AnalysisRequest:
    if args.command == "energy":
        return AnalysisRequest(
            analysis_type="energy",
            topology=topology,
            trajectory=trajectory,
            reference="",
            energy_file=args.energy_file,
            energy_terms=tuple(args.term),
            backend=args.backend,
            species_roles=species_roles,
        )
    common: dict[str, Any] = {
        "topology": topology,
        "trajectory": trajectory,
        "index_file": index_file,
        "frames": _frame_range(args),
        "backend": args.backend,
        "species_roles": species_roles,
    }
    if args.command == "rdf":
        return AnalysisRequest(
            analysis_type="rdf",
            reference=args.reference,
            selection=args.selection,
            r_max_nm=args.r_max,
            bin_width_nm=args.bin_width,
            **common,
        )
    if args.command == "cn":
        return AnalysisRequest(
            analysis_type="cumulative_rdf",
            reference=args.reference,
            selection=args.selection,
            r_max_nm=args.r_max,
            bin_width_nm=args.bin_width,
            **common,
        )
    raise InputError(f"Cannot build request for {args.command!r}.")


def _run(
    app: ApplicationService,
    request: AnalysisRequest,
    output: str,
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


def _load_request(path: str) -> AnalysisRequest:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigurationError(
            f"Could not load analysis request: {path}",
            details={"exception": f"{type(exc).__name__}: {exc}"},
        ) from exc
    if not isinstance(value, dict):
        raise ConfigurationError("An analysis request JSON document must be an object.")
    return AnalysisRequest.from_dict(value)


def handle(args: argparse.Namespace, app: ApplicationService) -> int:
    if args.command == "inspect":
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
    if args.command in {"rdf", "cn"}:
        topology, trajectory, index_file, project = _resolve_inputs(args, app)
        species_roles = dict(project.manifest.get("species_roles", {})) if project else {}
        species_roles.update(args.role)
        request = _request(args, topology, trajectory, index_file, species_roles)
        return _run(
            app, request, args.output, not args.no_figures, args.json_progress, project
        )
    if args.command == "energy":
        project = (
            app.projects.open(args.project, verify_inputs=False) if args.project else None
        )
        topology = ""
        trajectory = ""
        energy_roles: dict[str, str] = {}
        if project is not None:
            inputs = project.resolve_inputs()
            topology = str(inputs["topology"])
            trajectory = str(inputs["trajectory"])
            energy_roles = dict(project.manifest.get("species_roles", {}))
        request = _request(args, topology, trajectory, None, energy_roles)
        return _run(
            app, request, args.output, not args.no_figures, args.json_progress, project
        )
    if args.command == "run":
        request = _load_request(args.request)
        project = None
        if args.project:
            project = app.projects.open(args.project)
            inputs = project.resolve_inputs()
            replacement: dict[str, Any] = {
                "topology": str(inputs["topology"]),
                "trajectory": str(inputs["trajectory"]),
            }
            if request.index_file is not None and "index" in inputs:
                replacement["index_file"] = str(inputs["index"])
            species_roles = dict(project.manifest.get("species_roles", {}))
            species_roles.update(request.species_roles)
            replacement["species_roles"] = species_roles
            request = replace(request, **replacement)
        return _run(
            app, request, args.output, not args.no_figures, args.json_progress, project
        )
    raise ConfigurationError(f"Unknown command: {args.command}")
