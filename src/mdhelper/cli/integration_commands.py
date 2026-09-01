"""External integration CLI commands."""

from __future__ import annotations

import signal
import sys
from threading import Event
from typing import Any

from jsonargparse import Namespace

from mdhelper.app import ApplicationService
from mdhelper.cli.output import write_json
from mdhelper.core.errors import BackendError


def handle(args: Namespace, app: ApplicationService) -> int:
    action = args.action
    options = args[action]
    if action == "list":
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
    if action == "detect":
        status = app.integrations.detect(options.integration, options.path)
        write_json(status.to_dict())
        return 0 if status.available else 6

    config = app.config.integration(options.integration)
    cancel_event = Event()
    previous_handler = signal.getsignal(signal.SIGINT)

    def request_cancel(_signum: int, _frame: Any) -> None:
        cancel_event.set()
        sys.stderr.write("\nCancellation requested; terminating the integration...\n")
        sys.stderr.flush()

    signal.signal(signal.SIGINT, request_cancel)
    try:
        project = (
            app.projects.open(options.project, verify_inputs=False)
            if options.project
            else None
        )
        record = app.integrations.run(
            options.integration,
            list(options.arguments),
            options.cwd,
            override=options.path,
            timeout_seconds=(
                config.run_timeout_seconds if options.timeout is None else options.timeout
            ),
            cancel_event=cancel_event,
            output_files=options.output_files,
            project=project,
        )
    finally:
        signal.signal(signal.SIGINT, previous_handler)
    write_json(record.to_dict())
    if record.exit_code != 0:
        raise BackendError(
            f"{options.integration} exited with code {record.exit_code}.",
            details={"stderr": record.stderr[-4000:]},
        )
    return 0
