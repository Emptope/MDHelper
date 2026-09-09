"""Bounded text detection and incremental UTF-8 decoding."""

from __future__ import annotations

import codecs
from collections.abc import Generator
from pathlib import Path
from threading import Event

from mdhelper.core.errors import JobCancelled

TEXT_LIMIT = 1024 * 1024
BLOCK_SIZE = 65536


def check_cancel(cancel: Event | None) -> None:
    if cancel is not None and cancel.is_set():
        raise JobCancelled("File loading cancelled")


def is_text(path: Path, cancel: Event | None) -> bool:
    check_cancel(cancel)
    with path.open("rb") as handle:
        chunk = handle.read(BLOCK_SIZE)
    if b"\0" in chunk:
        return False
    try:
        codecs.getincrementaldecoder("utf-8")().decode(chunk, final=len(chunk) < BLOCK_SIZE)
    except UnicodeDecodeError:
        return False
    return True


def text_records(
    path: Path, cancel: Event | None,
) -> Generator[tuple[tuple[str, ...], ...], None, None]:
    decoder = codecs.getincrementaldecoder("utf-8")()
    offset = 0
    with path.open("rb") as handle:
        while True:
            check_cancel(cancel)
            chunk = handle.read(4096)
            text = decoder.decode(chunk, final=not chunk)
            if text:
                yield ((str(offset), text),)
                offset += len(text)
            if not chunk:
                break
