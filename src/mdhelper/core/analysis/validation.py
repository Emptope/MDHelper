"""Shared validation for serialized analysis contracts."""

from __future__ import annotations

import math


def json_issue(value: object, path: str) -> str | None:
    if value is None or isinstance(value, (bool, int, str)):
        return None
    if isinstance(value, float):
        return None if math.isfinite(value) else f"{path} contains a non-finite number."
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                return f"{path} contains a non-string object key."
            issue = json_issue(item, f"{path}.{key}")
            if issue:
                return issue
        return None
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            issue = json_issue(item, f"{path}[{index}]")
            if issue:
                return issue
        return None
    return f"{path} contains a non-JSON value of type {type(value).__name__}."
