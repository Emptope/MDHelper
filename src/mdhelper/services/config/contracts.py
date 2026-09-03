"""Configuration contracts shared by application and presentation code."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from mdhelper.core.analysis import AnalysisType
from mdhelper.core.integrations import IntegrationConfig

SCHEMA_VERSION = 1
ThemeMode = Literal["system", "light", "dark"]
THEME_MODES: tuple[ThemeMode, ...] = ("system", "light", "dark")


@dataclass
class GuiConfig:
    theme: ThemeMode = "system"
    font_size: float = 11.0


@dataclass
class UserConfig:
    schema_version: int = SCHEMA_VERSION
    gui: GuiConfig = field(default_factory=GuiConfig)
    integrations: dict[str, IntegrationConfig] = field(
        default_factory=lambda: {
            "gromacs": IntegrationConfig(),
            "vmd": IntegrationConfig(),
        }
    )
    workflows: dict[str, tuple[AnalysisType, ...]] = field(default_factory=dict)

    def integration(self, name: str) -> IntegrationConfig:
        return self.integrations.get(name.casefold(), IntegrationConfig())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "gui": asdict(self.gui),
            "integrations": {
                name: asdict(config) for name, config in sorted(self.integrations.items())
            },
            "workflows": {
                name: list(projects) for name, projects in sorted(self.workflows.items())
            },
        }
