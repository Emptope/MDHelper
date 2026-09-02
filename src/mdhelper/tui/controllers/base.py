"""Shared state contract for terminal controllers."""

from __future__ import annotations

from mdhelper.app import ApplicationService
from mdhelper.jobs import JobRunner
from mdhelper.tui.model import Workspace
from mdhelper.tui.terminal import Terminal


class ControllerContext:
    application: ApplicationService
    terminal: Terminal
    workspace: Workspace
    job_runner: JobRunner

    def _roles(self) -> None:
        raise NotImplementedError

    def _require_confirmed_roles(self) -> None:
        raise NotImplementedError
