from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "packaging" / "check_release.py"


def write_metadata(root: Path, project_version: str, source_version: str) -> None:
    (root / "src" / "mdhelper").mkdir(parents=True)
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "sample"\nversion = "{project_version}"\n',
        encoding="utf-8",
    )
    (root / "src" / "mdhelper" / "version.py").write_text(
        f'__version__ = "{source_version}"\n',
        encoding="utf-8",
    )


def run_check(root: Path, tag: str | None = None) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(SCRIPT), "--root", str(root)]
    if tag is not None:
        command.extend(("--tag", tag))
    return subprocess.run(command, capture_output=True, check=False, text=True)


def test_release_check_accepts_matching_versions_and_tag(tmp_path: Path) -> None:
    write_metadata(tmp_path, "2.4.6", "2.4.6")

    result = run_check(tmp_path, "v2.4.6")

    assert result.returncode == 0
    assert result.stdout.strip() == "2.4.6"


def test_release_check_rejects_source_version_mismatch(tmp_path: Path) -> None:
    write_metadata(tmp_path, "2.4.6", "2.4.7")

    result = run_check(tmp_path)

    assert result.returncode != 0
    assert "Project and source versions differ" in result.stderr


def test_release_check_rejects_tag_version_mismatch(tmp_path: Path) -> None:
    write_metadata(tmp_path, "2.4.6", "2.4.6")

    result = run_check(tmp_path, "v3.5.7")

    assert result.returncode != 0
    assert "Release tag does not match version" in result.stderr


def test_release_check_rejects_invalid_tag(tmp_path: Path) -> None:
    write_metadata(tmp_path, "2.4.6", "2.4.6")

    result = run_check(tmp_path, "release-2.4.6")

    assert result.returncode != 0
    assert "Release tag must use v<version>" in result.stderr
