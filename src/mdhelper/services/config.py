"""Editable, versioned configuration service shared by every frontend."""

from __future__ import annotations

import math
import os
import sys
import tomllib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal, cast

import tomli_w

from mdhelper.core.errors import ConfigurationError
from mdhelper.integrations.models import IntegrationConfig

SCHEMA_VERSION = 1
ThemeMode = Literal["system", "light", "dark"]
THEME_MODES: tuple[ThemeMode, ...] = ("system", "light", "dark")


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


@dataclass
class ResourceConfig:
    max_pairs_per_chunk: int = 500_000


@dataclass
class GuiConfig:
    theme: ThemeMode = "system"
    font_size: float = 11.0


@dataclass
class UserConfig:
    schema_version: int = SCHEMA_VERSION
    gui: GuiConfig = field(default_factory=GuiConfig)
    resources: ResourceConfig = field(default_factory=ResourceConfig)
    integrations: dict[str, IntegrationConfig] = field(
        default_factory=lambda: {
            "gromacs": IntegrationConfig(),
            "vmd": IntegrationConfig(),
        }
    )

    def integration(self, name: str) -> IntegrationConfig:
        return self.integrations.get(name.casefold(), IntegrationConfig())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "gui": asdict(self.gui),
            "resources": asdict(self.resources),
            "integrations": {
                name: asdict(config) for name, config in sorted(self.integrations.items())
            },
        }


DEFAULT_CONFIG_TEMPLATE = """# MDHelper user configuration
# Schema documentation: docs/CONFIGURATION.md
schema_version = 1

[gui]
# "system" follows the operating system; "light" and "dark" are explicit overrides.
theme = "system"
# GUI font size in points (6-32).
font_size = 11.0

[resources]
# Bounds temporary pair arrays; increase only after profiling.
max_pairs_per_chunk = 500000

[integrations.gromacs]
enabled = true
# Full executable path, for example C:/Program Files/GROMACS/bin/gmx.exe
# Leave empty to use environment variables, PATH, and known candidate paths.
path = ""
search_paths = []
use_environment = true
detect_timeout_seconds = 10.0
run_timeout_seconds = 3600.0

[integrations.vmd]
enabled = true
path = ""
search_paths = []
use_environment = true
detect_timeout_seconds = 10.0
run_timeout_seconds = 3600.0
"""


def config_path(
    environment: dict[str, str] | None = None,
    executable: str | Path | None = None,
) -> Path:
    env = os.environ if environment is None else environment
    explicit = env.get("MDHELPER_CONFIG")
    if explicit:
        return Path(explicit).expanduser()
    program = Path(sys.executable if executable is None else executable).resolve()
    return program.parent / "config.toml"


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
    value = table.get("theme", "system")
    if not isinstance(value, str) or value not in THEME_MODES:
        raise ConfigurationError(
            "Configuration field 'gui.theme' must be one of: system, light, dark.",
            details={"path": str(path), "field": "gui.theme", "value": value},
        )
    return cast(ThemeMode, value)


def _font_size(table: dict[str, Any], path: Path) -> float:
    value = table.get("font_size", 11.0)
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


