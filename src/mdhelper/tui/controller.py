"""Top-level terminal state machine and controller composition."""

from __future__ import annotations

from collections.abc import Callable

from mdhelper.app import ApplicationService
from mdhelper.core.errors import MDHelperError
from mdhelper.jobs import JobRunner
from mdhelper.runtime.logging import record_error
from mdhelper.tui.controllers import (
    AnalysisController,
    ResultController,
    ToolController,
    WorkspaceController,
)
from mdhelper.tui.formatting import error_text
from mdhelper.tui.model import Workspace
from mdhelper.tui.terminal import EndOfInput, Terminal
from mdhelper.version import DEVELOPER, __version__

_QUIT = "q"


class Tui(
    AnalysisController,
    ResultController,
    WorkspaceController,
    ToolController,
):
    """Compose focused controllers behind one numbered-menu interface."""

    def __init__(self, application: ApplicationService, terminal: Terminal):
        self.application = application
        self.terminal = terminal
        self.workspace = Workspace()
        self.job_runner = JobRunner(application)

    def run(self) -> int:
        self._banner()
        main_menu = False
        try:
            while True:
                if main_menu:
                    choice = self._main_choice()
                    if choice == _QUIT:
                        return 0
                    self._action(choice)
                    continue
                choice = self._load_choice()
                if choice == _QUIT:
                    return 0
                main_menu = self._load_action(choice)
        except EndOfInput:
            self.terminal.write("\nInput closed; exiting MDHelper.")
            return 0
        except KeyboardInterrupt:
            self.terminal.write(
                "\nOperation interrupted; incomplete results were not committed."
            )
            return 7
        finally:
            self.job_runner.shutdown()

    def _banner(self) -> None:
        self.terminal.panel(
            (
                f"MDHelper {__version__}",
                f"Developer: {DEVELOPER}",
            )
        )

    def _load_choice(self) -> str | None:
        self._write_context()
        return self.terminal.menu(
            "Load",
            (
                ("Open project", "1"),
                ("Main menu", "2"),
                ("Quit", _QUIT),
            ),
            back=False,
        )

    def _main_choice(self) -> str | None:
        self._write_context()
        return self.terminal.menu(
            "Main menu",
            (
                ("Analysis", "1"),
                ("Results and export", "2"),
                ("System and project", "3"),
                ("Species roles", "4"),
                ("Tools", "5"),
                ("Quit", _QUIT),
            ),
            back=False,
        )

    def _write_context(self) -> None:
        project = (
            "none" if self.workspace.project is None else str(self.workspace.project.root)
        )
        self.terminal.write()
        self.terminal.write(f"Current project: {project}")

    def _load_action(self, choice: str | None) -> bool:
        if choice == "2":
            return True
        if choice == "1":
            self._perform(self._open_project)
            return self.workspace.loaded
        return False

    def _action(self, choice: str | None) -> None:
        actions = {
            "1": self._analyses,
            "2": self._results,
            "3": self._workspace,
            "4": self._roles,
            "5": self._tools,
        }
        self._perform(actions.get(choice or ""))

    def _perform(self, action: Callable[[], None] | None) -> None:
        if action is None:
            return
        try:
            action()
        except EndOfInput:
            raise
        except (MDHelperError, OSError, ValueError) as exc:
            record_error(exc, "TUI operation")
            self.terminal.heading("Action could not be completed")
            self.terminal.write(error_text(exc))
        except Exception as exc:
            record_error(exc, "TUI operation")
            self.terminal.heading("Unexpected internal error")
            self.terminal.write(error_text(exc))
