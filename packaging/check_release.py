"""Validate release metadata before building artifacts."""

from __future__ import annotations

import argparse
import ast
import tomllib
from pathlib import Path
from typing import Any

PROJECT_FILE = "pyproject.toml"
VERSION_FILE = Path("src/mdhelper/version.py")


def project_version(root: Path) -> str:
    data: dict[str, Any]
    with (root / PROJECT_FILE).open("rb") as stream:
        data = tomllib.load(stream)
    value = data.get("project", {}).get("version")
    if not isinstance(value, str) or not value:
        raise SystemExit("Project version is missing or invalid.")
    return value


def source_version(root: Path) -> str:
    path = root / VERSION_FILE
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if (
            isinstance(target, ast.Name)
            and target.id == "__version__"
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
            and node.value.value
        ):
            return node.value.value
    raise SystemExit("Source version is missing or invalid.")


def validate(root: Path, tag: str | None = None) -> str:
    project = project_version(root)
    source = source_version(root)
    if project != source:
        raise SystemExit(f"Project and source versions differ: {project} != {source}")
    if tag is not None:
        if not tag.startswith("v") or len(tag) == 1:
            raise SystemExit("Release tag must use v<version>.")
        if tag[1:] != project:
            raise SystemExit(f"Release tag does not match version: {tag} != v{project}")
    return project


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).parents[1])
    parser.add_argument("--tag")
    args = parser.parse_args()
    print(validate(args.root.resolve(), args.tag))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
