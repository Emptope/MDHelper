from __future__ import annotations

import json
from pathlib import Path

import pytest

from mdhelper.cli import build_parser, main, parse_args


def test_cli_uses_explicit_config_path(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "settings" / "config.toml"
    assert main(["--config", str(path), "config", "init"]) == 0
    assert Path(capsys.readouterr().out.strip()) == path
    assert main(["--config", str(path), "config", "check"]) == 0
    checked = json.loads(capsys.readouterr().out)
    assert checked["path"] == str(path)
    assert checked["exists"]


@pytest.mark.parametrize(
    "values",
    [
        ["integrations", "run", "gromacs", "--cwd", "work", "--", "command", "--flag"],
        ["integrations", "run", "--cwd", "work", "gromacs", "--", "command", "--flag"],
    ],
)
def test_cli_integration_boundary_preserves_arguments(values: list[str]) -> None:
    args = parse_args(build_parser(), values)

    assert args.integration == "gromacs"
    assert args.cwd == "work"
    assert args.arguments == ["command", "--flag"]
