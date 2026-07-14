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
    ch = put(calc)
    assert ch is not None
    rows = query(formula="Si", converged_only=False)
    assert len(rows) >= 1
    assert "total_energy" in rows[0]
    assert rows[0]["content_hash"] == ch or rows[0]["content_hash"] == content_hash(calc)


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
