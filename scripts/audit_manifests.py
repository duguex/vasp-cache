#!/usr/bin/env python3
"""Audit metadata object maps as read-only manifest candidates.

The audit never opens a write-capable cache connection and never changes cache
state.  It reports manifest identity separately from the legacy metadata hash
and from the integrity of referenced CAS objects.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from vasp_cache import cas, meta


def _non_negative_limit(value: str) -> int:
    limit = int(value)
    if limit < 0:
        raise argparse.ArgumentTypeError("limit must be non-negative")
    return limit


def _manifest(objects: dict[Any, Any]) -> tuple[dict[str, Any], str]:
    normalized = {
        str(name): (value.lower() if isinstance(value, str) else str(value).lower())
        for name, value in objects.items()
    }
    manifest = {
        "manifest_schema": 1,
        "objects": {name: normalized[name] for name in sorted(normalized)},
    }
    canonical = json.dumps(
        manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return manifest, "manifest:" + hashlib.sha256(canonical).hexdigest()


def _relative_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _object_check(
    root: Path,
    logical_name: str,
    raw_digest: Any,
    verification: dict[str, str],
    verify_content: bool,
) -> dict[str, Any]:
    digest_text = raw_digest if isinstance(raw_digest, str) else str(raw_digest)
    normalized = digest_text.lower()
    path: Path | None = None
    path_valid = False
    exists = False
    size: int | None = None
    status: str

    try:
        path = cas.object_path(root, normalized)
        # object_path provides the only valid layout.  A symlink at the
        # location is not a canonical CAS path, even if it points to a file.
        path_valid = path == path.resolve()
        exists = path.is_file()
        if exists:
            size = path.stat().st_size
    except (OSError, ValueError):
        path_valid = False

    if path is None:
        status = "invalid_digest"
    elif not path_valid:
        status = "path_mismatch"
    elif not exists:
        status = "missing"
    elif not verify_content:
        status = "unverified"
    else:
        if normalized not in verification:
            try:
                actual = cas.file_digest(path).lower()
            except OSError:
                verification[normalized] = "missing"
            else:
                verification[normalized] = (
                    "verified" if actual == normalized else "digest_mismatch"
                )
        status = verification[normalized]

    return {
        "logical_name": logical_name,
        "object_digest": raw_digest,
        "path": _relative_path(root, path) if path is not None else None,
        "path_valid": path_valid,
        "exists": exists,
        "size": size,
        "content_status": status,
    }


def _candidate_status(checks: list[dict[str, Any]]) -> str:
    statuses = {check["content_status"] for check in checks}
    if statuses & {"invalid_digest", "path_mismatch", "missing", "digest_mismatch", "digest_error"}:
        return "invalid"
    if statuses and statuses == {"verified"}:
        return "ready"
    return "unverified"


def _empty_report() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "rows_selected": 0,
        "candidates": [],
        "conflicts": [],
        "object_summary": {
            "referenced_objects": 0,
            "present_objects": 0,
            "verified_objects": 0,
            "unverified_objects": 0,
            "missing_objects": 0,
            "path_mismatch_objects": 0,
            "digest_mismatch_objects": 0,
            "invalid_digest_objects": 0,
        },
        "errors": [],
    }


def audit_root(
    root: Path, *, limit: int = 0, verify_content: bool = False
) -> dict[str, Any]:
    """Return a deterministic, read-only audit report for *root*."""
    if limit < 0:
        raise ValueError("limit must be non-negative")
    root = Path(root)
    report = _empty_report()
    root = Path(root).resolve()
    conn = meta.connect_readonly(root)
    if conn is None:
        return report

    verification: dict[str, str] = {}
    try:
        query = "SELECT * FROM entries ORDER BY cached_at, content_hash"
        params: tuple[int, ...] = ()
        if limit > 0:
            query += " LIMIT ?"
            params = (limit,)
        cursor = conn.execute(query, params)
        for row in cursor:
            report["rows_selected"] += 1
            try:
                content_hash = row["content_hash"]
                if not isinstance(content_hash, str) or not content_hash:
                    raise ValueError("content_hash must be a non-empty string")
                entry = meta._row_to_dict(row)
            except Exception as exc:
                try:
                    content_hash = row["content_hash"]
                except Exception:
                    content_hash = None
                report["errors"].append(
                    {"content_hash": content_hash, "error": str(exc)}
                )
                continue
            try:
                objects_value = entry.get("objects")
                if not isinstance(objects_value, dict) or not objects_value:
                    raise TypeError("objects must be a non-empty JSON object")
                objects = objects_value
                manifest, manifest_digest = _manifest(objects)
                checks = [
                    _object_check(
                        root,
                        name,
                        objects[name],
                        verification,
                        verify_content,
                    )
                    for name in sorted(objects, key=str)
                ]
            except Exception as exc:
                report["errors"].append(
                    {"content_hash": content_hash, "error": str(exc)}
                )
                continue

            legacy_hash = str(entry.get("legacy_content_hash") or content_hash)
            candidate = {
                "candidate_id": str(content_hash),
                "legacy_content_hash": legacy_hash,
                "candidate_status": _candidate_status(checks),
                "manifest": manifest,
                "manifest_digest": manifest_digest,
                "object_checks": checks,
            }
            report["candidates"].append(candidate)
    finally:
        conn.close()

    object_checks = [
        check
        for candidate in report["candidates"]
        for check in candidate["object_checks"]
    ]
    by_digest: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for check in object_checks:
        digest = str(check["object_digest"]).lower()
        by_digest[digest].append(check)
    summary = report["object_summary"]
    summary["referenced_objects"] = len(by_digest)
    summary["present_objects"] = sum(
        1 for checks in by_digest.values() if any(check["exists"] for check in checks)
    )
    summary["verified_objects"] = sum(
        1 for digest in by_digest if verification.get(digest) == "verified"
    )
    summary["unverified_objects"] = sum(
        1
        for checks in by_digest.values()
        if any(check["content_status"] == "unverified" for check in checks)
    )
    summary["missing_objects"] = sum(
        1 for checks in by_digest.values() if any(check["content_status"] == "missing" for check in checks)
    )
    summary["path_mismatch_objects"] = sum(
        1
        for checks in by_digest.values()
        if any(check["content_status"] == "path_mismatch" for check in checks)
    )
    summary["digest_mismatch_objects"] = sum(
        1
        for checks in by_digest.values()
        if any(check["content_status"] == "digest_mismatch" for check in checks)
    )
    summary["invalid_digest_objects"] = sum(
        1
        for checks in by_digest.values()
        if any(check["content_status"] == "invalid_digest" for check in checks)
    )

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in report["candidates"]:
        groups[candidate["legacy_content_hash"]].append(candidate)
    for legacy_hash in sorted(groups):
        candidates = groups[legacy_hash]
        if len({candidate["manifest_digest"] for candidate in candidates}) <= 1:
            continue
        report["conflicts"].append(
            {
                "legacy_content_hash": legacy_hash,
                "candidate_ids": [candidate["candidate_id"] for candidate in candidates],
                "candidate_count": len(candidates),
                "reason": "legacy_identity_collision",
            }
        )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--limit", type=_non_negative_limit, default=0)
    parser.add_argument("--verify-content", action="store_true")
    parser.add_argument("--json", action="store_true", help="emit JSON output")
    args = parser.parse_args(argv)
    report = audit_root(args.root, limit=args.limit, verify_content=args.verify_content)
    print(json.dumps(report, indent=2 if args.json else None, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
