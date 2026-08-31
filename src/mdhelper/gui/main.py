"""Windows GUI entry point with lazy Qt imports."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from mdhelper.version import __version__


def _write_error(message: str) -> None:
    if sys.stderr is not None:
        sys.stderr.write(message + "\n")


def tui_command(
    executable: str | Path | None = None,
    frozen: bool | None = None,
) -> list[str]:
    """Build the unified application command that opens the TUI adapter."""

    program = str(sys.executable if executable is None else executable)
    is_frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    if is_frozen:
        return [program, "tui"]
    return [program, "-m", "mdhelper", "tui"]


def start_tui() -> bool:
    """Start the TUI without importing it into the GUI process."""

    try:
        if sys.platform == "win32":
            subprocess.Popen(
                tui_command(),
                close_fds=True,
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
        else:
            subprocess.Popen(tui_command(), close_fds=True, start_new_session=True)
    except OSError:
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if arguments not in ([], ["--smoke-test"]):
        sys.stderr.write("Usage: mdhelper gui [--smoke-test]\n")
        return 2
    try:
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication, QMessageBox

        from mdhelper.core.errors import MDHelperError
        from mdhelper.gui.formatting import error_text
        from mdhelper.runtime.logging import record_error

        from .window import MainWindow
    except ImportError as exc:
        _write_error(
            "MDHelper GUI requires PySide6. On Windows run 'uv sync --group dev'; "
            "on other development platforms install the 'gui' extra."
        )
        _write_error(f"Import error: {exc}")
        return 6
    existing = QApplication.instance()
    application = existing if isinstance(existing, QApplication) else QApplication(sys.argv)
    application.setApplicationName("MDHelper")
    application.setApplicationVersion(__version__)
    try:
        window = MainWindow()
    except MDHelperError as exc:
        record_error(exc, "GUI startup")
        message = error_text(exc)
        _write_error(message)
        if arguments != ["--smoke-test"]:
            QMessageBox.critical(None, "MDHelper Startup Error", message)
        return exc.exit_code
    window.show()
    if arguments == ["--smoke-test"]:
        QTimer.singleShot(0, window.close)
    return int(application.exec())
