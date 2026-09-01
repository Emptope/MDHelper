"""Audit frozen applications and release artifacts."""

from __future__ import annotations

import argparse
import struct
from pathlib import Path, PurePosixPath

ALLOWED_WINDOWS_QT_PLUGINS = {
    "qmodernwindowsstyle.dll",
    "qoffscreen.dll",
    "qwindows.dll",
}
ALLOWED_LINUX_QT_PLUGINS = {
    "iconengines/libqsvgicon.so",
    "imageformats/libqgif.so",
    "imageformats/libqico.so",
    "imageformats/libqjpeg.so",
    "imageformats/libqsvg.so",
    "platforminputcontexts/libcomposeplatforminputcontextplugin.so",
    "platforminputcontexts/libibusplatforminputcontextplugin.so",
    "platforms/libqoffscreen.so",
    "platforms/libqwayland.so",
    "platforms/libqxcb.so",
    "platformthemes/libqgtk3.so",
    "platformthemes/libqxdgdesktopportal.so",
    "wayland-decoration-client/libadwaita.so",
    "wayland-decoration-client/libbradient.so",
    "wayland-graphics-integration-client/libdmabuf-server.so",
    "wayland-graphics-integration-client/libdrm-egl-server.so",
    "wayland-graphics-integration-client/libqt-plugin-wayland-egl.so",
    "wayland-graphics-integration-client/libshm-emulation-server.so",
    "wayland-graphics-integration-client/libvulkan-server.so",
    "wayland-shell-integration/libfullscreen-shell-v1.so",
    "wayland-shell-integration/libivi-shell.so",
    "wayland-shell-integration/libqt-shell.so",
    "wayland-shell-integration/libwl-shell-plugin.so",
    "wayland-shell-integration/libxdg-shell.so",
    "xcbglintegrations/libqxcb-egl-integration.so",
    "xcbglintegrations/libqxcb-glx-integration.so",
}
FORBIDDEN_ROOTS = {
    "_pyinstaller_hooks_contrib",
    "_pytest",
    "build",
    "pip",
    "pyinstaller",
    "pytest",
    "setuptools",
    "wheel",
}
FORBIDDEN_WINDOWS_FILES = {
    "opengl32sw.dll",
    "qt6network.dll",
    "qt6opengl.dll",
    "qt6pdf.dll",
    "qt6qml.dll",
    "qt6quick.dll",
    "qt6virtualkeyboard.dll",
}
FORBIDDEN_LINUX_GUI_PREFIXES = (
    "libqt6network",
    "libqt6opengl",
    "libqt6pdf",
    "libqt6qml",
    "libqt6quick",
    "libqt6virtualkeyboard",
)
FORBIDDEN_MODULES = {
    "pyside6.qtnetwork",
    "pyside6.qtopengl",
    "pyside6.qtpdf",
    "pyside6.qtqml",
    "pyside6.qtquick",
    "scipy.integrate",
    "scipy.optimize",
    "scipy.signal",
    "scipy.stats",
}
FORBIDDEN_LINUX_MODULES = {
    "mdhelper.bootstrap.windows_console",
}
REQUIRED_OPTIONS = {"windows": set(), "linux": set(), "linux-gui": set()}
WINDOWS_CONSOLE_SUBSYSTEM = 3


