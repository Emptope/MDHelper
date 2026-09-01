"""Unified application facade shared by CLI, GUI, and task adapters."""

from __future__ import annotations

from pathlib import Path

from mdhelper.analysis import DEFAULT_ANALYSIS_REGISTRY
from mdhelper.app.analyses import AnalysisUseCases
from mdhelper.app.checks import CheckUseCases
from mdhelper.app.context import ApplicationContext, TrajectoryLoader, load_source
from mdhelper.app.integrations import IntegrationUseCases
from mdhelper.app.projects import ProjectUseCases
from mdhelper.app.templates import TemplateUseCases
from mdhelper.integrations import DEFAULT_INTEGRATION_REGISTRY, IntegrationRegistry
from mdhelper.integrations.manager import IntegrationManager
from mdhelper.plugins.analysis import AnalysisRegistry
from mdhelper.services.config import UserConfig, config_path, load_config


class ApplicationService:
    """Compose use-case groups without exposing infrastructure to presentations."""

    def __init__(
        self,
        user_config: UserConfig | None = None,
        user_config_path: str | Path | None = None,
        trajectory_loader: TrajectoryLoader | None = None,
        analysis_registry: AnalysisRegistry = DEFAULT_ANALYSIS_REGISTRY,
        integration_registry: IntegrationRegistry = DEFAULT_INTEGRATION_REGISTRY,
    ):
        config_file = (
            config_path()
            if user_config_path is None
            else Path(user_config_path).expanduser().resolve()
        )
        config = load_config(config_file) if user_config is None else user_config
        integrations = IntegrationManager(config.integrations, integration_registry)
        loader = (
            trajectory_loader
            if trajectory_loader is not None
            else lambda topology, trajectory, backend, cancel_event, progress: load_source(
                topology, trajectory, backend, integrations, cancel_event, progress
            )
        )
        self.context = ApplicationContext(
            config_file,
            config,
            loader,
            analysis_registry,
            integrations,
        )
        self.checks = CheckUseCases(self.context)
        self.analyses = AnalysisUseCases(self.context)
        self.projects = ProjectUseCases()
        self.integrations = IntegrationUseCases(self.context)
        self.templates = TemplateUseCases()

    @property
    def config_file(self) -> Path:
        return self.context.config_file

    @property
    def config(self) -> UserConfig:
        return self.context.config
