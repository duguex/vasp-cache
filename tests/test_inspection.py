"""Read-only cache inspection collectors."""

from __future__ import annotations

from pathlib import Path

from conftest import write_complete_calc
from vasp_cache import cas
from vasp_cache.api import put
from vasp_cache.inspection import entry, objects, summary, entries
from vasp_cache.paths import _reset_project


def test_summary_empty_cache_does_not_create_database(tmp_path: Path):
    root = tmp_path / "missing"
    result = summary(root)
    assert result["entries"] == 0
    assert result["cas_objects"] == 0
    assert not root.exists()


def test_summary_counts_entries_and_storage(cache_root: Path, tmp_path: Path):
    _reset_project()
    calc = write_complete_calc(tmp_path / "calc")
    assert put(calc, provenance="canonical")
    result = summary(cache_root)
    assert result["entries"] == 1
    assert result["provenance"]["canonical"] == 1
    assert result["cas_objects"] >= 1
    assert result["referenced_objects"] == result["cas_objects"]


def test_entry_reports_object_sizes_and_presence(cache_root: Path, tmp_path: Path):
    _reset_project()
    calc = write_complete_calc(tmp_path / "calc")
    content_hash = put(calc, provenance="canonical")
    assert content_hash is not None
    detail = entry(cache_root, content_hash)
    assert detail is not None
    outcar = detail["objects"]["OUTCAR"]
    assert outcar["digest"]
    assert outcar["size"] == (calc / "OUTCAR").stat().st_size
    assert outcar["present"] is True
    assert outcar["location"] == (
        f"cas/{outcar['digest'][:2]}/{outcar['digest'][2:4]}/{outcar['digest']}"
    )


def test_objects_reports_orphan_without_mutating_it(cache_root: Path):
    orphan = cas.put_bytes(cache_root, b"unreferenced")
    result = objects(cache_root, orphans_only=True)
    assert [row["digest"] for row in result] == [orphan]
    assert result[0]["size"] == len(b"unreferenced")
    assert result[0]["reference_count"] == 0
    assert result[0]["logical_names"] == []
    assert result[0]["orphan"] is True
    assert cas.has_object(cache_root, orphan)


def test_entry_reports_deleted_cas_object(cache_root: Path, tmp_path: Path):
    _reset_project()
    calc = write_complete_calc(tmp_path / "calc")
    content_hash = put(calc, provenance="canonical")
    assert content_hash is not None
    detail = entry(cache_root, content_hash)
    assert detail is not None
    digest = detail["objects"]["OUTCAR"]["digest"]
    cas.object_path(cache_root, digest).unlink()
    detail = entry(cache_root, content_hash)
    assert detail is not None
    outcar = detail["objects"]["OUTCAR"]
    assert outcar["present"] is False
    assert outcar["size"] is None


def test_missing_content_hash_returns_none_without_creating_database(tmp_path: Path):
    root = tmp_path / "missing"
    result = entry(root, "0" * 64)
    assert result is None
    assert not root.exists()


def test_entries_preserves_metadata_and_paginates(cache_root: Path, tmp_path: Path):
    _reset_project()
    first = write_complete_calc(tmp_path / "first")
    second = write_complete_calc(tmp_path / "second", energy="-4.0")
    (second / "INCAR").write_text((second / "INCAR").read_text() + "\nENCUT = 400\n")
    assert put(first, provenance="canonical")
    assert put(second, provenance="sampled")
    rows = entries(cache_root, provenance="all", limit=1, offset=1)
    assert len(rows) == 1
    assert rows[0]["objects"]
    assert rows[0]["object_count"] == len(rows[0]["objects"])
    assert rows[0]["total_energy"] == -5.0


def test_objects_are_digest_sorted_and_summary_accounts_for_missing_refs(
    cache_root: Path, tmp_path: Path
):
    _reset_project()
    calc = write_complete_calc(tmp_path / "calc")
    content_hash = put(calc, provenance="canonical")
    assert content_hash is not None
    detail = entry(cache_root, content_hash)
    assert detail is not None
    digest = detail["objects"]["OUTCAR"]["digest"]
    cas.object_path(cache_root, digest).unlink()
    orphan = cas.put_bytes(cache_root, b"orphan")
    rows = objects(cache_root)
    assert [r["digest"] for r in rows] == sorted(r["digest"] for r in rows)
    assert {r["digest"] for r in rows} >= {digest, orphan}
    missing = next(r for r in rows if r["digest"] == digest)
    assert missing["orphan"] is False
    result = summary(cache_root)
    assert result["referenced_objects"] >= 1
    assert result["orphan_objects"] == 1
