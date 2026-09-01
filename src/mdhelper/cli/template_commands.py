"""Bundled template CLI commands."""

from __future__ import annotations

from jsonargparse import Namespace

from mdhelper.app import ApplicationService
from mdhelper.cli.output import write_json


def handle(args: Namespace, app: ApplicationService) -> int:
    action = args.action
    options = args[action]
    if action == "list":
        write_json({"templates": [item.to_dict() for item in app.templates.list()]})
    elif action == "show":
        write_json(app.templates.get(options.key).to_dict(include_content=True))
    elif action == "save":
        output = app.templates.save(options.key, options.output)
        write_json({"key": options.key, "output": str(output)})
    return 0
