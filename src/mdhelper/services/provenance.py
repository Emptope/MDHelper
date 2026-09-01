"""Reproducibility records and cancellable content fingerprints."""

from __future__ import annotations

import hashlib
import importlib.metadata
import platform
import sys
from collections.abc import Callable
from pathlib import Path
from threading import Event
from typing import Any

from mdhelper.core.errors import InputFileError, TaskCancelled
from mdhelper.version import __version__


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
            raise TaskCancelled("Input fingerprinting was cancelled.")
        total = target.stat().st_size
        with target.open("rb") as handle:
            for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
                if cancel_event is not None and cancel_event.is_set():
                    raise TaskCancelled("Input fingerprinting was cancelled.")
                digest.update(chunk)
                processed += len(chunk)
                if progress:
                    progress(processed, total, f"Fingerprinting {target.name}")
    except TaskCancelled:
        raise
    except OSError as exc:
        raise InputFileError(
            f"Could not fingerprint input file: {target}",
            details={"exception": f"{type(exc).__name__}: {exc}"},
        ) from exc
    return digest.hexdigest()


def dependency_versions() -> dict[str, str]:
    result: dict[str, str] = {}
    for distribution in ("MDAnalysis", "pyedr", "numpy", "scipy", "matplotlib"):
        try:
            result[distribution] = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            result[distribution] = "not-installed"
    return result


def analysis_provenance(
    topology: Path,
    trajectory: Path,
    configuration_sources: dict[str, str] | None = None,
    additional_inputs: dict[str, Path] | None = None,
    species_roles: dict[str, str] | None = None,
    parameter_provenance: dict[str, Any] | None = None,
    cancel_event: Event | None = None,
    progress: Callable[[int, int | None, str], None] | None = None,
    fingerprint_inputs: bool = True,
) -> dict[str, Any]:
    inputs = {"topology": topology, "trajectory": trajectory}
    inputs.update(additional_inputs or {})
    return input_provenance(
        inputs,
        configuration_sources,
        species_roles,
        parameter_provenance,
        cancel_event,
        progress,
        fingerprint_inputs,
    )


def input_provenance(
    inputs: dict[str, Path],
    configuration_sources: dict[str, str] | None = None,
    species_roles: dict[str, str] | None = None,
    parameter_provenance: dict[str, Any] | None = None,
    cancel_event: Event | None = None,
    progress: Callable[[int, int | None, str], None] | None = None,
    fingerprint_inputs: bool = True,
) -> dict[str, Any]:
    input_files: dict[str, str] = {}
    fingerprints: dict[str, str] = {}
    for role, path in inputs.items():
        resolved = path.expanduser().resolve()
        value = str(resolved)
        input_files[role] = value
        if fingerprint_inputs and value not in fingerprints:
            fingerprints[value] = sha256_file(resolved, cancel_event, progress)
    provenance = {
        "mdhelper_version": __version__,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "backend_versions": dependency_versions(),
        "input_files": input_files,
        "configuration_sources": configuration_sources or {},
        "species_mapping": {
            "status": "confirmed" if species_roles else "not_provided",
            "roles": dict(sorted((species_roles or {}).items())),
        },
        "parameter_decisions": parameter_provenance or {},
        "byte_order": sys.byteorder,
    }
    if fingerprint_inputs:
        provenance["input_sha256"] = fingerprints
    return provenance
