"""Analysis backend selection and availability state."""

from __future__ import annotations

from typing import cast

from PySide6.QtWidgets import QComboBox, QWidget

from mdhelper.core.analysis import AnalysisBackend, AnalysisType
from mdhelper.core.errors import InputError
from mdhelper.gui.components.choices import choice_enabled, set_choice_enabled


class BackendChoice(QComboBox):
    """Choose a backend supported by the active analysis type."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._analysis_type: AnalysisType = "rdf"
        self._gromacs_configured = False
        self._gromacs_available = False
        self.setMinimumWidth(180)
        self._refresh()

    def set_analysis_type(self, analysis_type: AnalysisType) -> None:
        self._analysis_type = analysis_type
        self._refresh()

    def set_gromacs_configured(self, configured: bool) -> bool:
        if self._gromacs_configured == configured:
            return False
        self._gromacs_configured = configured
        self._refresh()
        return True

    def set_gromacs_available(self, available: bool) -> None:
        self._gromacs_available = available
        if self.findData("gromacs") >= 0:
            set_choice_enabled(self, "gromacs", available, "auto")
        self._set_gromacs_label()

    def set_gromacs_pending(self) -> None:
        self._gromacs_available = True
        if self.findData("gromacs") >= 0:
            set_choice_enabled(self, "gromacs", True, "auto")
        self._set_gromacs_label(pending=True)

    def value(self) -> AnalysisBackend:
        value = self.currentData()
        if value not in {"auto", "mdanalysis", "gromacs"}:
            raise InputError("No analysis backend was selected.")
        return cast(AnalysisBackend, value)

    def set_value(self, value: str) -> None:
        index = self.findData(value)
        if index < 0:
            raise InputError(
                f"Analysis backend {value!r} is unavailable for this analysis."
            )
        if not choice_enabled(self, value):
            raise InputError(
                f"Analysis backend {value!r} is unavailable.",
                "Configure a compatible GROMACS executable or select another backend.",
            )
        self.setCurrentIndex(index)

    def _refresh(self) -> None:
        previous = self.currentData()
        self.blockSignals(True)
        try:
            self.clear()
            self.addItem("Automatic", "auto")
            self.addItem("MDAnalysis", "mdanalysis")
            if self._gromacs_configured:
                self.addItem("GROMACS (local gmx)", "gromacs")
                set_choice_enabled(
                    self,
                    "gromacs",
                    self._gromacs_available,
                    "auto",
                )
            target = previous if isinstance(previous, str) else "auto"
            index = self.findData(target)
            if index < 0 or not choice_enabled(self, target):
                index = self.findData("auto")
            self.setCurrentIndex(index)
            self._set_gromacs_label()
        finally:
            self.blockSignals(False)

    def _set_gromacs_label(self, pending: bool = False) -> None:
        index = self.findData("gromacs")
        if index < 0:
            return
        suffix = (
            " - Checking..."
            if pending
            else ""
            if self._gromacs_available
            else " - Unavailable"
        )
        self.setItemText(index, f"GROMACS (local gmx){suffix}")