def load_config(path: Path | None = None) -> UserConfig:
    target = config_path() if path is None else Path(path)
    if not target.exists():
        return UserConfig()
    if not target.is_file():
        raise ConfigurationError(
            f"Configuration path is not a file: {target}",
            "Run 'mdhelper config path' to inspect the active path.",
        )
    try:
        with target.open("rb") as handle:
            raw = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigurationError(
            f"Could not read configuration: {target}",
            "Fix the TOML syntax or regenerate a template with 'mdhelper config init --force'.",
            {"exception": f"{type(exc).__name__}: {exc}"},
        ) from exc
    schema_version = raw.get("schema_version", SCHEMA_VERSION)
    if type(schema_version) is not int or schema_version != SCHEMA_VERSION:
        raise ConfigurationError(
            f"Unsupported configuration schema version: {schema_version}",
            f"This release supports schema_version = {SCHEMA_VERSION}.",
            {"path": str(target)},
        )
    _reject_unknown(
        raw, {"schema_version", "gui", "resources", "integrations"}, "", target
    )
    gui = _mapping(raw.get("gui"), "gui", target)
    resources = _mapping(raw.get("resources"), "resources", target)
    integrations = _mapping(raw.get("integrations"), "integrations", target)
    _reject_unknown(gui, {"theme", "font_size"}, "gui", target)
    _reject_unknown(resources, {"max_pairs_per_chunk"}, "resources", target)
    max_pairs = resources.get("max_pairs_per_chunk", 500_000)
    if isinstance(max_pairs, bool) or not isinstance(max_pairs, int) or max_pairs < 1_000:
        raise ConfigurationError(
            "Configuration field 'max_pairs_per_chunk' must be an integer of at least 1000.",
            details={"path": str(target), "value": max_pairs},
        )
    parsed_integrations: dict[str, IntegrationConfig] = {}
    if not integrations:
        integrations = {"gromacs": {}, "vmd": {}}
    for name, raw_integration in integrations.items():
        if not isinstance(name, str) or not name.strip():
            raise ConfigurationError(
                "Every entry under [integrations] must have a non-empty string name.",
                details={"path": str(target), "name": name},
            )
        integration = _mapping(raw_integration, f"integrations.{name}", target)
        _reject_unknown(
            integration,
            {
                "enabled",
                "path",
                "search_paths",
                "use_environment",
                "detect_timeout_seconds",
                "run_timeout_seconds",
            },
            f"integrations.{name}",
            target,
        )
        configured_path = integration.get("path", "")
        if not isinstance(configured_path, str):
            raise ConfigurationError(
                f"Configuration field 'integrations.{name}.path' must be a string.",
                details={"path": str(target), "value": configured_path},
            )
        if configured_path and not configured_path.strip():
            raise ConfigurationError(
                f"Configuration field 'integrations.{name}.path' cannot contain only "
                "whitespace.",
                details={"path": str(target), "field": f"integrations.{name}.path"},
            )
        search_paths = integration.get("search_paths", [])
        if not isinstance(search_paths, list) or any(
            not isinstance(item, str) or not item.strip() for item in search_paths
        ):
            raise ConfigurationError(
                f"Configuration field 'integrations.{name}.search_paths' must contain paths.",
                details={"path": str(target), "value": search_paths},
            )
        parsed_integrations[name.casefold()] = IntegrationConfig(
            enabled=_bool(integration, "enabled", True, target),
            path=configured_path,
            search_paths=tuple(search_paths),
            use_environment=_bool(integration, "use_environment", True, target),
            detect_timeout_seconds=_positive_number(
                integration, "detect_timeout_seconds", 10.0, target
            ),
            run_timeout_seconds=_positive_number(
                integration, "run_timeout_seconds", 3600.0, target
            ),
        )
    return UserConfig(
        gui=GuiConfig(
            theme=_theme(gui, target),
            font_size=_font_size(gui, target),
        ),
        resources=ResourceConfig(max_pairs_per_chunk=max_pairs),
        integrations=parsed_integrations,
    )


def initialize_config(path: Path | None = None, force: bool = False) -> Path:
    target = config_path() if path is None else Path(path)
    if target.exists() and not force:
        raise ConfigurationError(
            f"Configuration already exists: {target}",
            "Use --force only if replacing it is intentional.",
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp")
    try:
        temporary.write_text(DEFAULT_CONFIG_TEMPLATE, encoding="utf-8")
        os.replace(temporary, target)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise ConfigurationError(
            f"Could not write configuration: {target}",
            details={"exception": f"{type(exc).__name__}: {exc}"},
        ) from exc
    return target


def save_config(config: UserConfig, path: Path | None = None) -> Path:
    target = config_path() if path is None else Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp")
    try:
        with temporary.open("wb") as handle:
            tomli_w.dump(config.to_dict(), handle)
        load_config(temporary)
        os.replace(temporary, target)
    except (ConfigurationError, OSError, TypeError) as exc:
        temporary.unlink(missing_ok=True)
        if isinstance(exc, ConfigurationError):
            raise
        raise ConfigurationError(
            f"Could not save configuration: {target}",
            details={"exception": f"{type(exc).__name__}: {exc}"},
        ) from exc
    return target
