"""Atomic result serialization and figure export."""

from __future__ import annotations

import csv
import json
import math
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from mdhelper.core.analysis import AnalysisResult
from mdhelper.core.errors import BackendError
from mdhelper.core.plotting import (
    DEFAULT_PLOT_SCHEME,
    DEFAULT_PLOT_SIZE,
    PlotLimits,
    PlotModel,
    PlotSize,
    draw_plot,
    results_plots,
)
from mdhelper.services.provenance import unique_records
from mdhelper.services.run_streams import (
    externalize_run_streams,
    remove_run_streams,
)

EXPORT_SIGNIFICANT_DIGITS = 15
_FIGURE_STYLE = {
    "font.family": "sans-serif",
    "font.size": 10.0,
    "axes.labelsize": 10.0,
    "axes.titlesize": 12.0,
    "xtick.labelsize": 9.0,
    "ytick.labelsize": 9.0,
    "savefig.facecolor": "white",
    "savefig.edgecolor": "white",
}


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


def _safe_stem(value: str) -> str:
    stem = "".join(
        character if character.isalnum() or character in "-_." else "_"
        for character in value
    )
    return stem.strip("._") or "analysis"


def _load_pyplot() -> Any:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise BackendError("Matplotlib is required for figure export.") from exc
    return plt


def _save_figure(figure: Any, output: Path, filename: str) -> list[Path]:
    paths: list[Path] = []
    temporary: Path | None = None
    try:
        for suffix in ("png", "svg", "pdf"):
            path = output / f"{filename}.{suffix}"
            temporary = path.with_name(f".{path.name}.tmp")
            figure.savefig(
                temporary,
                dpi=300 if suffix == "png" else None,
                format=suffix,
            )
            os.replace(temporary, path)
            paths.append(path)
    except OSError as exc:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise BackendError(
            f"Could not export analysis figure to {output}.",
            details={"exception": f"{type(exc).__name__}: {exc}"},
        ) from exc
    return paths


def _write_figures(
    results: Sequence[AnalysisResult],
    output: Path,
    stem: str | None = None,
    labels: Sequence[str | None] | None = None,
    color_ids: Sequence[int] | None = None,
    series_keys: Sequence[str | None] | None = None,
    group_ids: Sequence[str | None] | None = None,
    titles: Sequence[str | None] | None = None,
    scheme: str = DEFAULT_PLOT_SCHEME,
    limits: PlotLimits | None = None,
    size: PlotSize | None = None,
) -> list[Path]:
    plt = _load_pyplot()
    filename = _safe_stem(results[0].analysis_type if stem is None else stem)
    with plt.rc_context(_FIGURE_STYLE):
        models = results_plots(
            results,
            labels,
            color_ids,
            series_keys,
            group_ids,
            titles,
        )
        panel_size = DEFAULT_PLOT_SIZE if size is None else size
        panel_size.validate()
        figure = plt.figure(
            figsize=(panel_size.width, panel_size.height * len(models)),
            constrained_layout=True,
        )
        figure.set_facecolor("white")
        for index, model in enumerate(models, start=1):
            axis = figure.add_subplot(len(models), 1, index)
            axis.set_facecolor("white")
            draw_plot(axis, model, scheme, limits)
        try:
            return _save_figure(figure, output, filename)
        finally:
            plt.close(figure)


def _output_directory(path: str | Path) -> Path:
    output = Path(path).expanduser().resolve()
    try:
        output.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise BackendError(
            f"Could not create export directory: {output}",
            "Choose a writable directory and verify that no file occupies that path.",
            {"exception": f"{type(exc).__name__}: {exc}"},
        ) from exc
    return output


def export_figures(
    result: AnalysisResult,
    output_directory: str | Path,
    stem: str | None = None,
    scheme: str = DEFAULT_PLOT_SCHEME,
    limits: PlotLimits | None = None,
    size: PlotSize | None = None,
) -> list[Path]:
    """Export only plot files, optionally under a result-specific filename."""

    return _write_figures(
        (result,),
        _output_directory(output_directory),
        stem,
        scheme=scheme,
        limits=limits,
        size=size,
    )


def export_comparison_figures(
    results: Sequence[AnalysisResult],
    output_directory: str | Path,
    stem: str = "comparison",
    labels: Sequence[str | None] | None = None,
    color_ids: Sequence[int] | None = None,
    series_keys: Sequence[str | None] | None = None,
    group_ids: Sequence[str | None] | None = None,
    titles: Sequence[str | None] | None = None,
    scheme: str = DEFAULT_PLOT_SCHEME,
    limits: PlotLimits | None = None,
    size: PlotSize | None = None,
) -> list[Path]:
    """Export one figure containing multiple compatible results."""

    if not results:
        raise BackendError("At least one completed result is required for figure export.")
    return _write_figures(
        results,
        _output_directory(output_directory),
        stem,
        labels,
        color_ids,
        series_keys,
        group_ids,
        titles,
        scheme,
        limits,
        size,
    )


def export_plot_model(
    model: PlotModel,
    output_directory: str | Path,
    stem: str,
    scheme: str = DEFAULT_PLOT_SCHEME,
    limits: PlotLimits | None = None,
    size: PlotSize | None = None,
) -> list[Path]:
    """Export one prepared plot model without changing its grouping or labels."""

    plt = _load_pyplot()
    output = _output_directory(output_directory)
    panel_size = DEFAULT_PLOT_SIZE if size is None else size
    panel_size.validate()
    with plt.rc_context(_FIGURE_STYLE):
        figure = plt.figure(
            figsize=(panel_size.width, panel_size.height),
            constrained_layout=True,
        )
        figure.set_facecolor("white")
        axis = figure.add_subplot(1, 1, 1)
        axis.set_facecolor("white")
        draw_plot(axis, model, scheme, limits)
        try:
            return _save_figure(figure, output, _safe_stem(stem))
        finally:
            plt.close(figure)


def export_result(
    result: AnalysisResult,
    output_directory: str | Path,
    include_figures: bool = True,
    scheme: str = DEFAULT_PLOT_SCHEME,
    limits: PlotLimits | None = None,
    size: PlotSize | None = None,
) -> list[Path]:
    output = _output_directory(output_directory)
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
    paths = [metadata, *_export_csv(result, output), *stream_paths]
    if include_figures:
        paths.extend(
            _write_figures((result,), output, scheme=scheme, limits=limits, size=size)
        )
    return paths
