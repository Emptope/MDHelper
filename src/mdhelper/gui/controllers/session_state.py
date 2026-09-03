"""Project session state for the desktop GUI."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SessionPhase(Enum):
    EMPTY = "empty"
    READY = "ready"
    RUNNING = "running"
    COMPLETE = "complete"


@dataclass
class SessionState:
    phase: SessionPhase = SessionPhase.EMPTY

    def ready(self) -> None:
        self.phase = SessionPhase.READY

    def start(self) -> None:
        if self.phase not in {
            SessionPhase.EMPTY,
            SessionPhase.READY,
            SessionPhase.COMPLETE,
        }:
            raise RuntimeError("The project session is already running an analysis.")
        self.phase = SessionPhase.RUNNING

    def complete(self) -> None:
        if self.phase is not SessionPhase.RUNNING:
            raise RuntimeError("The project session has no running analysis.")
        self.phase = SessionPhase.COMPLETE

    def restore(self) -> None:
        if self.phase is SessionPhase.EMPTY:
            raise RuntimeError("The project session is not open.")
        self.phase = SessionPhase.COMPLETE

    def abort(self, project_open: bool) -> None:
        if self.phase is not SessionPhase.RUNNING:
            return
        self.phase = SessionPhase.READY if project_open else SessionPhase.EMPTY

    def reset(self) -> None:
        self.phase = SessionPhase.EMPTY
