"""Serialize document I/O away from the widget thread."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from threading import Event, Lock
from typing import Any

from PySide6.QtCore import QObject, Signal

from mdhelper.services.workspace import WorkspaceDocument, export_workspace_data


class DocumentWorker(QObject):
    opened = Signal(object)
    paged = Signal(object)
    imaged = Signal(object)
    failed = Signal(object)
    exported = Signal(object)
    export_failed = Signal(object)
    _finished = Signal(int, str, object)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="workspace")
        self._document: WorkspaceDocument | None = None
        self._lock = Lock()
        self._generation = 0
        self._cancel = Event()
        self._export_cancel = Event()
        self._closed = False
        self._finished.connect(self._deliver)

    def open(self, path: str) -> None:
        self._submit("opened", path)

    def page(self, offset: int) -> None:
        self._submit("paged", offset)

    def image(self, size: tuple[int, int]) -> None:
        self._submit("imaged", size)

    def export(
        self, source: str, destination: str, columns: tuple[int, ...] | None = None,
    ) -> None:
        self._export_cancel = Event()
        self._submit("exported", source, destination, self._export_cancel, columns)

    def cancel_export(self) -> None:
        self._export_cancel.set()

    def cancel(self) -> None:
        self.cancel_export()
        with self._lock:
            self._generation += 1
            self._cancel.set()
        if not self._closed:
            self._executor.submit(self._close_document)

    def _submit(self, operation: str, *args: Any) -> None:
        with self._lock:
            if self._closed:
                return
            if operation == "opened":
                self.cancel_export()
                self._cancel.set()
                self._cancel = Event()
                self._generation += 1
            generation = self._generation
            future = self._executor.submit(self._run, operation, self._cancel, args)
        future.add_done_callback(lambda item: self._complete(generation, operation, item))

    def _run(self, operation: str, cancel: Event, args: tuple[Any, ...]) -> object:
        if cancel.is_set():
            return None
        # Export owns a separate reader; failures must not invalidate the preview.
        if operation == "exported":
            return export_workspace_data(*args)
        try:
            if operation == "opened":
                self._close_document()
                self._document = WorkspaceDocument(args[0], cancel)
                if cancel.is_set():
                    self._close_document()
                    return None
                return self._document.file, self._document.rows
            if self._document is None:
                return None
            if operation == "imaged":
                return self._document.image(*args)
            return self._document.page(*args)
        except BaseException:
            self._close_document()
            raise

    def _complete(self, generation: int, operation: str, future: Future[object]) -> None:
        try:
            result = future.result()
        except BaseException as exc:
            operation, result = "export_failed" if operation == "exported" else "failed", exc
        with self._lock:
            if not self._closed and generation == self._generation:
                self._finished.emit(generation, operation, result)

    def _deliver(self, generation: int, operation: str, result: object) -> None:
        if not self._closed and generation == self._generation and result is not None:
            getattr(self, operation).emit(result)

    def _close_document(self) -> None:
        document, self._document = self._document, None
        if document is not None:
            document.close()

    def shutdown(self) -> None:
        if self._closed:
            return
        self.cancel()
        with self._lock:
            self._closed = True
        self._executor.shutdown(wait=True)
