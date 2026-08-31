"""Platform process-creation policy."""

from __future__ import annotations

import os
import subprocess


def hidden_window_flags(platform: str | None = None) -> int:
    system = os.name if platform is None else platform
    if system != "nt":
        return 0
    return int(vars(subprocess)["CREATE_NO_WINDOW"])
