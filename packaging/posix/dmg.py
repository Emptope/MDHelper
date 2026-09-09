"""Assemble the desktop bundle from the audited portable payload."""

from __future__ import annotations

import argparse
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image


def create_bundle(source: Path, bundle: Path, version: str, icon: Path) -> None:
    contents = bundle / "Contents"
    binaries = contents / "MacOS"
    resources = contents / "Resources"
    binaries.mkdir(parents=True)
    resources.mkdir()
    shutil.copy2(source / "mdhelper", binaries / "mdhelper")
    for entry in source.iterdir():
        if entry.name in {"mdhelper", "config.toml"}:
            continue
        target = resources / entry.name
        if entry.is_dir():
            shutil.copytree(entry, target)
        else:
            shutil.copy2(entry, target)
    with Image.open(icon) as image:
        image.save(resources / "mdhelper.icns", format="ICNS")
    with (contents / "Info.plist").open("wb") as handle:
        plistlib.dump(
            {
                "CFBundleDevelopmentRegion": "en",
                "CFBundleDisplayName": "MDHelper",
                "CFBundleExecutable": "mdhelper",
                "CFBundleIconFile": "mdhelper.icns",
                "CFBundleIdentifier": "org.mdhelper.desktop",
                "CFBundleInfoDictionaryVersion": "6.0",
                "CFBundleName": "MDHelper",
                "CFBundlePackageType": "APPL",
                "CFBundleShortVersionString": version,
                "CFBundleVersion": version,
                "NSHighResolutionCapable": True,
                "NSAppleEventsUsageDescription": "Open interactive tools in Terminal.",
            },
            handle,
        )


def create_dmg(source: Path, artifact: Path, version: str, request: Path | None) -> None:
    project = Path(__file__).resolve().parents[2]
    python = sys.executable

    def run(*command: str, env: dict[str, str] | None = None) -> None:
        subprocess.run(command, check=True, env=env)

    with tempfile.TemporaryDirectory(prefix="mdhelper-dmg-") as temporary:
        stage = Path(temporary)
        image = stage / "image"
        bundle = image / "MDHelper.app"
        create_bundle(
            source, bundle, version, project / "src/mdhelper/resources/icons/mdhelper.png"
        )
        (image / "Applications").symlink_to("/Applications", target_is_directory=True)
        run("codesign", "--force", "--sign", "-", str(bundle))
        run("codesign", "--verify", "--deep", "--strict", str(bundle))
        run(
            python,
            str(project / "packaging/smoke_check.py"),
            "distribution",
            "--root",
            str(bundle),
            "--platform",
            "macos",
        )
        run(
            "hdiutil",
            "create",
            "-volname",
            f"MDHelper {version}",
            "-srcfolder",
            str(image),
            "-format",
            "UDZO",
            "-fs",
            "HFS+",
            str(artifact),
        )
        run("hdiutil", "verify", str(artifact))
        run(
            python,
            str(project / "packaging/frozen_audit.py"),
            "--artifact",
            str(artifact),
            "--platform",
            "macos",
            "--max-size-mb",
            os.environ.get("MAX_ARTIFACT_SIZE_MB", "256"),
        )
        if request is not None:
            mount = stage / "mounted"
            installed = stage / "installed applications" / bundle.name
            run(
                "hdiutil",
                "attach",
                "-readonly",
                "-nobrowse",
                "-mountpoint",
                str(mount),
                str(artifact),
            )
            try:
                if (mount / "Applications").readlink() != Path("/Applications"):
                    raise ValueError("DMG Applications link has an invalid target")
                installed.parent.mkdir()
                run("ditto", str(mount / bundle.name), str(installed))
            finally:
                run("hdiutil", "detach", str(mount))
            run("codesign", "--verify", "--deep", "--strict", str(installed))
            environment = dict(os.environ)
            environment.pop("MDHELPER_CONFIG", None)
            home = stage / "home"
            home.mkdir()
            environment.update(HOME=str(home), PYTHON=python)
            run(
                "bash",
                str(project / "packaging/posix/smoke.sh"),
                str(installed),
                "macos",
                str(request),
                env=environment,
            )
            run("open", "-W", "-n", str(installed), "--args", "gui", "--smoke-test")
    print(f"macos DMG: {artifact}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--request", type=Path)
    args = parser.parse_args()
    create_dmg(args.source.resolve(), args.artifact.resolve(), args.version, args.request)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
