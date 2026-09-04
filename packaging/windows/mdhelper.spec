from pathlib import Path

project_root = Path(SPECPATH).parents[1]
source_root = project_root / "src"
template_root = source_root / "mdhelper" / "resources" / "templates"
icon_root = source_root / "mdhelper" / "resources" / "icons"
application_icon = icon_root / "mdhelper.ico"
hook_root = project_root / "packaging" / "hooks"
figure_backends = [
    "matplotlib.backends.backend_agg",
    "matplotlib.backends.backend_pdf",
    "matplotlib.backends.backend_svg",
]
common_hidden = [*figure_backends, "MDAnalysis.lib._transformations"]
excluded_modules = [
    "_pytest",
    "build",
    "pip",
    "PyInstaller",
    "pytest",
    "setuptools",
    "wheel",
    "scipy.integrate",
    "scipy.optimize",
    "scipy.signal",
    "scipy.stats",
    "PySide6.QtNetwork",
    "PySide6.QtOpenGL",
    "PySide6.QtPdf",
    "PySide6.QtQml",
    "PySide6.QtQuick",
]

common = {
    "pathex": [str(source_root)],
    "binaries": [],
    "datas": [
        (str(template_root), "mdhelper/resources/templates"),
        (str(icon_root), "mdhelper/resources/icons"),
    ],
    "hiddenimports": common_hidden,
    "hookspath": [str(hook_root)],
    "hooksconfig": {},
    "runtime_hooks": [],
    "excludes": excluded_modules,
    "noarchive": False,
    "optimize": 0,
}

application_analysis = Analysis(
    [str(project_root / "packaging/windows/entry.py")],
    **{
        **common,
        "hiddenimports": [
            *common_hidden,
            "mdhelper.cli.main",
            "mdhelper.gui.window",
            "mdhelper.tui.main",
        ],
    },
)

qt_plugins = {
    "qmodernwindowsstyle.dll",
    "qoffscreen.dll",
    "qwindows.dll",
}
qt_unused_libraries = {
    "opengl32sw.dll",
    "qt6network.dll",
    "qt6opengl.dll",
    "qt6pdf.dll",
    "qt6qml.dll",
    "qt6qmlmeta.dll",
    "qt6qmlmodels.dll",
    "qt6qmlworkerscript.dll",
    "qt6quick.dll",
    "qt6virtualkeyboard.dll",
}


def keep_binary(item):
    target = item[0].replace("\\", "/")
    name = Path(target).name.lower()
    if target.lower().startswith("pyside6/plugins/"):
        return name in qt_plugins
    return name not in qt_unused_libraries


def keep_data(item):
    target = item[0].replace("\\", "/").lower()
    return not target.startswith("pyside6/translations/")


application_analysis.binaries = list(filter(keep_binary, application_analysis.binaries))
application_analysis.datas = list(filter(keep_data, application_analysis.datas))
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
    hide_console="hide-early",
    icon=str(application_icon),
)
