"""Project repository CLI commands."""

from __future__ import annotations

from jsonargparse import Namespace

from mdhelper.app import ApplicationService
from mdhelper.cli.output import write_json
from mdhelper.core.species import validate_species_roles


def handle(args: Namespace, app: ApplicationService) -> int:
    action = args.action
    options = args[action]
    if action == "create":
        validate_species_roles(options.roles)
        project = app.projects.create(
            options.path,
            options.topology,
            options.trajectory,
            options.roles,
            index_file=options.index,
        )
        write_json(project.manifest)
    elif action == "show":
        write_json(app.projects.open(options.path, verify_inputs=options.verify).manifest)
    elif action == "relocate":
        project = app.projects.open(options.path, verify_inputs=False)
        project.relocate_input(options.input, options.file)
        write_json(project.manifest)
    elif action == "set-roles":
        validate_species_roles(options.roles)
        project = app.projects.open(options.path, verify_inputs=False)
        app.projects.set_species_roles(project, options.roles)
        write_json(project.manifest)
    elif action == "list-results":
        project = app.projects.open(options.path, verify_inputs=False)
        write_json({"analyses": list(app.projects.list_results(project))})
    elif action == "show-result":
        project = app.projects.open(options.path, verify_inputs=False)
        write_json(app.projects.load_result(project, options.analysis_id).to_dict())
    elif action == "export-result":
        project = app.projects.open(options.path, verify_inputs=False)
        result = app.projects.load_result(project, options.analysis_id)
        paths = app.exports.export(result, options.output, include_figures=options.figures)
        write_json(
            {
                "status": "completed",
                "analysis_id": result.analysis_id,
                "exports": [str(path) for path in paths],
            }
        )
    return 0
