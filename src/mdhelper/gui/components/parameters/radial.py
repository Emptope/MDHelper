"""Reusable radial-analysis parameter controls."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtWidgets import QDoubleSpinBox, QFormLayout, QWidget

from mdhelper.core.analysis import AnalysisBackend, AnalysisType, RadialRequest
from mdhelper.core.errors import InputError
from mdhelper.gui.components.layout import configure_form
from mdhelper.gui.components.selections import (
    SelectionField,
    SelectionInput,
    SelectionPair,
    SelectionPairEditor,
    SelectionQueue,
)


class RadialParameters(QWidget):
    """Own the shared selection and distance controls for a radial analysis."""

    def __init__(
        self,
        show_hint: Callable[[], None],
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.reference = SelectionInput()
        self.reference.setPlaceholderText("selection")
        self.selection = SelectionInput()
        self.selection.setPlaceholderText("selection")
        self.r_max = QDoubleSpinBox()
        self.r_max.setRange(0.001, 100.0)
        self.r_max.setDecimals(4)
        self.r_max.setValue(1.0)
        self.bin_width = QDoubleSpinBox()
        self.bin_width.setRange(0.000001, 100.0)
        self.bin_width.setDecimals(6)
        self.bin_width.setValue(0.002)
        self.queue = SelectionQueue(
            self.reference,
            self.selection,
            (
                SelectionField("r_max_nm", "R max (nm)", "float"),
                SelectionField("bin_width_nm", "Bin width (nm)", "float"),
            ),
            labels=("Reference", "Selection"),
        )
        self._sync_defaults()
        self.queue.row_loaded.connect(self._load_pair)
        self.r_max.valueChanged.connect(
            lambda value: self.queue.set_current_parameter("r_max_nm", value)
        )
        self.bin_width.valueChanged.connect(
            lambda value: self.queue.set_current_parameter("bin_width_nm", value)
        )
        self.inputs = SelectionPairEditor(
            self.reference,
            self.selection,
            show_hint,
        )
        form = QFormLayout(self)
        configure_form(form)
        form.addRow(self.inputs)
        form.addRow("Plot Queue", self.queue)
        form.addRow("Maximum radius (nm)", self.r_max)
        form.addRow("Bin width (nm)", self.bin_width)

    def request(
        self,
        analysis_type: AnalysisType,
        common: dict[str, Any],
        backend: AnalysisBackend,
        pair: SelectionPair | None = None,
    ) -> RadialRequest:
        parameters = {} if pair is None else pair.parameters
        request = RadialRequest(
            analysis_type=analysis_type,
            reference=self.reference.text() if pair is None else pair.reference,
            selection=self.selection.text() if pair is None else pair.selection,
            r_max_nm=float(parameters.get("r_max_nm", self.r_max.value())),
            bin_width_nm=float(parameters.get("bin_width_nm", self.bin_width.value())),
            **{**common, "analysis_backend": backend},
        )
        request.validate()
        return request

    def queued_requests(
        self,
        analysis_type: AnalysisType,
        common: dict[str, Any],
        backend: AnalysisBackend,
    ) -> tuple[tuple[RadialRequest, str], ...]:
        pairs = self.queue.pairs()
        if not pairs:
            raise InputError(
                "No queue item is enabled.",
                "Enable at least one selection pair or clear the list to use the current pair.",
            )
        return tuple(
            (self.request(analysis_type, common, backend, pair), pair.label)
            for pair in pairs
        )

    def set_selection_groups(self, use_index: bool, groups: dict[str, int]) -> None:
        source = "index" if use_index else "expression"
        self.reference.set_source(source, groups)
        self.selection.set_source(source, groups)

    def set_backend(self, backend: AnalysisBackend) -> None:
        expression = self.reference.source == "expression"
        self.inputs.set_hint_visible(expression)
        gromacs = backend == "gromacs"
        self.inputs.reference_label.setText("Reference (-ref)" if gromacs else "Reference")
        self.inputs.selection_label.setText("Selection (-sel)" if gromacs else "Selection")
        placeholder = "GROMACS Selection Language" if gromacs else "selection"
        self.reference.setPlaceholderText(placeholder)
        self.selection.setPlaceholderText(placeholder)

    def apply_request(self, request: RadialRequest) -> None:
        self.reference.setText(request.reference)
        self.selection.setText(request.selection)
        self.r_max.setValue(request.r_max_nm)
        self.bin_width.setValue(request.bin_width_nm)

    def reset(self) -> None:
        self.reference.setText("")
        self.selection.setText("")
        self.queue.clear()
        self.r_max.setValue(1.0)
        self.bin_width.setValue(0.002)

    def _sync_defaults(self) -> None:
        self.queue.set_defaults(
            {
                "r_max_nm": self.r_max.value(),
                "bin_width_nm": self.bin_width.value(),
            }
        )

    def _load_pair(self, pair: SelectionPair) -> None:
        self.r_max.blockSignals(True)
        self.bin_width.blockSignals(True)
        try:
            self.r_max.setValue(float(pair.parameters["r_max_nm"]))
            self.bin_width.setValue(float(pair.parameters["bin_width_nm"]))
        finally:
            self.r_max.blockSignals(False)
            self.bin_width.blockSignals(False)
