"""Analysis batch state for the desktop GUI."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from mdhelper.core.analysis import AnalysisRequest

RunItem = tuple[AnalysisRequest, str]


class AnalysisPhase(Enum):
    IDLE = "idle"
    RUNNING = "running"
    CANCELLING = "cancelling"


@dataclass
class AnalysisBatch:
    phase: AnalysisPhase = AnalysisPhase.IDLE
    total: int = 0
    completed: int = 0
    current: RunItem | None = None
    _pending: list[RunItem] = field(default_factory=list)

    @property
    def pending(self) -> int:
        return len(self._pending)

    @property
    def position(self) -> int:
        return self.completed + (self.current is not None)

    def start(self, items: tuple[RunItem, ...]) -> None:
        if self.phase is not AnalysisPhase.IDLE:
            raise RuntimeError("An analysis batch is already active.")
        if not items:
            raise ValueError("An analysis batch requires at least one request.")
        self.phase = AnalysisPhase.RUNNING
        self.total = len(items)
        self.completed = 0
        self.current = None
        self._pending = list(items)

    def take_next(self) -> RunItem:
        if self.phase is not AnalysisPhase.RUNNING:
            raise RuntimeError("The analysis batch is not running.")
        if self.current is not None:
            raise RuntimeError("The current analysis has not completed.")
        if not self._pending:
            raise RuntimeError("The analysis batch has no pending request.")
        self.current = self._pending.pop(0)
        return self.current

    def complete_current(self) -> bool:
        if self.current is None:
            raise RuntimeError("The analysis batch has no current request.")
        self.current = None
        self.completed += 1
        finished = not self._pending or self.phase is AnalysisPhase.CANCELLING
        if finished:
            self.reset()
        return finished

    def cancel(self) -> None:
        self._pending.clear()
        if self.current is None:
            self.reset()
            return
        self.phase = AnalysisPhase.CANCELLING

    def fail(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.phase = AnalysisPhase.IDLE
        self.total = 0
        self.completed = 0
        self.current = None
        self._pending.clear()
