"""Reproducibility metadata for analysis results."""

from __future__ import annotations

import importlib.metadata
import platform
import sys
from collections.abc import Callable
from pathlib import Path
from threading import Event
from typing import Any

from mdhelper.io.files import sha256_file
from mdhelper.version import __version__


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
    cancel_event: Event | None = None,
    progress: Callable[[int, int | None, str], None] | None = None,
    fingerprint_inputs: bool = True,
) -> dict[str, Any]:
    inputs = {"topology": topology, "trajectory": trajectory}
    inputs.update(additional_inputs or {})
    return input_provenance(
        inputs,
        configuration_sources,
        cancel_event,
        progress,
        fingerprint_inputs,
    )


def input_provenance(
    inputs: dict[str, Path],
    configuration_sources: dict[str, str] | None = None,
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
        "byte_order": sys.byteorder,
    }
    if fingerprint_inputs:
        provenance["input_sha256"] = fingerprints
    return provenance
