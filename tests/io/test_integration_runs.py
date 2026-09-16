from __future__ import annotations

from pathlib import Path

import pytest

from mdhelper.core.errors import ConfigurationError
from mdhelper.io.integration_runs import (
    externalize_run_streams,
    hydrate_run_streams,
    read_output_texts,
)


def test_output_texts_round_trip_without_changing_bytes(tmp_path: Path) -> None:
    content = b"# Original data\r\n0.12345678901234567 12.345678901234567"
    source = tmp_path / "curve.xvg"
    source.write_bytes(content)
    outputs = read_output_texts([source])
    source.unlink()
    record = {"stdout": "progress\r\n", "stderr": "", "output_texts": outputs}
    directory = tmp_path / "archive"

    stored, paths = externalize_run_streams([record, record], directory, "run")

    assert len(paths) == len(set(paths)) == 6
    assert sum(path.read_bytes() == content for path in paths) == 2
    assert all("output_texts" not in item for item in stored)
    assert hydrate_run_streams(stored, directory, "run") == [record, record]
    assert record["output_texts"] == outputs


def test_original_names_avoid_reserved_and_repeated_names(tmp_path: Path) -> None:
    records = [
        {
            "stdout": "",
            "stderr": "",
            "output_texts": {"rdf.csv": "raw\n", "rdf.xvg": "0 1\n"},
        },
        {"stdout": "", "stderr": "", "output_texts": {"rdf.xvg": "0 2\n"}},
    ]
    reserved = ("result.json", "rdf.csv")

    stored, paths = externalize_run_streams(
        records, tmp_path, "run", original_names=True, reserved_names=reserved
    )

    assert {path.name for path in paths if path.suffix in {".csv", ".xvg"}} == {
        "rdf-2.csv",
        "rdf.xvg",
        "rdf-2.xvg",
    }
    assert (
        hydrate_run_streams(
            stored, tmp_path, "run", original_names=True, reserved_names=reserved
        )
        == records
    )


@pytest.mark.parametrize("remove", (False, True))
def test_changed_or_missing_raw_output_is_rejected(tmp_path: Path, remove: bool) -> None:
    record = {"stdout": "", "stderr": "", "output_texts": {"curve.xvg": "0 1\n"}}
    stored, paths = externalize_run_streams([record], tmp_path, "run")
    output = next(path for path in paths if path.suffix == ".xvg")
    if remove:
        output.unlink()
    else:
        output.write_text("0 2\n", encoding="ascii")

    with pytest.raises(ConfigurationError, match="fingerprint"):
        hydrate_run_streams(stored, tmp_path, "run")


@pytest.mark.parametrize(
    "outputs",
    (
        {"../escape.xvg": "0 1"},
        {"sub\\escape.xvg": "0 1"},
        {"/escape.xvg": "0 1"},
        {"C:escape.xvg": "0 1"},
        {"curve.xvg.": "0 1"},
        {"": "0 1"},
        {"curve.xvg": 42},
        [],
        None,
    ),
)
def test_invalid_output_metadata_rolls_back_streams(tmp_path: Path, outputs: object) -> None:
    record = {"stdout": "progress", "stderr": "", "output_texts": outputs}

    with pytest.raises(ConfigurationError):
        externalize_run_streams([record], tmp_path, "run")

    assert not list(tmp_path.iterdir())


def test_existing_output_is_not_overwritten(tmp_path: Path) -> None:
    output = tmp_path / "run.data-curve.xvg"
    output.write_bytes(b"original")
    record = {"stdout": "", "stderr": "", "output_texts": {"curve.xvg": "replacement"}}

    with pytest.raises(ConfigurationError, match="already exists"):
        externalize_run_streams([record], tmp_path, "run")

    assert list(tmp_path.iterdir()) == [output]
    assert output.read_bytes() == b"original"


def test_capture_rejects_duplicate_names_and_unreadable_outputs(tmp_path: Path) -> None:
    source = tmp_path / "curve.xvg"
    with pytest.raises(ConfigurationError, match="Could not read"):
        read_output_texts([source])
    source.write_bytes(b"0 1\n")
    with pytest.raises(ConfigurationError, match="Duplicate"):
        read_output_texts([source, source])
