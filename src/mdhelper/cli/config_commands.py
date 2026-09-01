"""User configuration CLI commands."""

from __future__ import annotations

import sys
from pathlib import Path

from jsonargparse import Namespace

from mdhelper.cli.output import write_json
from mdhelper.services.config import config_path, initialize_config, load_config


def handle(args: Namespace, settings: Path | None) -> int:
    path = config_path() if settings is None else settings.expanduser().resolve()
    action = args.action
    options = args[action]
    if action == "path":
        sys.stdout.write(str(path) + "\n")
    elif action == "init":
        sys.stdout.write(str(initialize_config(path, force=options.force)) + "\n")
    elif action in {"check", "show"}:
        config = load_config(path)
        write_json(
            {
                "status": "valid",
                "path": str(path),
                "exists": path.exists(),
                "configuration": config.to_dict(),
            }
        )
    return 0
