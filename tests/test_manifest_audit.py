from __future__ import annotations

import hashlib
import json
import importlib.util
from pathlib import Path

import pytest

from vasp_cache import cas, meta

_SPEC = importlib.util.spec_from_file_location(
    "audit_manifests", Path(__file__).parents[1] / "scripts" / "audit_manifests.py"
)
assert _SPEC is not None and _SPEC.loader is not None
_AUDIT = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_AUDIT)
audit_root = _AUDIT.audit_root


EXPECTED_DIGEST = hashlib.sha256(b"shared object").hexdigest()
OTHER_DIGEST = hashlib.sha256(b"other object").hexdigest()


def _seed_entry(
    root: Path,
    content_hash: str,
    objects: dict[str, str],
    *,
    cached_at: float,
    legacy_content_hash: str | None = None,
) -> None:
    meta.upsert_entry(
        root,
        content_hash=content_hash,
        objects=objects,
        cached_at=cached_at,
        extra=(
            {"legacy_content_hash": legacy_content_hash}
            if legacy_content_hash is not None
            else None
        ),
    )


def test_audit_streams_candidates_and_separates_conflicts(cache_root: Path):
    cas.put_bytes(cache_root, b"shared object")
    _seed_entry(
        cache_root,
        "row-a",
        {"OUTCAR": EXPECTED_DIGEST},
        cached_at=1,
        legacy_content_hash="legacy-collision",
    )
    _seed_entry(
        cache_root,
        "row-b",
        {"OUTCAR": "f" * 64},
        cached_at=2,
        legacy_content_hash="legacy-collision",
    )
    _seed_entry(
        cache_root,
        "row-c",
        {"OUTCAR": EXPECTED_DIGEST},
        cached_at=3,
        legacy_content_hash="legacy-valid",
    )

    report = audit_root(cache_root)

    assert report["rows_selected"] == 3
    assert report["candidates"]
    assert report["conflicts"][0]["reason"] == "legacy_identity_collision"
    assert any(
        check["content_status"] == "missing"
        for candidate in report["candidates"]
        for check in candidate["object_checks"]
    )
    assert any(
        candidate["candidate_status"] == "unverified"
        for candidate in report["candidates"]
    )
    assert all("manifest_digest" in candidate for candidate in report["candidates"])
    assert report["object_summary"]["referenced_objects"] == 2


def test_audit_verify_content_deduplicates_object_hashing(
    cache_root: Path, monkeypatch: pytest.MonkeyPatch
):
    cas.put_bytes(cache_root, b"shared object")
    _seed_entry(cache_root, "row-a", {"OUTCAR": EXPECTED_DIGEST}, cached_at=1)
    _seed_entry(cache_root, "row-b", {"CONTCAR": EXPECTED_DIGEST}, cached_at=2)
    calls: list[str] = []

    monkeypatch.setattr(
        cas,
        "file_digest",
        lambda path: calls.append(str(path)) or EXPECTED_DIGEST,
    )

    report = audit_root(cache_root, verify_content=True)

    assert report["object_summary"]["verified_objects"] == 1
    assert len(calls) == 1
    assert all(
        value == EXPECTED_DIGEST
        for candidate in report["candidates"]
        for value in candidate["manifest"]["objects"].values()
    )
    assert all(
        check["content_status"] == "verified"
        for candidate in report["candidates"]
        for check in candidate["object_checks"]
    )
    assert all(candidate["candidate_status"] == "ready" for candidate in report["candidates"])


def test_manifest_digest_is_canonical_and_distinct_from_cas_digest(cache_root: Path):
    cas.put_bytes(cache_root, b"shared object")
    _seed_entry(
        cache_root,
        "row-a",
        {"z": EXPECTED_DIGEST.upper(), "a": OTHER_DIGEST},
        cached_at=1,
    )

    report = audit_root(cache_root)
    candidate = report["candidates"][0]
    manifest = {
        "manifest_schema": 1,
        "objects": {"a": OTHER_DIGEST, "z": EXPECTED_DIGEST},
    }
    canonical = json.dumps(
        manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")

    assert candidate["manifest"] == manifest
    assert candidate["manifest_digest"] == "manifest:" + hashlib.sha256(canonical).hexdigest()
    assert candidate["manifest_digest"] != EXPECTED_DIGEST
    assert candidate["manifest_digest"] != OTHER_DIGEST
    assert candidate["object_checks"][0]["path_valid"] is True
    assert candidate["candidate_status"] == "invalid"


def test_malformed_row_is_error_and_later_rows_continue(cache_root: Path):
    _seed_entry(cache_root, "bad", {"OUTCAR": EXPECTED_DIGEST}, cached_at=1)
    _seed_entry(cache_root, "good", {"OUTCAR": EXPECTED_DIGEST}, cached_at=2)
    connection = meta.connect(cache_root)
    connection.execute(
        "UPDATE entries SET objects_json = ? WHERE content_hash = ?",
        ("{malformed", "bad"),
    )
    connection.commit()

    report = audit_root(cache_root)

    assert report["rows_selected"] == 2
    assert report["errors"]
    assert report["errors"][0]["content_hash"] == "bad"
    assert [candidate["legacy_content_hash"] for candidate in report["candidates"]] == [
        "good"
    ]

def test_blob_content_hash_error_is_json_safe_and_later_rows_continue(
    cache_root: Path, capsys: pytest.CaptureFixture[str]
):
    _seed_entry(cache_root, b"\x00\xff", {"OUTCAR": EXPECTED_DIGEST}, cached_at=1)
    _seed_entry(cache_root, "good", {"OUTCAR": EXPECTED_DIGEST}, cached_at=2)

    exit_code = _AUDIT.main(["--root", str(cache_root), "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["errors"] == [
        {
            "content_hash": "hex:00ff",
            "error": "content_hash must be a non-empty string",
        }
    ]
    assert [candidate["candidate_id"] for candidate in payload["candidates"]] == [
        "good"
    ]


def test_audit_missing_root_does_not_create_state(tmp_path: Path):
    root = tmp_path / "missing"

    report = audit_root(root)

    assert report["rows_selected"] == 0
    assert not root.exists()
    assert report["candidates"] == []
    assert report["errors"] == []


def test_audit_rejects_negative_limit(cache_root: Path):
    with pytest.raises(ValueError, match="non-negative"):
        audit_root(cache_root, limit=-1)

@pytest.mark.parametrize("objects", [None, {}, [], "", 0, False])
def test_audit_rejects_empty_or_non_object_shapes(cache_root: Path, objects: object):
    _seed_entry(cache_root, "bad-objects", objects, cached_at=1)  # type: ignore[arg-type]

    report = audit_root(cache_root)

    assert report["candidates"] == []
    assert report["conflicts"] == []
    assert report["errors"] == [
        {
            "content_hash": "bad-objects",
            "error": "objects must be a non-empty JSON object",
        }
    ]

@pytest.mark.parametrize(
    ("content_hash", "expected_identifier"),
    [(None, None), ("", ""), (b"not-text", "hex:6e6f742d74657874")],
)
def test_audit_rejects_invalid_content_hash_rows(
    cache_root: Path, content_hash: object, expected_identifier: str | None
):
    _seed_entry(
        cache_root,
        content_hash,  # type: ignore[arg-type]
        {"OUTCAR": EXPECTED_DIGEST},
        cached_at=1,
    )

    report = audit_root(cache_root)

    assert report["candidates"] == []
    assert report["conflicts"] == []
    assert len(report["errors"]) == 1
    assert report["errors"][0]["content_hash"] == expected_identifier
    assert report["errors"][0]["error"] == "content_hash must be a non-empty string"
