from __future__ import annotations

from pathlib import Path

from vasp_cache.api import fetch, has, put
from vasp_cache.paths import _reset_project, override_cache_root
from conftest import write_complete_calc, write_minimal_inputs


def test_put_fetch_roundtrip(cache_root: Path, tmp_path: Path):
    _reset_project()
    calc = write_complete_calc(tmp_path / "calc", energy="-12.5")
    outcar_bytes = (calc / "OUTCAR").read_bytes()

    ch = put(calc)
    assert ch is not None
    assert has(calc) is True

    # simulate clean workdir with inputs only
    work = write_minimal_inputs(tmp_path / "work")
    assert (work / "OUTCAR").exists() is False
    # same inputs as calc -> same hash (CONTCAR/POSCAR/INCAR/KPOINTS match)
    assert has(work) is True
    assert fetch(work) is True
    assert (work / "OUTCAR").is_file()
    assert (work / "OUTCAR").read_bytes() == outcar_bytes


def test_has_false_when_empty(cache_root: Path, tmp_path: Path):
    _reset_project()
    d = write_minimal_inputs(tmp_path / "only_in")
    assert has(d) is False
    assert fetch(d) is False


def test_put_skips_without_outcar(cache_root: Path, tmp_path: Path):
    _reset_project()
    d = write_minimal_inputs(tmp_path / "no_out")
    assert put(d) is None


def test_put_does_not_store_potcar(cache_root: Path, tmp_path: Path):
    _reset_project()
    calc = write_complete_calc(tmp_path / "calc")
    ch = put(calc)
    from vasp_cache.paths import get_project

    job = get_project().open_job({"content_hash": ch})
    assert not Path(job.fn("POTCAR")).is_file()
