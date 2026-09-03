"""Atomic JSON, CSV, and run-stream export."""

from __future__ import annotations

import csv
import json
import math
import os
from pathlib import Path
from typing import Any

from mdhelper.core.analysis import AnalysisResult
from mdhelper.core.errors import BackendError
from mdhelper.services.provenance import unique_records
from mdhelper.services.run_streams import externalize_run_streams, remove_run_streams

from .paths import output_directory

EXPORT_SIGNIFICANT_DIGITS = 15


def export_result(
    result: AnalysisResult,
    destination: str | Path,
) -> list[Path]:
    """Export one validated result without rendering figures."""

    output = output_directory(destination)
    metadata = output / "result.json"
    value = result.to_dict()
    stream_paths: list[Path] = []
    provenance = value.get("provenance")
    if isinstance(provenance, dict):
        raw_runs = provenance.get("integration_runs")
        if raw_runs is not None:
            if not isinstance(raw_runs, list):
                raise BackendError("Integration runs must be an array before export.")
            records = [dict(record) for record in raw_runs if isinstance(record, dict)]
            if len(records) != len(raw_runs):
                raise BackendError("Integration runs must be objects before export.")
            if records:
                records = unique_records(records)
                stored, stream_paths = externalize_run_streams(records, output, "run")
                provenance["integration_runs"] = stored
    try:
        _atomic_json(metadata, value)
    except BaseException:
        remove_run_streams(stream_paths)
        raise
    return [metadata, *_export_csv(result, output), *stream_paths]


def _clean_number(value: float) -> float:
    if value == 0.0:
        return 0.0
    return float(f"{value:.{EXPORT_SIGNIFICANT_DIGITS}g}")


def _clean_json(value: Any) -> Any:
    if isinstance(value, float):
        return _clean_number(value)
    if isinstance(value, dict):
        return {key: _clean_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean_json(item) for item in value]
    return value


def _csv_value(value: Any) -> Any:
    if not isinstance(value, float):
        return value
    if not math.isfinite(value):
        return value
    if value == 0.0:
        return "0"
    return f"{value:.{EXPORT_SIGNIFICANT_DIGITS}g}"


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_text(
            json.dumps(_clean_json(value), indent=2, ensure_ascii=False, allow_nan=False)
            + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    except (OSError, ValueError) as exc:
        temporary.unlink(missing_ok=True)
        raise BackendError(
            f"Could not write JSON export: {path}",
            details={"exception": f"{type(exc).__name__}: {exc}"},
        ) from exc


def _atomic_csv(path: Path, header: list[str], rows: list[list[Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(header)
            writer.writerows([[_csv_value(value) for value in row] for row in rows])
        os.replace(temporary, path)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise BackendError(
            f"Could not write CSV export: {path}",
            details={"exception": f"{type(exc).__name__}: {exc}"},
        ) from exc


def _export_csv(result: AnalysisResult, output: Path) -> list[Path]:
    data = result.data
    paths: list[Path] = []
    if result.analysis_type == "rdf":
        path = output / "rdf.csv"
        _atomic_csv(
            path,
            ["radius_nm", "g_r"],
            [
                list(row)
                for row in zip(
                    data["radius_nm"],
                    data["g_r"],
                    strict=True,
                )
            ],
        )
        paths.append(path)
    elif result.analysis_type == "cumulative_rdf":
        path = output / "cn.csv"
        _atomic_csv(
            path,
            ["radius_nm", "cumulative_number"],
            [
                list(row)
                for row in zip(
                    data["radius_nm"],
                    data["cumulative_number"],
                    strict=True,
                )
            ],
        )
        paths.append(path)
    elif result.analysis_type == "energy":
        series = data.get("series")
        if not isinstance(series, dict) or not series:
            raise BackendError("Energy export requires at least one numeric series.")
        path = output / "energy.csv"
        labels = list(series)
        _atomic_csv(
            path,
            ["time_ps", *labels],
            [
                [time, *[series[label][row] for label in labels]]
                for row, time in enumerate(data["time_ps"])
            ],
        )
        paths.append(path)
    return paths
