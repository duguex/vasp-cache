from __future__ import annotations

from pathlib import Path

import json
import os
import sqlite3
import time
import pytest
from unittest.mock import patch
from vasp_cache.api import fetch, has, put, query, rebuild
from vasp_cache.index import identity_for_directory, normalize_incar

POSCAR = "Si\n1.0\n5.43 0 0\n0 5.43 0\n0 0 5.43\nSi\n2\nDirect\n0 0 0\n0.25 0.25 0.25\n"


def write_calc(path: Path, incar: str = "ENCUT = 520\nNSW = 0\n") -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / "POSCAR").write_text(POSCAR)
    (path / "INCAR").write_text(incar)
    (path / "KPOINTS").write_text(
        "Automatic mesh\n0\nGamma\n1 1 1\n")
    (path / "POTCAR").write_text(
        "   TITEL  = PAW_PBE Si 05Jan2001\n")
    for name in ("OUTCAR", "CONTCAR", "vasprun.xml"):
        (path / name).write_bytes(b"fake " + name.encode())
    return path


def test_normalize_incar_sorts_keys_and_collapses_value_whitespace(
    tmp_path: Path,
):
    path = tmp_path / "INCAR"
    path.write_text("sigma =   0.1   0.2\nENCUT=520\n")
    assert normalize_incar(path) == {"ENCUT": "520", "SIGMA": "0.1 0.2"}


def test_identity_perturbation_keeps_key(tmp_path: Path):
    """Coordinate perturbation within same formula+lattice → same key."""
    write_calc(tmp_path / "a", "ENCUT=520\n")
    write_calc(tmp_path / "b", "ENCUT=520\n")
    # b has different atomic position
    (tmp_path / "b" / "POSCAR").write_text(
        "Si\n1.0\n5.43 0 0\n0 5.43 0\n0 0 5.43\nSi\n2\nDirect\n"
        "0 0 0\n0.30 0.30 0.30\n")
    assert identity_for_directory(tmp_path / "a").key == \
        identity_for_directory(tmp_path / "b").key


def test_different_formula_changes_key(tmp_path: Path):
    write_calc(tmp_path / "a", "ENCUT=520\n")
    write_calc(tmp_path / "b", "ENCUT=520\n")
    (tmp_path / "b" / "POSCAR").write_text(
        "GaAs\n1.0\n5.65 0 0\n0 5.65 0\n0 0 5.65\n"
        "Ga As\n1 1\nDirect\n0 0 0\n0.25 0.25 0.25\n")
    assert identity_for_directory(tmp_path / "a").key != \
        identity_for_directory(tmp_path / "b").key


def test_different_lattice_changes_key(tmp_path: Path):
    write_calc(tmp_path / "a", "ENCUT=520\n")
    write_calc(tmp_path / "b", "ENCUT=520\n")
    (tmp_path / "b" / "POSCAR").write_text(
        "Si\n1.0\n6.0 0 0\n0 6.0 0\n0 0 6.0\nSi\n2\nDirect\n"
        "0 0 0\n0.25 0.25 0.25\n")
    assert identity_for_directory(tmp_path / "a").key != \
        identity_for_directory(tmp_path / "b").key


def test_different_incar_changes_key(tmp_path: Path):
    write_calc(tmp_path / "a", "ENCUT=520\n")
    write_calc(tmp_path / "b", "ENCUT=400\n")
    assert identity_for_directory(tmp_path / "a").key != \
        identity_for_directory(tmp_path / "b").key


