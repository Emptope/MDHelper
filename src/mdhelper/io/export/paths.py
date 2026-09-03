"""Export destination preparation."""

from __future__ import annotations

from pathlib import Path

from mdhelper.core.errors import BackendError


def output_directory(path: str | Path) -> Path:
    output = Path(path).expanduser().resolve()
    try:
        output.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise BackendError(
            f"Could not create export directory: {output}",
            "Choose a writable directory and verify that no file occupies that path.",
            {"exception": f"{type(exc).__name__}: {exc}"},
        ) from exc
    return output
