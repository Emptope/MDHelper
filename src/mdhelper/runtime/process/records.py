"""External-process command formatting and run records."""

from __future__ import annotations

import hashlib
import math
import os
import shlex
import subprocess
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal

from .contracts import ExecutionAdapter, ExecutionStatus

RunStatus = Literal["completed", "failed", "cancelled", "timed_out"]


def format_command(arguments: Sequence[str], platform: str | None = None) -> str:
    current = os.name if platform is None else platform
    values = list(arguments)
    return subprocess.list2cmdline(values) if current == "nt" else shlex.join(values)


def build_record(
    adapter: ExecutionAdapter,
    integration: ExecutionStatus,
    command: str,
    arguments: list[str],
    cwd: Path,
    environment: dict[str, str],
    exit_code: int,
    stdout: str,
    stderr: str,
    output_files: list[str | Path] | None,
    started: float,
    started_at: str,
    status: RunStatus,
    record_factory: Any,
    *,
    reported_elapsed: float | None = None,
) -> Any:
    assert integration.path is not None
    assert integration.version is not None
    keys = adapter.provenance_environment_keys()
    output_fingerprints = _fingerprints(output_files, cwd)
    elapsed = time.monotonic() - started
    if reported_elapsed is not None and elapsed <= reported_elapsed:
        elapsed = math.nextafter(reported_elapsed, math.inf)
    return record_factory(
        name=adapter.name,
        display_name=adapter.display_name.strip() or adapter.name,
        path=integration.path,
        version=integration.version,
        command=command,
        arguments=list(arguments),
        working_directory=str(cwd),
        environment_summary={key: environment[key] for key in keys if key in environment},
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        started_at=started_at,
        output_fingerprints=output_fingerprints,
        elapsed_seconds=elapsed,
        status=status,
    )


def _fingerprints(output_files: list[str | Path] | None, cwd: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for output in output_files or []:
        path = Path(output)
        if not path.is_absolute():
            path = cwd / path
        if path.is_file():
            values[str(path.resolve())] = _sha256(path)
    return values


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
