"""GUI asset loading."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QIcon

ICON_ROOT = Path(__file__).parents[1] / "resources" / "icons"


def application_icon() -> QIcon:
    """Load the application icon from packaged resources."""

    return QIcon(str(ICON_ROOT / "mdhelper.png"))
