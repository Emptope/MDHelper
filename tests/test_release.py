from __future__ import annotations

import json
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
SCRIPT = Path(__file__).parents[1] / "packaging" / "check_release.py"
CLEAN_SCRIPT = Path(__file__).parents[1] / "packaging" / "clean_build.py"
FROZEN_AUDIT = runpy.run_path(str(ROOT / "packaging" / "frozen_audit.py"))
SMOKE_CHECK = runpy.run_path(str(ROOT / "packaging" / "smoke_check.py"))


def write_distribution(root: Path, platform: str) -> Path:
    root.mkdir()
    application = root / ("mdhelper.exe" if platform == "windows" else "mdhelper")
    application.write_bytes(b"application")
    application.chmod(0o755)
    for name in (
        "LICENSE",
        "README.md",
        "README.zh-CN.md",
        "config.example.toml",
        "config.toml",
    ):
        (root / name).write_text(name, encoding="ascii")
    for directory, name in (
        ("docs", "guide.md"),
        ("licenses", "notices.json"),
        ("schemas", "contract.json"),
    ):
        target = root / directory
        target.mkdir()
        (target / name).write_text("{}", encoding="ascii")
    return application


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


def test_build_cleanup_removes_only_generated_tree(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[build-system]\n", encoding="utf-8")
    build = tmp_path / "build"
    build.mkdir()
    (build / "stale.txt").write_text("stale", encoding="utf-8")
    source = tmp_path / "source.txt"
    source.write_text("keep", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(CLEAN_SCRIPT), "--root", str(tmp_path)],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0
    assert not build.exists()
    assert source.read_text(encoding="utf-8") == "keep"


def test_build_cleanup_rejects_non_project_root(tmp_path: Path) -> None:
    build = tmp_path / "build"
    build.mkdir()

    result = subprocess.run(
        [sys.executable, str(CLEAN_SCRIPT), "--root", str(tmp_path)],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode != 0
    assert build.is_dir()


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


@pytest.mark.parametrize(
    ("platform", "entries", "expected"),
    [
        (
            "windows",
            ["PySide6/plugins/platforms/qoffscreen.dll"],
            ["qwindows.dll"],
        ),
        (
            "linux-gui",
            [
                "PySide6/Qt/plugins/platforms/libqoffscreen.so",
                "PySide6/Qt/plugins/platforms/libqwayland.so",
            ],
            ["libqxcb.so"],
        ),
        ("linux", [], []),
    ],
)
def test_frozen_audit_requires_runtime_qt_plugins(
    platform: str,
    entries: list[str],
    expected: list[str],
) -> None:
    assert FROZEN_AUDIT["missing_plugins"](entries, platform) == expected


def test_smoke_check_validates_distribution_contract(tmp_path: Path) -> None:
    distribution = tmp_path / "distribution"
    application = write_distribution(distribution, "windows")

    assert SMOKE_CHECK["validate_distribution"](distribution, "windows") == application

    (distribution / "schemas" / "contract.json").unlink()
    with pytest.raises(SMOKE_CHECK["SmokeFailure"], match="schemas"):
        SMOKE_CHECK["validate_distribution"](distribution, "windows")


def test_smoke_check_rejects_empty_distribution_directory(tmp_path: Path) -> None:
    distribution = tmp_path / "distribution"
    write_distribution(distribution, "linux")
    for path in (distribution / "docs").iterdir():
        path.unlink()

    with pytest.raises(SMOKE_CHECK["SmokeFailure"], match="docs"):
        SMOKE_CHECK["validate_distribution"](distribution, "linux")


def test_smoke_check_rejects_invalid_archive_layout(tmp_path: Path) -> None:
    expected = tmp_path / "release"
    expected.mkdir()

    assert SMOKE_CHECK["validate_archive_root"](tmp_path, "release") == expected

    (tmp_path / "extra").mkdir()
    with pytest.raises(SMOKE_CHECK["SmokeFailure"], match="one root directory"):
        SMOKE_CHECK["validate_archive_root"](tmp_path, "release")


def test_smoke_check_validates_reported_exports_without_fixed_stem(
    tmp_path: Path,
) -> None:
    output = tmp_path / "analysis"
    output.mkdir()
    names = (
        "result.json",
        "custom.csv",
        "custom.png",
        "custom.svg",
        "custom.pdf",
    )
    for name in names:
        content = '{"schema_version": 1, "analysis_type": "energy"}'
        (output / name).write_text(content, encoding="ascii")
    report = json.dumps(
        {
            "status": "completed",
            "analysis_type": "energy",
            "exports": [str(output / name) for name in names],
        }
    )

    SMOKE_CHECK["validate_analysis"](output, report)

    (output / "custom.pdf").unlink()
    with pytest.raises(SMOKE_CHECK["SmokeFailure"], match="missing export"):
        SMOKE_CHECK["validate_analysis"](output, report)


def test_smoke_check_rejects_export_outside_output(tmp_path: Path) -> None:
    output = tmp_path / "analysis"
    output.mkdir()
    external = tmp_path / "external.json"
    external.write_text('{"schema_version": 1, "analysis_type": "energy"}', encoding="ascii")
    report = json.dumps(
        {
            "status": "completed",
            "analysis_type": "energy",
            "exports": [str(external)],
        }
    )

    with pytest.raises(SMOKE_CHECK["SmokeFailure"], match="outside"):
        SMOKE_CHECK["validate_analysis"](output, report)


def test_smoke_check_rejects_result_type_mismatch(tmp_path: Path) -> None:
    output = tmp_path / "analysis"
    output.mkdir()
    exports = []
    for suffix in ("json", "csv", "png", "svg", "pdf"):
        path = output / f"custom.{suffix}"
        path.write_text(
            '{"schema_version": 1, "analysis_type": "rdf"}',
            encoding="ascii",
        )
        exports.append(str(path))
    report = json.dumps(
        {
            "status": "completed",
            "analysis_type": "energy",
            "exports": exports,
        }
    )

    with pytest.raises(SMOKE_CHECK["SmokeFailure"], match="analysis type"):
        SMOKE_CHECK["validate_analysis"](output, report)


def test_smoke_check_validates_config_report(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text("", encoding="ascii")
    report = json.dumps(
        {
            "status": "valid",
            "path": str(config),
            "exists": True,
            "configuration": {},
        }
    )

    SMOKE_CHECK["validate_config"](report, config)

    wrong = tmp_path / "wrong.toml"
    with pytest.raises(SMOKE_CHECK["SmokeFailure"], match="configuration path"):
        SMOKE_CHECK["validate_config"](report, wrong)
