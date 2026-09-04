"""Energy-analysis parameter controls."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFormLayout, QWidget

from mdhelper.core.analysis import AnalysisBackend, EnergyRequest
from mdhelper.gui.components.layout import configure_form
from mdhelper.gui.components.paths import PathRow
from mdhelper.gui.components.queues import ItemQueue


class EnergyParameters(QWidget):
    """Own the energy file and ordered term selection."""

    terms_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._source = ""
        self.file = PathRow("Select GROMACS energy file", "GROMACS energy (*.edr)")
        self.file.path_selected.connect(self._request_terms)
        self.file.edit.editingFinished.connect(self._request_terms)
        self.file.edit.textChanged.connect(self._path_changed)
        self.queue = ItemQueue("Available energy terms", "Analysis queue")
        form = QFormLayout(self)
        configure_form(form)
        form.addRow("Energy file", self.file)
        form.addRow(self.queue)

    def path(self) -> str:
        return cast(str, self.file.edit.text()).strip()

    def request(self, backend: AnalysisBackend) -> EnergyRequest:
        request = EnergyRequest(
            analysis_type="energy",
            energy_file=self.path(),
            energy_terms=self.queue.items(),
            analysis_backend=backend,
        )
        request.validate()
        return request

    def set_terms(self, path: str, terms: tuple[str, ...]) -> None:
        source = path.strip()
        selected = self.queue.items() if source == self._source else ()
        available = set(terms)
        self.queue.set_available(terms)
        self.queue.set_items(item for item in selected if item in available)
        self._source = source

    def apply_request(self, request: EnergyRequest) -> None:
        self.file.set_path(request.energy_file)
        self._source = request.energy_file
        self.queue.set_available(())
        self.queue.set_items(request.energy_terms)

    def reset(self) -> None:
        self.file.edit.clear()
        self.queue.clear_all()
        self._source = ""

    def _request_terms(self, path: str | None = None) -> None:
        value = self.path() if path is None else path.strip()
        if Path(value).expanduser().is_file():
            self.terms_requested.emit(value)

    def _path_changed(self, path: str) -> None:
        if path.strip() != self._source:
            self._source = ""
            self.queue.clear_all()
