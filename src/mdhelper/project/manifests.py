"""Project-manifest repository and directory initialization."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mdhelper.core.errors import ConfigurationError
from mdhelper.project.schema import validate_manifest
from mdhelper.project.storage import atomic_json

PROJECT_DIRECTORIES = ("results", "results/data", "results/runs", "figures", "cache")
PROJECT_MANIFEST = "mdhelper-project.json"


class ManifestRepository:
    def __init__(self, root: Path):
        self.root = root

    @property
    def path(self) -> Path:
        return self.root / PROJECT_MANIFEST

    def ensure_layout(self) -> None:
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            for name in PROJECT_DIRECTORIES:
                (self.root / name).mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ConfigurationError(
                f"Could not prepare project directories: {self.root}",
                "Restore write access and ensure no file occupies a required directory path.",
                {"exception": f"{type(exc).__name__}: {exc}"},
            ) from exc

    def create(
        self, manifest: dict[str, Any], allow_nonempty: bool = False
    ) -> dict[str, Any]:
        if self.root.exists():
            if not self.root.is_dir():
                raise ConfigurationError(f"Project path is not a directory: {self.root}")
            if self.path.exists():
                raise ConfigurationError(
                    f"A project already exists at {self.root}.",
                    "Open the existing project or choose a new directory.",
                )
            if not allow_nonempty and any(self.root.iterdir()):
                raise ConfigurationError(
                    f"The project directory is not empty: {self.root}",
                    "Choose an empty directory so MDHelper cannot collide with existing files.",
                )
        value = validate_manifest(manifest)
        self.ensure_layout()
        atomic_json(self.path, value)
        return value

    def load(self) -> dict[str, Any]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigurationError(
                f"Could not open project: {self.root}",
                details={"exception": f"{type(exc).__name__}: {exc}"},
            ) from exc
        return validate_manifest(raw)

    def commit(self, manifest: dict[str, Any]) -> dict[str, Any]:
        value = validate_manifest(manifest)
        atomic_json(self.path, value)
        return value