def test_lattice_permutation_keeps_key(tmp_path: Path):
    """Swapping lattice vectors should produce the same key."""
    import shutil as _sh
    write_calc(tmp_path / "a", "ENCUT=520\n")
    (tmp_path / "a" / "POSCAR").write_text(
        "Si\n1.0\n3.84 0 0\n0 3.84 0\n0 0 3.84\nSi\n2\nDirect\n"
        "0 0 0\n0.25 0.25 0.25\n")
    perms = [
        "3.84 0 0\n0 3.84 0\n0 0 3.84",
        "0 3.84 0\n0 0 3.84\n3.84 0 0",
        "0 0 3.84\n3.84 0 0\n0 3.84 0",
    ]
    key_a = identity_for_directory(tmp_path / "a").key
    for i, rows in enumerate(perms):
        b = tmp_path / f"perm_{i}"
        b.mkdir()
        for f in ("INCAR","KPOINTS","POTCAR"):
            _sh.copy(tmp_path / "a" / f, b / f)
        (b / "POSCAR").write_text(
            f"Si\n1.0\n{rows}\nSi\n2\nDirect\n"
            "0 0 0\n0.25 0.25 0.25\n")
        for f in ("OUTCAR","CONTCAR","vasprun.xml"):
            (b / f).write_bytes(b"fake")
        assert key_a == identity_for_directory(b).key, \
            f"perm {i} differs"


def test_rebuild_groups_duplicate_identity_and_skips_invalid(
    tmp_path: Path, cache_root: Path,
):
    write_calc(tmp_path / "cpd" / "first")
    write_calc(tmp_path / "cpd" / "second")
    # has INCAR but missing vasprun — should be skipped
    partial = tmp_path / "cpd" / "partial"
    partial.mkdir(parents=True)
    (partial / "POSCAR").write_text(POSCAR)
    (partial / "INCAR").write_text("ENCUT=520\n")
    (partial / "KPOINTS").write_text("Automatic\n0\nGamma\n1 1 1\n")
    (partial / "POTCAR").write_text("Si_pv")
    (partial / "OUTCAR").write_bytes(b"fake")
    (partial / "CONTCAR").write_bytes(b"fake")
    result = rebuild(tmp_path, root=cache_root)
    assert result["identities"] == 1
    assert result["done"] == 2
    assert result["scanned"] >= 2
    assert result["skipped"] >= 1


def test_put_has_and_fetch_use_blob_schema(
    cache_root: Path, tmp_path: Path,
):
    calc = write_calc(tmp_path / "calc")
    key = put(calc, root=cache_root)
    assert key is not None
    assert has(calc, root=cache_root) is True
    destination = tmp_path / "restored"
    assert fetch(key, destination, root=cache_root) is True
    assert (destination / "OUTCAR").read_bytes() == b"fake OUTCAR"
    assert (destination / "CONTCAR").read_bytes() == b"fake CONTCAR"
    assert (destination / "vasprun.xml").read_bytes() == b"fake vasprun.xml"
    assert (destination / "POSCAR").is_file()
    assert (destination / "INCAR").is_file()


def test_put_refreshes_entry_for_same_identity(
    cache_root: Path, tmp_path: Path,
):
    calc = write_calc(tmp_path / "calc")
    key1 = put(calc, root=cache_root)
    key2 = put(calc, root=cache_root)
    assert key1 == key2
    assert len(query(root=cache_root)) == 1


def test_query_formula_filter(tmp_path: Path, cache_root: Path):
    write_calc(tmp_path / "calc")
    put(tmp_path / "calc", root=cache_root)
    assert len(query(formula="Si", root=cache_root)) == 1
    assert query(formula="GaN", root=cache_root) == []




