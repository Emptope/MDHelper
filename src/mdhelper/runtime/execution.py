"""External-process execution, cancellation, and run provenance."""

from __future__ import annotations

import hashlib
import math
import os
import shlex
import signal
import subprocess
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from threading import Event, Thread
from typing import Any, Literal, Protocol, TextIO

from mdhelper.core.errors import BackendError, TaskCancelled
from mdhelper.runtime.environment import child_environment
from mdhelper.runtime.logging import record_command
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


def format_command(arguments: Sequence[str], platform: str | None = None) -> str:
    current = os.name if platform is None else platform
    values = list(arguments)
    return subprocess.list2cmdline(values) if current == "nt" else shlex.join(values)


def _record(
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
        command=command,
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


ProcessProgress = Callable[[float, str, str], None]


def _signal_tree(process: subprocess.Popen[str], force: bool) -> None:
    try:
        if os.name == "nt":
            if force:
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    check=False,
                    capture_output=True,
                    timeout=2,
                    creationflags=hidden_window_flags(),
                )
            elif process.poll() is None:
                process.terminate()
        else:
            kill_group = getattr(os, "killpg", None)
            if not callable(kill_group):
                raise OSError("Process-group signaling is unavailable.")
            group_signal = (
                getattr(signal, "SIGKILL", signal.SIGTERM)
                if force
                else signal.SIGTERM
            )
            kill_group(process.pid, group_signal)
    except (OSError, subprocess.SubprocessError):
        if process.poll() is None:
            try:
                process.kill() if force else process.terminate()
            except OSError:
                pass


def _stop(process: subprocess.Popen[str], terminate: bool) -> None:
    if terminate and os.name != "nt":
        _signal_tree(process, force=False)
        try:
            process.wait(timeout=0.5)
            return
        except subprocess.TimeoutExpired:
            pass
    _signal_tree(process, force=True)
    try:
        process.wait(timeout=0.5)
    except subprocess.TimeoutExpired:
        pass


def _read_stream(stream: TextIO, chunks: list[str]) -> None:
    try:
        while value := stream.read(1):
            chunks.append(value)
    except (OSError, ValueError):
        pass


def _finish_readers(
    process: subprocess.Popen[str],
    readers: tuple[Thread, Thread],
) -> None:
    for reader in readers:
        reader.join(timeout=0.5)
    if any(reader.is_alive() for reader in readers):
        for stream in (process.stdout, process.stderr):
            if stream is not None:
                try:
                    stream.close()
                except OSError:
                    pass
        for reader in readers:
            reader.join(timeout=0.25)


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
    process_progress: ProcessProgress | None = None,
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
    argv = [integration.path, *adapter.command_prefix(), *arguments]
    command = format_command(argv)
    record_command(command, cwd)
    try:
        creationflags = hidden_window_flags()
        if os.name == "nt":
            creationflags |= int(vars(subprocess)["CREATE_NEW_PROCESS_GROUP"])
        process = subprocess.Popen(
            argv,
            cwd=cwd,
            env=child_env,
            shell=False,
            stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=creationflags,
            start_new_session=os.name != "nt",
        )
    except OSError as exc:
        raise BackendError(
            f"Could not start {adapter.name}.",
            details={"exception": f"{type(exc).__name__}: {exc}"},
        ) from exc
    assert process.stdout is not None
    assert process.stderr is not None
    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []
    readers = (
        Thread(target=_read_stream, args=(process.stdout, stdout_chunks), daemon=True),
        Thread(target=_read_stream, args=(process.stderr, stderr_chunks), daemon=True),
    )
    for reader in readers:
        reader.start()
    if process.stdin is not None:
        try:
            process.stdin.write(input_text or "")
            process.stdin.flush()
        except (BrokenPipeError, OSError):
            pass
        finally:
            process.stdin.close()
    next_progress = started + 0.25
    last_progress = ("", "")
    while True:
        if cancel_event is not None and cancel_event.is_set():
            _stop(process, terminate=True)
            _finish_readers(process, readers)
            stdout = "".join(stdout_chunks)
            stderr = "".join(stderr_chunks)
            exit_code = process.returncode if process.returncode is not None else -1
            record = _record(
                adapter, integration, command, arguments, cwd, child_env, exit_code,
                stdout, stderr, output_files, started, started_at, "cancelled",
                record_factory,
            )
            raise TaskCancelled(
                f"{adapter.name} execution was cancelled.",
                {"integration_run": record.to_dict()},
            )
        remaining = timeout_seconds - (time.monotonic() - started)
        if remaining <= 0:
            _stop(process, terminate=False)
            _finish_readers(process, readers)
            stdout = "".join(stdout_chunks)
            stderr = "".join(stderr_chunks)
            exit_code = process.returncode if process.returncode is not None else -1
            record = _record(
                adapter, integration, command, arguments, cwd, child_env, exit_code,
                stdout, stderr, output_files, started, started_at, "timed_out",
                record_factory,
            )
            raise BackendError(
                f"{adapter.name} exceeded the {timeout_seconds:g}-second timeout.",
                details={"integration_run": record.to_dict()},
            )
        if process.poll() is not None and not any(reader.is_alive() for reader in readers):
            break
        now = time.monotonic()
        if process_progress is not None and now >= next_progress:
            current_output = ("".join(stdout_chunks), "".join(stderr_chunks))
            try:
                process_progress(
                    now - started,
                    *current_output,
                )
            except BaseException:
                _stop(process, terminate=True)
                _finish_readers(process, readers)
                raise
            last_progress = current_output
            next_progress = now + 0.25
        time.sleep(min(0.05, remaining))
    _finish_readers(process, readers)
    stdout = "".join(stdout_chunks)
    stderr = "".join(stderr_chunks)
    if process_progress is not None and (stdout, stderr) != last_progress:
        process_progress(time.monotonic() - started, stdout, stderr)
    return _record(
        adapter,
        integration,
        command,
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
