"""Shared availability handling for combo-box choices."""

from __future__ import annotations

from PySide6.QtGui import QStandardItemModel, QWheelEvent
from PySide6.QtWidgets import QComboBox


class NoWheelComboBox(QComboBox):
    def wheelEvent(self, event: QWheelEvent) -> None:
        event.ignore()


def choice_enabled(combo: QComboBox, value: object) -> bool:
    index = combo.findData(value)
    if index < 0:
        return False
    model = combo.model()
    return isinstance(model, QStandardItemModel) and model.item(index).isEnabled()


def set_choice_enabled(
    combo: QComboBox,
    value: object,
    enabled: bool,
    fallback: object,
) -> None:
    index = combo.findData(value)
    fallback_index = combo.findData(fallback)
    model = combo.model()
    if index < 0 or fallback_index < 0 or not isinstance(model, QStandardItemModel):
        raise RuntimeError("Combo-box availability requires registered standard items.")
    model.item(index).setEnabled(enabled)
    if not enabled and combo.currentIndex() == index:
        combo.setCurrentIndex(fallback_index)
