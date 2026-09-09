"""Workspace documents loaded only as their views request data."""

from __future__ import annotations

from dataclasses import replace
from itertools import chain, islice
from pathlib import Path
from threading import Event
from typing import TYPE_CHECKING

from mdhelper.core.errors import ConfigurationError, JobCancelled
from mdhelper.core.workspace import DataLayout, DataPage, ImagePixels, WorkspaceFile
from mdhelper.io.workspace import DataStore

from .images import image_info, image_pixels
from .text import TEXT_LIMIT, check_cancel, is_text, raw_text_file

if TYPE_CHECKING:
    from collections.abc import Generator, Iterator

    from mdhelper.backends.mdanalysis.workspace import BinaryDocument


class WorkspaceDocument:
    def __init__(self, path: str | Path, cancel: Event | None = None):
        self.store: DataStore | None = None
        self._binary: BinaryDocument | None = None
        self._batches: Generator[tuple[tuple[str, ...], ...], None, None] | None = None
        self._records: Iterator[tuple[str, ...]] = iter(())
        self._cancel = cancel
        self.complete = True
        self.source = Path(path).expanduser().resolve()
        check_cancel(cancel)
        if not self.source.is_file():
            raise ConfigurationError(f"File does not exist: {self.source}")
        info = image_info(self.source)
        if info is not None:
            self.file = WorkspaceFile(
                str(self.source), "", False, False,
                f"{info.format} | {info.width} x {info.height}", image=info,
            )
            return
        if is_text(self.source, cancel):
            self.file = raw_text_file(self.source, cancel)
            return
        from mdhelper.backends.mdanalysis.workspace import BinaryDocument

        try:
            self._binary = BinaryDocument(self.source)
            self._batches = self._binary.records(cancel)
            self._start(replace(self._binary.layout, streaming=True), "Read-only data")
            check_cancel(cancel)
        except JobCancelled:
            self.close()
            raise
        except Exception as exc:
            self.close()
            self.file = WorkspaceFile(
                str(self.source), "", False, False, f"Cannot parse binary file: {exc}",
            )

    def _start(self, layout: DataLayout, message: str) -> None:
        self.store = DataStore(layout.columns)
        self.complete = False
        assert self._batches is not None
        self._records = chain.from_iterable(self._batches)
        self.file = WorkspaceFile(str(self.source), "", False, True, message, layout)

    @property
    def rows(self) -> int:
        return 0 if self.store is None else self.store.count

    def page(self, offset: int, limit: int = 256) -> DataPage:
        if self.store is None:
            raise ConfigurationError("No parsed data is open")
        if offset < 0 or limit < 1:
            raise ValueError("Invalid data page range")
        try:
            check_cancel(self._cancel)
            while not self.complete and self.store.count < offset + limit:
                count = min(256, offset + limit - self.store.count)
                rows = tuple(islice(self._records, count))
                self.store.append(rows)
                check_cancel(self._cancel)
                if len(rows) < count:
                    self.complete = True
                    self._close_reader()
            self.store.finish()
            return replace(self.store.page(offset, limit), complete=self.complete)
        except BaseException:
            self.close()
            raise

    def image(self, size: tuple[int, int]) -> ImagePixels:
        if self.file.image is None:
            raise ConfigurationError("No image is open")
        return image_pixels(self.source, size, self._cancel)

    def _close_reader(self) -> None:
        batches, self._batches = self._batches, None
        binary, self._binary = self._binary, None
        self._records = iter(())
        try:
            if batches is not None:
                batches.close()
        finally:
            if binary is not None:
                binary.close()

    def close(self) -> None:
        try:
            self._close_reader()
        finally:
            if self.store is not None:
                store, self.store = self.store, None
                store.close()

    def __enter__(self) -> WorkspaceDocument:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


def open_workspace_file(path: str | Path) -> WorkspaceFile:
    with WorkspaceDocument(path) as document:
        return document.file


def save_workspace_text(path: str | Path, text: str) -> WorkspaceFile:
    source = Path(path).expanduser().resolve()
    if source.stat().st_size > TEXT_LIMIT or len(text.encode("utf-8")) > TEXT_LIMIT:
        raise ConfigurationError("Large text files are read-only in Workspace")
    source.write_text(text, encoding="utf-8")
    return WorkspaceFile(str(source), text, True, False, "Saved")
