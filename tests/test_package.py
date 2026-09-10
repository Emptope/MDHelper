from __future__ import annotations

import multiprocessing
import plistlib
import runpy
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).parents[1]
PACKAGE = runpy.run_path(str(ROOT / "packaging" / "posix" / "dmg.py"))
SMOKE = runpy.run_path(str(ROOT / "packaging" / "smoke_check.py"))
AUDIT = runpy.run_path(str(ROOT / "packaging" / "frozen_audit.py"))


@pytest.mark.parametrize("worker", [False, True])
def test_frozen_entry_dispatches_workers_before_application(
    monkeypatch: pytest.MonkeyPatch, worker: bool,
) -> None:
    from mdhelper.bootstrap import portable

    calls: list[str] = []

    def freeze_support() -> None:
        calls.append("freeze_support")
        if worker:
            raise SystemExit(0)

    def main() -> int:
        calls.append("application")
        return 7

    monkeypatch.setattr(multiprocessing, "freeze_support", freeze_support)
    monkeypatch.setattr(portable, "main", main)
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_path(str(ROOT / "packaging" / "entry.py"), run_name="__main__")
    assert exit_info.value.code == (0 if worker else 7)
    assert calls == (["freeze_support"] if worker else ["freeze_support", "application"])


def make_bundle(tmp_path: Path) -> Path:
    source = tmp_path / "portable"
    source.mkdir()
    frozen = source / "MDHelper.app" / "Contents"
    binaries = frozen / "MacOS"
    resources = frozen / "Resources"
    frameworks = frozen / "Frameworks"
    for directory in (binaries, resources, frameworks):
        directory.mkdir(parents=True)
    executable = binaries / "mdhelper"
    executable.write_bytes(b"application")
    executable.chmod(0o755)
    for name in SMOKE["REQUIRED_FILES"]:
        (source / name).write_text("example", encoding="ascii")
    for name in SMOKE["REQUIRED_DIRECTORIES"]:
        (source / name).mkdir()
        (source / name / "data.json").write_text("{}", encoding="ascii")
    (resources / "mdhelper.icns").write_bytes(b"icon")
    (frameworks / "libpython.dylib").write_bytes(b"runtime")
    with (frozen / "Info.plist").open("wb") as handle:
        plistlib.dump({
            "CFBundleExecutable": "mdhelper",
            "CFBundleIconFile": "mdhelper.icns",
            "CFBundlePackageType": "APPL",
            "CFBundleShortVersionString": "2.4.6",
        }, handle)
    bundle = tmp_path / "image" / "Sample App.app"
    PACKAGE["create_bundle"](source, bundle)
    return bundle


def test_bundle_preserves_payload_and_registers_executable(tmp_path: Path) -> None:
    bundle = make_bundle(tmp_path)
    contents = bundle / "Contents"
    with (contents / "Info.plist").open("rb") as handle:
        info = plistlib.load(handle)
    executable = contents / "MacOS" / info["CFBundleExecutable"]
    assert executable.read_bytes() == b"application"
    assert info["CFBundlePackageType"] == "APPL"
    assert info["CFBundleShortVersionString"] == "2.4.6"
    resources = contents / "Resources"
    assert (resources / info["CFBundleIconFile"]).read_bytes() == b"icon"
    assert (contents / "Frameworks" / "libpython.dylib").read_bytes() == b"runtime"
    assert not list(bundle.rglob("config.toml"))
    assert (resources / "config.example.toml").is_file()
    assert SMOKE["validate_distribution"](bundle, "macos") == executable
    renamed = executable.with_name("renamed-launcher")
    executable.rename(renamed)
    info["CFBundleExecutable"] = renamed.name
    with (contents / "Info.plist").open("wb") as handle:
        plistlib.dump(info, handle)
    assert SMOKE["validate_distribution"](bundle, "macos") == renamed


@pytest.mark.skipif(sys.platform == "win32", reason="macOS bundle uses POSIX symlinks")
def test_bundle_preserves_relative_runtime_symlinks(tmp_path: Path) -> None:
    make_bundle(tmp_path)
    source = tmp_path / "portable"
    resource = source / "MDHelper.app" / "Contents" / "Resources" / "libpython.dylib"
    resource.symlink_to("../Frameworks/libpython.dylib")
    bundle = tmp_path / "Copied App.app"

    PACKAGE["create_bundle"](source, bundle)

    copied = bundle / "Contents" / "Resources" / resource.name
    assert copied.is_symlink()
    assert copied.readlink() == Path("../Frameworks/libpython.dylib")
    assert copied.read_bytes() == b"runtime"


@pytest.mark.parametrize("payload", ["onedir", "onefile", "forbidden", "missing-plugin"])
def test_macos_audit_checks_expanded_and_embedded_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, payload: str,
) -> None:
    from PyInstaller.archive import readers

    bundle = make_bundle(tmp_path)
    frameworks = bundle / "Contents" / "Frameworks"
    plugin = frameworks / "PySide6" / "Qt" / "plugins" / "platforms" / "libqcocoa.dylib"
    if payload != "missing-plugin":
        plugin.parent.mkdir(parents=True)
        plugin.write_bytes(b"plugin")
    if payload == "forbidden":
        (plugin.parent / "libqminimal.dylib").write_bytes(b"unused plugin")
    reader = SimpleNamespace(
        toc={"libpython.dylib": (0, 1, 1, 1, "b")} if payload == "onefile" else {},
        options=[],
    )
    monkeypatch.setattr(readers, "CArchiveReader", lambda _path: reader)
    monkeypatch.setattr(
        readers, "pkg_archive_contents",
        lambda _path, recursive: ["entry", "PYZ.pyz", "mdhelper.gui.main"],
    )

    if payload == "onedir":
        AUDIT["audit"](bundle, "macos", 256)
    else:
        message = {
            "onefile": "must not extract a onefile payload",
            "forbidden": "Forbidden frozen payload",
            "missing-plugin": "Required Qt platform plugins are missing",
        }[payload]
        with pytest.raises(SystemExit, match=message):
            AUDIT["audit"](bundle, "macos", 256)


