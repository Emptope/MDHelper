from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6", reason="GUI dependencies are not installed")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from mdhelper.core.analysis import RadialRequest
from mdhelper.gui.window import MainWindow
from mdhelper.gui.workflows.dialog import WorkflowDialog
from mdhelper.services.config import UserConfig, config_path, save_config


def _request(analysis_type: str) -> RadialRequest:
    return RadialRequest(
        analysis_type=analysis_type,
        topology="topology.gro",
        trajectory="trajectory.xtc",
        reference="reference",
        selection="selection",
    )


def test_workflow_review_validates_each_project_and_preserves_order() -> None:
    QApplication.instance() or QApplication([])
    dialog = WorkflowDialog()
    built: list[str] = []
    errors: list[BaseException] = []
    submitted: list[tuple[tuple[RadialRequest, str], ...]] = []

    def build(panel):
        analysis_type = panel.analysis_type_value()
        built.append(analysis_type)
        return ((_request(analysis_type), ""),)

    dialog.failed.connect(errors.append)
    dialog.run_requested.connect(submitted.append)
    dialog.configure(
        {"radial": ("rdf", "cumulative_rdf")},
        lambda _panel: None,
        build,
    )

    assert tuple(panel.analysis_type_value() for panel in dialog.panels) == (
        "rdf",
        "cumulative_rdf",
    )
    assert dialog.current_index == 0
    assert not dialog.run_button.isEnabled()

    dialog.next_button.click()

    assert built == ["rdf"]
    assert dialog.current_index == 1
    assert dialog.run_button.isEnabled()

    dialog.run_button.click()

    assert errors == []
    assert built == ["rdf", "rdf", "cumulative_rdf"]
    assert [item[0].analysis_type for item in submitted[0]] == [
        "rdf",
        "cumulative_rdf",
    ]


def test_workflow_review_stays_on_invalid_project() -> None:
    QApplication.instance() or QApplication([])
    dialog = WorkflowDialog()
    error = ValueError("invalid")
    errors: list[BaseException] = []
    dialog.failed.connect(errors.append)
    dialog.configure(
        {"radial": ("rdf", "cumulative_rdf")},
        lambda _panel: None,
        lambda _panel: (_ for _ in ()).throw(error),
    )

    dialog.next_button.click()

    assert dialog.current_index == 0
    assert errors == [error]


def test_workflow_review_shows_complete_names_and_current_project() -> None:
    app = QApplication.instance() or QApplication([])
    dialog = WorkflowDialog()
    font = dialog.steps.font()
    font.setPointSizeF(font.pointSizeF() * 2)
    dialog.steps.setFont(font)
    dialog.configure(
        {"workflow": ("rdf", "cumulative_rdf", "energy")},
        lambda _panel: None,
        lambda _panel: (),
    )
    dialog.show()
    app.processEvents()

    assert dialog.steps.wordWrap()
    assert dialog.steps.textElideMode() == Qt.TextElideMode.ElideNone
    assert not dialog.steps.horizontalScrollBar().isVisible()
    assert dialog.steps.width() * 3 <= dialog.content.width()
    assert dialog.stack.width() >= dialog.stack.minimumSizeHint().width()
    assert dialog.steps.currentRow() == dialog.current_index
    assert dialog.steps.currentItem().isSelected()

    dialog.next_button.click()

    assert dialog.steps.currentRow() == dialog.current_index
    assert dialog.steps.currentItem().isSelected()


def test_workflow_selection_rebuilds_the_ordered_review() -> None:
    QApplication.instance() or QApplication([])
    dialog = WorkflowDialog()
    workflows = {
        "radial": ("rdf", "cumulative_rdf"),
        "single": ("cumulative_rdf",),
    }
    dialog.configure(
        workflows,
        lambda _panel: None,
        lambda panel: ((_request(panel.analysis_type_value()), ""),),
    )

    for name, projects in workflows.items():
        dialog.choice.setCurrentIndex(dialog.choice.findData(name))
        assert tuple(panel.analysis_type_value() for panel in dialog.panels) == projects
        assert dialog.current_index == 0


def test_workflow_menu_opens_configured_review_below_terminal() -> None:
    QApplication.instance() or QApplication([])
    config = UserConfig(workflows={"radial": ("rdf", "cumulative_rdf")})
    save_config(config, config_path())
    window = MainWindow()

    window.menu_actions.workflow.trigger()

    dialog = window.windows.get(WorkflowDialog)
    assert dialog is not None
    assert dialog.isVisible()
    assert tuple(panel.analysis_type_value() for panel in dialog.panels) == config.workflows[
        "radial"
    ]
    actions = window.menu_actions.tools.actions()
    terminal_index = actions.index(window.menu_actions.terminal)
    assert actions[terminal_index + 1] is window.menu_actions.workflow
    window.close()
