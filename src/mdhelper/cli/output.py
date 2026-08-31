"""Stable JSON output for CLI commands and errors."""

from __future__ import annotations

import json
import sys
from typing import Any


def write_json(value: Any, stream: Any | None = None) -> None:
    output = sys.stdout if stream is None else stream
    output.write(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    output.flush()
