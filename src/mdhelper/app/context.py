"""Application dependency composition shared by all features."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from threading import Event

from mdhelper.analysis.pipeline import AnalysisRegistry
from mdhelper.core.progress import ProgressCallback
from mdhelper.core.trajectory import TrajectorySource
from mdhelper.integrations.manager import IntegrationManager
from mdhelper.services.config import UserConfig
from mdhelper.services.system import load_source

TrajectoryLoader = Callable[
    [str, str, str, Event | None, ProgressCallback | None],
    TrajectorySource,
]


@dataclass(frozen=True)
class ApplicationContext:
    config_file: Path
    config: UserConfig
    trajectory_loader: TrajectoryLoader
    analysis_registry: AnalysisRegistry
    integrations: IntegrationManager


__all__ = ["ApplicationContext", "TrajectoryLoader", "load_source"]
