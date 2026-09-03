"""Configuration path selection and atomic TOML persistence."""

from __future__ import annotations

import os
import sys
import tomllib
from pathlib import Path

import tomli_w

from mdhelper.core.errors import ConfigurationError
from mdhelper.services.config.contracts import UserConfig
from mdhelper.services.config.parsing import parse_config

DEFAULT_CONFIG_TEMPLATE = """# MDHelper user configuration
# Schema documentation: docs/CONFIGURATION.md
schema_version = 1

[gui]
# "system" follows the operating system; "light" and "dark" are explicit overrides.
theme = "system"
# GUI font size in points (6-32).
font_size = 11.0

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
    return parse_config(raw, target)


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
