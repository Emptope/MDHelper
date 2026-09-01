from pathlib import Path
from threading import Event

import pytest

from mdhelper.core.errors import TaskCancelled
from mdhelper.services.provenance import sha256_file, unique_records


def test_unique_records_preserves_order_and_removes_exact_duplicates() -> None:
    first = {"name": "first", "values": [1, 2]}
    second = {"name": "second", "values": [1, 2]}

    assert unique_records([first, dict(first), second]) == [first, second]


def test_fingerprinting_reports_progress_and_honors_cancellation(
    tmp_path: Path,
) -> None:
    source = tmp_path / "input.dat"
    source.write_bytes(b"abcdef")
    updates: list[tuple[int, int | None, str]] = []

    assert len(sha256_file(source, progress=lambda *args: updates.append(args))) == 64
    assert updates == [(6, 6, "Fingerprinting input.dat")]

    cancel = Event()
    cancel.set()
    with pytest.raises(TaskCancelled, match="fingerprinting was cancelled"):
        sha256_file(source, cancel_event=cancel)
