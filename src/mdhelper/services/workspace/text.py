"""Bounded text detection and incremental UTF-8 decoding."""

from __future__ import annotations

import codecs
from pathlib import Path
from threading import Event

from mdhelper.core.errors import JobCancelled
from mdhelper.core.workspace import WorkspaceFile

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


def raw_text_file(path: Path, cancel: Event | None = None) -> WorkspaceFile:
    """Preview detected text without invoking a structural reader."""
    check_cancel(cancel)
    with path.open("rb") as handle:
        data = handle.read(TEXT_LIMIT + 1)
    check_cancel(cancel)
    complete = len(data) <= TEXT_LIMIT
    data = data[:TEXT_LIMIT]
    editable = complete
    try:
        text = codecs.getincrementaldecoder("utf-8")().decode(data, final=complete)
    except UnicodeDecodeError:
        text = codecs.getincrementaldecoder("utf-8")("replace").decode(data, final=complete)
        editable = False
    message = "Text" if editable else "Read-only text (invalid UTF-8)"
    if not complete:
        message = f"Read-only text preview (first {TEXT_LIMIT} bytes; file exceeds preview limit)"
    return WorkspaceFile(str(path), text, editable, False, message)
