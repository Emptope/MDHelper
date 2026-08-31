"""External software integration CLI commands."""

from __future__ import annotations

import argparse
import signal
import sys
from threading import Event
from typing import Any

from mdhelper.app import ApplicationService
from mdhelper.cli.output import write_json
from mdhelper.core.errors import BackendError, InputError


def handle(args: argparse.Namespace, app: ApplicationService) -> int:
    if args.integration_command == "list":
        write_json(
            {
                "supported": list(app.integrations.names()),
                "configured": {
                    name: config.enabled
                    for name, config in sorted(app.config.integrations.items())
                },
            }
        )
        return 0
    if args.integration_command == "templates":
        if args.key:
            write_json(app.templates.get(args.key).to_dict(include_content=True))
        else:
            write_json({"templates": [item.to_dict() for item in app.templates.list()]})
        return 0
    config = app.config.integration(args.integration)
    if args.integration_command == "detect":
        status = app.integrations.detect(args.integration, getattr(args, "path", None))
        write_json(status.to_dict())
        return 0 if status.available else 6
    arguments = list(args.arguments)
    if arguments and arguments[0] == "--":
        arguments.pop(0)
    if not arguments:
        raise InputError("Integration execution requires arguments after '--'.")
    cancel_event = Event()
    previous_handler = signal.getsignal(signal.SIGINT)

    def request_cancel(_signum: int, _frame: Any) -> None:
        cancel_event.set()
        sys.stderr.write("\nCancellation requested; terminating the integration...\n")
        sys.stderr.flush()

    signal.signal(signal.SIGINT, request_cancel)
    try:
        project = app.projects.open(args.project, verify_inputs=False) if args.project else None
        record = app.integrations.run(
            args.integration,
            arguments,
            args.cwd,
            override=getattr(args, "path", None),
            timeout_seconds=(
                config.run_timeout_seconds if args.timeout is None else args.timeout
            ),
            cancel_event=cancel_event,
            output_files=args.output_file,
            project=project,
        )
    finally:
        signal.signal(signal.SIGINT, previous_handler)
    write_json(record.to_dict())
    if record.exit_code != 0:
        raise BackendError(
            f"{args.integration} exited with code {record.exit_code}.",
            details={"stderr": record.stderr[-4000:]},
        )
    return 0
