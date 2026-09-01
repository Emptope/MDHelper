"""Composable jsonargparse grammar for the CLI adapter."""

from .analysis import add_analysis_commands
from .config import add_config_commands
from .integrations import add_integration_commands
from .projects import add_project_commands
from .templates import add_template_commands

__all__ = [
    "add_analysis_commands",
    "add_config_commands",
    "add_integration_commands",
    "add_project_commands",
    "add_template_commands",
]