def test_collision_converged_replaces_unconverged(
    cache_root: Path, tmp_path: Path, monkeypatch,
):
    """Converged candidate replaces unconverged entry."""
    import sqlite3 as _sql

    def _fake_extract_vasprun(path):
        conv = 1 if path.parent.name == "bb" else 0
        return {
            "converged_ionic": conv,
            "converged_electronic": conv,
            "n_ionic_steps": 1,
            "final_structure_json": "{}",
            "final_energy": -5.0,
        }
    monkeypatch.setattr(
        "vasp_cache.index._extract_vasprun", _fake_extract_vasprun)

    a = tmp_path / "a"
    write_calc(a)
    key_a = put(a, root=cache_root)
    assert key_a is not None
    # entry is unconverged
    assert query(root=cache_root)[0]["converged_ionic"] == 0

    b = tmp_path / "bb"
    write_calc(b)
    key_b = put(b, root=cache_root)
    assert key_b == key_a
    # entry is now converged
    assert query(root=cache_root)[0]["converged_ionic"] == 1
    conn = _sql.connect(str(cache_root / "index.sqlite"))
    conn.row_factory = _sql.Row
    disc = conn.execute(
        "SELECT reason FROM discarded_candidates ORDER BY id"
    ).fetchall()
    assert ["replaced"] == [d["reason"] for d in disc]
    conn.close()


def test_collision_converged_stays(
    cache_root: Path, tmp_path: Path, monkeypatch,
):
    """Existing converged entry not replaced by unconverged candidate."""
    import sqlite3 as _sql

    def _fake_extract_vasprun(path):
        conv = 0 if path.parent.name == "b" else 1
        return {
            "converged_ionic": conv,
            "converged_electronic": conv,
            "n_ionic_steps": 1,
            "final_structure_json": "{}",
            "final_energy": -5.0,
        }
    monkeypatch.setattr(
        "vasp_cache.index._extract_vasprun", _fake_extract_vasprun)

    a = tmp_path / "aa"
    write_calc(a)
    put(a, root=cache_root)
    assert query(root=cache_root)[0]["converged_ionic"] == 1

    b = tmp_path / "b"
    write_calc(b)
    put(b, root=cache_root)
    # entry still converged
    assert query(root=cache_root)[0]["converged_ionic"] == 1
    conn = _sql.connect(str(cache_root / "index.sqlite"))
    conn.row_factory = _sql.Row
    disc = conn.execute(
        "SELECT reason FROM discarded_candidates"
    ).fetchall()
    assert disc[0]["reason"] == "existing_kept"
    conn.close()


def test_collision_discard_records_energy(cache_root: Path, tmp_path: Path, monkeypatch):
    """Discarded candidate's energy is recorded in audit table."""
    import sqlite3 as _sql

    monkeypatch.setattr(
        "vasp_cache.index._extract_vasprun",
        lambda p: {"converged_ionic": 1, "converged_electronic": 1,
                   "n_ionic_steps": 1, "final_structure_json": "{}",
                   "final_energy": -5.0})

    a = tmp_path / "aa"
    write_calc(a)
    put(a, root=cache_root)

    b = tmp_path / "bb"
    write_calc(b)
    put(b, root=cache_root)

    conn = _sql.connect(str(cache_root / "index.sqlite"))
    conn.row_factory = _sql.Row
    disc = conn.execute(
        "SELECT reason, final_energy FROM discarded_candidates"
    ).fetchone()
    assert disc["reason"] == "existing_kept"
    assert disc["final_energy"] == -5.0
    conn.close()
def test_rebuild_tiebreak_by_relative_path(
    cache_root: Path, tmp_path: Path, monkeypatch,
):
    """When all candidates have same convergence, relative path picks winner."""
    import sqlite3 as _sql

    monkeypatch.setattr(
        "vasp_cache.index._extract_vasprun",
        lambda p: {"converged_ionic": 0, "converged_electronic": 0,
                   "n_ionic_steps": 1, "final_structure_json": "{}",
                   "final_energy": -5.0})

    # both unconverged, aa < bb alphabetically
    write_calc(tmp_path / "aa")
    write_calc(tmp_path / "bb")

    result = rebuild(tmp_path, root=cache_root)
    assert result["done"] == 2
    assert result["discarded"] == 1
    assert result["identities"] == 1

    conn = _sql.connect(str(cache_root / "index.sqlite"))
    conn.row_factory = _sql.Row
    # winner should be aa (sorted first)
    e = conn.execute("SELECT source_path FROM entries").fetchone()
    assert "aa" in e["source_path"], f"expected aa, got {e['source_path']}"
    # discard should be bb
    d = conn.execute(
        "SELECT source_path, reason FROM discarded_candidates"
    ).fetchone()
    assert "bb" in d["source_path"]
    assert d["reason"] == "existing_kept"
    conn.close()


