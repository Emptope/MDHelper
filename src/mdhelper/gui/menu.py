"""Main-window menu assembly."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import QMainWindow, QMessageBox

from mdhelper.services.config import THEME_MODES, ThemeMode
from mdhelper.version import DEVELOPER, __version__


@dataclass(frozen=True)
class MenuActions:
    project: QAction
    themes: dict[ThemeMode, QAction]
    theme_group: QActionGroup
    templates: QAction
    terminal: QAction
    make_index: QAction
    settings: QAction


def install_menu(
    window: QMainWindow,
    open_project: Callable[[], None],
    export_result: Callable[[], None],
    integrations: Callable[[], None],
    templates: Callable[[], None],
    terminal: Callable[[], None],
    make_index: Callable[[], None],
    settings: Callable[[], None],
    theme: ThemeMode,
    set_theme: Callable[[ThemeMode], None],
) -> MenuActions:
    file_menu = window.menuBar().addMenu("&File")
    open_action = QAction("Open Project...", window)
    open_action.triggered.connect(open_project)
    export_action = QAction("Export Last Result...", window)
    export_action.triggered.connect(export_result)
    exit_action = QAction("Exit", window)
    exit_action.triggered.connect(window.close)
    file_menu.addActions([open_action, export_action])
    file_menu.addSeparator()
    file_menu.addAction(exit_action)

    tools_menu = window.menuBar().addMenu("&Tools")
    external_action = QAction("Integrations...", window)
    external_action.triggered.connect(integrations)
    templates_action = QAction("Templates...", window)
    templates_action.triggered.connect(templates)
    terminal_action = QAction("Open Terminal Interface", window)
    terminal_action.triggered.connect(terminal)
    tools_menu.addAction(terminal_action)
    tools_menu.addSeparator()
    tools_menu.addActions([templates_action, external_action])
    tools_menu.addSeparator()
    make_index_action = QAction("Make Index File...", window)
    make_index_action.triggered.connect(make_index)
    tools_menu.addAction(make_index_action)

    view_menu = window.menuBar().addMenu("&View")
    appearance_menu = view_menu.addMenu("&Appearance")
    theme_group = QActionGroup(window)
    theme_group.setExclusive(True)
    labels = {"system": "System", "light": "Light", "dark": "Dark"}
    themes: dict[ThemeMode, QAction] = {}
    for mode in THEME_MODES:
        action = QAction(labels[mode], window)
        action.setCheckable(True)
        action.setData(mode)
        action.setChecked(mode == theme)
        appearance_menu.addAction(action)
        theme_group.addAction(action)
        themes[mode] = action

    def select_theme(action: QAction) -> None:
        mode = action.data()
        if mode in THEME_MODES:
            set_theme(mode)

    theme_group.triggered.connect(select_theme)

    settings_action = QAction("&Settings", window)
    settings_action.triggered.connect(settings)
    window.menuBar().addAction(settings_action)

    help_menu = window.menuBar().addMenu("&Help")
    about_action = QAction("About", window)
    help_menu.addAction(about_action)
    about_action.triggered.connect(
        lambda: QMessageBox.about(
            window,
            "About MDHelper",
            f"MDHelper {__version__}<br>"
            "A toolkit for the analysis of <b>Molecular Dynamics</b> data."
            "<br><br>"
            f"Developer: {DEVELOPER}"
            "<br><br>"
            "License: GNU General Public License v2.0 (GPL-2.0)"
            "<br><br>"
            "MDHelper is free software: you are free to use, study, share, "
            "and modify it under the terms of the GNU General Public License.",
        )
    )
    return MenuActions(
        project=open_action,
        themes=themes,
        theme_group=theme_group,
        templates=templates_action,
        terminal=terminal_action,
        make_index=make_index_action,
        settings=settings_action,
    )
