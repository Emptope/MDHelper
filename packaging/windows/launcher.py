"""Build the small native console forwarder with an installed C toolchain."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path


def toolchain() -> tuple[str, dict[str, str]]:
    environment = dict(os.environ)
    for name in ("cl", "gcc"):
        compiler = shutil.which(name)
        if compiler:
            return compiler, environment
    locator = (
        Path(environment["PROGRAMFILES(X86)"]) / "Microsoft Visual Studio/Installer/vswhere.exe"
    )
    installation = subprocess.check_output(
        [str(locator), "-latest", "-products", "*", "-requires",
         "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "-property", "installationPath"],
        text=True,
    ).strip()
    if not installation:
        raise RuntimeError("Install an x64 C compiler: Visual Studio C++ build tools or MinGW-w64")
    setup = Path(installation) / "VC/Auxiliary/Build/vcvars64.bat"
    values = subprocess.check_output(
        ["cmd.exe", "/d", "/c", f'call "{setup}" >nul && set'], text=True,
    )
    for line in values.splitlines():
        key, separator, value = line.partition("=")
        if separator and key:
            environment[key.upper()] = value
    compiler = shutil.which("cl", path=environment["PATH"])
    if compiler is None:
        raise RuntimeError("The C++ build tools did not provide an x64 compiler")
    return compiler, environment


def build(output: Path, work: Path) -> None:
    output = output.resolve()
    work = work.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    source = Path(__file__).with_suffix(".c").resolve()
    compiler, environment = toolchain()
    if Path(compiler).stem.lower() == "cl":
        command = [compiler, "/nologo", "/W4", "/WX", "/O2", "/MT",
                   "/D_CRT_SECURE_NO_WARNINGS", str(source), f"/Fe:{output}",
                   "/link", "/SUBSYSTEM:CONSOLE", "/MACHINE:X64"]
    else:
        command = [compiler, "-Wall", "-Wextra", "-Werror", "-Os", "-municode",
                   "-static", "-s", str(source), "-o", str(output)]
    subprocess.run(command, cwd=work, env=environment, check=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    build(args.output, args.work)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
