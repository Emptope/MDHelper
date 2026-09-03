from __future__ import annotations

from pathlib import Path

import pytest

from mdhelper.core.errors import FormatError
from mdhelper.io.itp import discover_molecule_types, read_molecule_types
from mdhelper.services.species import inspect_species_roles


def _write_itp(path: Path, name: str, charges: tuple[str, ...]) -> None:
    atoms = "\n".join(
        f"{index} type 1 {name} A{index} {index} {charge} 1.0"
        for index, charge in enumerate(charges, 1)
    )
    path.write_text(
        "[ moleculetype ]\n"
        "; name nrexcl\n"
        f"{name} 3\n"
        "[ atoms ]\n"
        "; nr type resnr residue atom cgnr charge mass\n"
        f"{atoms}\n"
        "[ bonds ]\n"
        "1 1 1\n",
        encoding="ascii",
    )


def test_itp_reader_uses_sections_and_charge_column(tmp_path: Path) -> None:
    path = tmp_path / "molecule.itp"
    path.write_text(
        "; ignored header\n"
        "[ atomtypes ]\n"
        "kind 1 1.0 9.0 A 0.1 0.2\n"
        "[ MOLECULETYPE ] ; section comment\n"
        "alpha 3 ; record comment\n"
        "[ Atoms ]\n"
        "1 kind 1 alpha A1 1 +7.5e-1 1.0\n"
        "2 kind 1 alpha A2 2 -2.5E-1 1.0\n"
        "[ bonds ]\n"
        "1 2 1\n",
        encoding="ascii",
    )

    records = read_molecule_types(path)

    assert len(records) == 1
    assert records[0].name == "alpha"
    assert records[0].atom_count == 2
    assert records[0].charge_e == pytest.approx(0.5)
    assert records[0].path == path.resolve()


def test_itp_discovery_is_recursive_case_insensitive_and_ignores_parameter_files(
    tmp_path: Path,
) -> None:
    _write_itp(tmp_path / "B.ITP", "beta", ("-1.0",))
    _write_itp(tmp_path / "a.itp", "alpha", ("1.0",))
    (tmp_path / "params.itp").write_text("[ atomtypes ]\nkind 1\n", encoding="ascii")
    nested = tmp_path / "nested"
    nested.mkdir()
    _write_itp(nested / "hidden.itp", "hidden", ("0.0",))

    records = discover_molecule_types(tmp_path)

    assert tuple(records) == ("alpha", "beta", "hidden")
    assert records["alpha"].path.name == "a.itp"
    assert records["beta"].path.name == "B.ITP"
    assert records["hidden"].path.relative_to(tmp_path).as_posix() == "nested/hidden.itp"


def test_itp_discovery_rejects_invalid_and_conflicting_definitions(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.itp"
    invalid.write_text(
        "[ moleculetype ]\nalpha 3\n[ atoms ]\n"
        "1 kind 1 alpha A1 1 not-a-charge 1.0\n",
        encoding="ascii",
    )
    with pytest.raises(FormatError, match="charge"):
        discover_molecule_types(tmp_path)

    invalid.unlink()
    _write_itp(tmp_path / "first.itp", "alpha", ("1.0",))
    _write_itp(tmp_path / "second.itp", "alpha", ("-1.0",))
    with pytest.raises(FormatError, match="multiple definitions"):
        discover_molecule_types(tmp_path)


def test_itp_reader_rejects_conditional_atom_tables(tmp_path: Path) -> None:
    path = tmp_path / "conditional.itp"
    path.write_text(
        "[ moleculetype ]\nalpha 3\n[ atoms ]\n"
        "#ifdef CHARGED\n"
        "1 kind 1 alpha A1 1 1.0 1.0\n"
        "#endif\n",
        encoding="ascii",
    )

    with pytest.raises(FormatError, match="preprocessor"):
        read_molecule_types(path)


def test_itp_roles_are_suggestions_and_ignore_charge_roundoff(tmp_path: Path) -> None:
    _write_itp(tmp_path / "positive.itp", "alpha", ("0.4", "0.4"))
    _write_itp(tmp_path / "negative.itp", "beta", ("-0.4", "-0.4"))
    nested = tmp_path / "molecules"
    nested.mkdir()
    _write_itp(nested / "neutral.itp", "gamma", ("0.2", "-0.2000000001"))
    _write_itp(nested / "charged.itp", "epsilon", ("-0.00001",))

    inspection = inspect_species_roles(
        tmp_path,
        {"alpha": 1, "beta": 1, "gamma": 1, "delta": 1, "epsilon": 1},
    )
    suggestions = inspection.suggestions

    assert suggestions["alpha"].suggested_role == "cation"
    assert suggestions["beta"].suggested_role == "anion"
    assert suggestions["gamma"].suggested_role == "solvent"
    assert suggestions["epsilon"].suggested_role == "anion"
    assert suggestions["delta"].suggested_role is None
    assert all(item.requires_user_confirmation for item in suggestions.values())
    assert suggestions["gamma"].evidence["molecule_charge_e"] == pytest.approx(-1e-10)
    assert suggestions["gamma"].evidence["zero_tolerance_e"] == 1e-6
    assert suggestions["gamma"].evidence["source_file"] == "molecules/neutral.itp"
    assert inspection.system_charge_e is None


def test_itp_system_charge_uses_molecule_counts_and_requires_complete_data(
    tmp_path: Path,
) -> None:
    _write_itp(tmp_path / "positive.itp", "alpha", ("0.4",))
    _write_itp(tmp_path / "negative.itp", "beta", ("-0.2",))

    complete = inspect_species_roles(tmp_path, {"alpha": 1, "beta": 2})
    incomplete = inspect_species_roles(tmp_path, {"alpha": 1, "missing": 1})

    assert complete.system_charge_e == pytest.approx(0)
    assert incomplete.system_charge_e is None
