import logging
import os
import posixpath
import runpy
import sys
from pathlib import Path

project_root = Path(SPECPATH).parents[1]
source_root = project_root / "src"
resource_root = source_root / "mdhelper" / "resources"
hook_root = project_root / "packaging" / "hooks"
figure_backends = [
    "matplotlib.backends.backend_agg",
    "matplotlib.backends.backend_pdf",
    "matplotlib.backends.backend_svg",
]
gui_build = os.environ.get("MDHELPER_GUI_BUILD") == "1"
audit_platform = "macos" if sys.platform == "darwin" else "linux-gui"
policy = runpy.run_path(str(project_root / "packaging" / "frozen_audit.py"))


class PlatformLibraryFilter(logging.Filter):
    names = {"ntdll", "ole32", "shell32", "user32"}

    def filter(self, record):
        return not (
            record.msg == "Library %s required via ctypes not found"
            and record.args
            and str(record.args[0]).casefold() in self.names
        )


logging.getLogger("PyInstaller.depend.utils").addFilter(PlatformLibraryFilter())
excluded_modules = [
    "_pytest",
    "build",
    "pip",
    "PyInstaller",
    "pytest",
    "setuptools",
    "wheel",
    "mdhelper.bootstrap.windows_console",
    "scipy.integrate",
    "scipy.optimize",
    "scipy.signal",
    "scipy.stats",
]
if gui_build:
    excluded_modules.extend(
        [
            "PySide6.QtNetwork",
            "PySide6.QtOpenGL",
            "PySide6.QtPdf",
            "PySide6.QtQml",
            "PySide6.QtQuick",
        ]
    )
else:
    excluded_modules.append("PySide6")

application_analysis = Analysis(
    [str(project_root / "packaging/entry.py")],
    pathex=[str(source_root)],
    binaries=[],
    datas=[
        (str(resource_root), "mdhelper/resources"),
    ],
    hiddenimports=[
        *figure_backends,
        "MDAnalysis.lib._transformations",
        "mdhelper.cli.main",
        "mdhelper.gui.window" if gui_build else "mdhelper.gui.main",
        "mdhelper.tui.main",
    ],
    hookspath=[str(hook_root)],
    hooksconfig={
        "matplotlib": {
            "backends": ["Agg", "QtAgg"] if gui_build else ["Agg"],
        },
    },
    runtime_hooks=[],
    excludes=excluded_modules,
    noarchive=False,
    optimize=0,
)

qt_plugins = policy["POSIX_QT_PLUGINS"][audit_platform]
qt_unused_library_prefixes = policy["FORBIDDEN_LINUX_GUI_PREFIXES"]


def keep_binary(item):
    target = item[0].replace("\\", "/")
    lower_target = target.lower()
    name = Path(target).name.lower()
    for plugin_root in ("pyside6/plugins/", "pyside6/qt/plugins/"):
        if lower_target.startswith(plugin_root):
            return lower_target.removeprefix(plugin_root) in qt_plugins
    return not name.startswith(qt_unused_library_prefixes)


def keep_data(item):
    target = item[0].replace("\\", "/").lower()
    return not target.startswith(("pyside6/translations/", "pyside6/qt/translations/"))


if gui_build:
    application_analysis.binaries = list(filter(keep_binary, application_analysis.binaries))
    application_analysis.datas = [
        item for item in application_analysis.datas if keep_data(item) and keep_binary(item)
    ]
    binary_targets = {item[0].replace("\\", "/") for item in application_analysis.binaries}
    application_analysis.dependencies = [
        item
        for item in application_analysis.dependencies
        if item[2] != "SYMLINK"
        or posixpath.normpath(posixpath.join(posixpath.dirname(item[0]), item[1]))
        in binary_targets
    ]
application_pyz = PYZ(application_analysis.pure)
application = EXE(
    application_pyz,
    application_analysis.scripts,
    application_analysis.binaries,
    application_analysis.datas,
    [],
    name="mdhelper",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    target_arch="arm64" if sys.platform == "darwin" else None,
    codesign_identity=None,
    entitlements_file=None,
)
