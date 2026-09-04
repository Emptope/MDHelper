"""Strict validation for versioned project manifests."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from mdhelper.core.errors import ConfigurationError, InputError
from mdhelper.core.plotting import PlotState
from mdhelper.core.species import validate_species_roles

PROJECT_SCHEMA_VERSION = 1
_PROJECT_FIELDS = {
    "schema_version", "mdhelper_version", "created_at", "inputs", "species_roles",
    "analyses", "plot",
}
_INPUT_FIELDS = {"path", "sha256"}
_ANALYSIS_FIELDS = {
    "analysis_id", "result_sha256", "committed_at",
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
    manifest["plot"] = PlotState.from_dict(manifest["plot"]).to_dict()
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
        _sha256(entry["result_sha256"], f"{field}.result_sha256")
        _date_time(entry["committed_at"], f"{field}.committed_at")
    return manifest
