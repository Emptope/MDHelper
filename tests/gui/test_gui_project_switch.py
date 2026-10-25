from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QMessageBox

from mdhelper.core.analysis import AnalysisResult, RadialRequest
from mdhelper.gui.controllers.analysis_state import AnalysisPhase
from mdhelper.gui.controllers.session_state import SessionPhase
from mdhelper.gui.window import MainWindow
from mdhelper.gui.workflows.dialog import WorkflowDialog
from tests.support.molecular import write_trajectory


@pytest.mark.parametrize("saved", [False, True])
def test_open_folder_replaces_project_state(tmp_path: Path, monkeypatch, saved: bool) -> None:
    source = tmp_path / "system.gro"
    write_trajectory(source)
    target = tmp_path / "next"
    target.mkdir()
    window = MainWindow()
    try:
        first = window.session.create(tmp_path / "first", source, source, {})
        window.editor.set_root(first.root)
        window.project_actions._set_inputs(str(source), str(source), "")
        request = RadialRequest(
            analysis_type="rdf", topology=str(source), trajectory=str(source),
            reference="all", selection="all",
        )
        result = AnalysisResult(
            data={"radius_nm": [0.1, 0.2], "g_r": [1.0, 2.0]},
            parameters={}, units={}, diagnostics={},
            provenance={"input_files": {"topology": str(source), "trajectory": str(source)}},
            request=request.to_dict(),
        )
        window.session.request = request
        window.session.result = result
        window.results.show_result(result)
        window.results.set_project(True)
        window.analysis.set_details_available(True)
        window.system_actions.watch_index_file(first.root / "pending.ndx")
        window.workflow_actions.open()
        window.editor.open_path(str(source))
        if saved:
            project, _ = window.application.projects.ensure(target, source, source, {}, None)
            project.commit_result(request, result)
        manifest = first.manifest_path.read_bytes()
        monkeypatch.setattr(
            "mdhelper.gui.actions.project.QFileDialog.getExistingDirectory",
            lambda *_: str(target),
        )
        window.project_actions.open()
        assert window.editor.root == target
        assert window.editor.current_path is None
        assert not window.editor.tree.currentIndex().isValid()
        assert window.editor._loading_path is None
        assert window.editor._resume_path is None
        assert not window.editor.editor.toPlainText()
        assert window.system_actions.index_path is None
        assert not window.system_actions.index_timer.isActive()
        assert not window.analysis.details_button.isEnabled()
        assert window.job_controller.latest is None
        assert window.windows.get(WorkflowDialog) is None
        assert first.manifest_path.read_bytes() == manifest
        if saved:
            assert window.session.project.root == target
            assert window.load.inputs.topology.edit.text() == str(source)
            assert window.session.result.analysis_id == result.analysis_id
            assert window.results.result.analysis_id == result.analysis_id
            assert window.results.project_results.count() == 1
        else:
            assert window.session.project is None
            assert window.session.request is None
            assert window.session.result is None
            assert window.session.state.phase is SessionPhase.EMPTY
            assert not window.load.inputs.topology.edit.text()
            assert not window.load.index_groups
            assert not window.results.text.toPlainText()
            assert not window.results.plot_results()
            assert not window.results.project_available
            assert not window.results.export_button.isEnabled()
        assert target.name in window.windowTitle()
    finally:
        window.close()


@pytest.mark.parametrize("action", ["cancel", "discard_cancel", "invalid", "same", "finishing"])
def test_unsuccessful_or_same_project_open_preserves_session(
    tmp_path: Path, monkeypatch, action: str,
) -> None:
    source = tmp_path / "system.gro"
    write_trajectory(source)
    window = MainWindow()
    try:
        project = window.session.create(tmp_path / "first", source, source, {})
        window.editor.set_root(project.root)
        window.project_actions._set_inputs(str(source), str(source), "")
        window.results.show_message("retained")
        target = tmp_path / "next"
        if action != "invalid":
            target.mkdir()
        if action == "discard_cancel":
            monkeypatch.setattr(window.editor, "confirm_discard", lambda: False)
        if action == "finishing":
            window.analysis_actions.controller.state.phase = AnalysisPhase.RUNNING
            monkeypatch.setattr(QMessageBox, "information", lambda *_: None)
        errors = []
        monkeypatch.setattr(window.project_actions, "show_error", errors.append)
        monkeypatch.setattr(
            "mdhelper.gui.actions.project.QFileDialog.getExistingDirectory",
            lambda *_: "" if action == "cancel" else str(
                project.root if action == "same" else target
            ),
        )
        window.project_actions.open()
        assert window.session.project is project
        assert window.editor.root == project.root
        assert window.load.inputs.topology.edit.text() == str(source)
        assert window.results.text.toPlainText() == "retained"
        assert bool(errors) == (action == "invalid")
    finally:
        window.close()
