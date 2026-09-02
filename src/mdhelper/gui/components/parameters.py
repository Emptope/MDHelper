"""Analysis-specific parameter forms and domain request construction."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
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
    RadialRequest,
    analysis_label,
)
from mdhelper.core.errors import InputError
from mdhelper.core.system import FrameRange
from mdhelper.gui.components.choices import choice_enabled, set_choice_enabled
from mdhelper.gui.components.layout import configure_form
from mdhelper.gui.components.paths import PathRow
from mdhelper.gui.components.queues import ItemQueue
from mdhelper.gui.components.radial import RadialParameters


class ParameterPanel(QGroupBox):
    energy_terms_requested = Signal(str)
    selection_hint_requested = Signal(str)
    analysis_backend_changed = Signal()
    backend_requirements_changed = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__("Analysis", parent)
        self._energy_source = ""
        self._gromacs_configured = False
        self._gromacs_available = False
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
        self.analysis_backend = QComboBox()
        self.analysis_backend.setMinimumWidth(180)
        choice.addWidget(self.analysis_backend)
        layout.addLayout(choice)
        self.rdf = RadialParameters(self._request_selection_hint)
        self.cn = RadialParameters(self._request_selection_hint)
        self.rdf_reference = self.rdf.reference
        self.rdf_selection = self.rdf.selection
        self.rdf_max = self.rdf.r_max
        self.rdf_bin_width = self.rdf.bin_width
        self.rdf_series = self.rdf.series
        self.rdf_inputs = self.rdf.inputs
        self.cn_reference = self.cn.reference
        self.cn_selection = self.cn.selection
        self.cn_max = self.cn.r_max
        self.cn_bin_width = self.cn.bin_width
        self.cn_series = self.cn.series
        self.cn_inputs = self.cn.inputs
        self.stack = QStackedWidget()
        self.stack.addWidget(self.rdf)
        self.stack.addWidget(self.cn)
        self.stack.addWidget(self._energy_page())
        self.analysis_choice.currentIndexChanged.connect(self._analysis_changed)
        self.analysis_backend.currentIndexChanged.connect(self._backend_changed)
        layout.addWidget(self.stack, 1)
        frames = QGroupBox("Frame Sampling")
        frames.setLayout(self._frames())
        layout.addWidget(frames)
        self.frames = frames
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
        previous = self.analysis_backend.currentData()
        self.analysis_backend.blockSignals(True)
        try:
            self.analysis_backend.clear()
            if self._analysis_type() == "energy":
                self.analysis_backend.addItem("Automatic", "auto")
                self.analysis_backend.addItem("MDAnalysis", "mdanalysis")
            else:
                self.analysis_backend.addItem("Automatic", "auto")
                self.analysis_backend.addItem("Native", "native")
                self.analysis_backend.addItem("MDAnalysis", "mdanalysis")
            default = "auto"
            if self._gromacs_configured:
                self.analysis_backend.addItem("GROMACS (local gmx)", "gromacs")
                set_choice_enabled(
                    self.analysis_backend,
                    "gromacs",
                    self._gromacs_available,
                    default,
                )
            target = previous if isinstance(previous, str) else default
            index = self.analysis_backend.findData(target)
            if index < 0 or not choice_enabled(self.analysis_backend, target):
                index = self.analysis_backend.findData(default)
            self.analysis_backend.setCurrentIndex(index)
            self._set_gromacs_label()
        finally:
            self.analysis_backend.blockSignals(False)
        self.analysis_backend_changed.emit()

    def set_gromacs_configured(self, configured: bool) -> None:
        if self._gromacs_configured == configured:
            return
        self._gromacs_configured = configured
        self._set_backend_choices()

    def _set_gromacs_label(self, pending: bool = False) -> None:
        index = self.analysis_backend.findData("gromacs")
        if index < 0:
            return
        suffix = (
            " - Checking..."
            if pending
            else ""
            if self._gromacs_available
            else " - Unavailable"
        )
        self.analysis_backend.setItemText(index, f"GROMACS (local gmx){suffix}")

    def set_gromacs_available(self, available: bool) -> None:
        self._gromacs_available = available
        if self.analysis_backend.findData("gromacs") >= 0:
            set_choice_enabled(self.analysis_backend, "gromacs", available, "auto")
        self._set_gromacs_label()

    def set_gromacs_pending(self) -> None:
        self._gromacs_available = True
        if self.analysis_backend.findData("gromacs") >= 0:
            set_choice_enabled(self.analysis_backend, "gromacs", True, "auto")
        self._set_gromacs_label(pending=True)

    def analysis_backend_value(self) -> AnalysisBackend:
        value = self.analysis_backend.currentData()
        if value not in {"auto", "native", "mdanalysis", "gromacs"}:
            raise InputError("No analysis backend was selected.")
        return cast(AnalysisBackend, value)

    def set_analysis_backend(self, value: str) -> None:
        index = self.analysis_backend.findData(value)
        if index < 0:
            raise InputError(
                f"Analysis backend {value!r} is unavailable for this analysis."
            )
        if not choice_enabled(self.analysis_backend, value):
            raise InputError(
                f"Analysis backend {value!r} is unavailable.",
                "Configure a compatible GROMACS executable or select another backend.",
            )
        self.analysis_backend.setCurrentIndex(index)

    def _energy_page(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        configure_form(form)
        self.energy_file = PathRow("Select GROMACS energy file", "GROMACS energy (*.edr)")
        self.energy_file.path_selected.connect(self._request_energy_terms)
        self.energy_file.edit.editingFinished.connect(self._request_energy_terms)
        self.energy_file.edit.textChanged.connect(self._energy_path_changed)
        self.energy_queue = ItemQueue("Available energy terms", "Analysis queue")
        form.addRow("Energy file", self.energy_file)
        form.addRow(self.energy_queue)
        return page

    def _request_energy_terms(self, path: str | None = None) -> None:
        value = (self.energy_file.edit.text() if path is None else path).strip()
        if Path(value).expanduser().is_file():
            self.energy_terms_requested.emit(value)

    def _energy_path_changed(self, path: str) -> None:
        value = path.strip()
        if value != self._energy_source:
            self._energy_source = ""
            self.energy_queue.clear_all()

    def set_energy_terms(self, path: str, terms: tuple[str, ...]) -> None:
        source = path.strip()
        selected = self.energy_queue.items() if source == self._energy_source else ()
        available = set(terms)
        self.energy_queue.set_available(terms)
        self.energy_queue.set_items(item for item in selected if item in available)
        self._energy_source = source

    def _frames(self) -> QGridLayout:
        grid = QGridLayout()
        grid.setContentsMargins(12, 10, 12, 10)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        self.start = QSpinBox()
        self.start.setRange(0, 2_000_000_000)
        self.stop = QLineEdit()
        self.stop.setPlaceholderText("end")
        self.stride = QSpinBox()
        self.stride.setRange(1, 2_000_000_000)
        self.stride.setValue(1)
        self.start.valueChanged.connect(
            lambda _value: self.backend_requirements_changed.emit()
        )
        self.stop.editingFinished.connect(self.backend_requirements_changed.emit)
        self.stride.valueChanged.connect(
            lambda _value: self.backend_requirements_changed.emit()
        )
        grid.addWidget(QLabel("First frame (0-based)"), 0, 0)
        grid.addWidget(self.start, 0, 1)
        grid.addWidget(QLabel("Stop frame (exclusive)"), 0, 2)
        grid.addWidget(self.stop, 0, 3)
        grid.addWidget(QLabel("Stride (frames)"), 1, 0)
        grid.addWidget(self.stride, 1, 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        return grid

    def frame_range(self) -> FrameRange:
        stop_text = self.stop.text().strip()
        return FrameRange(
            start=self.start.value(),
            stop=None if not stop_text else int(stop_text),
            stride=self.stride.value(),
        )

    def set_selection_groups(self, use_index: bool, groups: dict[str, int]) -> None:
        source = "index" if use_index else "expression"
        for control in (
            self.rdf_reference,
            self.rdf_selection,
            self.cn_reference,
            self.cn_selection,
        ):
            control.set_source(source, groups)
        self._sync_selection_hints()

    def _sync_selection_hints(self) -> None:
        backend = self.analysis_backend_value()
        expression = self.rdf_reference.source == "expression"
        visible = expression and backend in {"auto", "mdanalysis", "gromacs"}
        self.rdf_inputs.set_hint_visible(visible)
        self.cn_inputs.set_hint_visible(visible)
        gromacs = backend == "gromacs"
        labels = (
            ("Reference (-ref)", "Selection (-sel)")
            if gromacs
            else ("Reference", "Selection")
        )
        for editor in (self.rdf_inputs, self.cn_inputs):
            editor.reference_label.setText(labels[0])
            editor.selection_label.setText(labels[1])
        placeholders = (
            ("GROMACS Selection Language", "GROMACS Selection Language")
            if gromacs
            else ("selection", "selection")
        )
        for reference, selection in (
            (self.rdf_reference, self.rdf_selection),
            (self.cn_reference, self.cn_selection),
        ):
            reference.setPlaceholderText(placeholders[0])
            selection.setPlaceholderText(placeholders[1])
    def _request_selection_hint(self) -> None:
        self.selection_hint_requested.emit(self.analysis_backend_value())

    def request(self, common: dict[str, Any]) -> AnalysisRequest:
        choice = self._analysis_type()
        if choice == "rdf":
            request = self._pair_request(
                common,
                self.rdf_reference.text(),
                self.rdf_selection.text(),
            )
        elif choice == "cumulative_rdf":
            request = self._pair_request(
                common,
                self.cn_reference.text(),
                self.cn_selection.text(),
            )
        else:
            request = EnergyRequest(
                analysis_type="energy",
                energy_file=self.energy_file.edit.text().strip(),
                energy_terms=self.energy_queue.items(),
                analysis_backend=cast(EnergyBackend, self.analysis_backend_value()),
            )
        request.validate()
        return request

    def request_series(
        self, common: dict[str, Any]
    ) -> tuple[tuple[AnalysisRequest, str], ...]:
        """Build the independent requests represented by the active plot-series list."""

        choice = self._analysis_type()
        if choice == "energy":
            return ((self.request(common), ""),)
        selection = self.rdf_series if choice == "rdf" else self.cn_series
        pairs = selection.pairs()
        if not pairs:
            raise InputError(
                "No plot series is enabled.",
                "Enable at least one selection pair or clear the list to use the current pair.",
            )
        runs: list[tuple[AnalysisRequest, str]] = []
        for pair in pairs:
            item = self._pair_request(
                common,
                pair.reference,
                pair.selection,
                pair.parameters,
            )
            runs.append((item, pair.label))
        return tuple(runs)

    def _pair_request(
        self,
        common: dict[str, Any],
        reference: str,
        selection: str,
        parameters: dict[str, int | float] | None = None,
    ) -> AnalysisRequest:
        values = parameters or {}
        common = {**common, "analysis_backend": self.analysis_backend_value()}
        if self._analysis_type() == "rdf":
            request = RadialRequest(
                analysis_type="rdf",
                reference=reference,
                selection=selection,
                r_max_nm=float(values.get("r_max_nm", self.rdf_max.value())),
                bin_width_nm=float(
                    values.get("bin_width_nm", self.rdf_bin_width.value())
                ),
                **common,
            )
        else:
            request = RadialRequest(
                analysis_type="cumulative_rdf",
                reference=reference,
                selection=selection,
                r_max_nm=float(values.get("r_max_nm", self.cn_max.value())),
                bin_width_nm=float(
                    values.get("bin_width_nm", self.cn_bin_width.value())
                ),
                **common,
            )
        request.validate()
        return request

    def apply_request(self, request: AnalysisRequest) -> None:
        if isinstance(request, RadialRequest):
            self.start.setValue(request.frames.start)
            self.stop.setText(
                "" if request.frames.stop is None else str(request.frames.stop)
            )
            self.stride.setValue(request.frames.stride)
            self._set_analysis(request.analysis_type)
        if isinstance(request, RadialRequest) and request.analysis_type == "rdf":
            self.rdf.apply_request(request)
        elif isinstance(request, RadialRequest):
            self.cn.apply_request(request)
        elif isinstance(request, EnergyRequest):
            self._set_analysis("energy")
            self.energy_file.edit.setText(request.energy_file)
            self._energy_source = request.energy_file
            self.energy_queue.set_available(())
            self.energy_queue.set_items(request.energy_terms)
        else:
            raise InputError("Unknown analysis request type.")
        self.set_analysis_backend(request.analysis_backend)

    def reset(self) -> None:
        self._set_analysis("rdf")
        self.rdf.reset()
        self.cn.reset()
        self.energy_file.edit.clear()
        self.energy_queue.clear_all()
        self._energy_source = ""
        self.start.setValue(0)
        self.stop.clear()
        self.stride.setValue(1)

    def _analysis_type(self) -> AnalysisType:
        return cast(AnalysisType, self.analysis_choice.currentData())

    def analysis_type_value(self) -> AnalysisType:
        return self._analysis_type()

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