def violations(entries: list[str], platform: str) -> list[str]:
    """Return payload entries that violate a platform's frozen-package policy."""

    invalid: list[str] = []
    for raw_name in entries:
        name = raw_name.replace("\\", "/")
        path = PurePosixPath(name)
        root = path.parts[0].split(".")[0].split("-")[0].lower() if path.parts else ""
        filename = path.name.lower()
        module = name.replace("/", ".").lower()
        if root in FORBIDDEN_ROOTS:
            invalid.append(raw_name)
            continue
        if any(
            module == prefix or module.startswith(f"{prefix}.")
            for prefix in FORBIDDEN_MODULES
        ):
            invalid.append(raw_name)
            continue
        if platform.startswith("linux") and any(
            module == prefix or module.startswith(f"{prefix}.")
            for prefix in FORBIDDEN_LINUX_MODULES
        ):
            invalid.append(raw_name)
            continue
        if platform == "linux" and root == "pyside6":
            invalid.append(raw_name)
            continue
        if platform == "linux-gui" and filename.startswith(FORBIDDEN_LINUX_GUI_PREFIXES):
            invalid.append(raw_name)
            continue
        if platform == "linux-gui" and name.lower().startswith(
            ("pyside6/translations/", "pyside6/qt/translations/")
        ):
            invalid.append(raw_name)
            continue
        if platform == "linux-gui":
            plugin = None
            for plugin_root in ("pyside6/plugins/", "pyside6/qt/plugins/"):
                if name.lower().startswith(plugin_root):
                    plugin = name.lower().removeprefix(plugin_root)
                    break
            if plugin is not None and plugin not in ALLOWED_LINUX_QT_PLUGINS:
                invalid.append(raw_name)
                continue
        if platform == "windows" and filename in FORBIDDEN_WINDOWS_FILES:
            invalid.append(raw_name)
            continue
        if platform == "windows" and name.lower().startswith("pyside6/translations/"):
            invalid.append(raw_name)
            continue
        if (
            platform == "windows"
            and name.lower().startswith("pyside6/plugins/")
            and filename not in ALLOWED_WINDOWS_QT_PLUGINS
        ):
            invalid.append(raw_name)
    return invalid


def archive(application: Path) -> tuple[list[str], list[str]]:
    from PyInstaller.archive.readers import CArchiveReader, pkg_archive_contents

    reader = CArchiveReader(str(application))
    return pkg_archive_contents(str(application), recursive=True), list(reader.options)


def windows_subsystem(application: Path) -> int:
    """Read the PE subsystem without adding a packaging dependency."""

    with application.open("rb") as handle:
        dos_header = handle.read(64)
        if len(dos_header) != 64 or dos_header[:2] != b"MZ":
            raise ValueError("missing DOS header")
        pe_offset = struct.unpack_from("<I", dos_header, 0x3C)[0]
        handle.seek(pe_offset)
        pe_header = handle.read(94)
    if len(pe_header) != 94 or pe_header[:4] != b"PE\0\0":
        raise ValueError("missing PE header")
    optional_magic = struct.unpack_from("<H", pe_header, 24)[0]
    if optional_magic not in (0x10B, 0x20B):
        raise ValueError("unsupported PE optional header")
    return struct.unpack_from("<H", pe_header, 24 + 68)[0]


def check_subsystem(application: Path, platform: str) -> None:
    if platform != "windows":
        return
    try:
        subsystem = windows_subsystem(application)
    except (OSError, ValueError) as exc:
        raise SystemExit(f"Could not read the Windows PE subsystem: {application}") from exc
    if subsystem != WINDOWS_CONSOLE_SUBSYSTEM:
        raise SystemExit(
            f"Windows application must use the console subsystem, found {subsystem}: "
            f"{application}"
        )


def missing_options(options: list[str], platform: str) -> list[str]:
    """Return required bootloader options absent from the frozen archive."""

    return sorted(REQUIRED_OPTIONS[platform] - set(options))


def check_size(artifact: Path, max_size_mb: int) -> int:
    """Reject a release artifact that exceeds the configured decimal-MB limit."""

    maximum = max_size_mb * 1_000_000
    size = artifact.stat().st_size
    if size > maximum:
        raise SystemExit(f"Artifact is {size} bytes; limit is {maximum} bytes: {artifact}")
    print(f"Verified artifact size: {artifact} ({size} bytes)")
    return size


def audit(application: Path, platform: str, max_size_mb: int) -> None:
    check_size(application, max_size_mb)
    check_subsystem(application, platform)
    entries, options = archive(application)
    missing = missing_options(options, platform)
    if missing:
        raise SystemExit(f"Required frozen options are missing: {missing}")
    invalid = violations(entries, platform)
    if invalid:
        raise SystemExit(f"Forbidden frozen payload entries: {sorted(invalid)}")
    print(f"Verified frozen payload: {application}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--application", type=Path)
    parser.add_argument("--artifact", action="append", default=[], type=Path)
    parser.add_argument("--platform", choices=sorted(REQUIRED_OPTIONS), required=True)
    parser.add_argument("--max-size-mb", type=int, required=True)
    args = parser.parse_args()
    if args.application is None and not args.artifact:
        parser.error("at least one --application or --artifact is required")
    if args.application is not None:
        audit(args.application.resolve(), args.platform, args.max_size_mb)
    for artifact in args.artifact:
        check_size(artifact.resolve(), args.max_size_mb)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
