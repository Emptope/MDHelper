"""Capture real Qt rendering (not palette swatches), without touching user settings.

QT_QPA_PLATFORM=cocoa uv run python tests/gui/capture_appearance.py .local-records/appearance
Use --native for an unmodified platform-style baseline; --font-size 18 for large text.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from collections import Counter
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from mdhelper.app import InputCandidates
from mdhelper.gui.dialogs.integrations import IntegrationsDialog
from mdhelper.gui.dialogs.projects import NewProjectDialog
from mdhelper.gui.plotting.settings import PlotSettingsDialog
from mdhelper.gui.theme import theme_controller
from mdhelper.gui.window import MainWindow
from mdhelper.gui.workflows.dialog import WorkflowDialog


def controls() -> tuple[QWidget, dict[str, QWidget]]:
    panel = QWidget()
    panel.setWindowTitle("Input states / native subcontrols")
    form = QFormLayout(panel)
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    items: dict[str, QWidget] = {}
    for name in ("enabled", "focused", "selected", "placeholder", "readonly", "disabled"):
        edit = QLineEdit("" if name == "placeholder" else "Selection: resname LI")
        edit.setPlaceholderText("Enter selection expression")
        edit.setReadOnly(name == "readonly")
        edit.setEnabled(name != "disabled")
        if name == "selected":
            edit.selectAll()
        items[name] = edit
    items["number"] = QDoubleSpinBox()
    combo = QComboBox()
    combo.setEditable(True)
    combo.addItem("Editable choice")
    items["combo"] = combo
    for name in ("text", "readonly_text"):
        text = QPlainTextEdit("Multi-line text\nSecond line")
        text.setReadOnly(name == "readonly_text")
        items[name] = text
    table = QTableWidget(2, 2)
    table.setHorizontalHeaderLabels(["Name", "Value"])
    table.setItem(0, 0, QTableWidgetItem("Selected row"))
    table.selectRow(0)
    items["table"] = table
    items["button"] = QPushButton("Native button")
    for name, widget in items.items():
        form.addRow(name, widget)
    panel.resize(700, 900)
    return panel, items


def capture(widget: QWidget, path: Path) -> None:
    widget.show()
    widget.activateWindow()
    QTest.qWait(120)
    assert widget.grab().save(str(path)), path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--native", action="store_true")
    parser.add_argument("--font-size", type=int, default=11)
    parser.add_argument("--width", type=int, default=860)
    parser.add_argument("--height", type=int, default=800)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("MDHelper")
    controller = theme_controller(app)
    report: dict[str, object] = {"platform": app.platformName(), "modes": {}}
    # MainWindow normally persists user preferences and starts tool detection.
    isolation = ExitStack()
    temporary = isolation.enter_context(TemporaryDirectory())
    isolation.enter_context(patch.dict(os.environ, {
        "MDHELPER_CONFIG": str(Path(temporary) / "config.toml"),
        "MDHELPER_LOG": str(Path(temporary) / "mdhelper.log"),
    }))
    isolation.enter_context(patch("mdhelper.gui.actions.backend.BackendActions.detect_gromacs"))
    with patch.object(controller, "apply"):
        window = MainWindow()
        window.resize(args.width, args.height)
    try:
        sample = (Path(temporary) / "simulation-notes.txt").resolve()
        sample.write_text("\n".join(
            f"Step {i:03d}: inspect trajectory and confirm parameters"
            for i in range(1, 121)
        ) + "\nUnicode: 中文\n\tTab-aligned notes", encoding="utf-8")
        workspace = window.tabs.editor
        workspace.set_root(temporary)
        workspace.open_path(str(sample))
        deadline = time.monotonic() + 10
        while workspace.current_path != str(sample) and time.monotonic() < deadline:
            app.processEvents()
            # QTest.qWait does not yield the GIL to Python document workers.
            time.sleep(0.01)
        assert workspace.current_path == str(sample), (
            workspace.current_path, workspace._loading_path, workspace.status.text(),
            workspace.status.toolTip(), str(sample),
        )
        for mode in (("native",) if args.native else ("system", "light", "dark")):
            if mode != "native":
                controller.apply(mode)
            font = QFont(app.font())
            font.setPointSize(args.font_size)
            app.setFont(font)
            cursor = workspace.editor.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            cursor.movePosition(QTextCursor.MoveOperation.NextBlock, n=10)
            cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, 8)
            workspace.editor.setTextCursor(cursor)
            for index in range(window.tabs.count()):
                window.tabs.setCurrentIndex(index)
                capture(window, args.output / f"{mode}-{window.tabs.tabText(index).lower()}.png")
            dialogs = {
                "integrations": IntegrationsDialog(window.application),
                "project": NewProjectDialog(InputCandidates(Path("/example"), (), (), ())),
                "plot-settings": PlotSettingsDialog(),
                "workflow": WorkflowDialog(),
            }
            for name, dialog in dialogs.items():
                capture(dialog, args.output / f"{mode}-{name}.png")
                dialog.close()
            gallery, items = controls()
            gallery.show()
            items["focused"].setFocus()
            capture(gallery, args.output / f"{mode}-controls.png")
            selected = items["selected"]
            selected.setFocus()
            selected.selectAll()
            capture(gallery, args.output / f"{mode}-selection.png")
            pixels = {}
            for name, item in items.items():
                image = item.grab().toImage()
                colors = Counter(
                    image.pixelColor(x, y).name()
                    for x in range(image.width()) for y in range(image.height())
                )
                pixels[name] = {
                    "dominant_pixels": colors.most_common(4),
                    "size": [item.width(), item.height()],
                    "size_hint": [item.sizeHint().width(), item.sizeHint().height()],
                }
            report["modes"][mode] = {
                "style": app.style().objectName() or controller._active_style,
                "device_pixel_ratio": gallery.devicePixelRatioF(),
                "controls": pixels,
                "editor": {
                    "font_size": workspace.editor.font().pointSizeF(),
                    "line_count": workspace.editor.blockCount(),
                    "gutter_width": workspace.editor.line_number_width(),
                    "cursor_status": workspace.cursor_position.text(),
                },
            }
            gallery.close()
    finally:
        window.close()
        isolation.close()
    report["settings"] = {
        "menu_role": window.menu_actions.settings.menuRole().name,
        "shortcut": window.menu_actions.settings.shortcut().toString(),
    }
    (args.output / "rendering.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
