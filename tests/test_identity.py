"""Input-only identity and protocol separation tests."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from conftest import write_minimal_inputs
from vasp_cache.errors import IdentityInputError
from vasp_cache.fingerprint import input_protocol_identity, result_geometry_hash
from vasp_cache.mapping import mapping_digest


def test_primary_identity_uses_poscar_not_contcar(tmp_path: Path):
    completed = write_minimal_inputs(tmp_path / "completed")
    input_only = tmp_path / "input_only"
    shutil.copytree(completed, input_only)
    (input_only / "CONTCAR").unlink()
    (completed / "CONTCAR").write_text(
        (completed / "CONTCAR").read_text().replace("5.43", "5.50")
    )

    assert mapping_digest(completed) == mapping_digest(input_only)


def test_missing_poscar_does_not_fall_back_to_contcar(tmp_path: Path):
    calc = write_minimal_inputs(tmp_path / "result_only")
    (calc / "POSCAR").unlink()

    with pytest.raises(IdentityInputError):
        mapping_digest(calc)


@pytest.mark.parametrize(
    ("incar", "mode"),
    [
        ("", "static"),
        ("NSW = 0\nIBRION = -1\n", "static"),
        ("NSW = 100\nIBRION = 2\n", "relaxation"),
        ("NSW = 100\nIBRION = 0\n", "md"),
        ("NSW = 100\nIBRION = 3\n", "md"),
        ("IBRION = 6\n", "phonon"),
    ],
)
def test_input_protocol_identity_uses_effective_mode(
    tmp_path: Path, incar: str, mode: str
):
    calc = write_minimal_inputs(tmp_path / mode)
    (calc / "INCAR").write_text(incar)

    identity = input_protocol_identity(calc)

    assert identity["calc_mode"] == mode
    assert isinstance(identity["nsw"], int)
    assert isinstance(identity["ibrion"], int)
    assert isinstance(identity["isif"], int)


def test_protocol_values_change_primary_identity(tmp_path: Path):
    static = write_minimal_inputs(tmp_path / "static")
    relax = write_minimal_inputs(tmp_path / "relax")
    (relax / "INCAR").write_text("NSW = 100\nIBRION = 2\nISIF = 3\n")

    assert mapping_digest(static) != mapping_digest(relax)


def test_nsw_step_count_changes_primary_identity(tmp_path: Path):
    one_step = write_minimal_inputs(tmp_path / "one_step")
    many_steps = write_minimal_inputs(tmp_path / "many_steps")
    (one_step / "INCAR").write_text("NSW = 1\nIBRION = 2\nISIF = 3\n")
    (many_steps / "INCAR").write_text("NSW = 100\nIBRION = 2\nISIF = 3\n")

    assert mapping_digest(one_step) != mapping_digest(many_steps)


def test_identity_parser_does_not_use_outcar_or_taskdoc(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    calc = write_minimal_inputs(tmp_path / "inputs")

    def fail(*_args, **_kwargs):
        raise AssertionError("output parser must not run during identity hashing")

    monkeypatch.setattr("vasp_cache.parse.summarize_calc", fail)
    monkeypatch.setattr("emmet.core.tasks.TaskDoc.from_directory", fail)

    digest = mapping_digest(calc)

    assert digest.startswith("5:")


def test_result_geometry_hash_tracks_contcar_without_primary_identity(
    tmp_path: Path
):
    calc = write_minimal_inputs(tmp_path / "result")
    primary_before = mapping_digest(calc)
    before = result_geometry_hash(calc)
    (calc / "CONTCAR").write_text(
        (calc / "CONTCAR").read_text().replace("5.43", "5.50")
    )

    after = result_geometry_hash(calc)

    assert before != after
    assert mapping_digest(calc) == primary_before
