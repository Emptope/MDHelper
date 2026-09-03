from __future__ import annotations

import pytest

from mdhelper.core.analysis import AnalysisResult, EnergyRequest, RadialRequest
from mdhelper.gui.controllers.analysis_state import AnalysisBatch, AnalysisPhase
from mdhelper.gui.controllers.session_state import SessionPhase, SessionState
from mdhelper.gui.controllers.system_state import InspectionPhase, InspectionState
from mdhelper.gui.plotting.state import PlotSession


def _request(selection: str) -> RadialRequest:
    return RadialRequest(
        analysis_type="rdf",
        topology="topology.gro",
        trajectory="trajectory.xtc",
        reference="reference",
        selection=selection,
    )


def _energy_result() -> AnalysisResult:
    request = EnergyRequest(
        analysis_type="energy",
        energy_file="energy.edr",
        energy_terms=("first", "second", "third"),
    )
    return AnalysisResult(
        analysis_type="energy",
        data={
            "time_ps": [0.0, 1.0],
            "series": {
                "first": [1.0, 2.0],
                "second": [2.0, 3.0],
                "third": [3.0, 4.0],
            },
        },
        parameters={},
        units={"time_ps": "ps", "series": "value"},
        diagnostics={},
        provenance={},
        request=request.to_dict(),
    )


def test_analysis_batch_owns_queue_transitions() -> None:
    first = (_request("first"), "First")
    second = (_request("second"), "Second")
    batch = AnalysisBatch()

    batch.start((first, second))

    assert batch.phase is AnalysisPhase.RUNNING
    assert batch.total == 2
    assert batch.position == 0
    assert batch.take_next() == first
    assert batch.position == 1
    assert batch.complete_current() is False
    assert batch.take_next() == second
    assert batch.complete_current() is True
    assert batch.phase is AnalysisPhase.IDLE
    assert batch.total == 0


def test_analysis_batch_cancel_discards_pending_work() -> None:
    batch = AnalysisBatch()
    batch.start(((_request("first"), ""), (_request("second"), "")))
    batch.take_next()

    batch.cancel()

    assert batch.phase is AnalysisPhase.CANCELLING
    assert batch.pending == 0
    assert batch.complete_current() is True
    assert batch.phase is AnalysisPhase.IDLE


def test_analysis_batch_rejects_invalid_transitions() -> None:
    batch = AnalysisBatch()

    with pytest.raises(ValueError):
        batch.start(())
    with pytest.raises(RuntimeError):
        batch.take_next()

    batch.start(((_request("first"), ""),))
    with pytest.raises(RuntimeError):
        batch.start(((_request("second"), ""),))
    with pytest.raises(RuntimeError):
        batch.complete_current()


def test_inspection_state_tracks_work_and_role_data() -> None:
    state = InspectionState()

    state.schedule({"SOL": "solvent"})
    assert state.phase is InspectionPhase.PENDING
    assert state.pending_roles == {"SOL": "solvent"}

    state.begin()
    state.complete({"SOL": object()}, {"SOL": {"source": "project_manifest"}})

    assert state.phase is InspectionPhase.READY
    assert set(state.suggestions) == {"SOL"}
    assert set(state.provenance) == {"SOL"}

    state.schedule({})
    state.begin()
    state.fail()
    assert state.phase is InspectionPhase.FAILED

    state.reset()
    assert state.phase is InspectionPhase.EMPTY
    assert state.suggestions == {}
    assert state.provenance == {}


def test_project_session_state_has_explicit_transitions() -> None:
    state = SessionState()

    state.ready()
    assert state.phase is SessionPhase.READY
    state.start()
    assert state.phase is SessionPhase.RUNNING
    state.complete()
    assert state.phase is SessionPhase.COMPLETE
    state.start()
    state.complete()
    state.start()
    state.abort(project_open=True)
    assert state.phase is SessionPhase.READY
    state.start()
    state.abort(project_open=False)
    assert state.phase is SessionPhase.EMPTY
    state.ready()
    state.reset()
    assert state.phase is SessionPhase.EMPTY

    with pytest.raises(RuntimeError):
        state.complete()


def test_plot_session_owns_grouping_and_singleton_normalization() -> None:
    state = PlotSession()

    assert state.add(_energy_result()) == (0, 1, 2)
    assert state.combine((0, 1), 0)
    assert state.entries[0].group == state.entries[1].group
    assert len(state.models()) == 2

    state.remove((0,))

    assert all(not entry.group for entry in state.entries)
    assert len(state.models()) == 2
