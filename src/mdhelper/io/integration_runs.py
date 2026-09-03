"""Deterministic external storage for integration run streams."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from mdhelper.core.errors import ConfigurationError

_STREAMS = (("stdout", "out"), ("stderr", "err"))


def _path(directory: Path, stem: str, index: int, extension: str) -> Path:
    if not stem or Path(stem).name != stem or "/" in stem or "\\" in stem:
        raise ConfigurationError("Integration stream file stem is invalid.")
    suffix = "" if index == 0 else f"-{index + 1}"
    return directory / f"{stem}{suffix}.{extension}"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise ConfigurationError(
            f"Could not fingerprint integration stream: {path}",
            details={"exception": f"{type(exc).__name__}: {exc}"},
        ) from exc
    return digest.hexdigest()


def _atomic_text(path: Path, content: str) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(content, encoding="utf-8", newline="")
        os.replace(temporary, path)
    except (OSError, UnicodeError) as exc:
        temporary.unlink(missing_ok=True)
        raise ConfigurationError(
            f"Could not write integration stream: {path}",
            details={"exception": f"{type(exc).__name__}: {exc}"},
        ) from exc


def externalize_run_streams(
    records: Sequence[dict[str, Any]],
    directory: Path,
    stem: str,
) -> tuple[list[dict[str, Any]], list[Path]]:
    stored: list[dict[str, Any]] = []
    created: list[Path] = []
    try:
        for index, source in enumerate(records):
            record = dict(source)
            for stream, extension in _STREAMS:
                content = record.pop(stream, None)
                if not isinstance(content, str):
                    raise ConfigurationError(
                        f"Integration run field {stream!r} must be a string."
                    )
                path = _path(directory, stem, index, extension)
                if path.exists():
                    raise ConfigurationError(f"Integration stream already exists: {path}")
                _atomic_text(path, content)
                created.append(path)
                record[f"{stream}_sha256"] = _sha256(path)
            stored.append(record)
    except BaseException:
        remove_run_streams(created)
        raise
    return stored, created


def hydrate_run_streams(
    records: Sequence[dict[str, Any]],
    directory: Path,
    stem: str,
) -> list[dict[str, Any]]:
    hydrated: list[dict[str, Any]] = []
    for index, source in enumerate(records):
        record = dict(source)
        for stream, extension in _STREAMS:
            path = _path(directory, stem, index, extension)
            expected = record.pop(f"{stream}_sha256", None)
            if not path.is_file():
                raise ConfigurationError(
                    f"Integration stream is missing: {path}",
                    "Restore the committed stream or rerun the integration.",
                )
            if not isinstance(expected, str) or _sha256(path) != expected:
                raise ConfigurationError(
                    f"Integration stream fingerprint changed: {path}",
                    "Restore the committed stream or rerun the integration.",
                )
            try:
                record[stream] = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                raise ConfigurationError(
                    f"Could not read integration stream: {path}",
                    details={"exception": f"{type(exc).__name__}: {exc}"},
                ) from exc
        hydrated.append(record)
    return hydrated


def remove_run_streams(paths: Sequence[Path]) -> None:
    for path in paths:
        path.unlink(missing_ok=True)