def test_concurrent_put_does_not_corrupt(cache_root: Path, tmp_path: Path):
    """Concurrent put() from multiple processes must not corrupt the DB."""
    import multiprocessing
    import sqlite3 as _sql

    for i in range(8):
        write_calc(tmp_path / f"calc_{i}")

    args = [(str(cache_root), str(tmp_path / f"calc_{i}")) for i in range(8)]
    with multiprocessing.Pool(4) as pool:
        results = pool.starmap(_concurrent_worker, args)
    assert all(r for r in results), f"some puts failed: {results}"
    assert len(query(root=cache_root)) == 1
    conn = _sql.connect(str(cache_root / "index.sqlite"))
    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    assert integrity == "ok"
    conn.close()


def _concurrent_worker(cache_root: str, calc_dir: str) -> bool:
    """Module-level worker for multiprocessing."""
    import vasp_cache.index as _ix
    _ix._extract_vasprun = lambda p: {
        "converged_ionic": 1, "converged_electronic": 1,
        "n_ionic_steps": 1, "final_structure_json": "{}",
        "final_energy": -5.0}
    from vasp_cache.index import put
    key = put(Path(calc_dir), root=Path(cache_root))
    return key is not None

def test_fetch_unknown_key_returns_false(cache_root: Path, tmp_path: Path):
    assert fetch("deadbeef", tmp_path / "gone", root=cache_root) is False


def test_put_rejects_incomplete_outputs(tmp_path: Path, cache_root: Path):
    calc = tmp_path / "partial"
    calc.mkdir(parents=True)
    for f in ("POSCAR", "INCAR", "KPOINTS", "POTCAR",
              "OUTCAR", "CONTCAR"):
        (calc / f).write_text(f)
    assert put(calc, root=cache_root) is None


def test_rebuild_skips_incomplete_outputs(tmp_path: Path, cache_root: Path):
    write_calc(tmp_path / "complete")
    partial = tmp_path / "partial"
    partial.mkdir(parents=True)
    (partial / "POSCAR").write_text(POSCAR)
    (partial / "INCAR").write_text("ENCUT=520\n")
    (partial / "KPOINTS").write_text("Automatic\n0\nGamma\n1 1 1\n")
    (partial / "POTCAR").write_text("Si_pv")
    (partial / "OUTCAR").write_bytes(b"fake")
    report = rebuild(tmp_path, root=cache_root)
    assert report["done"] == 1
    assert report["skipped"] >= 1


def test_rebuild_excludes_matched_directories(
    tmp_path: Path, cache_root: Path,
):
    write_calc(tmp_path / "valid")
    write_calc(tmp_path / "backup_old")
    report = rebuild(tmp_path, root=cache_root, exclude=["*backup*"])
    assert report["done"] == 1


def test_put_overwrite_replaces_existing(cache_root: Path, tmp_path: Path, monkeypatch):
    """overwrite=True replaces existing entry regardless of convergence."""
    import sqlite3 as _sql

    monkeypatch.setattr(
        "vasp_cache.index._extract_vasprun",
        lambda p: {"converged_ionic": 1, "converged_electronic": 1,
                   "n_ionic_steps": 1, "final_structure_json": "{}",
                   "final_energy": -5.0})

    a = tmp_path / "a"
    write_calc(a)
    k1 = put(a, root=cache_root)
    assert k1 is not None

    # second put without overwrite is discarded
    b = tmp_path / "bb"
    write_calc(b)
    k2 = put(b, root=cache_root)
    assert k2 == k1  # same key, not replaced

    # third put with overwrite=True forces replacement
    k3 = put(b, root=cache_root, overwrite=True)
    assert k3 == k1
    entry = query(root=cache_root)[0]
    assert entry["converged_ionic"] == 1
    assert "bb" in entry["source_path"], f"expected bb, got {entry['source_path']}"
    # audit shows: existing_kept + overwritten
    conn = _sql.connect(str(cache_root / "index.sqlite"))
    conn.row_factory = _sql.Row
    disc = conn.execute(
        "SELECT reason FROM discarded_candidates ORDER BY id"
    ).fetchall()
    reasons = [d["reason"] for d in disc]
    assert "existing_kept" in reasons
    assert "overwritten" in reasons
    assert len(reasons) == 2
    conn.close()

