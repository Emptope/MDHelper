"""Shared validation for packaged application smoke tests."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

PLATFORMS = ("linux", "linux-gui", "windows")
REQUIRED_FILES = (
    "LICENSE",
    "README.md",
    "README.zh-CN.md",
    "config.example.toml",
    "config.toml",
)
REQUIRED_DIRECTORIES = ("docs", "licenses", "schemas")
REQUIRED_EXPORT_SUFFIXES = {".csv", ".json", ".pdf", ".png", ".svg"}


class SmokeFailure(ValueError):
    """Raised when a release candidate violates the smoke-test contract."""


def _files(directory: Path) -> list[Path]:
    return [path for path in directory.rglob("*") if path.is_file()]


def validate_distribution(root: Path, platform: str) -> Path:
    """Validate the external release layout and return its application path."""

    if platform not in PLATFORMS:
        raise SmokeFailure(f"unknown platform: {platform}")
    distribution = root.resolve()
    if not distribution.is_dir():
        raise SmokeFailure(f"distribution directory is missing: {distribution}")

    missing_files = [name for name in REQUIRED_FILES if not (distribution / name).is_file()]
    if missing_files:
        raise SmokeFailure(f"distribution files are missing: {missing_files}")
    for name in REQUIRED_DIRECTORIES:
        directory = distribution / name
        if not directory.is_dir() or not _files(directory):
            raise SmokeFailure(f"distribution directory is missing or empty: {name}")

    metadata = list((distribution / "licenses").glob("*.json"))
    if len(metadata) != 1:
        raise SmokeFailure(f"expected one license metadata file, found {len(metadata)}")
    if not list((distribution / "schemas").glob("*.json")):
        raise SmokeFailure("schemas does not contain a JSON contract")

    application = distribution / ("mdhelper.exe" if platform == "windows" else "mdhelper")
    if not application.is_file():
        raise SmokeFailure(f"packaged application is missing: {application}")
    if platform == "windows":
        executables = list(distribution.glob("*.exe"))
    else:
        executables = [
            path
            for path in distribution.iterdir()
            if path.is_file() and os.access(path, os.X_OK)
        ]
    if executables != [application]:
        names = sorted(path.name for path in executables)
        raise SmokeFailure(f"expected only the packaged application, found: {names}")
    return application


def validate_archive_root(extraction: Path, expected_name: str) -> Path:
    """Require an extracted archive to contain exactly its named root directory."""

    root = extraction.resolve()
    if not root.is_dir():
        raise SmokeFailure(f"archive extraction directory is missing: {root}")
    entries = list(root.iterdir())
    if len(entries) != 1 or not entries[0].is_dir():
        raise SmokeFailure("archive must contain exactly one root directory")
    expected = root / expected_name
    if entries[0] != expected:
        raise SmokeFailure(
            f"archive root is {entries[0].name!r}, expected {expected_name!r}"
        )
    return expected


def _report(value: str, label: str) -> dict[str, Any]:
    try:
        report = json.loads(value)
    except json.JSONDecodeError as exc:
        raise SmokeFailure(f"{label} report is not valid JSON") from exc
    if not isinstance(report, dict):
        raise SmokeFailure(f"{label} report must be a JSON object")
    return report


def validate_config(value: str, expected_path: Path) -> None:
    """Validate config loading and the selected portable config path in one report."""

    report = _report(value, "configuration")
    if report.get("status") != "valid" or report.get("exists") is not True:
        raise SmokeFailure("packaged configuration is not valid")
    raw_path = report.get("path")
    if not isinstance(raw_path, str):
        raise SmokeFailure("configuration report does not contain a path")
    if Path(raw_path).resolve() != expected_path.resolve():
        raise SmokeFailure(
            f"configuration path is {raw_path!r}, expected {str(expected_path)!r}"
        )


def _result_type(paths: list[Path]) -> str:
    for path in paths:
        if path.suffix.casefold() != ".json":
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(value, dict) or value.get("schema_version") != 1:
            continue
        analysis_type = value.get("analysis_type")
        request = value.get("request")
        if not isinstance(analysis_type, str) and isinstance(request, dict):
            analysis_type = request.get("analysis_type")
        if isinstance(analysis_type, str):
            return analysis_type
    raise SmokeFailure("reported exports do not contain a versioned analysis result")


def validate_analysis(output: Path, value: str) -> None:
    """Validate every reported analysis export without assuming an analysis-specific stem."""

    report = _report(value, "analysis")
    if report.get("status") != "completed":
        raise SmokeFailure("analysis did not report completed status")
    analysis_type = report.get("analysis_type")
    if not isinstance(analysis_type, str) or not analysis_type:
        raise SmokeFailure("analysis report does not contain an analysis type")
    exports = report.get("exports")
    if not isinstance(exports, list) or not exports or any(
        not isinstance(path, str) or not path for path in exports
    ):
        raise SmokeFailure("analysis report does not contain valid exports")

    root = output.resolve()
    paths = [Path(path).resolve() for path in exports]
    if len(paths) != len(set(paths)):
        raise SmokeFailure("analysis report contains duplicate exports")
    for path in paths:
        if not path.is_relative_to(root):
            raise SmokeFailure(f"reported export is outside the analysis output: {path}")
        if not path.is_file():
            raise SmokeFailure(f"missing export reported by the analysis: {path}")
        if path.stat().st_size == 0:
            raise SmokeFailure(f"reported export is empty: {path}")

    suffixes = {path.suffix.casefold() for path in paths}
    missing_suffixes = sorted(REQUIRED_EXPORT_SUFFIXES - suffixes)
    if missing_suffixes:
        raise SmokeFailure(f"analysis report is missing export formats: {missing_suffixes}")
    if _result_type(paths) != analysis_type:
        raise SmokeFailure("result analysis type does not match the analysis report")


def _read_report(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise SmokeFailure(f"could not read smoke report: {path}") from exc


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)

    distribution = commands.add_parser("distribution")
    distribution.add_argument("--root", type=Path, required=True)
    distribution.add_argument("--platform", choices=PLATFORMS, required=True)

    archive_root = commands.add_parser("archive-root")
    archive_root.add_argument("--root", type=Path, required=True)
    archive_root.add_argument("--expected-name", required=True)

    config = commands.add_parser("config")
    config.add_argument("--report", type=Path, required=True)
    config.add_argument("--expected-path", type=Path, required=True)

    analysis = commands.add_parser("analysis")
    analysis.add_argument("--output", type=Path, required=True)
    analysis.add_argument("--report", type=Path, required=True)

    args = parser.parse_args()
    try:
        if args.command == "distribution":
            print(validate_distribution(args.root, args.platform))
        elif args.command == "archive-root":
            print(validate_archive_root(args.root, args.expected_name))
        elif args.command == "config":
            validate_config(_read_report(args.report), args.expected_path)
        else:
            validate_analysis(args.output, _read_report(args.report))
    except SmokeFailure as exc:
        parser.exit(1, f"Smoke validation failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
