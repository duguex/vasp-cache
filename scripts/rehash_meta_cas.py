#!/usr/bin/env python3
"""Recompute content_hash for all CAS meta rows using current mapping.

Materializes INCAR/POSCAR/KPOINTS (and CONTCAR if needed) from CAS into a
temp dir, runs ``content_hash``, rewrites the primary key. Use after
mapping identity changes (e.g. potcar off / key_generation bump).

Example::

    python scripts/rehash_meta_cas.py --root /mnt/shared/vasp_cache
"""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

from vasp_cache import cas, meta
from vasp_cache.mapping import content_hash
from vasp_cache.paths import _reset_project, override_cache_root


def _non_negative_limit(value: str) -> int:
    limit = int(value)
    if limit < 0:
        raise argparse.ArgumentTypeError("limit must be non-negative")
    return limit


_BASE_FIELDS = {
    "content_hash",
    "objects",
    "formula",
    "task_name",
    "total_energy",
    "converged",
    "bandgap",
    "nsites",
    "max_abc",
    "tags",
    "source_dir",
    "profile_id",
    "key_generation",
    "mapping_digest",
    "cached_at",
    "provenance",
    "provenance_source",
    "outcar_complete",
    "electronic_converged",
    "ionic_converged",
    "nsw",
    "ibrion",
    "isif",
}


def _materialize_inputs(root: Path, entry: dict[str, Any], dest: Path) -> None:
    objects = entry.get("objects") or {}
    for name in ("INCAR", "POSCAR", "KPOINTS"):
        digest = objects.get(name)
        if not digest or not cas.has_object(root, digest):
            raise FileNotFoundError(f"required CAS object missing: {name}")
        cas.materialize(root, digest, dest / name)
    digest = objects.get("CONTCAR")
    if digest and cas.has_object(root, digest):
        cas.materialize(root, digest, dest / "CONTCAR")

def _new_hash(root: Path, entry: dict[str, Any]) -> str:
    with tempfile.TemporaryDirectory(prefix="rehash_") as td:
        td_path = Path(td)
        _materialize_inputs(root, entry, td_path)
        return content_hash(td_path)


def _group_row(
    group: dict[str, Any], old_hash: str, entry: dict[str, Any]
) -> None:
    group["old_hashes"].append(old_hash)
    group["output_digests"].append((entry.get("objects") or {}).get("OUTCAR"))


def inventory_root(root: Path, *, limit: int = 0) -> dict[str, Any]:
    """Inventory generation changes without modifying rows or CAS objects."""
    if limit < 0:
        raise ValueError("limit must be non-negative")
    conn = meta.connect_readonly(root)
    if conn is None:
        rows = []
    else:
        try:
            rows = conn.execute(
                "SELECT content_hash FROM entries ORDER BY cached_at"
            ).fetchall()
        finally:
            conn.close()
    if limit:
        rows = rows[:limit]

    groups: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, str]] = []
    for row in rows:
        old_hash = row["content_hash"]
        try:
            entry = meta.get_entry(root, old_hash)
            if entry is None:
                raise KeyError(f"metadata row missing: {old_hash}")
            new_hash = _new_hash(root, entry)
            group = groups.setdefault(
                new_hash,
                {
                    "new_hash": new_hash,
                    "old_hashes": [],
                    "output_digests": [],
                },
            )
            _group_row(group, old_hash, entry)
        except Exception as exc:
            errors.append({"old_hash": old_hash, "error": str(exc)})

    safe = []
    collisions: dict[str, dict[str, Any]] = {}
    unchanged = []
    for new_hash, group in groups.items():
        if (
            len(group["old_hashes"]) > 1
            or len(set(group["output_digests"])) > 1
        ):
            collisions[new_hash] = group
        elif group["old_hashes"][0] == new_hash:
            unchanged.append(group)
        else:
            safe.append(group)
    return {
        "rows": len(rows),
        "groups": groups,
        "safe": safe,
        "unchanged": unchanged,
        "collisions": collisions,
        "errors": errors,
    }


def _upsert_preserving_metadata(
    root: Path, new_hash: str, entry: dict[str, Any]
) -> None:
    extra = {k: v for k, v in entry.items() if k not in _BASE_FIELDS}
    meta.upsert_entry(
        root,
        content_hash=new_hash,
        objects=entry.get("objects") or {},
        formula=entry.get("formula"),
        task_name=entry.get("task_name"),
        total_energy=entry.get("total_energy"),
        converged=entry.get("converged"),
        bandgap=entry.get("bandgap"),
        nsites=entry.get("nsites"),
        max_abc=entry.get("max_abc"),
        tags=entry.get("tags"),
        source_dir=entry.get("source_dir"),
        profile_id=entry.get("profile_id"),
        key_generation=entry.get("key_generation"),
        mapping_digest=entry.get("mapping_digest"),
        cached_at=entry.get("cached_at"),
        extra=extra or None,
        provenance=entry.get("provenance", "unknown"),
        provenance_source=entry.get("provenance_source", "legacy"),
        outcar_complete=entry.get("outcar_complete"),
        electronic_converged=entry.get("electronic_converged"),
        ionic_converged=entry.get("ionic_converged"),
        nsw=entry.get("nsw"),
        ibrion=entry.get("ibrion"),
        isif=entry.get("isif"),
    )


def apply_inventory(root: Path, inventory: dict[str, Any]) -> dict[str, Any]:
    """Apply only safe, single-row inventory groups."""
    _reset_project()
    override_cache_root(root)
    applied = 0
    skipped = 0
    errors = list(inventory.get("errors", []))
    conn = meta.connect(root)
    for group in inventory.get("safe", []):
        old_hash = group["old_hashes"][0]
        new_hash = group["new_hash"]
        if meta.get_entry(root, new_hash) is not None:
            errors.append(
                {"old_hash": old_hash, "error": "target hash already exists"}
            )
            continue
        entry = meta.get_entry(root, old_hash)
        if entry is None:
            errors.append(
                {"old_hash": old_hash, "error": "source row missing"}
            )
            continue
        _upsert_preserving_metadata(root, new_hash, entry)
        conn.execute("DELETE FROM entries WHERE content_hash = ?", (old_hash,))
        conn.commit()
        applied += 1
    skipped = len(inventory.get("collisions", {}))
    return {"applied": applied, "skipped": skipped, "errors": errors}


def rehash_root(
    root: Path, *, limit: int = 0, apply: bool = False
) -> dict[str, Any]:
    """Inventory by default; apply only explicit, safe rewrites."""
    inventory = inventory_root(root, limit=limit)
    if apply:
        result = apply_inventory(root, inventory)
        inventory["apply"] = result
    return inventory


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--limit", type=_non_negative_limit, default=0)
    ap.add_argument(
        "--apply",
        action="store_true",
        help="rewrite only non-colliding groups from the inventory",
    )
    args = ap.parse_args(argv)
    result = rehash_root(args.root, limit=args.limit, apply=args.apply)
    print(json.dumps(result, indent=2, sort_keys=True))
    errors = result.get("errors", [])
    errors += result.get("apply", {}).get("errors", [])
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
