"""Analysis-specific parameter forms and domain request construction."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
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

from mdhelper.core.analysis import AnalysisRequest, AnalysisType, analysis_label
from mdhelper.core.errors import InputError
from mdhelper.core.system import FrameRange
from mdhelper.gui.choices import choice_enabled
from mdhelper.gui.dialogs import PathRow
from mdhelper.gui.queues import ItemQueue
from mdhelper.gui.selections import (
    SelectionField,
    SelectionHintDialog,
    SelectionInput,
    SelectionPair,
    SelectionPairEditor,
    SelectionSeries,
)


class ParameterPanel(QGroupBox):
    energy_terms_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__("Analysis Settings", parent)
        self._energy_source = ""
        self._hint_dialog: SelectionHintDialog | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)
        choice = QHBoxLayout()
        choice.addWidget(QLabel("Analysis type"))
        self.analysis_choice = QComboBox()
        for analysis_type in ("rdf", "cumulative_rdf", "energy"):
            self.analysis_choice.addItem(analysis_label(analysis_type), analysis_type)
        choice.addWidget(self.analysis_choice, 1)
        layout.addLayout(choice)
        self.stack = QStackedWidget()
        self.stack.addWidget(self._rdf_page())
        self.stack.addWidget(self._coordination_page())
        self.stack.addWidget(self._energy_page())
        self.analysis_choice.currentIndexChanged.connect(self._analysis_changed)
        layout.addWidget(self.stack, 1)
        frames = QGroupBox("Frame Sampling")
        frames.setLayout(self._frames())
        layout.addWidget(frames)
        self.frames = frames

    def _analysis_changed(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        self.frames.setVisible(self._analysis_type() != "energy")

    def _rdf_page(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self._compact_form(form)
        self.rdf_reference = SelectionInput()
        self.rdf_reference.setPlaceholderText("selection")
        self.rdf_selection = SelectionInput()
        self.rdf_selection.setPlaceholderText("selection")
        self.rdf_max = QDoubleSpinBox()
        self.rdf_max.setRange(0.001, 100.0)
        self.rdf_max.setDecimals(4)
        self.rdf_max.setValue(1.0)
        self.rdf_bin_width = QDoubleSpinBox()
        self.rdf_bin_width.setRange(0.000001, 100.0)
        self.rdf_bin_width.setDecimals(6)
        self.rdf_bin_width.setValue(0.002)
        self.rdf_series = SelectionSeries(
            self.rdf_reference,
            self.rdf_selection,
            (
                SelectionField("r_max_nm", "R max (nm)", "float"),
                SelectionField("bin_width_nm", "Bin width (nm)", "float"),
            ),
            labels=("Reference", "Selection"),
        )
        self._set_rdf_defaults()
        self.rdf_series.row_loaded.connect(self._load_rdf_pair)
        self.rdf_max.valueChanged.connect(
            lambda value: self.rdf_series.set_current_parameter("r_max_nm", value)
        )
        self.rdf_bin_width.valueChanged.connect(
            lambda value: self.rdf_series.set_current_parameter("bin_width_nm", value)
        )
        self.rdf_inputs = SelectionPairEditor(
            self.rdf_reference,
            self.rdf_selection,
            self._show_selection_hint,
        )
        form.addRow(self.rdf_inputs)
        form.addRow("Plot series", self.rdf_series)
        form.addRow("Maximum radius (nm)", self.rdf_max)
        form.addRow("Bin width (nm)", self.rdf_bin_width)
        return page

    def _coordination_page(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self._compact_form(form)
        self.cn_reference = SelectionInput()
        self.cn_reference.setPlaceholderText("selection")
        self.cn_selection = SelectionInput()
        self.cn_selection.setPlaceholderText("selection")
        self.cn_max = QDoubleSpinBox()
        self.cn_max.setRange(0.001, 100.0)
        self.cn_max.setDecimals(4)
        self.cn_max.setValue(1.0)
        self.cn_bin_width = QDoubleSpinBox()
        self.cn_bin_width.setRange(0.000001, 100.0)
        self.cn_bin_width.setDecimals(6)
        self.cn_bin_width.setValue(0.002)
        self.cn_series = SelectionSeries(
            self.cn_reference,
            self.cn_selection,
            (
                SelectionField("r_max_nm", "R max (nm)", "float"),
                SelectionField("bin_width_nm", "Bin width (nm)", "float"),
            ),
            labels=("Reference", "Selection"),
        )
        self._set_cn_defaults()
        self.cn_series.row_loaded.connect(self._load_cn_pair)
        self.cn_max.valueChanged.connect(
            lambda value: self.cn_series.set_current_parameter("r_max_nm", value)
        )
        self.cn_bin_width.valueChanged.connect(
            lambda value: self.cn_series.set_current_parameter("bin_width_nm", value)
        )
        self.cn_inputs = SelectionPairEditor(
            self.cn_reference,
            self.cn_selection,
            self._show_selection_hint,
        )
        form.addRow(self.cn_inputs)
        form.addRow("Plot series", self.cn_series)
        form.addRow("Maximum radius (nm)", self.cn_max)
        form.addRow("Bin width (nm)", self.cn_bin_width)
        return page

    def _energy_page(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self._compact_form(form)
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
        grid.addWidget(QLabel("First frame (0-based)"), 0, 0)
        grid.addWidget(self.start, 0, 1)
        grid.addWidget(QLabel("Stop frame (exclusive)"), 0, 2)
        grid.addWidget(self.stop, 0, 3)
        grid.addWidget(QLabel("Stride"), 1, 0)
        grid.addWidget(self.stride, 1, 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        return grid

    @staticmethod
    def _compact_form(form: QFormLayout) -> None:
        form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)

    def frame_range(self) -> FrameRange:
        stop_text = self.stop.text().strip()
        return FrameRange(
            start=self.start.value(),
            stop=None if not stop_text else int(stop_text),
            stride=self.stride.value(),
        )

    def _set_rdf_defaults(self, _value: object = None) -> None:
        self.rdf_series.set_defaults(
            {
                "r_max_nm": self.rdf_max.value(),
                "bin_width_nm": self.rdf_bin_width.value(),
            }
        )

    def _set_cn_defaults(self, _value: object = None) -> None:
        self.cn_series.set_defaults(
            {
                "r_max_nm": self.cn_max.value(),
                "bin_width_nm": self.cn_bin_width.value(),
            }
        )

    def _load_rdf_pair(self, pair: SelectionPair) -> None:
        values = pair.parameters
        self.rdf_max.blockSignals(True)
        self.rdf_bin_width.blockSignals(True)
        try:
            self.rdf_max.setValue(float(values["r_max_nm"]))
            self.rdf_bin_width.setValue(float(values["bin_width_nm"]))
        finally:
            self.rdf_max.blockSignals(False)
            self.rdf_bin_width.blockSignals(False)

    def _load_cn_pair(self, pair: SelectionPair) -> None:
        values = pair.parameters
        self.cn_max.blockSignals(True)
        self.cn_bin_width.blockSignals(True)
        try:
            self.cn_max.setValue(float(values["r_max_nm"]))
            self.cn_bin_width.setValue(float(values["bin_width_nm"]))
        finally:
            self.cn_max.blockSignals(False)
            self.cn_bin_width.blockSignals(False)

    def set_selection_source(self, source: str, groups: dict[str, int]) -> None:
        for control in (
            self.rdf_reference,
            self.rdf_selection,
            self.cn_reference,
            self.cn_selection,
        ):
            control.set_source(source, groups)
        visible = source == "expression"
        self.rdf_inputs.set_hint_visible(visible)
        self.cn_inputs.set_hint_visible(visible)

    def _show_selection_hint(self) -> None:
        if self._hint_dialog is None:
            self._hint_dialog = SelectionHintDialog(self)
        self._hint_dialog.show()
        self._hint_dialog.raise_()
        self._hint_dialog.activateWindow()

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
            request = AnalysisRequest(
                analysis_type="energy",
                reference="",
                selection=None,
                energy_file=self.energy_file.edit.text().strip(),
                energy_terms=self.energy_queue.items(),
                **common,
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
        if self._analysis_type() == "rdf":
            request = AnalysisRequest(
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
            request = AnalysisRequest(
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
        self.start.setValue(request.frames.start)
        self.stop.setText("" if request.frames.stop is None else str(request.frames.stop))
        self.stride.setValue(request.frames.stride)
        if request.analysis_type == "rdf":
            self._set_analysis("rdf")
            self.rdf_reference.setText(request.reference)
            self.rdf_selection.setText(request.selection or "")
            self.rdf_max.setValue(request.r_max_nm)
            self.rdf_bin_width.setValue(request.bin_width_nm)
        elif request.analysis_type == "cumulative_rdf":
            self._set_analysis("cumulative_rdf")
            self.cn_reference.setText(request.reference)
            self.cn_selection.setText(request.selection or "")
            self.cn_max.setValue(request.r_max_nm)
            self.cn_bin_width.setValue(request.bin_width_nm)
        else:
            self._set_analysis("energy")
            self.energy_file.edit.setText(request.energy_file or "")
            self._energy_source = request.energy_file or ""
            self.energy_queue.set_available(())
            self.energy_queue.set_items(request.energy_terms)

    def reset(self) -> None:
        self._set_analysis("rdf")
        for control in (
            self.rdf_reference,
            self.rdf_selection,
            self.cn_reference,
            self.cn_selection,
        ):
            control.setText("")
        self.rdf_series.clear()
        self.cn_series.clear()
        self.energy_file.edit.clear()
        self.energy_queue.clear_all()
        self._energy_source = ""
        self.rdf_max.setValue(1.0)
        self.rdf_bin_width.setValue(0.002)
        self.cn_max.setValue(1.0)
        self.cn_bin_width.setValue(0.002)
        self.start.setValue(0)
        self.stop.clear()
        self.stride.setValue(1)

    def _analysis_type(self) -> AnalysisType:
        return cast(AnalysisType, self.analysis_choice.currentData())

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
