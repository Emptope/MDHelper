"""Strict validation for versioned project manifests."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from mdhelper.core.errors import ConfigurationError, InputError
from mdhelper.core.plotting import PlotState
from mdhelper.core.species import validate_species_roles

PROJECT_SCHEMA_VERSION = 1
_PROJECT_FIELDS = {
    "schema_version", "mdhelper_version", "created_at", "inputs", "species_roles",
    "integration_preferences", "integration_runs", "analyses", "plot",
}
_INPUT_FIELDS = {"path", "sha256"}
_ANALYSIS_FIELDS = {
    "analysis_id", "analysis_type", "result_sha256", "committed_at",
}
_RUN_FIELDS = {
    "name", "display_name", "path", "version", "command", "arguments", "working_directory",
    "environment_summary", "exit_code", "stdout_path", "stdout_sha256", "stderr_path",
    "stderr_sha256", "started_at", "output_fingerprints", "elapsed_seconds", "status",
}


def _object(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigurationError(
            f"Project field {field!r} must be an object.", details={"field": field}
        )
    return value


def _array(value: object, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise ConfigurationError(
            f"Project field {field!r} must be an array.", details={"field": field}
        )
    return value


def _fields(
    value: dict[str, Any], required: set[str], allowed: set[str], field: str
) -> None:
    missing = sorted(required - set(value))
    unknown = sorted(set(value) - allowed)
    if missing:
        raise ConfigurationError(
            f"Project field {field!r} is missing required members.",
            details={"field": field, "missing_fields": missing},
        )
    if unknown:
        raise ConfigurationError(
            f"Project field {field!r} contains unknown members.",
            details={"field": field, "unknown_fields": unknown},
        )


def _string(value: object, field: str) -> None:
    if not isinstance(value, str) or not value:
        raise ConfigurationError(
            f"Project field {field!r} must be a non-empty string.",
            details={"field": field},
        )


def _date_time(value: object, field: str) -> None:
    _string(value, field)
    assert isinstance(value, str)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ConfigurationError(
            f"Project field {field!r} must be an ISO 8601 date-time.",
            details={"field": field, "value": value},
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ConfigurationError(
            f"Project field {field!r} must include a time-zone offset.",
            details={"field": field, "value": value},
        )


def _sha256(value: object, field: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ConfigurationError(
            f"Project field {field!r} must be a lowercase SHA-256 digest.",
            details={"field": field, "value": value},
        )


def _roles(value: object, field: str) -> None:
    roles = _object(value, field)
    try:
        validate_species_roles(roles)
    except InputError as exc:
        raise ConfigurationError(
            "The project contains an invalid species-role mapping.",
            str(exc),
            {"field": field},
        ) from exc


def _integration_preferences(value: object) -> None:
    for name, raw in _object(value, "integration_preferences").items():
        _string(name, "integration_preferences name")
        field = f"integration_preferences.{name}"
        preference = _object(raw, field)
        expected = {"preferred", "required_capabilities"}
        _fields(preference, expected, expected, field)
        if type(preference["preferred"]) is not bool:
            raise ConfigurationError(
                f"Project field {field + '.preferred'!r} must be true or false."
            )
        capabilities = _array(
            preference["required_capabilities"], f"{field}.required_capabilities"
        )
        if any(not isinstance(item, str) or not item.strip() for item in capabilities):
            raise ConfigurationError(
                f"Project field {field + '.required_capabilities'!r} must contain "
                "non-empty strings."
            )
        if len(set(capabilities)) != len(capabilities):
            raise ConfigurationError(
                f"Project field {field + '.required_capabilities'!r} contains duplicates."
            )


def _integration_run(value: object, field: str) -> None:
    record = _object(value, field)
    _fields(record, _RUN_FIELDS, _RUN_FIELDS, field)
    for name in (
        "name", "display_name", "path", "version", "command", "working_directory"
    ):
        _string(record[name], f"{field}.{name}")
    for stream in ("stdout", "stderr"):
        path_field = f"{field}.{stream}_path"
        path = record[f"{stream}_path"]
        _string(path, path_field)
        assert isinstance(path, str)
        name = path.removeprefix("results/logs/")
        if (
            name == path
            or not name
            or "/" in name
            or "\\" in name
            or not name.endswith(f".{stream}.log")
        ):
            raise ConfigurationError(
                f"Project field {path_field!r} must name a dedicated project log."
            )
        _sha256(record[f"{stream}_sha256"], f"{field}.{stream}_sha256")
    if any(not isinstance(item, str) for item in _array(record["arguments"], f"{field}.arguments")):
        raise ConfigurationError(f"Project field {field + '.arguments'!r} must contain strings.")
    environment = _object(record["environment_summary"], f"{field}.environment_summary")
    if any(
        not isinstance(key, str) or not isinstance(item, str)
        for key, item in environment.items()
    ):
        raise ConfigurationError(
            f"Project field {field + '.environment_summary'!r} must map strings to strings."
        )
    if type(record["exit_code"]) is not int:
        raise ConfigurationError(f"Project field {field + '.exit_code'!r} must be an integer.")
    _date_time(record["started_at"], f"{field}.started_at")
    for path, digest in _object(
        record["output_fingerprints"], f"{field}.output_fingerprints"
    ).items():
        _string(path, f"{field}.output_fingerprints path")
        _sha256(digest, f"{field}.output_fingerprints.{path}")
    elapsed = record["elapsed_seconds"]
    if (
        isinstance(elapsed, bool)
        or not isinstance(elapsed, (int, float))
        or not math.isfinite(elapsed)
        or elapsed < 0
    ):
        raise ConfigurationError(
            f"Project field {field + '.elapsed_seconds'!r} must be a finite non-negative number."
        )
    if record["status"] not in {"completed", "failed", "cancelled", "timed_out"}:
        raise ConfigurationError(f"Project field {field + '.status'!r} is invalid.")


def validate_manifest(value: object) -> dict[str, Any]:
    """Validate a project manifest without third-party schema objects."""

    manifest = _object(value, "project")
    _fields(manifest, _PROJECT_FIELDS, _PROJECT_FIELDS, "project")
    version = manifest["schema_version"]
    if type(version) is not int or version != PROJECT_SCHEMA_VERSION:
        raise ConfigurationError(
            f"Unsupported project schema version: {version}",
            f"This release supports schema version {PROJECT_SCHEMA_VERSION}.",
        )
    _string(manifest["mdhelper_version"], "mdhelper_version")
    _date_time(manifest["created_at"], "created_at")
    inputs = _object(manifest["inputs"], "inputs")
    _fields(
        inputs,
        {"topology", "trajectory"},
        {"topology", "trajectory", "index", "energy"},
        "inputs",
    )
    for role, raw in inputs.items():
        field = f"inputs.{role}"
        record = _object(raw, field)
        _fields(record, _INPUT_FIELDS, _INPUT_FIELDS, field)
        _string(record["path"], f"{field}.path")
        _sha256(record["sha256"], f"{field}.sha256")
    _roles(manifest["species_roles"], "species_roles")
    _integration_preferences(manifest["integration_preferences"])
    manifest["plot"] = PlotState.from_dict(manifest["plot"]).to_dict()
    for index, record in enumerate(
        _array(manifest["integration_runs"], "integration_runs")
    ):
        _integration_run(record, f"integration_runs[{index}]")

    identifiers: set[str] = set()
    for index, raw in enumerate(_array(manifest["analyses"], "analyses")):
        field = f"analyses[{index}]"
        entry = _object(raw, field)
        _fields(entry, _ANALYSIS_FIELDS, _ANALYSIS_FIELDS, field)
        _string(entry["analysis_id"], f"{field}.analysis_id")
        if entry["analysis_id"] in identifiers:
            raise ConfigurationError(
                f"Project field {field + '.analysis_id'!r} is duplicated."
            )
        identifiers.add(entry["analysis_id"])
        if entry["analysis_type"] not in {"rdf", "cumulative_rdf", "energy"}:
            raise ConfigurationError(f"Project field {field + '.analysis_type'!r} is invalid.")
        _sha256(entry["result_sha256"], f"{field}.result_sha256")
        _date_time(entry["committed_at"], f"{field}.committed_at")
    return manifest
