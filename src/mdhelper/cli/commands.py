"""Top-level routing for native jsonargparse namespaces."""

from __future__ import annotations

from jsonargparse import Namespace

from mdhelper.app import ApplicationService
from mdhelper.cli.analysis_commands import handle as handle_analysis
from mdhelper.cli.analysis_commands import inspect as inspect_system
from mdhelper.cli.config_commands import handle as handle_config
from mdhelper.cli.integration_commands import handle as handle_integration
from mdhelper.cli.project_commands import handle as handle_project
from mdhelper.cli.template_commands import handle as handle_template


def dispatch(args: Namespace) -> int:
    command = args.command
    options = args[command]
    if command == "config":
        return handle_config(options, args.settings)
    app = ApplicationService(user_config_path=args.settings)
    if command == "inspect":
        return inspect_system(options, app)
    if command == "analyze":
        return handle_analysis(options, app)
    if command == "project":
        return handle_project(options, app)
    if command == "integrations":
        return handle_integration(options, app)
    if command == "templates":
        return handle_template(options, app)
    raise AssertionError(f"Unhandled command: {command}")
