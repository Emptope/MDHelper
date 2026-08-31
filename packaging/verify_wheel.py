"""Verify that a built wheel exactly matches the source package architecture."""

from __future__ import annotations

import argparse
import zipfile
from pathlib import Path, PurePosixPath

ROOT_MODULES = {"__init__.py", "__main__.py", "version.py"}
SOURCE_PACKAGE_ROOT = Path(__file__).parents[1] / "src" / "mdhelper"
SOURCE_TEMPLATE_ROOT = (
    SOURCE_PACKAGE_ROOT / "resources" / "templates"
)
WHEEL_TEMPLATE_ROOT = PurePosixPath("mdhelper/resources/templates")
MAX_WHEEL_BYTES = 256_000_000


def root_modules(wheel: Path) -> set[str]:
    with zipfile.ZipFile(wheel) as archive:
        return {
            path.name
            for name in archive.namelist()
            if (path := PurePosixPath(name)).parent == PurePosixPath("mdhelper")
            and path.suffix == ".py"
        }


def source_modules(root: Path = SOURCE_PACKAGE_ROOT) -> set[PurePosixPath]:
    return {
        PurePosixPath("mdhelper") / path.relative_to(root).as_posix()
        for path in root.rglob("*.py")
    }


def wheel_modules(wheel: Path) -> set[PurePosixPath]:
    with zipfile.ZipFile(wheel) as archive:
        return {
            path
            for name in archive.namelist()
            if (path := PurePosixPath(name)).parts[0] == "mdhelper"
            and path.suffix == ".py"
        }


def source_templates(root: Path = SOURCE_TEMPLATE_ROOT) -> set[PurePosixPath]:
    return {
        WHEEL_TEMPLATE_ROOT / path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
        and not any(part.startswith(".") for part in path.relative_to(root).parts)
    }


def verify(wheel: Path) -> None:
    size = wheel.stat().st_size
    if size > MAX_WHEEL_BYTES:
        raise SystemExit(f"Wheel exceeds {MAX_WHEEL_BYTES} bytes: {size}")
    actual = root_modules(wheel)
    if actual != ROOT_MODULES:
        unexpected = sorted(actual - ROOT_MODULES)
        missing = sorted(ROOT_MODULES - actual)
        raise SystemExit(
            f"Wheel package-root modules are invalid: unexpected={unexpected}, missing={missing}"
        )
    expected_modules = source_modules()
    actual_modules = wheel_modules(wheel)
    if actual_modules != expected_modules:
        unexpected = sorted(actual_modules - expected_modules)
        missing = sorted(expected_modules - actual_modules)
        raise SystemExit(
            f"Wheel modules do not match source: unexpected={unexpected}, missing={missing}"
        )
    expected_templates = source_templates()
    if not expected_templates:
        raise SystemExit("No source templates were discovered.")
    with zipfile.ZipFile(wheel) as archive:
        archive_files = {PurePosixPath(name) for name in archive.namelist()}
        missing_templates = sorted(expected_templates - archive_files)
    if missing_templates:
        raise SystemExit(f"Wheel templates are missing: {missing_templates}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("wheel", type=Path)
    args = parser.parse_args()
    verify(args.wheel)
    print(f"Verified wheel architecture: {args.wheel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
