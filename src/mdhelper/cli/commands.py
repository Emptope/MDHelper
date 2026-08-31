"""Top-level routing for parsed CLI commands."""

from __future__ import annotations

import argparse

from mdhelper.app import ApplicationService
from mdhelper.cli.analysis_commands import handle as handle_analysis
from mdhelper.cli.config_commands import handle as handle_config
from mdhelper.cli.integration_commands import handle as handle_integration
from mdhelper.cli.project_commands import handle as handle_project


def dispatch(args: argparse.Namespace) -> int:
    if args.command == "config":
        return handle_config(args)
    app = ApplicationService(user_config_path=args.config)
    if args.command == "integrations":
        return handle_integration(args, app)
    if args.command == "project":
        return handle_project(args, app)
    return handle_analysis(args, app)
