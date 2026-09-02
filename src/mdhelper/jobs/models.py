"""State models for analysis jobs."""

from __future__ import annotations

from concurrent.futures import Future
from dataclasses import dataclass, field
from enum import StrEnum
from threading import Event, Lock
from uuid import uuid4

from mdhelper.core.analysis import AnalysisResult


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class JobHandle:
    name: str = "Analysis"
    job_id: str = field(default_factory=lambda: str(uuid4()))
    status: JobStatus = JobStatus.PENDING
    current: int = 0
    total: int | None = None
    message: str = ""
    result: AnalysisResult | None = None
    error: BaseException | None = None
    cancel_event: Event = field(default_factory=Event)
    future: Future[AnalysisResult] | None = None
    _messages: list[str] = field(default_factory=list, init=False, repr=False)
    _progress_lock: Lock = field(default_factory=Lock, init=False, repr=False)

    def cancel(self) -> None:
        self.cancel_event.set()

    def update_progress(self, current: int, total: int | None, message: str) -> None:
        with self._progress_lock:
            self.current = current
            self.total = total
            self.message = message
            if message and (not self._messages or self._messages[-1] != message):
                self._messages.append(message)

    def progress_snapshot(self) -> tuple[int, int | None, str, tuple[str, ...]]:
        with self._progress_lock:
            return self.current, self.total, self.message, tuple(self._messages)

    def log_snapshot(self) -> tuple[str, ...]:
        with self._progress_lock:
            return tuple(self._messages)
