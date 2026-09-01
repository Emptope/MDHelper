"""Atomic JSON persistence for project metadata and results."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from mdhelper.core.errors import ConfigurationError


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(
            json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    except (OSError, ValueError) as exc:
        temporary.unlink(missing_ok=True)
        raise ConfigurationError(
            f"Could not commit project metadata: {path}",
            details={"exception": f"{type(exc).__name__}: {exc}"},
        ) from exc
