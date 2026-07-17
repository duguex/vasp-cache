from __future__ import annotations

import os
from pathlib import Path

from vasp_cache import health as health_module
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
    assert list(report) == ["schema_version", "report_timestamp", "cache_root", "metadata", "cas", "energy", "scan"]
    assert report["report_timestamp"].endswith("+00:00")


def test_health_reports_malformed_identity_separately(cache_root: Path):
    _make_fixture(cache_root)
    meta.upsert_entry(
        cache_root,
        content_hash="d" * 64,
        objects={},
        key_generation=0,
        profile_id="",
        cached_at=4.0,
    )
    meta.upsert_entry(
        cache_root,
        content_hash="e" * 64,
        objects={},
        key_generation="not-an-integer",  # type: ignore[arg-type]
        profile_id=123,  # type: ignore[arg-type]
        cached_at=5.0,
    )
    report = health_report(cache_root)
    assert report["metadata"]["missing_identity"] == 1
    assert report["metadata"]["malformed_identity"] == 2
    assert len(report["metadata"]["samples"]["malformed_identity"]) == 2


def test_health_energy_outlier_samples_stay_bounded_for_large_stream(
    cache_root: Path, monkeypatch
):
    seen_keys: list[str] = []
    original_add_sample = health_module._add_sample

    def tracking_add_sample(samples, key, record):
        seen_keys.append(key)
        original_add_sample(samples, key, record)

    monkeypatch.setattr(health_module, "_add_sample", tracking_add_sample)
    for index in range(25):
        meta.upsert_entry(
            cache_root,
            content_hash=f"{index + 1:064x}",
            objects={},
            total_energy=10.0 + index,
            key_generation=5,
            profile_id="default",
            cached_at=float(index),
        )
    report = health_report(cache_root, energy_max=0.0)
    assert seen_keys.count("energy_outliers") == 25
    assert len(report["energy"]["samples"]) == 20
    assert [row["content_hash"] for row in report["energy"]["samples"]] == [
        f"{index + 1:064x}" for index in range(20)
    ]


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


def test_health_cas_scan_detects_duplicate_digest_path(cache_root: Path):
    digest = cas.put_bytes(cache_root, b"duplicate")
    duplicate = cas.cas_root(cache_root) / "zz" / "zz" / digest
    duplicate.parent.mkdir(parents=True)
    duplicate.write_bytes(b"duplicate")
    meta.upsert_entry(
        cache_root,
        content_hash="d" * 64,
        objects={"OUTCAR": digest},
        key_generation=5,
        profile_id="default",
    )
    report = health_report(cache_root, scan_cas=True)
    assert report["cas"]["physical_objects"] == 1
    assert report["cas"]["path_mismatches"] == 1


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
