"""Infrastructure shared by analysis implementations."""

from __future__ import annotations

import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from threading import Event

from mdhelper.core.errors import BackendError, JobCancelled
from mdhelper.core.progress import ProgressCallback


@contextmanager
def analysis_directory(cache_dir: Path | None, name: str) -> Iterator[Path]:
    if cache_dir is None:
        with tempfile.TemporaryDirectory(prefix=f"mdhelper-{name}-") as directory:
            yield Path(directory)
        return
    root = cache_dir.expanduser().resolve()
    try:
        root.mkdir(parents=True, exist_ok=True)
        directory = tempfile.mkdtemp(prefix=f"{name}-", dir=root)
    except OSError as exc:
        raise BackendError(
            f"Could not prepare analysis cache directory: {root}",
            details={"exception": f"{type(exc).__name__}: {exc}"},
        ) from exc
    yield Path(directory)


def report_progress(
    callback: ProgressCallback | None,
    current: int,
    total: int | None,
    message: str,
) -> None:
    if callback:
        callback(current, total, message)


def check_cancel(cancel_event: Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise JobCancelled()
