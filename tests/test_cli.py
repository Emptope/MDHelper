from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonargparse import ArgumentParser, Namespace

from mdhelper.cli import build_parser, main, parse_args


def test_cli_uses_native_jsonargparse_namespaces() -> None:
    parser = build_parser()
    args = parse_args(
        parser,
        [
            "analyze",
            "energy",
            "--energy-file",
            "run.edr",
            "--terms",
            "[Potential, Temperature]",
            "--output",
            "out",
        ],
    )

    assert isinstance(parser, ArgumentParser)
    assert isinstance(args, Namespace)
    assert args.command == "analyze"
    assert args.analyze.analysis == "energy"
    assert args.analyze.energy.terms == ["Potential", "Temperature"]


def test_cli_uses_explicit_settings_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "settings" / "config.toml"
    assert main(["--settings", str(path), "config", "init"]) == 0
    assert Path(capsys.readouterr().out.strip()) == path
    assert main(["--settings", str(path), "config", "check"]) == 0
    checked = json.loads(capsys.readouterr().out)
    assert checked["path"] == str(path)
    assert checked["exists"]


def test_cli_loads_structured_arguments_from_file(tmp_path: Path) -> None:
    path = tmp_path / "args.json"
    path.write_text(
        json.dumps(
            {
                "command": "analyze",
                "analyze": {
                    "analysis": "rdf",
                    "rdf": {
                        "topology": "system.gro",
                        "trajectory": "run.xtc",
                        "reference": "A",
                        "selection": "B",
                        "roles": {"SOL": "solvent"},
                        "output": "out",
                    },
                },
            }
        ),
        encoding="ascii",
    )

    args = parse_args(build_parser(), ["--args-file", str(path)])

    assert args.analyze.rdf.roles == {"SOL": "solvent"}
    assert args.analyze.rdf.output == Path("out")


def test_cli_integration_boundary_preserves_arguments() -> None:
    args = parse_args(
        build_parser(),
        [
            "integrations",
            "run",
            "gromacs",
            "--cwd",
            "work",
            "--",
            "command",
            "--flag",
        ],
    )

    assert args.integrations.run.integration == "gromacs"
    assert args.integrations.run.cwd == Path("work")
    assert args.integrations.run.arguments == ["command", "--flag"]


@pytest.mark.parametrize(
    "values",
    [
        ["inspect"],
        ["config", "path"],
        ["project", "show", "--path", "project"],
        ["integrations", "list"],
        ["templates", "list"],
        [
            "analyze",
            "rdf",
            "--output",
            "out",
            "--reference",
            "A",
            "--selection",
            "B",
        ],
        [
            "analyze",
            "cumulative-rdf",
            "--output",
            "out",
            "--reference",
            "A",
            "--selection",
            "B",
        ],
        [
            "analyze",
            "energy",
            "--energy-file",
            "run.edr",
            "--terms",
            "[Potential]",
            "--output",
            "out",
        ],
        [
            "analyze",
            "request",
            "--request",
            "request.json",
            "--output",
            "out",
        ],
    ],
)
def test_cli_parses_each_primary_command(values: list[str]) -> None:
    parse_args(build_parser(), values)
