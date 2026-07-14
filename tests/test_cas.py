"""CAS object store + SQLite meta."""

from __future__ import annotations

from pathlib import Path

from vasp_cache import cas, meta
from vasp_cache.api import fetch, has, put, stats
from vasp_cache.paths import _reset_project, override_cache_root
from conftest import write_complete_calc, write_minimal_inputs


def test_cas_put_dedup(tmp_path: Path):
    root = tmp_path / "c"
    d1 = cas.put_bytes(root, b"hello")
    d2 = cas.put_bytes(root, b"hello")
    assert d1 == d2
    assert cas.has_object(root, d1)
    assert cas.read_bytes(root, d1) == b"hello"
    # single object file
    files = list((root / "cas").rglob("*"))
    files = [f for f in files if f.is_file()]
    assert len(files) == 1


def test_put_creates_meta_and_cas(cache_root: Path, tmp_path: Path):
    _reset_project()
    override_cache_root(cache_root)
    calc = write_complete_calc(tmp_path / "calc", energy="-1.23")
    ch = put(calc)
    assert ch
    assert (cache_root / "meta.sqlite").is_file()
    assert (cache_root / "cas").is_dir()
    st = stats()
    assert st["entries"] == 1
    assert st["backend"] == "cas+sqlite"
    entry = meta.get_entry(cache_root, ch)
    assert entry is not None
    assert "OUTCAR" in entry["objects"]
    assert cas.has_object(cache_root, entry["objects"]["OUTCAR"])


def test_dedup_same_outcar_two_jobs(cache_root: Path, tmp_path: Path):
    """Identical OUTCAR bytes share one CAS object across different hashes."""
    _reset_project()
    override_cache_root(cache_root)
    a = write_complete_calc(tmp_path / "a", energy="-5.0")
    b = write_complete_calc(tmp_path / "b", energy="-5.0")
    # change hard INCAR key so content_hash differs
    incar = (b / "INCAR").read_text()
    if "ENCUT" in incar:
        (b / "INCAR").write_text(incar.replace("520", "400"))
    else:
        (b / "INCAR").write_text(incar + "\nENCUT = 400\n")
    (b / "OUTCAR").write_bytes((a / "OUTCAR").read_bytes())

    ch_a = put(a)
    ch_b = put(b)
    assert ch_a != ch_b
    ea = meta.get_entry(cache_root, ch_a)
    eb = meta.get_entry(cache_root, ch_b)
    assert ea["objects"]["OUTCAR"] == eb["objects"]["OUTCAR"]
    out_files = [
        p
        for p in (cache_root / "cas").rglob("*")
        if p.is_file() and p.stat().st_size == (a / "OUTCAR").stat().st_size
    ]
    assert len(out_files) == 1


def test_fetch_from_cas(cache_root: Path, tmp_path: Path):
    _reset_project()
    override_cache_root(cache_root)
    calc = write_complete_calc(tmp_path / "calc")
    out_b = (calc / "OUTCAR").read_bytes()
    put(calc)
    work = write_minimal_inputs(tmp_path / "work")
    assert has(work)
    assert fetch(work)
    assert (work / "OUTCAR").read_bytes() == out_b
