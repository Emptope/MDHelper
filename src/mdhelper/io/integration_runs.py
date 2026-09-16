"""Deterministic storage for integration streams and original text outputs."""

from __future__ import annotations

import os
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from mdhelper.core.errors import ConfigurationError, InputFileError
from mdhelper.io.files import sha256_file

_STREAMS = (("stdout", "out"), ("stderr", "err"))


def validate_output_texts(value: object) -> dict[str, str]:
    """Validate portable output names and text contents or digests."""

    if not isinstance(value, dict):
        raise ConfigurationError("Integration text outputs must be an object.")
    for name, content in value.items():
        if (
            not isinstance(name, str)
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", name) is None
            or name.endswith(".")
            or not isinstance(content, str)
        ):
            raise ConfigurationError("Integration text output name or content is invalid.")
    return value


def _read_text(path: Path) -> str:
    try:
        return path.read_bytes().decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise ConfigurationError(
            f"Could not read integration output: {path}",
            details={"exception": f"{type(exc).__name__}: {exc}"},
        ) from exc


def read_output_texts(paths: Sequence[str | Path]) -> dict[str, str]:
    """Capture selected text outputs before their working directory is removed."""

    outputs: dict[str, str] = {}
    for item in paths:
        path = Path(item)
        if path.name in outputs:
            raise ConfigurationError(f"Duplicate integration output name: {path.name}")
        outputs[path.name] = _read_text(path)
    return validate_output_texts(outputs)


def _path(directory: Path, stem: str, index: int, extension: str) -> Path:
    if not stem or Path(stem).name != stem or "/" in stem or "\\" in stem:
        raise ConfigurationError("Integration stream file stem is invalid.")
    suffix = "" if index == 0 else f"-{index + 1}"
    return directory / f"{stem}{suffix}.{extension}"


def _sha256(path: Path) -> str:
    try:
        return sha256_file(path)
    except InputFileError as exc:
        raise ConfigurationError(
            f"Could not fingerprint integration stream: {path}",
            details=exc.details,
        ) from exc


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


def _output_paths(
    records: Sequence[dict[str, Any]], directory: Path, stem: str, field: str,
    original_names: bool, reserved_names: Sequence[str],
) -> list[dict[str, Path]]:
    used = {name.casefold() for name in reserved_names}
    used.update(
        _path(directory, stem, index, extension).name.casefold()
        for index in range(len(records)) for _, extension in _STREAMS
    )
    paths = []
    for index, record in enumerate(records):
        outputs = {}
        for name in validate_output_texts(record.get(field, {})):
            if original_names:
                source = Path(name)
                candidate = name
                suffix = 2
                while candidate.casefold() in used:
                    candidate = f"{source.stem}-{suffix}{source.suffix}"
                    suffix += 1
                used.add(candidate.casefold())
                outputs[name] = directory / candidate
            else:
                outputs[name] = _path(directory, stem, index, f"data-{name}")
        paths.append(outputs)
    return paths


def externalize_run_streams(
    records: Sequence[dict[str, Any]],
    directory: Path,
    stem: str,
    *,
    original_names: bool = False,
    reserved_names: Sequence[str] = (),
) -> tuple[list[dict[str, Any]], list[Path]]:
    output_paths = _output_paths(
        records, directory, stem, "output_texts", original_names, reserved_names
    )
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
            if "output_texts" in record:
                outputs = record.pop("output_texts")
                digests = {}
                for name, content in validate_output_texts(outputs).items():
                    path = output_paths[index][name]
                    if path.exists():
                        raise ConfigurationError(f"Integration output already exists: {path}")
                    _atomic_text(path, content)
                    created.append(path)
                    digests[name] = _sha256(path)
                record["output_texts_sha256"] = digests
            stored.append(record)
    except BaseException:
        remove_run_streams(created)
        raise
    return stored, created


def hydrate_run_streams(
    records: Sequence[dict[str, Any]],
    directory: Path,
    stem: str,
    *,
    original_names: bool = False,
    reserved_names: Sequence[str] = (),
) -> list[dict[str, Any]]:
    output_paths = _output_paths(
        records, directory, stem, "output_texts_sha256", original_names, reserved_names
    )
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
            record[stream] = _read_text(path)
        if "output_texts_sha256" in record:
            digests = record.pop("output_texts_sha256")
            outputs = {}
            for name, expected in validate_output_texts(digests).items():
                path = output_paths[index][name]
                if not path.is_file() or _sha256(path) != expected:
                    raise ConfigurationError(
                        f"Integration output is missing or its fingerprint changed: {path}"
                    )
                outputs[name] = _read_text(path)
            record["output_texts"] = outputs
        hydrated.append(record)
    return hydrated


def remove_run_streams(paths: Sequence[Path]) -> None:
    for path in paths:
        path.unlink(missing_ok=True)