@pytest.mark.parametrize("smoke, fail_copy", [(False, False), (True, False), (True, True)])
def test_dmg_audits_and_cleans_up_installation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, smoke: bool, fail_copy: bool,
) -> None:
    make_bundle(tmp_path)
    commands: list[tuple[str, ...]] = []
    environments: list[dict[str, str]] = []
    image: Path | None = None

    def run(command: tuple[str, ...], *, check: bool, env: dict[str, str] | None) -> None:
        nonlocal image
        assert check
        commands.append(command)
        if command[:2] == ("hdiutil", "create"):
            image = Path(command[command.index("-srcfolder") + 1])
            assert "-format" in command and "UDZO" in command
            Path(command[-1]).write_bytes(b"image")
        if command[0] == "ditto":
            if fail_copy:
                raise subprocess.CalledProcessError(1, command)
            assert image is not None
            shutil.copytree(image / Path(command[1]).name, command[2])
        if command[0] == "bash":
            assert env is not None
            environments.append(env)
            assert Path(command[2]).is_dir()
            assert Path(env["HOME"]).is_dir()

    monkeypatch.setattr(PACKAGE["subprocess"], "run", run)
    links: list[tuple[Path, str]] = []
    monkeypatch.setattr(
        Path, "symlink_to",
        lambda path, target, **kwargs: links.append((path, target)),
    )
    monkeypatch.setattr(Path, "readlink", lambda path: Path(links[0][1]))
    monkeypatch.setenv("MDHELPER_CONFIG", str(tmp_path / "existing.toml"))
    artifact = tmp_path / "release.dmg"
    request = tmp_path / "request.json" if smoke else None
    if fail_copy:
        with pytest.raises(subprocess.CalledProcessError):
            PACKAGE["create_dmg"](tmp_path / "portable", artifact, "2.4.6", request)
    else:
        PACKAGE["create_dmg"](tmp_path / "portable", artifact, "2.4.6", request)
    assert image is not None and not image.parent.exists()
    assert links[0][1] == "/Applications"
    assert ("hdiutil", "verify", str(artifact)) in commands
    assert any("--artifact" in command for command in commands)
    actions = [command[:2] for command in commands]
    if smoke:
        assert ("hdiutil", "attach") in actions
        assert ("hdiutil", "detach") in actions
        attach = commands[actions.index(("hdiutil", "attach"))]
        assert "-readonly" in attach
        if not fail_copy:
            launch = next(i for i, command in enumerate(commands) if command[0] == "bash")
            assert actions.index(("hdiutil", "detach")) < launch
            assert "MDHELPER_CONFIG" not in environments[0]
            assert commands[-1][0] == "open"
    else:
        assert ("hdiutil", "attach") not in actions
        assert not environments


@pytest.mark.parametrize("field", ["LSBackgroundOnly", "LSUIElement"])
@pytest.mark.parametrize("value", [True, False, None])
def test_bundle_validation_requires_foreground_application(
    tmp_path: Path, field: str, value: bool | None,
) -> None:
    bundle = make_bundle(tmp_path)
    path = bundle / "Contents" / "Info.plist"
    with path.open("rb") as handle:
        info = plistlib.load(handle)
    if value is not None:
        info[field] = value
    with path.open("wb") as handle:
        plistlib.dump(info, handle)

    if value:
        with pytest.raises(SMOKE["SmokeFailure"], match=field):
            SMOKE["validate_distribution"](bundle, "macos")
    else:
        assert SMOKE["validate_distribution"](bundle, "macos").is_file()


@pytest.mark.parametrize("field", ["CFBundleExecutable", "CFBundleIconFile"])
def test_bundle_validation_rejects_missing_resources(tmp_path: Path, field: str) -> None:
    bundle = make_bundle(tmp_path)
    contents = bundle / "Contents"
    with (contents / "Info.plist").open("rb") as handle:
        info = plistlib.load(handle)
    directory = "MacOS" if field == "CFBundleExecutable" else "Resources"
    (contents / directory / info[field]).unlink()
    with pytest.raises(SMOKE["SmokeFailure"]):
        SMOKE["validate_distribution"](bundle, "macos")


@pytest.mark.parametrize("value", ["../outside", "/outside", ""])
def test_bundle_validation_rejects_unsafe_executable(tmp_path: Path, value: str) -> None:
    bundle = make_bundle(tmp_path)
    path = bundle / "Contents" / "Info.plist"
    with path.open("rb") as handle:
        info = plistlib.load(handle)
    info["CFBundleExecutable"] = value
    with path.open("wb") as handle:
        plistlib.dump(info, handle)
    with pytest.raises(SMOKE["SmokeFailure"]):
        SMOKE["validate_distribution"](bundle, "macos")
