from __future__ import annotations

from pathlib import Path

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
