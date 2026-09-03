"""Composite analysis parameter panel."""

from __future__ import annotations

from typing import Any, cast

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from mdhelper.core.analysis import (
    AnalysisBackend,
    AnalysisRequest,
    AnalysisType,
    EnergyBackend,
    EnergyRequest,
    RadialBackend,
    RadialRequest,
    analysis_label,
)
from mdhelper.core.errors import InputError
from mdhelper.core.system import FrameRange
from mdhelper.gui.components.choices import choice_enabled
from mdhelper.gui.components.parameters.backend import BackendChoice
from mdhelper.gui.components.parameters.energy import EnergyParameters
from mdhelper.gui.components.parameters.frames import FrameRangeParameters
from mdhelper.gui.components.parameters.radial import RadialParameters


class ParameterPanel(QGroupBox):
    """Coordinate the parameter editor for the selected analysis type."""

    energy_terms_requested = Signal(str)
    selection_hint_requested = Signal(str)
    analysis_backend_changed = Signal()
    backend_requirements_changed = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__("Analysis", parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        choice = QHBoxLayout()
        choice.addWidget(QLabel("Type"))
        self.analysis_choice = QComboBox()
        for analysis_type in ("rdf", "cumulative_rdf", "energy"):
            self.analysis_choice.addItem(analysis_label(analysis_type), analysis_type)
        choice.addWidget(self.analysis_choice, 1)
        choice.addWidget(QLabel("Backend"))
        self.analysis_backend = BackendChoice()
        choice.addWidget(self.analysis_backend)
        layout.addLayout(choice)

        self.rdf = RadialParameters(self._request_selection_hint)
        self.cumulative = RadialParameters(self._request_selection_hint)
        self.energy = EnergyParameters()
        self.stack = QStackedWidget()
        self.stack.addWidget(self.rdf)
        self.stack.addWidget(self.cumulative)
        self.stack.addWidget(self.energy)
        layout.addWidget(self.stack, 1)

        self.frames = FrameRangeParameters()
        layout.addWidget(self.frames)

        self.analysis_choice.currentIndexChanged.connect(self._analysis_changed)
        self.analysis_backend.currentIndexChanged.connect(self._backend_changed)
        self.energy.terms_requested.connect(self.energy_terms_requested.emit)
        self.frames.changed.connect(self.backend_requirements_changed.emit)
        self._set_backend_choices()

    def _backend_changed(self, _index: int) -> None:
        self._sync_selection_hints()
        self.analysis_backend_changed.emit()

    def _analysis_changed(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        self.frames.setVisible(self._analysis_type() != "energy")
        self._set_backend_choices()
        self.backend_requirements_changed.emit()

    def _set_backend_choices(self) -> None:
        self.analysis_backend.set_analysis_type(self._analysis_type())
        self.analysis_backend_changed.emit()

    def set_gromacs_configured(self, configured: bool) -> None:
        if self.analysis_backend.set_gromacs_configured(configured):
            self.analysis_backend_changed.emit()

    def set_gromacs_available(self, available: bool) -> None:
        self.analysis_backend.set_gromacs_available(available)

    def set_gromacs_pending(self) -> None:
        self.analysis_backend.set_gromacs_pending()

    def analysis_backend_value(self) -> AnalysisBackend:
        return self.analysis_backend.value()

    def set_analysis_backend(self, value: str) -> None:
        self.analysis_backend.set_value(value)

    def set_energy_terms(self, path: str, terms: tuple[str, ...]) -> None:
        self.energy.set_terms(path, terms)

    def energy_path(self) -> str:
        return self.energy.path()

    def frame_range(self) -> FrameRange:
        return self.frames.value()

    def set_selection_groups(self, use_index: bool, groups: dict[str, int]) -> None:
        self.rdf.set_selection_groups(use_index, groups)
        self.cumulative.set_selection_groups(use_index, groups)
        self._sync_selection_hints()

    def _sync_selection_hints(self) -> None:
        backend = cast(RadialBackend, self.analysis_backend_value())
        self.rdf.set_backend(backend)
        self.cumulative.set_backend(backend)

    def _request_selection_hint(self) -> None:
        self.selection_hint_requested.emit(self.analysis_backend_value())

    def request(self, common: dict[str, Any]) -> AnalysisRequest:
        analysis_type = self._analysis_type()
        if analysis_type == "energy":
            return self.energy.request(
                cast(EnergyBackend, self.analysis_backend_value())
            )
        parameters = self.rdf if analysis_type == "rdf" else self.cumulative
        return parameters.request(
            analysis_type,
            common,
            cast(RadialBackend, self.analysis_backend_value()),
        )

    def request_series(
        self, common: dict[str, Any]
    ) -> tuple[tuple[AnalysisRequest, str], ...]:
        """Build the independent requests represented by the active series list."""

        analysis_type = self._analysis_type()
        if analysis_type == "energy":
            return ((self.request(common), ""),)
        parameters = self.rdf if analysis_type == "rdf" else self.cumulative
        return parameters.request_series(
            analysis_type,
            common,
            cast(RadialBackend, self.analysis_backend_value()),
        )

    def apply_request(self, request: AnalysisRequest) -> None:
        if isinstance(request, RadialRequest):
            self.frames.apply(request.frames)
            self._set_analysis(request.analysis_type)
            parameters = self.rdf if request.analysis_type == "rdf" else self.cumulative
            parameters.apply_request(request)
        elif isinstance(request, EnergyRequest):
            self._set_analysis("energy")
            self.energy.apply_request(request)
        else:
            raise InputError("Unknown analysis request type.")
        self.set_analysis_backend(request.analysis_backend)

    def reset(self) -> None:
        self._set_analysis("rdf")
        self.rdf.reset()
        self.cumulative.reset()
        self.energy.reset()
        self.frames.reset()

    def _analysis_type(self) -> AnalysisType:
        return cast(AnalysisType, self.analysis_choice.currentData())

    def analysis_type_value(self) -> AnalysisType:
        return self._analysis_type()

    def set_analysis_type(self, analysis_type: AnalysisType) -> None:
        self._set_analysis(analysis_type)

    def requires_selections(self) -> bool:
        return self._analysis_type() != "energy"

    def _set_analysis(self, analysis_type: AnalysisType) -> None:
        index = self.analysis_choice.findData(analysis_type)
        if index >= 0:
            if not choice_enabled(self.analysis_choice, analysis_type):
                raise InputError(
                    f"Analysis type {analysis_label(analysis_type)!r} is unavailable.",
                    "Configure a compatible GROMACS executable or choose another analysis.",
                )
            self.analysis_choice.setCurrentIndex(index)
