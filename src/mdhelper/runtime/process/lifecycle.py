"""External-process execution, streaming, cancellation, and timeout."""

from __future__ import annotations

import math
import os
import signal
import subprocess
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from threading import Event, Thread
from typing import Any, TextIO

from mdhelper.core.errors import BackendError, JobCancelled
from mdhelper.runtime.environment import child_environment
from mdhelper.runtime.logging import record_command

from .contracts import ExecutionAdapter, ExecutionStatus, integration_argv
from .records import RunStatus, build_record, format_command

ProcessProgress = Callable[[float, str, str], None]


def hidden_window_flags(platform: str | None = None) -> int:
    system = os.name if platform is None else platform
    if system != "nt":
        return 0
    return int(vars(subprocess)["CREATE_NO_WINDOW"])


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

    argv = integration_argv(adapter, integration, arguments)
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
    command = format_command(argv)
    record_command(command, cwd)
    process = _start(adapter, argv, cwd, child_env, input_text)
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
    _write_input(process, input_text)
    next_progress = started + 0.25
    last_progress = ("", "")
    reported_elapsed: float | None = None

    def finish_record(status: RunStatus) -> Any:
        return build_record(
            adapter,
            integration,
            command,
            arguments,
            cwd,
            child_env,
            _exit_code(process),
            "".join(stdout_chunks),
            "".join(stderr_chunks),
            output_files,
            started,
            started_at,
            status,
            record_factory,
            reported_elapsed=reported_elapsed,
        )

    while True:
        if cancel_event is not None and cancel_event.is_set():
            _stop(process, terminate=True)
            _finish_readers(readers)
            record = finish_record("cancelled")
            raise JobCancelled(
                f"{adapter.name} execution was cancelled.",
                {"integration_run": record.to_dict()},
            )
        remaining = timeout_seconds - (time.monotonic() - started)
        if remaining <= 0:
            _stop(process, terminate=False)
            _finish_readers(readers)
            record = finish_record("timed_out")
            raise BackendError(
                f"{adapter.name} exceeded the {timeout_seconds:g}-second timeout.",
                details={"integration_run": record.to_dict()},
            )
        if process.poll() is not None:
            break
        now = time.monotonic()
        if process_progress is not None and now >= next_progress:
            current_output = ("".join(stdout_chunks), "".join(stderr_chunks))
            try:
                reported_elapsed = now - started
                process_progress(reported_elapsed, *current_output)
            except BaseException:
                _stop(process, terminate=True)
                _finish_readers(readers)
                raise
            last_progress = current_output
            next_progress = now + 0.25
        try:
            process.wait(timeout=min(0.05, remaining))
        except subprocess.TimeoutExpired:
            pass
    _finish_readers(readers)
    stdout = "".join(stdout_chunks)
    stderr = "".join(stderr_chunks)
    if process_progress is not None and (stdout, stderr) != last_progress:
        reported_elapsed = time.monotonic() - started
        process_progress(reported_elapsed, stdout, stderr)
    return finish_record("completed" if process.returncode == 0 else "failed")


def _start(
    adapter: ExecutionAdapter,
    argv: list[str],
    cwd: Path,
    environment: dict[str, str],
    input_text: str | None,
) -> subprocess.Popen[str]:
    try:
        creationflags = hidden_window_flags()
        if os.name == "nt":
            creationflags |= int(vars(subprocess)["CREATE_NEW_PROCESS_GROUP"])
        return subprocess.Popen(
            argv,
            cwd=cwd,
            env=environment,
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


def _write_input(process: subprocess.Popen[str], input_text: str | None) -> None:
    if process.stdin is None:
        return
    try:
        process.stdin.write(input_text or "")
        process.stdin.flush()
    except (BrokenPipeError, OSError):
        pass
    finally:
        try:
            process.stdin.close()
        except (BrokenPipeError, OSError):
            pass


def _exit_code(process: subprocess.Popen[str]) -> int:
    return process.returncode if process.returncode is not None else -1


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
    finally:
        try:
            stream.close()
        except OSError:
            pass


def _finish_readers(readers: tuple[Thread, Thread]) -> None:
    deadline = time.monotonic() + 0.5
    for reader in readers:
        reader.join(timeout=max(0.0, deadline - time.monotonic()))
