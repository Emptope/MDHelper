"""Process boundary for the interactive terminal adapter."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TextIO

from mdhelper.app import ApplicationService
from mdhelper.core.errors import MDHelperError
from mdhelper.runtime.logging import configure_logging, record_error
from mdhelper.tui.controller import Tui
from mdhelper.tui.formatting import error_text
from mdhelper.tui.terminal import Terminal
from mdhelper.version import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mdhelper tui",
        description="Interactive terminal interface for MDHelper analyses.",
    )
    parser.add_argument("--version", action="version", version=f"MDHelper {__version__}")
    parser.add_argument("--config", type=Path, help="Explicit user configuration path.")
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Load the application composition without starting an interactive session.",
    )
    return parser


def main(
    argv: list[str] | None = None,
    input_stream: TextIO | None = None,
    output_stream: TextIO | None = None,
    application: ApplicationService | None = None,
) -> int:
    args = build_parser().parse_args(argv)
    terminal = Terminal(input_stream, output_stream)
    configure_logging()
    try:
        app = application or ApplicationService(user_config_path=args.config)
        if args.smoke_test:
            terminal.write(f"MDHelper TUI {__version__} ready")
            return 0
        return Tui(app, terminal).run()
    except MDHelperError as exc:
        record_error(exc, "TUI startup")
        terminal.write(error_text(exc))
        return exc.exit_code
    except KeyboardInterrupt:
        terminal.write("\nOperation interrupted; incomplete results were not committed.")
        return 7
    except Exception as exc:
        record_error(exc, "TUI startup")
        terminal.write(
            "MDHelper encountered an unexpected internal error.\n"
            f"{type(exc).__name__}: {exc}"
        )
        return 10


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
