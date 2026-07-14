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
import shutil
import sys
import tempfile
import time
from pathlib import Path

from vasp_cache import cas, meta
from vasp_cache.mapping import content_hash
from vasp_cache.paths import _reset_project, override_cache_root


def rehash_root(root: Path, *, limit: int = 0) -> dict:
    _reset_project()
    override_cache_root(root)
    conn = meta.connect(root)
    rows = conn.execute(
        "SELECT content_hash, objects_json FROM entries ORDER BY cached_at"
    ).fetchall()
    if limit:
        rows = rows[:limit]

    ok = same = collide = err = 0
    t0 = time.time()
    for i, row in enumerate(rows, 1):
        old_ch = row["content_hash"]
        try:
            entry = meta.get_entry(root, old_ch)
            if not entry:
                err += 1
                continue
            objects = entry.get("objects") or {}
            with tempfile.TemporaryDirectory(prefix="rehash_") as td:
                td_path = Path(td)
                for name in ("INCAR", "POSCAR", "KPOINTS", "CONTCAR"):
                    dig = objects.get(name)
                    if dig and cas.has_object(root, dig):
                        cas.materialize(root, dig, td_path / name)
                # POSCAR required for structure; fall back CONTCAR→POSCAR
                if not (td_path / "POSCAR").is_file() and (td_path / "CONTCAR").is_file():
                    shutil.copy2(td_path / "CONTCAR", td_path / "POSCAR")
                new_ch = content_hash(td_path)
            if new_ch == old_ch:
                same += 1
                ok += 1
            else:
                # rewrite PK: insert new, delete old (if collision, last wins)
                existing = meta.get_entry(root, new_ch)
                if existing is not None and existing.get("content_hash") != old_ch:
                    collide += 1
                objects = entry.pop("objects")
                # strip fields that are not upsert kwargs
                extra = {
                    k: v
                    for k, v in entry.items()
                    if k
                    not in {
                        "content_hash",
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
                        "objects",
                    }
                }
                meta.upsert_entry(
                    root,
                    content_hash=new_ch,
                    objects=objects,
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
                )
                if new_ch != old_ch:
                    conn.execute(
                        "DELETE FROM entries WHERE content_hash = ?", (old_ch,)
                    )
                    conn.commit()
                ok += 1
        except Exception as exc:
            err += 1
            print(f"ERR {old_ch[:40]}: {exc}", file=sys.stderr)
        if i % 500 == 0 or i == len(rows):
            print(
                f"progress {i}/{len(rows)} ok={ok} same={same} "
                f"collide={collide} err={err} t={time.time()-t0:.1f}s",
                flush=True,
            )

    st = meta.stats(root)
    print("stats", st)
    return {"ok": ok, "same": same, "collide": collide, "err": err, "stats": st}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args(argv)
    r = rehash_root(args.root, limit=args.limit)
    return 0 if r["err"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
