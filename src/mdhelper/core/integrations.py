"""Backend-independent external integration contracts."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class IntegrationConfig:
    enabled: bool = True
    path: str = ""
    search_paths: tuple[str, ...] = ()
    use_environment: bool = True
    detect_timeout_seconds: float = 10.0
    run_timeout_seconds: float = 3600.0


@dataclass(frozen=True)
class Detection:
    name: str
    source: str
    candidate: str
    available: bool
    path: str | None = None
    version: str | None = None
    capabilities: tuple[str, ...] = ()
    error: str | None = None
    rank: int = 0
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["capabilities"] = list(self.capabilities)
        return value


@dataclass(frozen=True)
class IntegrationStatus:
    name: str
    available: bool
    path: str | None = None
    version: str | None = None
    capabilities: tuple[str, ...] = ()
    source: str | None = None
    error: str | None = None
    detections: tuple[Detection, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "available": self.available,
            "path": self.path,
            "version": self.version,
            "capabilities": list(self.capabilities),
            "source": self.source,
            "error": self.error,
            "detections": [item.to_dict() for item in self.detections],
        }


@dataclass
class IntegrationRunRecord:
    name: str
    display_name: str
    path: str
    version: str
    command: str
    arguments: list[str]
    working_directory: str
    environment_summary: dict[str, str]
    exit_code: int
    stdout: str
    stderr: str
    started_at: str
    output_fingerprints: dict[str, str] = field(default_factory=dict)
    elapsed_seconds: float = 0.0
    status: Literal["completed", "failed", "cancelled", "timed_out"] = "completed"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def unique_run_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove exact duplicate records while preserving first-seen order."""
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in records:
        key = json.dumps(record, sort_keys=True, separators=(",", ":"))
        if key not in seen:
            seen.add(key)
            result.append(record)
    return result
