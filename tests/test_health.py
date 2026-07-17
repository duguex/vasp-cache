from __future__ import annotations

import os
from pathlib import Path

from vasp_cache import cas, meta
from vasp_cache.health import health_report


def _snapshot_tree(root: Path) -> tuple[tuple[str, int], ...]:
    if not root.exists():
        return ()
    return tuple(
        sorted(
            (str(path.relative_to(root)), path.stat().st_size)
            for path in root.rglob("*")
            if path.is_file()
        )
    )


def _make_fixture(cache_root: Path) -> tuple[str, str, str]:
    shared = cas.put_bytes(cache_root, b"shared")
    orphan = cas.put_bytes(cache_root, b"orphan")
    missing = "f" * 64
    meta.upsert_entry(
        cache_root,
        content_hash="a" * 64,
        objects={"OUTCAR": shared},
        formula="Si",
        total_energy=-5.0,
        converged=True,
        provenance="canonical",
        provenance_source="explicit",
        key_generation=5,
        profile_id="default",
        source_dir="/calculations/valid",
        cached_at=1.0,
    )
    meta.upsert_entry(
        cache_root,
        content_hash="b" * 64,
        objects={"OUTCAR": shared},
        formula="Si",
        total_energy=-4.0,
        converged=True,
        provenance="sampled",
        provenance_source="inferred",
        key_generation=5,
        profile_id="default",
        source_dir="/calculations/shared",
        cached_at=2.0,
    )
    meta.upsert_entry(
        cache_root,
        content_hash="c" * 64,
        objects={"OUTCAR": missing},
        formula=None,
        total_energy=None,
        converged=None,
        provenance="unknown",
        provenance_source="legacy",
        source_dir="/calculations/missing",
        cached_at=3.0,
    )
    return shared, missing, orphan


def test_health_fast_report_is_read_only_and_separates_metadata(cache_root: Path):
    _make_fixture(cache_root)
    before = _snapshot_tree(cache_root)
    report = health_report(cache_root)
    assert report["schema_version"] == 1
    assert report["scan"]["mode"] == "metadata"
    assert report["metadata"]["entries"] == 3
    assert report["metadata"]["missing_formula"] == 1
    assert report["metadata"]["missing_energy"] == 1
    assert report["metadata"]["missing_convergence"] == 1
    assert report["metadata"]["missing_objects"] == 0
    assert report["cas"]["scan_performed"] is False
    assert report["cas"]["physical_referenced_objects"] is None
    assert report["energy"]["missing"] == 1
    assert _snapshot_tree(cache_root) == before


def test_health_cas_scan_reports_missing_orphan_and_shared_references(cache_root: Path):
    _make_fixture(cache_root)
    report = health_report(cache_root, scan_cas=True)
    assert report["cas"]["missing_references"] == 1
    assert report["cas"]["orphan_objects"] == 1
    assert report["cas"]["shared_reference_objects"] == 1
    assert report["cas"]["referenced_objects"] == 2
    assert report["cas"]["physical_referenced_objects"] == 1
    assert report["cas"]["referenced_bytes"] == len(b"shared")
    assert report["cas"]["limited"] is False
    assert report["cas"]["path_mismatches"] == 0
    assert report["cas"]["physical_objects"] == 2


def test_health_cas_scan_limit_reports_progress_and_partial_reference_fields(cache_root: Path):
    _make_fixture(cache_root)
    seen: list[int] = []
    report = health_report(cache_root, scan_cas=True, max_objects=1, progress=seen.append)
    assert report["cas"]["limited"] is True
    assert seen == [1]
    assert report["cas"]["physical_objects"] == 1
    assert report["cas"]["referenced_objects"] == 2
    assert report["cas"]["physical_referenced_objects"] is None
    assert report["cas"]["referenced_bytes"] is None
    assert report["cas"]["missing_references"] is None
    assert report["cas"]["orphan_objects"] is None
    assert report["cas"]["orphan_bytes"] is None


def test_health_cas_scan_zero_limit_reports_zero_progress(cache_root: Path):
    _make_fixture(cache_root)
    seen: list[int] = []
    report = health_report(cache_root, scan_cas=True, max_objects=0, progress=seen.append)
    assert seen == [0]
    assert report["cas"]["physical_objects"] == 0
    assert report["cas"]["limited"] is True
    assert report["cas"]["physical_referenced_objects"] is None
    assert report["cas"]["referenced_bytes"] is None
    assert report["cas"]["missing_references"] is None
    assert report["cas"]["orphan_objects"] is None
    assert report["cas"]["orphan_bytes"] is None

def test_health_missing_root_is_zero_and_does_not_create_it(tmp_path: Path):
    root = tmp_path / "missing-health-root"
    report = health_report(root)
    assert report["metadata"]["entries"] == 0
    assert report["cas"]["physical_objects"] == 0
    assert report["cas"]["scan_performed"] is False
    assert not root.exists()


def test_health_energy_bounds_preserve_raw_outlier_samples(cache_root: Path):
    _make_fixture(cache_root)
    report = health_report(cache_root, energy_min=-4.5, energy_max=-3.5)
    assert report["energy"]["min"] == -5.0
    assert report["energy"]["max"] == -4.0
    assert report["energy"]["configured_min"] == -4.5
    assert report["energy"]["configured_max"] == -3.5
    assert report["energy"]["outliers"] == 1
    assert report["energy"]["samples"] == [
        {
            "content_hash": "a" * 64,
            "formula": "Si",
            "total_energy": -5.0,
            "source_dir": "/calculations/valid",
        }
    ]