def test_stats_uses_direct_sql(cache_root: Path, tmp_path: Path):
    from vasp_cache.api import stats
    write_calc(tmp_path / "calc")
    put(tmp_path / "calc", root=cache_root)
    result = stats(root=cache_root)
    assert result["entries"] == 1
    assert result["formulas"] == 1
    assert result["backend"] == "sqlite-index"
    assert result["total_blob_bytes"] > 0


# --- #26 regression tests -------------------------------------------------

def test_final_energy_zero_preserved(cache_root: Path, tmp_path: Path):
    """A: or-logic no longer swallows 0.0 as falsy."""
    from vasp_cache.index import _extract_outcar
    d = write_calc(tmp_path / "calc")
    # monkeypatch outcar extract to return exactly 0.0
    original = _extract_outcar
    def fake_extract_outcar(path):
        return {"final_energy": 0.0, "total_mag": None,
                "electrostatic_potentials": None}
    with patch("vasp_cache.index._extract_outcar", fake_extract_outcar):
        with patch("vasp_cache.index._extract_vasprun",
                   return_value={"final_energy": None, "converged_ionic": True,
                                 "converged_electronic": True}):
            key = put(d, root=cache_root)
    assert key is not None
    rows = query(root=cache_root)
    assert rows[0]["final_energy"] == 0.0


def test_normalize_lattice_rejects_zero_length_vector():
    """B: zero-length lattice vector raises IdentityInputError."""

    from vasp_cache.errors import IdentityInputError
    from vasp_cache.index import normalize_lattice
    with pytest.raises(IdentityInputError, match="degenerate"):
        normalize_lattice({"lattice": {"matrix": [[0, 0, 0], [1, 0, 0], [0, 1, 0]]}})


def test_fetch_rejects_existing_target(cache_root: Path, tmp_path: Path):
    """C: fetch refuses to overwrite an existing target directory."""
    d = write_calc(tmp_path / "calc")
    key = put(d, root=cache_root)
    dest = tmp_path / "already_exists"
    dest.mkdir()
    with pytest.raises(FileExistsError, match="existing directory"):
        fetch(key, dest, root=cache_root)


def test_fetch_cleans_up_on_reconstruction_failure(
    cache_root: Path, tmp_path: Path, monkeypatch,
):
    """C: fetch cleans up temp dir when reconstruction fails."""
    d = write_calc(tmp_path / "calc")
    key = put(d, root=cache_root)
    dest = tmp_path / "target"
    parent = dest.parent
    # Make _write_kpoints fail after BLOB files have been written
    def failing_write_kpoints(path, kpts):
        raise RuntimeError("simulated reconstruction failure")
    with patch("vasp_cache.index._write_kpoints", failing_write_kpoints):
        with pytest.raises(RuntimeError, match="simulated"):
            fetch(key, dest, root=cache_root)
    # Temp dir should have been cleaned up
    leftovers = list(parent.glob(".fetch-*"))
    assert len(leftovers) == 0, f"temp dir not cleaned: {leftovers}"
    assert not dest.exists()


