from __future__ import annotations

import ast
import importlib.util
import re
import struct
import tomllib
import zipfile
from pathlib import Path, PurePosixPath
from types import ModuleType
from urllib.parse import unquote, urlsplit

import pytest

ROOT = Path(__file__).parents[1]
WINDOWS = ROOT / "packaging" / "windows"
LINUX = ROOT / "packaging" / "linux"
MARKDOWN_LINK = re.compile(r"(?<!!)\[[^]]*\]\(([^)]+)\)")


def _calls(path: Path, name: str) -> list[ast.Call]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == name
    ]


def _audit_module() -> ModuleType:
    path = ROOT / "packaging" / "frozen_audit.py"
    spec = importlib.util.spec_from_file_location("packaging_audit", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _wheel_module() -> ModuleType:
    path = ROOT / "packaging" / "verify_wheel.py"
    spec = importlib.util.spec_from_file_location("wheel_audit", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_pe(path: Path, subsystem: int) -> None:
    image = bytearray(256)
    image[:2] = b"MZ"
    struct.pack_into("<I", image, 0x3C, 0x40)
    image[0x40:0x44] = b"PE\0\0"
    struct.pack_into("<H", image, 0x40 + 24, 0x20B)
    struct.pack_into("<H", image, 0x40 + 24 + 68, subsystem)
    path.write_bytes(image)


def test_distribution_exposes_one_public_entry_point() -> None:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        project = tomllib.load(handle)["project"]

    assert project["scripts"] == {"mdhelper": "mdhelper.bootstrap.portable:main"}
    assert "gui-scripts" not in project


def test_distribution_declares_gpl_v2() -> None:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        project = tomllib.load(handle)["project"]
    license_text = (ROOT / "LICENSE").read_text(encoding="ascii")

    assert project["license"] == "GPL-2.0"
    assert project["license-files"] == ["LICENSE"]
    assert "GNU GENERAL PUBLIC LICENSE" in license_text
    assert "Version 2, June 1991" in license_text
    assert "END OF TERMS AND CONDITIONS" in license_text


def test_local_documentation_links_resolve() -> None:
    sources = (
        *ROOT.glob("*.md"),
        *(ROOT / "docs").rglob("*.md"),
        *(ROOT / "examples").rglob("*.md"),
    )
    missing: list[str] = []
    for source in sources:
        for match in MARKDOWN_LINK.finditer(source.read_text(encoding="utf-8")):
            target = match.group(1).strip()
            if target.startswith("<") and ">" in target:
                target = target[1 : target.index(">")]
            else:
                target = target.split(maxsplit=1)[0]
            parsed = urlsplit(target)
            if parsed.scheme or not parsed.path:
                continue
            path = source.parent / unquote(parsed.path)
            if not path.exists():
                missing.append(f"{source.relative_to(ROOT)}: {target}")
    assert missing == []


def test_workflows_pin_bootstrap_dependencies() -> None:
    workflows = {
        path.name: path.read_text(encoding="ascii")
        for path in (ROOT / ".github" / "workflows").glob("*.yml")
    }
    combined = "\n".join(workflows.values())

    assert "actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803" in combined
    assert "actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1" in combined
    assert "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a" in combined
    assert "python -m pip install uv==0.12.6" in combined
    assert "uses: actions/checkout@v" not in combined
    assert "uses: actions/setup-python@v" not in combined
    assert "uses: actions/upload-artifact@v" not in combined


def test_windows_spec_builds_one_application_without_bulk_collection() -> None:
    path = WINDOWS / "mdhelper.spec"
    source = path.read_text(encoding="utf-8")

    assert len(_calls(path, "Analysis")) == 1
    assert len(_calls(path, "EXE")) == 1
    assert "collect_all" not in source
    assert 'console=False' in source
    assert "hide_console" not in source
    assert '"MDAnalysis.lib._transformations"' in source
    assert len(list(WINDOWS.glob("*entry.py"))) == 1


def test_linux_spec_builds_one_headless_application() -> None:
    path = LINUX / "mdhelper.spec"
    source = path.read_text(encoding="utf-8")

    assert len(_calls(path, "Analysis")) == 1
    assert len(_calls(path, "EXE")) == 1
    assert "collect_all" not in source
    assert '"PySide6"' in source
    assert '"mdhelper.bootstrap.windows_console"' in source
    assert 'names = {"ntdll", "ole32", "shell32", "user32"}' in source
    assert '"MDAnalysis.lib._transformations"' in source
    assert len(list(LINUX.glob("*entry.py"))) == 1


def test_linux_build_has_smoke_and_size_gates() -> None:
    source = (LINUX / "build.sh").read_text(encoding="utf-8")

    assert "MAX_ARTIFACT_SIZE_MB:-256" in source
    assert 'cp "$project_root/LICENSE" "$root/LICENSE"' in source
    assert source.count("frozen_audit.py") == 2
    assert "packaging/linux/smoke.sh" in source
    assert source.index("-xzf \"$archive\"") < source.index("packaging/linux/smoke.sh")


def test_frozen_payload_policy_rejects_duplicate_runtime_weight() -> None:
    module = _audit_module()
    accepted = [
        "PySide6/plugins/platforms/qwindows.dll",
        "PySide6/plugins/platforms/qoffscreen.dll",
        "PySide6/plugins/styles/qmodernwindowsstyle.dll",
    ]
    rejected = [
        "pytest/__init__.py",
        "PyInstaller/__init__.py",
        "setuptools-84.0.0.dist-info/METADATA",
        "scipy.signal._peak_finding",
        "PySide6/translations/qtbase_fr.qm",
        "PySide6/plugins/imageformats/qpdf.dll",
        "PySide6.QtQuick",
        "PySide6/Qt6Quick.dll",
    ]

    assert module.violations(accepted, "windows") == []
    assert module.violations(rejected, "windows") == rejected
    assert module.missing_options([], "windows") == []
    linux_rejected = [
        "PySide6.QtCore",
        "mdhelper.bootstrap.windows_console",
    ]
    assert module.violations(linux_rejected, "linux") == linux_rejected
    assert module.missing_options([], "linux") == []


def test_windows_frozen_audit_requires_gui_subsystem(tmp_path: Path) -> None:
    module = _audit_module()
    application = tmp_path / "application.exe"
    _write_pe(application, module.WINDOWS_GUI_SUBSYSTEM)

    module.check_subsystem(application, "windows")
    _write_pe(application, 3)

    with pytest.raises(SystemExit, match="must use the GUI subsystem"):
        module.check_subsystem(application, "windows")


def test_frozen_formats_hook_collects_compiled_submodules() -> None:
    source = (ROOT / "packaging" / "hooks" / "hook-MDAnalysis.lib.formats.py").read_text(
        encoding="utf-8"
    )

    assert "EXTENSION_SUFFIXES" in source
    assert 'distribution("MDAnalysis")' in source
    assert "collect_submodules" not in source


def test_scipy_hook_collects_only_available_compiled_submodules() -> None:
    source = (ROOT / "packaging" / "hooks" / "hook-scipy.special._ufuncs.py").read_text(
        encoding="utf-8"
    )

    assert "EXTENSION_SUFFIXES" in source
    assert 'distribution("scipy")' in source
    assert "if name in available" in source


def test_release_artifact_size_limit_is_enforced(tmp_path: Path) -> None:
    module = _audit_module()
    artifact = tmp_path / "artifact.bin"
    artifact.write_bytes(b"0" * 11)

    assert module.check_size(artifact, 1) == 11
    with pytest.raises(SystemExit, match="limit"):
        module.check_size(artifact, 0)


def test_platform_archives_use_platform_output_directories() -> None:
    windows_source = (WINDOWS / "build.ps1").read_text(encoding="utf-8")
    windows_workflow = (ROOT / ".github" / "workflows" / "windows-release.yml").read_text(
        encoding="utf-8"
    )
    linux_source = (LINUX / "build.sh").read_text(encoding="utf-8")
    linux_workflow = (ROOT / ".github" / "workflows" / "linux-release.yml").read_text(
        encoding="utf-8"
    )

    assert '[string]$OutputDirectory = "dist/windows"' in windows_source
    assert '$archiveName = "MDHelper-$version-Windows-x64"' in windows_source
    assert 'release_output="$project_root/dist/linux"' in linux_source
    assert 'name="MDHelper-$version-Linux-x86_64"' in linux_source
    assert "path: dist/windows/MDHelper-*-Windows-x64.zip" in windows_workflow
    assert "path: dist/linux/MDHelper-*-Linux-x86_64.tar.gz" in linux_workflow
    combined = "\n".join(
        (windows_source, windows_workflow, linux_source, linux_workflow)
    ).casefold()
    assert "dist/portable" not in combined
    assert "-portable." not in combined
    assert "portable.marker" not in combined
    assert 'config.toml") -Force' in windows_source
    assert '"$root/config.toml"' in linux_source


def test_windows_build_produces_only_one_release_archive() -> None:
    source = (WINDOWS / "build.ps1").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "windows-release.yml").read_text(
        encoding="utf-8"
    )

    assert "[int]$MaxArtifactSizeMB = 256" in source
    assert 'Join-Path $projectRoot "LICENSE"' in source
    assert source.count("frozen_audit.py") == 2
    for target in ("$stage", "$releaseOutput"):
        assert f"[IO.Directory]::Delete({target}, $true)" in source
    assert "--artifact $archivePath" in source
    assert '"archive_smoke.ps1"' in source
    assert not list(WINDOWS.glob("*.iss"))
    assert not list(WINDOWS.glob("*installer*"))
    assert "dist/installer" not in source.casefold()
    assert "innosetupcompiler" not in source.casefold()
    assert "inno" not in source.casefold()
    assert "installer" not in workflow.casefold()
    assert "inno" not in workflow.casefold()


def test_windows_smoke_rejects_additional_executables() -> None:
    smoke = (WINDOWS / "smoke.ps1").read_text(encoding="utf-8")

    assert '$_.Name -ne "mdhelper.exe"' in smoke
    assert "& $application gui --smoke-test | Out-Host" in smoke


def test_archive_smoke_uses_current_template_command() -> None:
    for path in (WINDOWS / "smoke.ps1", LINUX / "smoke.sh"):
        source = path.read_text(encoding="utf-8")
        assert "cli integrations templates" in source
    linux_source = (LINUX / "smoke.sh").read_text(encoding="utf-8")
    assert "Current workspace: not loaded" in linux_source
    assert "PYTHONWARNINGS=error" in linux_source
    windows_source = (WINDOWS / "smoke.ps1").read_text(encoding="utf-8")
    assert '$env:PYTHONWARNINGS = "error"' in windows_source


def test_wheel_audit_compares_every_python_module(tmp_path: Path) -> None:
    module = _wheel_module()
    assert module.MAX_WHEEL_BYTES == 256_000_000
    source = tmp_path / "source"
    package = source / "nested"
    package.mkdir(parents=True)
    (source / "__init__.py").write_text("", encoding="utf-8")
    (package / "current.py").write_text("", encoding="utf-8")

    assert module.source_modules(source) == {
        PurePosixPath("mdhelper/__init__.py"),
        PurePosixPath("mdhelper/nested/current.py"),
    }
    wheel = tmp_path / "package.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("mdhelper/__init__.py", "")
        archive.writestr("mdhelper/nested/current.py", "")
        archive.writestr("mdhelper/nested/stale.py", "")

    assert module.wheel_modules(wheel) - module.source_modules(source) == {
        PurePosixPath("mdhelper/nested/stale.py")
    }
