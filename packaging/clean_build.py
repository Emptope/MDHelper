"""Remove generated build state before a new build."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def clean_build(root: Path) -> Path:
    """Remove the build directory under a verified project root."""

    project_root = root.resolve()
    if project_root.parent == project_root or not (project_root / "pyproject.toml").is_file():
        raise ValueError(f"Invalid project root: {project_root}")
    target = project_root / "build"
    if target.is_symlink() or target.is_file():
        target.unlink()
    elif target.is_dir():
        shutil.rmtree(target)
    return target


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).parents[1])
    args = parser.parse_args()
    try:
        target = clean_build(args.root)
    except ValueError as exc:
        parser.error(str(exc))
    print(f"Clean build directory: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
