"""Qt-facing controller for asynchronous integration detection."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from threading import Lock
from typing import Any

from PySide6.QtCore import QObject, Signal

from mdhelper.app import ApplicationService

_DETECTION_EXECUTOR = ThreadPoolExecutor(
    max_workers=2,
    thread_name_prefix="mdhelper-detection",
)


class IntegrationDetectionController(QObject):
    completed = Signal(str, object)
    failed = Signal(str, object)

    def __init__(self, application: ApplicationService, parent: QObject | None = None):
        super().__init__(parent)
        self.application = application
        self._lock = Lock()
        self._generation = 0
        self._future: Future[Any] | None = None
        self._closed = False

    def submit(self, name: str) -> None:
        config = self.application.config.integration(name)
        with self._lock:
            if self._closed:
                return
            self._generation += 1
            generation = self._generation
            previous = self._future
            future = _DETECTION_EXECUTOR.submit(
                self.application.integrations.detect,
                name,
                None,
                config,
            )
            self._future = future
        if previous is not None:
            previous.cancel()
        future.add_done_callback(
            lambda result: self._finished(name, generation, result)
        )

    def _finished(
        self,
        name: str,
        generation: int,
        future: Future[Any],
    ) -> None:
        with self._lock:
            current = not self._closed and generation == self._generation
        if not current or future.cancelled():
            return
        try:
            status = future.result()
        except BaseException as exc:
            self.failed.emit(name, exc)
            return
        self.completed.emit(name, status)

    def shutdown(self) -> None:
        with self._lock:
            self._closed = True
            future = self._future
        if future is not None:
            future.cancel()
