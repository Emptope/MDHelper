from __future__ import annotations

import logging
import os
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

import mdhelper.io.export.figures as export_module
from mdhelper.core.analysis import AnalysisResult, EnergyRequest
from mdhelper.runtime.logging import LOGGER_NAME


def _close_log_handlers() -> None:
    logger = logging.getLogger(LOGGER_NAME)
    for handler in tuple(logger.handlers):
        logger.removeHandler(handler)
        handler.close()


@pytest.fixture(scope="session", autouse=True)
def _isolated_runtime_log(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    path = tmp_path_factory.mktemp("runtime-log") / "mdhelper.log"
    previous = os.environ.get("MDHELPER_LOG")
    _close_log_handlers()
    os.environ["MDHELPER_LOG"] = str(path)
    try:
        yield
    finally:
        _close_log_handlers()
        if previous is None:
            os.environ.pop("MDHELPER_LOG", None)
        else:
            os.environ["MDHELPER_LOG"] = previous


@pytest.fixture(autouse=True)
def _isolated_user_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MDHELPER_CONFIG", str(tmp_path / "config.toml"))


@pytest.fixture
def energy_result() -> AnalysisResult:
    request = EnergyRequest(
        analysis_type="energy",
        energy_file="energy.edr",
        energy_terms=("Potential", "Temperature", "Pressure"),
        analysis_backend="gromacs",
    )
    return AnalysisResult(
        data={
            "time_ps": [0.0, 1.0],
            "series": {
                "Potential": [-10.0, -9.0],
                "Temperature": [300.0, 301.0],
                "Pressure": [1.0, 1.5],
            },
        },
        parameters={},
        units={"time_ps": "ps", "series": "Value"},
        diagnostics={},
        provenance={},
        request=request.to_dict(),
        analysis_id="energy-id",
    )


@pytest.fixture
def stub_figure_exports(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[[], None]:
    def save(_figure: Any, output: Path, filename: str) -> list[Path]:
        paths = [output / f"{filename}.{suffix}" for suffix in ("png", "svg", "pdf")]
        for path in paths:
            path.touch()
        return paths

    def activate() -> None:
        monkeypatch.setattr(export_module, "_save_figure", save)

    return activate
