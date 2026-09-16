"""Contracts for shared analysis infrastructure."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from mdhelper.analysis.common import analysis_directory


def _symlinked_temp_base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(real, target_is_directory=True)
    except OSError:
        pytest.skip("Directory symlinks are unavailable")
    monkeypatch.setattr(tempfile, "tempdir", str(link))
    return real


def test_analysis_directory_yields_canonical_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = _symlinked_temp_base(tmp_path, monkeypatch)
    cache = real / "cache"

    with analysis_directory(None, "probe") as root:
        assert root == root.resolve()
        assert root.parent == real.resolve()
    with analysis_directory(cache, "probe") as root:
        assert root == root.resolve()
        assert root.parent == cache.resolve()
