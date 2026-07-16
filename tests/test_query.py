"""Tests for query / list_entries / stats / get_meta."""

from __future__ import annotations

from pathlib import Path

from conftest import write_complete_calc
from vasp_cache.api import get_meta, list_entries, put, query, stats
from vasp_cache.mapping import content_hash
from vasp_cache.paths import _reset_project


def test_query_by_formula(cache_root: Path, tmp_path: Path):
    _reset_project()
    calc = write_complete_calc(tmp_path / "Si_run")
    ch = put(calc, provenance="canonical")
    assert ch is not None
    rows = query(formula="Si", converged_only=False)
    assert len(rows) >= 1
    assert "total_energy" in rows[0]
    assert rows[0]["content_hash"] == ch or rows[0]["content_hash"] == content_hash(calc)



def test_query_defaults_to_canonical_and_all_is_explicit(
    cache_root: Path, tmp_path: Path
):
    _reset_project()
    canonical = write_complete_calc(tmp_path / "canonical")
    put(canonical, provenance="canonical")

    sampled = write_complete_calc(tmp_path / "sampled")
    (sampled / "INCAR").write_text("NSW = 4\nIBRION = 0\n")
    put(sampled, provenance="sampled")

    default_rows = query(formula="Si", converged_only=False)
    assert {row["provenance"] for row in default_rows} == {"canonical"}

    sampled_rows = query(formula="Si", provenance="sampled", converged_only=False)
    assert len(sampled_rows) == 1
    assert sampled_rows[0]["provenance"] == "sampled"

    all_rows = query(formula="Si", provenance="all", converged_only=False)
    assert {row["provenance"] for row in all_rows} == {"canonical", "sampled"}

def test_list_and_stats(cache_root: Path, tmp_path: Path):
    _reset_project()
    put(write_complete_calc(tmp_path / "a"))
    put(write_complete_calc(tmp_path / "b"))
    entries = list_entries(limit=10)
    assert len(entries) >= 1
    s = stats()
    assert s["entries"] >= 1
    assert s["formulas"] >= 1


def test_get_meta_by_dir(cache_root: Path, tmp_path: Path):
    _reset_project()
    calc = write_complete_calc(tmp_path / "c")
    put(calc)
    meta = get_meta(calc)
    assert meta is not None
    assert meta.get("formula") == "Si"