def test_get_meta_by_source_path(cache_root: Path, tmp_path: Path):
    """D3: get_meta finds entry by source_path."""
    from vasp_cache.api import get_meta
    d = write_calc(tmp_path / "calc")
    key = put(d, root=cache_root)
    sp = str(d.resolve())
    # lookup by source_path
    meta = get_meta(key=sp, root=cache_root)
    assert meta is not None
    assert meta["identity_key"] == key


def test_upsert_updates_created_at_and_enforces_fk(
    cache_root: Path, tmp_path: Path, monkeypatch,
):
    """8: UPSERT updates created_at; FK is enforced."""
    d1 = write_calc(tmp_path / "calc1", incar="ENCUT = 520\nNSW = 0\n")
    key = put(d1, root=cache_root)
    conn1 = sqlite3.connect(str(cache_root / "index.sqlite"))
    conn1.row_factory = sqlite3.Row
    conn1.execute("PRAGMA foreign_keys = ON")
    fk = conn1.execute("PRAGMA foreign_keys").fetchone()[0]
    created1 = conn1.execute(
        "SELECT created_at, source_path FROM entries WHERE identity_key = ?",
        (key,),
    ).fetchone()
    old_created = created1["created_at"]
    old_source = created1["source_path"]
    conn1.close()
    time.sleep(1.1)  # ensure datetime('now') resolution gap
    d2 = write_calc(tmp_path / "calc2", incar="ENCUT = 520\nNSW = 0\n")
    put(d2, root=cache_root, overwrite=True)
    conn2 = sqlite3.connect(str(cache_root / "index.sqlite"))
    conn2.row_factory = sqlite3.Row
    conn2.execute("PRAGMA foreign_keys = ON")
    created2 = conn2.execute(
        "SELECT created_at, source_path FROM entries WHERE identity_key = ?",
        (key,),
    ).fetchone()
    assert created2["created_at"] > old_created
    assert created2["source_path"] != old_source  # updated, not the old one
    # FK enforcement: inserting into discarded_candidates with bogus key must fail
    with pytest.raises(sqlite3.IntegrityError):
        conn2.execute(
            "INSERT INTO discarded_candidates(identity_key, source_path, reason) "
            "VALUES ('nonexistent', '/none', 'test')",
        )
    conn2.close()



# --- schema versioning tests -----------------------------------------------

def test_fresh_db_gets_schema_version_1(cache_root: Path):
    """Fresh index.sqlite gets user_version = 1."""
    from vasp_cache.index import connect
    conn = connect(root=cache_root)
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    assert version == 1
    conn.close()


def test_v0_compatible_db_upgrades_to_v1(cache_root: Path):
    """v0 DB with current v3 columns auto-upgrades to version 1."""
    db = cache_root / "index.sqlite"
    # Build a full v3 schema, then reset user_version to 0
    from vasp_cache.index import _SCHEMA, _SCHEMA_VERSION
    conn = sqlite3.connect(str(db))
    conn.executescript(_SCHEMA)
    conn.execute("PRAGMA user_version = 0")
    conn.commit()
    conn.close()
    # Reconnect — should upgrade, persisted across re-open
    from vasp_cache.index import connect, _SCHEMA_VERSION as expected_ver
    conn2 = connect(root=cache_root)
    version = conn2.execute("PRAGMA user_version").fetchone()[0]
    assert version == expected_ver
    conn2.close()
    # Re-open and verify persisted
    conn3 = sqlite3.connect(str(db))
    assert conn3.execute("PRAGMA user_version").fetchone()[0] == expected_ver
    conn3.close()


def test_incompatible_schema_raises_runtime_error(cache_root: Path):
    """v0 DB without v3 sentinel columns raises RuntimeError."""
    db = cache_root / "index.sqlite"
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA user_version = 0")
    conn.executescript("CREATE TABLE entries (old_column TEXT);")
    conn.commit()
    conn.close()
    from vasp_cache.index import connect
    with pytest.raises(RuntimeError, match="Incompatible"):
        connect(root=cache_root)
