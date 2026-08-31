"""Safe executable identity, version, and capability detection."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Protocol

from mdhelper.runtime.environment import child_environment
from mdhelper.runtime.process import hidden_window_flags


class DetectionAdapter(Protocol):
    name: str

    def command_prefix(self) -> tuple[str, ...]: ...

    def version_detect(self) -> tuple[str, str] | None: ...

    def version_arguments(self, detect_path: str | None = None) -> tuple[str, ...]: ...

    def parse_version(self, stdout: str, stderr: str, exit_code: int) -> str | None: ...

    def capability_arguments(self) -> tuple[str, ...] | None: ...

    def parse_capabilities(
        self, stdout: str, stderr: str, exit_code: int
    ) -> tuple[str, ...]: ...

    def capability_detection_required(self) -> bool: ...

    def default_capabilities(self) -> tuple[str, ...]: ...

    def environment_keys(self) -> frozenset[str]: ...


def resolved_path(value: str) -> str:
    try:
        return str(Path(value).expanduser().resolve())
    except OSError:
        return os.path.abspath(os.path.expanduser(value))


def canonical_path(value: str) -> str:
    return os.path.normcase(resolved_path(value))


def _run(
    path: str,
    prefix: tuple[str, ...],
    arguments: tuple[str, ...],
    timeout: float,
    environment: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [path, *prefix, *arguments],
        shell=False,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=environment,
        creationflags=hidden_window_flags(),
    )


@contextmanager
def _version_arguments(adapter: DetectionAdapter) -> Iterator[tuple[str, ...]]:
    detect = adapter.version_detect()
    if detect is None:
        yield adapter.version_arguments()
        return
    contents, suffix = detect
    path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=suffix,
            encoding="ascii",
            delete=False,
        ) as handle:
            handle.write(contents)
            path = Path(handle.name)
        yield adapter.version_arguments(str(path))
    finally:
        if path is not None:
            path.unlink(missing_ok=True)


def detect_candidate(
    adapter: DetectionAdapter,
    candidate: str,
    source: str,
    rank: int,
    timeout: float,
    environment: dict[str, str],
    detection_factory: Any,
) -> Any:
    expanded = str(Path(candidate).expanduser())
    resolved = (
        shutil.which(expanded, path=environment.get("PATH"))
        if not Path(expanded).is_absolute()
        else expanded
    )
    if not resolved:
        return detection_factory(
            adapter.name, source, candidate, False,
            error="Executable was not found.", rank=rank,
        )
    path = Path(resolved)
    if not path.is_file():
        return detection_factory(
            adapter.name, source, candidate, False,
            error="Candidate is not a file.", rank=rank,
        )
    if os.name != "nt" and not os.access(path, os.X_OK):
        return detection_factory(
            adapter.name, source, candidate, False,
            error="Candidate is not executable.", rank=rank,
        )
    executable_path = resolved_path(str(path))
    child_env = child_environment(adapter, environment)
    try:
        with _version_arguments(adapter) as version_args:
            version_run = _run(
                executable_path,
                adapter.command_prefix(),
                version_args,
                timeout,
                child_env,
            )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return detection_factory(
            adapter.name, source, candidate, False, path=executable_path,
            error=f"Version detection failed: {type(exc).__name__}: {exc}", rank=rank,
        )
    version = adapter.parse_version(
        version_run.stdout, version_run.stderr, version_run.returncode
    )
    if version is None:
        return detection_factory(
            adapter.name,
            source,
            candidate,
            False,
            path=executable_path,
            error=(
                f"Version detection exited with code {version_run.returncode} "
                "or returned an unexpected identity."
            ),
            rank=rank,
            diagnostics={
                "version_stdout_tail": version_run.stdout[-2000:],
                "version_stderr_tail": version_run.stderr[-2000:],
            },
        )
    capabilities = adapter.default_capabilities()
    arguments = adapter.capability_arguments()
    if arguments is not None:
        try:
            capability_run = _run(
                executable_path,
                adapter.command_prefix(),
                arguments,
                timeout,
                child_env,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return detection_factory(
                adapter.name, source, candidate, False, path=executable_path,
                version=version,
                error=f"Capability detection failed: {type(exc).__name__}: {exc}",
                rank=rank,
            )
        capabilities = adapter.parse_capabilities(
            capability_run.stdout, capability_run.stderr, capability_run.returncode
        )
        if adapter.capability_detection_required() and not capabilities:
            return detection_factory(
                adapter.name,
                source,
                candidate,
                False,
                path=executable_path,
                version=version,
                error="Capability detection returned no recognized capabilities.",
                rank=rank,
                diagnostics={
                    "capability_exit_code": capability_run.returncode,
                    "capability_stdout_tail": capability_run.stdout[-2000:],
                    "capability_stderr_tail": capability_run.stderr[-2000:],
                },
            )
    return detection_factory(
        adapter.name,
        source,
        candidate,
        True,
        path=executable_path,
        version=version,
        capabilities=capabilities,
        rank=rank,
    )
