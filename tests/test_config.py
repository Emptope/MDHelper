from pathlib import Path

import pytest

from mdhelper.bootstrap.portable import activate_portable_config, portable_config_path
from mdhelper.core.errors import ConfigurationError
from mdhelper.core.integrations import IntegrationConfig
from mdhelper.services.config import (
    DEFAULT_CONFIG_TEMPLATE,
    GuiConfig,
    UserConfig,
    config_path,
    initialize_config,
    load_config,
    save_config,
)

ROOT = Path(__file__).parents[1]


def test_initialized_config_matches_distributed_example(tmp_path: Path) -> None:
    expected = (ROOT / "config.example.toml").read_text(encoding="ascii")

    assert DEFAULT_CONFIG_TEMPLATE == expected
    assert initialize_config(tmp_path / "config.toml").read_text(encoding="ascii") == expected


def test_gui_theme_defaults_to_system_and_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    assert UserConfig().gui.theme == "system"
    assert UserConfig().gui.font_size == 11.0

    save_config(UserConfig(gui=GuiConfig(theme="dark", font_size=12.5)), path)

    assert load_config(path).gui.theme == "dark"
    assert load_config(path).gui.font_size == 12.5


def test_workflows_round_trip_in_project_order(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    config = UserConfig(
        workflows={
            "radial": ("rdf", "cumulative_rdf"),
            "full": ("rdf", "energy", "cumulative_rdf"),
        }
    )

    save_config(config, path)

    assert load_config(path).workflows == config.workflows


@pytest.mark.parametrize(
    "value, message",
    [
        ("[]", "at least one"),
        ('["unknown"]', "supported analysis project"),
        ('["rdf", 1]', "supported analysis project"),
    ],
)
def test_invalid_workflow_project_reports_field(
    tmp_path: Path, value: str, message: str
) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        f'schema_version=1\n[workflows]\nexample={value}\n',
        encoding="ascii",
    )

    with pytest.raises(ConfigurationError, match=message):
        load_config(path)


def test_invalid_gui_theme_reports_field(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('schema_version=1\n[gui]\ntheme="sepia"\n', encoding="utf-8")

    with pytest.raises(ConfigurationError, match=r"gui\.theme"):
        load_config(path)


@pytest.mark.parametrize("value", ("true", "5.9", "32.1", '"large"'))
def test_invalid_gui_font_size_reports_field(tmp_path: Path, value: str) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        f"schema_version=1\n[gui]\nfont_size={value}\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match=r"gui\.font_size"):
        load_config(path)


def test_config_round_trip_supports_arbitrary_integrations(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    initialize_config(path)
    config = load_config(path)
    config.integrations["fake"] = IntegrationConfig(path="/opt/fake/bin/fake")
    save_config(config, path)
    loaded = load_config(path)
    assert loaded.integration("gromacs").enabled
    assert loaded.integration("vmd").enabled
    assert loaded.integration("fake").path == "/opt/fake/bin/fake"


def test_invalid_config_reports_field(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        "schema_version=1\n[integrations.fake]\nenabled='yes'\n", encoding="utf-8"
    )
    with pytest.raises(ConfigurationError, match="true or false"):
        load_config(path)


def test_unknown_config_field_is_not_silently_ignored(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        "schema_version=1\n[integrations.gromacs]\nenabled=true\nunknown=true\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigurationError, match=r"integrations\.gromacs\.unknown"):
        load_config(path)


def test_environment_override_selects_config_path(tmp_path: Path) -> None:
    expected = tmp_path / "special.toml"
    assert config_path({"MDHELPER_CONFIG": str(expected)}) == expected


def test_frozen_distribution_uses_colocated_config(tmp_path: Path) -> None:
    executable = tmp_path / "mdhelper.exe"
    executable.write_bytes(b"")
    environment = {"APPDATA": "/settings", "MDHELPER_CONFIG": ""}

    expected = tmp_path / "config.toml"
    assert portable_config_path(executable, frozen=True) == expected
    assert activate_portable_config(environment, executable, frozen=True) == expected
    assert environment["MDHELPER_CONFIG"] == str(expected)
    assert config_path(environment, executable) == expected
    assert portable_config_path(executable, frozen=False) is None


def test_portable_config_preserves_explicit_environment_override(tmp_path: Path) -> None:
    executable = tmp_path / "mdhelper.exe"
    executable.write_bytes(b"")
    explicit = tmp_path / "custom.toml"
    environment = {"MDHELPER_CONFIG": str(explicit)}

    activate_portable_config(environment, executable, frozen=True)

    assert environment["MDHELPER_CONFIG"] == str(explicit)


def test_default_config_path_is_colocated_with_executable(tmp_path: Path) -> None:
    executable = tmp_path / "bin" / "python"

    assert config_path({}, executable) == executable.parent / "config.toml"


@pytest.mark.parametrize(
    "text, message",
    [
        ("schema_version=true\n", "schema version"),
        ("schema_version=1.0\n", "schema version"),
        (
            "schema_version=1\n[integrations.fake]\ndetect_timeout_seconds=nan\n",
            "positive number",
        ),
        (
            "schema_version=1\n[integrations.fake]\npath='   '\n",
            "whitespace",
        ),
    ],
)
def test_config_rejects_ambiguous_scalar_values(
    tmp_path: Path, text: str, message: str
) -> None:
    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ConfigurationError, match=message):
        load_config(path)


def test_save_validates_before_replacing_existing_config(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    initialize_config(path)
    original = path.read_bytes()
    config = UserConfig()
    vars(config)["schema_version"] = True

    with pytest.raises(ConfigurationError, match="schema version"):
        save_config(config, path)

    assert path.read_bytes() == original
