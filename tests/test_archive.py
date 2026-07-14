"""E2E: whole-cache export-archive / import-archive."""

from __future__ import annotations

from pathlib import Path

from conftest import write_complete_calc
from vasp_cache.api import fetch, has, put, stats
from vasp_cache.archive import export_archive, import_archive
from vasp_cache.paths import _reset_project, override_cache_root


def test_export_import_roundtrip(tmp_path: Path):
    src_root = tmp_path / "cache_src"
    dst_root = tmp_path / "cache_dst"
    arch = tmp_path / "bundle.tar.gz"
    calc = write_complete_calc(tmp_path / "calc", energy="-9.99")
    outcar_bytes = (calc / "OUTCAR").read_bytes()

    _reset_project()
    override_cache_root(src_root)
    ch = put(calc)
    assert ch is not None
    st0 = stats()
    assert st0["entries"] >= 1

    out = export_archive(arch, root=src_root)
    assert out.is_file()
    assert out.stat().st_size > 0

    _reset_project()
    override_cache_root(None)
    man = import_archive(arch, root=dst_root, overwrite=False)
    assert man.get("format") in ("vasp-cache-archive-v1", "vasp-cache-archive-v2")
    assert "stats" in man

    _reset_project()
    override_cache_root(dst_root)
    st1 = stats()
    assert st1["entries"] == st0["entries"]

    work = write_complete_calc(tmp_path / "work", energy="-1.0")
    # same inputs as calc for hash match: reuse calc inputs without OUTCAR
    work = tmp_path / "work2"
    work.mkdir()
    for name in ("INCAR", "POSCAR", "CONTCAR", "KPOINTS", "POTCAR"):
        (work / name).write_bytes((calc / name).read_bytes())
    assert has(work) is True
    assert fetch(work) is True
    assert (work / "OUTCAR").read_bytes() == outcar_bytes

    _reset_project()
    override_cache_root(None)


def test_import_refuses_nonempty_without_overwrite(tmp_path: Path):
    src_root = tmp_path / "c1"
    dst_root = tmp_path / "c2"
    arch = tmp_path / "a.tar.gz"
    calc = write_complete_calc(tmp_path / "calc")

    _reset_project()
    override_cache_root(src_root)
    put(calc)
    export_archive(arch, root=src_root)

    _reset_project()
    override_cache_root(dst_root)
    put(write_complete_calc(tmp_path / "other", energy="-2.0"))

    _reset_project()
    override_cache_root(None)
    try:
        import_archive(arch, root=dst_root, overwrite=False)
        raised = False
    except FileExistsError:
        raised = True
    assert raised

    man = import_archive(arch, root=dst_root, overwrite=True)
    assert man.get("format") in ("vasp-cache-archive-v1", "vasp-cache-archive-v2")
    override_cache_root(None)
