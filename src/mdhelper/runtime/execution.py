"""External-process execution, cancellation, and run provenance."""

from __future__ import annotations

import hashlib
import math
import os
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from threading import Event
from typing import Any, Literal, Protocol

from mdhelper.core.errors import BackendError, TaskCancelled
from mdhelper.runtime.environment import child_environment
from mdhelper.runtime.process import hidden_window_flags


class ExecutionAdapter(Protocol):
    name: str
    display_name: str

    def command_prefix(self) -> tuple[str, ...]: ...

    def environment_keys(self) -> frozenset[str]: ...

    def provenance_environment_keys(self) -> frozenset[str]: ...


class ExecutionStatus(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def available(self) -> bool: ...

    @property
    def path(self) -> str | None: ...

    @property
    def version(self) -> str | None: ...


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fingerprints(output_files: list[str | Path] | None, cwd: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for output in output_files or []:
        path = Path(output)
        if not path.is_absolute():
            path = cwd / path
        if path.is_file():
            values[str(path.resolve())] = _sha256(path)
    return values


def _record(
    adapter: ExecutionAdapter,
    integration: ExecutionStatus,
    arguments: list[str],
    cwd: Path,
    environment: dict[str, str],
    exit_code: int,
    stdout: str,
    stderr: str,
    output_files: list[str | Path] | None,
    started: float,
    started_at: str,
    status: Literal["completed", "failed", "cancelled", "timed_out"],
    record_factory: Any,
) -> Any:
    assert integration.path is not None
    assert integration.version is not None
    keys = adapter.provenance_environment_keys()
    return record_factory(
        name=adapter.name,
        display_name=adapter.display_name.strip() or adapter.name,
        path=integration.path,
        version=integration.version,
        arguments=list(arguments),
        working_directory=str(cwd),
        environment_summary={key: environment[key] for key in keys if key in environment},
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        started_at=started_at,
        output_fingerprints=_fingerprints(output_files, cwd),
        elapsed_seconds=time.monotonic() - started,
        status=status,
    )


def _stop(process: subprocess.Popen[str], terminate: bool) -> tuple[str, str]:
    if terminate:
        process.terminate()
        try:
            return process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            pass
    process.kill()
    return process.communicate()


def run_integration(
    adapter: ExecutionAdapter,
    integration: ExecutionStatus,
    arguments: list[str],
    working_directory: str | Path,
    timeout_seconds: float,
    cancel_event: Event | None = None,
    output_files: list[str | Path] | None = None,
    environment: dict[str, str] | None = None,
    input_text: str | None = None,
    record_factory: Any = None,
) -> Any:
    """Run a detected integration with a bounded environment and lifetime."""

    if integration.name.casefold() != adapter.name.casefold():
        raise BackendError("The integration status does not match the selected adapter.")
    if not integration.available or not integration.path or not integration.version:
        raise BackendError("An integration must pass detection before execution.")
    if any("\x00" in argument for argument in arguments):
        raise BackendError("Integration arguments cannot contain NUL bytes.")
    if input_text is not None and "\x00" in input_text:
        raise BackendError("Integration input cannot contain NUL bytes.")
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise BackendError("Integration timeout must be a finite positive number.")
    if record_factory is None:
        raise BackendError("Integration execution requires a record factory.")
    cwd = Path(working_directory).expanduser().resolve()
    if not cwd.is_dir():
        raise BackendError(f"Integration working directory does not exist: {cwd}")
    raw_environment = dict(os.environ if environment is None else environment)
    child_env = child_environment(adapter, raw_environment)
    started = time.monotonic()
    started_at = datetime.now(UTC).isoformat()
    try:
        process = subprocess.Popen(
            [integration.path, *adapter.command_prefix(), *arguments],
            cwd=cwd,
            env=child_env,
            shell=False,
            stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=hidden_window_flags(),
        )
    except OSError as exc:
        raise BackendError(
            f"Could not start {adapter.name}.",
            details={"exception": f"{type(exc).__name__}: {exc}"},
        ) from exc
    pending_input = input_text
    while True:
        if cancel_event is not None and cancel_event.is_set():
            stdout, stderr = _stop(process, terminate=True)
            record = _record(
                adapter, integration, arguments, cwd, child_env, process.returncode,
                stdout, stderr, output_files, started, started_at, "cancelled",
                record_factory,
            )
            raise TaskCancelled(
                f"{adapter.name} execution was cancelled.",
                {"integration_run": record.to_dict()},
            )
        remaining = timeout_seconds - (time.monotonic() - started)
        if remaining <= 0:
            stdout, stderr = _stop(process, terminate=False)
            record = _record(
                adapter, integration, arguments, cwd, child_env, process.returncode,
                stdout, stderr, output_files, started, started_at, "timed_out",
                record_factory,
            )
            raise BackendError(
                f"{adapter.name} exceeded the {timeout_seconds:g}-second timeout.",
                details={"integration_run": record.to_dict()},
            )
        payload = pending_input
        pending_input = None
        try:
            stdout, stderr = process.communicate(
                input=payload, timeout=min(0.25, remaining)
            )
            break
        except subprocess.TimeoutExpired:
            continue
    return _record(
        adapter,
        integration,
        arguments,
        cwd,
        child_env,
        process.returncode,
        stdout,
        stderr,
        output_files,
        started,
        started_at,
        "completed" if process.returncode == 0 else "failed",
        record_factory,
    )
