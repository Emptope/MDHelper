"""External run metadata and stream-log persistence."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from uuid import uuid4

from mdhelper.core.errors import ConfigurationError
from mdhelper.project.storage import atomic_text

_STREAMS = ("stdout", "stderr")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise ConfigurationError(
            f"Could not fingerprint project log: {path}",
            details={"exception": f"{type(exc).__name__}: {exc}"},
        ) from exc
    return digest.hexdigest()


class RunRepository:
    def __init__(self, root: Path):
        self.root = root
        self.directory = root / "results" / "logs"

    def store(
        self, records: Sequence[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[Path]]:
        stored: list[dict[str, Any]] = []
        created: list[Path] = []
        try:
            for source in records:
                record = dict(source)
                identifier = str(uuid4())
                for stream in _STREAMS:
                    content = record.pop(stream, None)
                    if not isinstance(content, str):
                        raise ConfigurationError(
                            f"Integration run field {stream!r} must be a string."
                        )
                    path = self.directory / f"{identifier}.{stream}.log"
                    if path.exists():
                        raise ConfigurationError(f"Project log already exists: {path}")
                    atomic_text(path, content)
                    created.append(path)
                    record[f"{stream}_path"] = path.relative_to(self.root).as_posix()
                    record[f"{stream}_sha256"] = _sha256(path)
                stored.append(record)
        except BaseException:
            self.remove(created)
            raise
        return stored, created

    def hydrate(self, records: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
        hydrated: list[dict[str, Any]] = []
        for source in records:
            record = dict(source)
            for stream in _STREAMS:
                path = self._verified_path(record, stream)
                record.pop(f"{stream}_sha256", None)
                record.pop(f"{stream}_path", None)
                try:
                    with path.open("r", encoding="utf-8", newline="") as handle:
                        record[stream] = handle.read()
                except (OSError, UnicodeError) as exc:
                    raise ConfigurationError(
                        f"Could not read project log: {path}",
                        details={"exception": f"{type(exc).__name__}: {exc}"},
                    ) from exc
            hydrated.append(record)
        return hydrated

    def verify(self, records: Sequence[dict[str, Any]]) -> None:
        for record in records:
            for stream in _STREAMS:
                self._verified_path(record, stream)

    @staticmethod
    def remove(paths: Sequence[Path]) -> None:
        for path in paths:
            path.unlink(missing_ok=True)

    def _path(self, record: dict[str, Any], stream: str) -> Path:
        value = record.get(f"{stream}_path")
        if not isinstance(value, str) or not value or Path(value).is_absolute():
            raise ConfigurationError(f"Project {stream} log path is invalid.")
        path = (self.root / value).resolve()
        directory = self.directory.resolve()
        try:
            path.relative_to(directory)
        except ValueError as exc:
            raise ConfigurationError(
                f"Project {stream} log path escapes the log directory: {value}"
            ) from exc
        if not path.is_file():
            raise ConfigurationError(
                f"Project log is missing: {path}",
                "Restore the committed log or rerun the integration.",
            )
        return path

    def _verified_path(self, record: dict[str, Any], stream: str) -> Path:
        path = self._path(record, stream)
        expected = record.get(f"{stream}_sha256")
        if not isinstance(expected, str) or _sha256(path) != expected:
            raise ConfigurationError(
                f"Project log fingerprint changed: {path}",
                "Restore the committed log or rerun the integration.",
            )
        return path
