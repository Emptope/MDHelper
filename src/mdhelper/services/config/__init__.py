"""Editable, versioned configuration service shared by every frontend."""

from mdhelper.services.config.contracts import (
    SCHEMA_VERSION,
    THEME_MODES,
    GuiConfig,
    ResourceConfig,
    ThemeMode,
    UserConfig,
)
from mdhelper.services.config.parsing import parse_config
from mdhelper.services.config.storage import (
    DEFAULT_CONFIG_TEMPLATE,
    config_path,
    initialize_config,
    load_config,
    save_config,
)

__all__ = [
    "DEFAULT_CONFIG_TEMPLATE",
    "SCHEMA_VERSION",
    "THEME_MODES",
    "GuiConfig",
    "ResourceConfig",
    "ThemeMode",
    "UserConfig",
    "config_path",
    "initialize_config",
    "load_config",
    "parse_config",
    "save_config",
]
