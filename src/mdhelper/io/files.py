"""Cancellable content fingerprints for input files."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path
from threading import Event

from mdhelper.core.errors import InputFileError, JobCancelled


def sha256_file(
    path: str | Path,
    cancel_event: Event | None = None,
    progress: Callable[[int, int | None, str], None] | None = None,
) -> str:
    target = Path(path)
    digest = hashlib.sha256()
    processed = 0
    try:
        if cancel_event is not None and cancel_event.is_set():
            raise JobCancelled("Input fingerprinting was cancelled.")
        total = target.stat().st_size
        with target.open("rb") as handle:
            for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
                if cancel_event is not None and cancel_event.is_set():
                    raise JobCancelled("Input fingerprinting was cancelled.")
                digest.update(chunk)
                processed += len(chunk)
                if progress:
                    progress(processed, total, f"Fingerprinting {target.name}")
    except JobCancelled:
        raise
    except OSError as exc:
        raise InputFileError(
            f"Could not fingerprint input file: {target}",
            details={"exception": f"{type(exc).__name__}: {exc}"},
        ) from exc
    return digest.hexdigest()
