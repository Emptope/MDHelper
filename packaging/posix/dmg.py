"""Add release documents to a frozen onedir bundle and create its disk image."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def create_bundle(source: Path, bundle: Path) -> None:
    # Preserve PyInstaller's framework layout and relative resource symlinks.
    shutil.copytree(source / "MDHelper.app", bundle, symlinks=True)
    resources = bundle / "Contents" / "Resources"
    for entry in source.iterdir():
        if entry.name in {"MDHelper.app", "config.toml"}:
            continue
        target = resources / entry.name
        if entry.is_dir():
            shutil.copytree(entry, target)
        else:
            shutil.copy2(entry, target)


def create_dmg(source: Path, artifact: Path, version: str, request: Path | None) -> None:
    project = Path(__file__).resolve().parents[2]
    python = sys.executable

    def run(*command: str, env: dict[str, str] | None = None) -> None:
        subprocess.run(command, check=True, env=env)

    with tempfile.TemporaryDirectory(prefix="mdhelper-dmg-") as temporary:
        stage = Path(temporary)
        image = stage / "image"
        bundle = image / "MDHelper.app"
        create_bundle(source, bundle)
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
