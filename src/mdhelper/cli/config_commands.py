"""Configuration CLI commands."""

from __future__ import annotations

import argparse
import sys

from mdhelper.cli.output import write_json
from mdhelper.services.config import config_path, initialize_config, load_config


def handle(args: argparse.Namespace) -> int:
    path = config_path() if args.config is None else args.config.expanduser().resolve()
    if args.config_command == "path":
        sys.stdout.write(str(path) + "\n")
    elif args.config_command == "init":
        sys.stdout.write(str(initialize_config(path, force=args.force)) + "\n")
    elif args.config_command in {"check", "show"}:
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
