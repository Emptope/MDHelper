"""Strict parsing of untrusted configuration values into contracts."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, cast

from mdhelper.core.analysis import ANALYSIS_LABELS, AnalysisType
from mdhelper.core.errors import ConfigurationError
from mdhelper.core.integrations import IntegrationConfig
from mdhelper.services.config.contracts import (
    SCHEMA_VERSION,
    THEME_MODES,
    GuiConfig,
    ThemeMode,
    UserConfig,
)


def _reject_unknown(
    table: dict[str, Any], allowed: set[str], field_name: str, path: Path
) -> None:
    unknown = sorted(set(table) - allowed)
    if unknown:
        field = f"{field_name}.{unknown[0]}" if field_name else unknown[0]
        raise ConfigurationError(
            f"Unknown configuration field {field!r}.",
            "Remove the field or regenerate the documented template with "
            "'mdhelper config init --force'.",
            {"path": str(path), "field": field, "unknown_fields": unknown},
        )


def _mapping(value: object, field_name: str, path: Path) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigurationError(
            f"Configuration field {field_name!r} must be a table.",
            details={"path": str(path), "field": field_name},
        )
    return value


def _bool(table: dict[str, Any], key: str, default: bool, path: Path) -> bool:
    value = table.get(key, default)
    if type(value) is not bool:
        raise ConfigurationError(
            f"Configuration field {key!r} must be true or false.",
            details={"path": str(path), "field": key, "value": value},
        )
    return value


def _positive_number(table: dict[str, Any], key: str, default: float, path: Path) -> float:
    value = table.get(key, default)
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ConfigurationError(
            f"Configuration field {key!r} must be a positive number.",
            details={"path": str(path), "field": key, "value": value},
        )
    return float(value)


def _theme(table: dict[str, Any], path: Path) -> ThemeMode:
    value = table.get("theme", GuiConfig().theme)
    if not isinstance(value, str) or value not in THEME_MODES:
        raise ConfigurationError(
            "Configuration field 'gui.theme' must be one of: system, light, dark.",
            details={"path": str(path), "field": "gui.theme", "value": value},
        )
    return cast(ThemeMode, value)


def _font_size(table: dict[str, Any], path: Path) -> float:
    value = table.get("font_size", GuiConfig().font_size)
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not 6.0 <= value <= 32.0
    ):
        raise ConfigurationError(
            "Configuration field 'gui.font_size' must be between 6 and 32 points.",
            details={"path": str(path), "field": "gui.font_size", "value": value},
        )
    return float(value)


def _integration(
    name: str, raw: object, path: Path
) -> IntegrationConfig:
    table = _mapping(raw, f"integrations.{name}", path)
    _reject_unknown(
        table,
        {
            "enabled",
            "path",
            "search_paths",
            "use_environment",
            "detect_timeout_seconds",
            "run_timeout_seconds",
        },
        f"integrations.{name}",
        path,
    )
    configured_path = table.get("path", "")
    if not isinstance(configured_path, str):
        raise ConfigurationError(
            f"Configuration field 'integrations.{name}.path' must be a string.",
            details={"path": str(path), "value": configured_path},
        )
    if configured_path and not configured_path.strip():
        raise ConfigurationError(
            f"Configuration field 'integrations.{name}.path' cannot contain only whitespace.",
            details={"path": str(path), "field": f"integrations.{name}.path"},
        )
    search_paths = table.get("search_paths", [])
    if not isinstance(search_paths, list) or any(
        not isinstance(item, str) or not item.strip() for item in search_paths
    ):
        raise ConfigurationError(
            f"Configuration field 'integrations.{name}.search_paths' must contain paths.",
            details={"path": str(path), "value": search_paths},
        )
    defaults = IntegrationConfig()
    return IntegrationConfig(
        enabled=_bool(table, "enabled", defaults.enabled, path),
        path=configured_path,
        search_paths=tuple(search_paths),
        use_environment=_bool(
            table, "use_environment", defaults.use_environment, path
        ),
        detect_timeout_seconds=_positive_number(
            table,
            "detect_timeout_seconds",
            defaults.detect_timeout_seconds,
            path,
        ),
        run_timeout_seconds=_positive_number(
            table, "run_timeout_seconds", defaults.run_timeout_seconds, path
        ),
    )


def _workflows(raw: object, path: Path) -> dict[str, tuple[AnalysisType, ...]]:
    table = _mapping(raw, "workflows", path)
    workflows: dict[str, tuple[AnalysisType, ...]] = {}
    for name, value in table.items():
        if not isinstance(name, str) or not name.strip() or name != name.strip():
            raise ConfigurationError(
                "Every workflow must have a non-empty name without surrounding whitespace.",
                details={"path": str(path), "name": name},
            )
        field = f"workflows.{name}"
        if not isinstance(value, list) or not value:
            raise ConfigurationError(
                f"Configuration field {field!r} must contain at least one analysis project.",
                details={"path": str(path), "field": field, "value": value},
            )
        if any(not isinstance(project, str) or project not in ANALYSIS_LABELS for project in value):
            raise ConfigurationError(
                f"Configuration field {field!r} must contain supported analysis project names.",
                "Choose from: " + ", ".join(ANALYSIS_LABELS),
                {"path": str(path), "field": field, "value": value},
            )
        workflows[name] = cast(tuple[AnalysisType, ...], tuple(value))
    return workflows


def parse_config(raw: dict[str, Any], path: Path) -> UserConfig:
    """Validate parsed TOML data without reading or writing the filesystem."""

    schema_version = raw.get("schema_version", SCHEMA_VERSION)
    if type(schema_version) is not int or schema_version != SCHEMA_VERSION:
        raise ConfigurationError(
            f"Unsupported configuration schema version: {schema_version}",
            f"This release supports schema_version = {SCHEMA_VERSION}.",
            {"path": str(path)},
        )
    _reject_unknown(
        raw,
        {"schema_version", "gui", "integrations", "workflows"},
        "",
        path,
    )
    gui = _mapping(raw.get("gui"), "gui", path)
    integrations = _mapping(raw.get("integrations"), "integrations", path)
    _reject_unknown(gui, {"theme", "font_size"}, "gui", path)

    default_integrations = UserConfig().integrations
    source_integrations = integrations or {
        name: {} for name in default_integrations
    }
    parsed_integrations: dict[str, IntegrationConfig] = {}
    for name, raw_integration in source_integrations.items():
        if not isinstance(name, str) or not name.strip():
            raise ConfigurationError(
                "Every entry under [integrations] must have a non-empty string name.",
                details={"path": str(path), "name": name},
            )
        parsed_integrations[name.casefold()] = _integration(name, raw_integration, path)

    return UserConfig(
        gui=GuiConfig(
            theme=_theme(gui, path),
            font_size=_font_size(gui, path),
        ),
        integrations=parsed_integrations,
        workflows=_workflows(raw.get("workflows"), path),
    )
