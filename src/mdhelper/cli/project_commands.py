"""Project repository CLI commands."""

from __future__ import annotations

import argparse

from mdhelper.app import ApplicationService
from mdhelper.cli.output import write_json


def handle(args: argparse.Namespace, app: ApplicationService) -> int:
    if args.project_command == "create":
        project = app.projects.create(
            args.path, args.topology, args.trajectory, dict(args.role), index_file=args.index
        )
        write_json(project.manifest)
    elif args.project_command == "show":
        write_json(app.projects.open(args.path, verify_inputs=not args.no_verify).manifest)
    elif args.project_command == "relocate":
        project = app.projects.open(args.path, verify_inputs=False)
        project.relocate_input(args.role, args.file)
        write_json(project.manifest)
    elif args.project_command == "set-roles":
        project = app.projects.open(args.path, verify_inputs=False)
        app.projects.set_species_roles(project, dict(args.role))
        write_json(project.manifest)
    elif args.project_command == "set-integration":
        project = app.projects.open(args.path, verify_inputs=False)
        project.set_integration_preference(
            args.integration, not args.not_preferred, tuple(args.required_capability)
        )
        write_json(project.manifest)
    elif args.project_command == "list-results":
        project = app.projects.open(args.path, verify_inputs=False)
        write_json({"analyses": list(app.projects.list_results(project))})
    elif args.project_command == "show-result":
        project = app.projects.open(args.path, verify_inputs=False)
        write_json(app.projects.load_result(project, args.analysis_id).to_dict())
    elif args.project_command == "export-result":
        project = app.projects.open(args.path, verify_inputs=False)
        result = app.projects.load_result(project, args.analysis_id)
        paths = app.analyses.export(
            result, args.output, include_figures=not args.no_figures
        )
        write_json(
            {
                "status": "completed",
                "analysis_id": result.analysis_id,
                "exports": [str(path) for path in paths],
            }
        )
    return 0
