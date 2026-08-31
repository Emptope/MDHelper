from __future__ import annotations

import json
from pathlib import Path

import pytest

from mdhelper.app import ApplicationService
from mdhelper.cli import main
from mdhelper.core.errors import ConfigurationError
from mdhelper.services.config import UserConfig
from mdhelper.services.templates import TEMPLATE_ROOT, load_templates


def test_template_directory_is_discovered_without_per_file_registration(
    tmp_path: Path,
) -> None:
    root = tmp_path / "templates"
    category = root / "example"
    category.mkdir(parents=True)
    (category / "first.txt").write_text("first template\n", encoding="ascii")
    (category / "second.inp").write_text("second template\n", encoding="ascii")

    registry = load_templates(root)

    assert [item.key for item in registry.templates()] == [
        "example/first",
        "example/second",
    ]
    assert registry.get("EXAMPLE/FIRST").content == "first template\n"


def test_template_directory_rejects_non_ascii_content(tmp_path: Path) -> None:
    root = tmp_path / "templates"
    root.mkdir()
    (root / "invalid.txt").write_bytes(b"invalid: \xff\n")

    with pytest.raises(ConfigurationError, match="ASCII template"):
        load_templates(root)


def test_bundled_templates_are_available_and_can_be_saved(tmp_path: Path) -> None:
    application = ApplicationService(UserConfig())
    templates = application.templates.list()
    expected = {
        path.relative_to(TEMPLATE_ROOT).with_suffix("").as_posix()
        for path in TEMPLATE_ROOT.rglob("*")
        if path.is_file()
        and not any(
            part.startswith(".")
            for part in path.relative_to(TEMPLATE_ROOT).parts
        )
    }

    assert expected
    assert {item.key for item in templates} == expected
    selected = templates[0]
    saved = application.templates.save(selected.key, tmp_path / selected.filename)
    assert saved.read_text(encoding="ascii") == selected.content


def test_cli_lists_and_prints_templates(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["integrations", "templates"]) == 0
    catalog = json.loads(capsys.readouterr().out)
    key = catalog["templates"][0]["key"]

    assert main(["integrations", "templates", key]) == 0
    selected = json.loads(capsys.readouterr().out)
    assert selected["key"] == key
    assert selected["content"].isascii()
