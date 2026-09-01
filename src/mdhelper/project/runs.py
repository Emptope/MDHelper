"""Project persistence and validation for external integration runs."""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from mdhelper.core.errors import ConfigurationError
from mdhelper.project.storage import atomic_json
from mdhelper.services.run_streams import (
    externalize_run_streams,
    hydrate_run_streams,
    remove_run_streams,
)

_COMMON_FIELDS = {
    "name",
    "display_name",
    "path",
    "version",
    "command",
    "arguments",
    "working_directory",
    "environment_summary",
    "exit_code",
    "started_at",
    "output_fingerprints",
    "elapsed_seconds",
    "status",
}
_SOURCE_FIELDS = _COMMON_FIELDS | {"stdout", "stderr"}
_STORED_FIELDS = _COMMON_FIELDS | {"stdout_sha256", "stderr_sha256"}


def _sha256(value: object, field: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ConfigurationError(f"Integration run field {field!r} is not a SHA-256 digest.")


def validate_run(record: object, stored: bool) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise ConfigurationError("An integration run must be an object.")
    expected = _STORED_FIELDS if stored else _SOURCE_FIELDS
    if set(record) != expected:
        raise ConfigurationError(
            "An integration run contains missing or unknown fields.",
            details={
                "missing_fields": sorted(expected - set(record)),
                "unknown_fields": sorted(set(record) - expected),
            },
        )
    for name in (
        "name",
        "display_name",
        "path",
        "version",
        "command",
        "working_directory",
    ):
        if not isinstance(record[name], str) or not record[name]:
            raise ConfigurationError(f"Integration run field {name!r} must be a string.")
    if not isinstance(record["arguments"], list) or any(
        not isinstance(item, str) for item in record["arguments"]
    ):
        raise ConfigurationError("Integration run arguments must contain strings.")
    environment = record["environment_summary"]
    if not isinstance(environment, dict) or any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in environment.items()
    ):
        raise ConfigurationError("Integration run environment must map strings to strings.")
    if type(record["exit_code"]) is not int:
        raise ConfigurationError("Integration run exit_code must be an integer.")
    started_at = record["started_at"]
    if not isinstance(started_at, str):
        raise ConfigurationError("Integration run started_at must be a date-time string.")
    try:
        parsed = datetime.fromisoformat(started_at)
    except ValueError as exc:
        raise ConfigurationError("Integration run started_at is invalid.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ConfigurationError("Integration run started_at must include a time zone.")
    fingerprints = record["output_fingerprints"]
    if not isinstance(fingerprints, dict):
        raise ConfigurationError("Integration run output_fingerprints must be an object.")
    for path, digest in fingerprints.items():
        if not isinstance(path, str) or not path:
            raise ConfigurationError("Integration output path must be a string.")
        _sha256(digest, f"output_fingerprints.{path}")
    elapsed = record["elapsed_seconds"]
    if (
        isinstance(elapsed, bool)
        or not isinstance(elapsed, (int, float))
        or not math.isfinite(elapsed)
        or elapsed < 0
    ):
        raise ConfigurationError("Integration run elapsed_seconds is invalid.")
    if record["status"] not in {"completed", "failed", "cancelled", "timed_out"}:
        raise ConfigurationError("Integration run status is invalid.")
    for stream in ("stdout", "stderr"):
        if stored:
            _sha256(record[f"{stream}_sha256"], f"{stream}_sha256")
        elif not isinstance(record[stream], str):
            raise ConfigurationError(f"Integration run field {stream!r} must be a string.")
    return record


class RunRepository:
    def __init__(self, root: Path):
        self.data_directory = root / "results" / "data"
        self.run_directory = root / "results" / "runs"

    def store(
        self,
        records: Sequence[dict[str, Any]],
        stem: str,
    ) -> tuple[list[dict[str, Any]], list[Path]]:
        sources = [validate_run(dict(record), stored=False) for record in records]
        stored, paths = externalize_run_streams(sources, self.data_directory, stem)
        return [validate_run(record, stored=True) for record in stored], paths

    def hydrate(
        self,
        records: Sequence[dict[str, Any]],
        stem: str,
    ) -> list[dict[str, Any]]:
        stored = [validate_run(dict(record), stored=True) for record in records]
        hydrated = hydrate_run_streams(stored, self.data_directory, stem)
        return [validate_run(record, stored=False) for record in hydrated]

    def record(self, source: dict[str, Any]) -> Path:
        record = validate_run(dict(source), stored=False)
        identifier = str(uuid4())
        stored, streams = externalize_run_streams((record,), self.run_directory, identifier)
        path = self.run_directory / f"{identifier}.json"
        try:
            value = validate_run(stored[0], stored=True)
            atomic_json(path, value)
        except BaseException:
            remove_run_streams(streams)
            path.unlink(missing_ok=True)
            raise
        return path

    def verify_archive(self) -> None:
        try:
            paths = tuple(self.run_directory.glob("*.json"))
        except OSError as exc:
            raise ConfigurationError("Could not inspect project integration runs.") from exc
        for path in paths:
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
                record = validate_run(value, stored=True)
                hydrate_run_streams((record,), self.run_directory, path.stem)
            except ConfigurationError:
                raise
            except (OSError, json.JSONDecodeError) as exc:
                raise ConfigurationError(f"Could not load integration run: {path}") from exc

    @staticmethod
    def remove(paths: Sequence[Path]) -> None:
        remove_run_streams(paths)
