import logging
from pathlib import Path

project_root = Path(SPECPATH).parents[1]
source_root = project_root / "src"
template_root = source_root / "mdhelper" / "resources" / "templates"
hook_root = project_root / "packaging" / "hooks"
figure_backends = [
    "matplotlib.backends.backend_agg",
    "matplotlib.backends.backend_pdf",
    "matplotlib.backends.backend_svg",
]


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
    "PySide6",
    "mdhelper.bootstrap.windows_console",
    "scipy.integrate",
    "scipy.optimize",
    "scipy.signal",
    "scipy.stats",
]

application_analysis = Analysis(
    [str(project_root / "packaging/linux/entry.py")],
    pathex=[str(source_root)],
    binaries=[],
    datas=[(str(template_root), "mdhelper/resources/templates")],
    hiddenimports=[
        *figure_backends,
        "MDAnalysis.lib._transformations",
        "mdhelper.cli.main",
        "mdhelper.gui.main",
        "mdhelper.tui.main",
    ],
    hookspath=[str(hook_root)],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excluded_modules,
    noarchive=False,
    optimize=0,
)
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
)
