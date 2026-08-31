"""Process boundary for the command-line adapter."""

from __future__ import annotations

import sys
import traceback

from mdhelper.cli.commands import dispatch
from mdhelper.cli.output import write_json
from mdhelper.cli.parser import build_parser, parse_args
from mdhelper.core.errors import MDHelperError
from mdhelper.runtime.logging import configure_logging, record_error


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parse_args(parser, argv)
    configure_logging()
    try:
        return dispatch(args)
    except MDHelperError as exc:
        record_error(exc, f"CLI command {args.command}")
        write_json(exc.to_dict(), sys.stderr)
        if args.debug:
            traceback.print_exc(file=sys.stderr)
        return exc.exit_code
    except KeyboardInterrupt:
        record_error(KeyboardInterrupt(), f"CLI command {args.command}")
        write_json(
            {
                "error": "interrupted",
                "message": "Operation was interrupted.",
                "hint": "Incomplete results were not committed.",
            },
            sys.stderr,
        )
        return 7
    except Exception as exc:
        record_error(exc, f"CLI command {args.command}")
        write_json(
            {
                "error": "internal_error",
                "message": "MDHelper encountered an unexpected internal error.",
                "hint": "Re-run with --debug and include the diagnostic output in a bug report.",
                "details": {"exception": f"{type(exc).__name__}: {exc}"},
            },
            sys.stderr,
        )
        if args.debug:
            traceback.print_exc(file=sys.stderr)
        return 10
