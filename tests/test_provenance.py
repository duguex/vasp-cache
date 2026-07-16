"""Provenance metadata, migration, and duplicate-ingest tests."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from conftest import write_complete_calc
from vasp_cache import meta
from vasp_cache.api import ProvenanceConflictError, put
from vasp_cache.paths import _reset_project


def test_metadata_fields_are_stored(cache_root: Path, tmp_path: Path):
    _reset_project()
    calc = write_complete_calc(tmp_path / "calc")
    ch = put(calc, provenance="canonical")

    entry = meta.get_entry(cache_root, ch)

    assert entry is not None
    assert entry["provenance"] == "canonical"
    assert entry["provenance_source"] == "explicit"
    assert entry["nsw"] == 0
    assert entry["ibrion"] == -1
    assert entry["isif"] == 3
    assert entry["outcar_complete"] is True
    assert entry["electronic_converged"] is None
    assert entry["ionic_converged"] is None


def test_legacy_metadata_migrates_without_losing_objects(
    cache_root: Path, tmp_path: Path
):
    _reset_project()
    db = cache_root / "meta.sqlite"
    old_hash = "old-hash"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE entries (
            content_hash TEXT PRIMARY KEY,
            formula TEXT,
            task_name TEXT,
            total_energy REAL,
            converged INTEGER,
            bandgap REAL,
            nsites INTEGER,
            max_abc REAL,
            tags TEXT,
            source_dir TEXT,
            profile_id TEXT,
            key_generation INTEGER,
            mapping_digest TEXT,
            cached_at REAL NOT NULL,
            objects_json TEXT NOT NULL,
            extra_json TEXT
        );
        """
    )
    conn.execute(
        "INSERT INTO entries (content_hash, formula, cached_at, objects_json) "
        "VALUES (?, ?, ?, ?)",
        (old_hash, "Si", 1.0, json.dumps({"OUTCAR": "existing-digest"})),
    )
    conn.commit()
    conn.close()
    meta.close_all()

    entry = meta.get_entry(cache_root, old_hash)

    assert entry is not None
    assert entry["provenance"] == "unknown"
    assert entry["provenance_source"] == "legacy"
    assert entry["objects"] == {"OUTCAR": "existing-digest"}


def test_preflight_preserves_explicit_role(cache_root: Path):
    _reset_project()
    meta.upsert_entry(
        cache_root,
        content_hash="same",
        objects={"OUTCAR": "digest"},
        formula="Si",
        provenance="canonical",
        provenance_source="explicit",
    )

    resolved = meta.preflight_provenance(
        cache_root, "same", "unknown", "inferred"
    )

    assert resolved == ("canonical", "explicit")


def test_same_hash_inferred_role_conflict_preserves_entry(cache_root: Path):
    _reset_project()
    meta.upsert_entry(
        cache_root,
        content_hash="same-inferred",
        objects={"OUTCAR": "digest"},
        formula="Si",
        provenance="canonical",
        provenance_source="inferred",
    )

    with pytest.raises(ProvenanceConflictError):
        meta.preflight_provenance(
            cache_root, "same-inferred", "sampled", "inferred"
        )

    entry = meta.get_entry(cache_root, "same-inferred")
    assert entry is not None
    assert entry["provenance"] == "canonical"
    assert entry["provenance_source"] == "inferred"


def test_same_hash_automatic_ingest_does_not_downgrade_explicit(
    cache_root: Path, tmp_path: Path
):
    _reset_project()
    calc = write_complete_calc(tmp_path / "calc")
    ch = put(calc, provenance="canonical")
    assert put(calc) == ch

    entry = meta.get_entry(cache_root, ch)

    assert entry is not None
    assert entry["provenance"] == "canonical"
    assert entry["provenance_source"] == "explicit"


def test_same_hash_explicit_conflict_fails_before_cas_write(
    cache_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _reset_project()
    calc = write_complete_calc(tmp_path / "calc")
    ch = put(calc, provenance="canonical")

    import vasp_cache.api as api_module

    def unexpected_cas_write(*_args, **_kwargs):
        raise AssertionError("CAS write occurred before provenance preflight")

    monkeypatch.setattr(api_module.cas, "put_file", unexpected_cas_write)
    with pytest.raises(ProvenanceConflictError):
        put(calc, provenance="sampled")

    entry = meta.get_entry(cache_root, ch)
    assert entry is not None
    assert entry["provenance"] == "canonical"
    assert entry["provenance_source"] == "explicit"


def test_explicit_provenance_overrides_inferred_mode(
    cache_root: Path, tmp_path: Path
):
    _reset_project()
    calc = write_complete_calc(tmp_path / "md")
    (calc / "INCAR").write_text("NSW = 4\nIBRION = 0\n")
    ch = put(calc, provenance="canonical")

    entry = meta.get_entry(cache_root, ch)

    assert entry is not None
    assert entry["provenance"] == "canonical"
    assert entry["provenance_source"] == "explicit"
    assert entry["nsw"] == 4
    assert entry["ibrion"] == 0
