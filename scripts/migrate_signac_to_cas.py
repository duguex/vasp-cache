#!/usr/bin/env python3
"""One-shot: signac workspace/ → CAS + meta.sqlite.

Does not delete the signac tree. Writes into --dest (default: same root's
sibling or --dest). Typical::

    python scripts/migrate_signac_to_cas.py \\
        --src ~/.vasp_cache \\
        --dest /mnt/shared/vasp_cache
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from vasp_cache import cas, meta
from vasp_cache.paths import _reset_project, override_cache_root


def migrate_job(job_dir: Path, dest: Path) -> str | None:
    """Migrate one signac job directory. Return content_hash or None."""
    sp_path = job_dir / "signac_statepoint.json"
    doc_path = job_dir / "signac_job_document.json"
    if not sp_path.is_file():
        return None
    sp = json.loads(sp_path.read_text())
    ch = sp.get("content_hash")
    if not ch:
        return None
    doc = {}
    if doc_path.is_file():
        doc = json.loads(doc_path.read_text())

    objects: dict[str, str] = {}
    for name in (
        "OUTCAR",
        "CONTCAR",
        "vasprun.xml",
        "INCAR",
        "POSCAR",
        "KPOINTS",
    ):
        p = job_dir / name
        if p.is_file():
            objects[name] = cas.put_file(dest, p)
    if "OUTCAR" not in objects:
        return None

    meta.upsert_entry(
        dest,
        content_hash=ch,
        objects=objects,
        formula=doc.get("formula"),
        task_name=doc.get("task_name"),
        total_energy=doc.get("total_energy"),
        converged=doc.get("converged"),
        bandgap=doc.get("bandgap"),
        nsites=doc.get("nsites"),
        max_abc=doc.get("max_abc"),
        tags=doc.get("tags"),
        source_dir=doc.get("source_dir"),
        profile_id=doc.get("profile_id"),
        key_generation=doc.get("key_generation"),
        mapping_digest=doc.get("mapping_digest"),
        cached_at=doc.get("cached_at") or time.time(),
        extra={
            k: v
            for k, v in doc.items()
            if k
            not in {
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
            }
        }
        or None,
    )
    return ch


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", type=Path, required=True, help="signac cache root")
    ap.add_argument("--dest", type=Path, required=True, help="CAS cache root")
    ap.add_argument("--limit", type=int, default=0, help="max jobs (0=all)")
    args = ap.parse_args(argv)

    workspace = args.src / "workspace"
    if not workspace.is_dir():
        print(f"no workspace at {workspace}", file=sys.stderr)
        return 1

    _reset_project()
    override_cache_root(args.dest)
    args.dest.mkdir(parents=True, exist_ok=True)

    jobs = sorted(p for p in workspace.iterdir() if p.is_dir())
    if args.limit:
        jobs = jobs[: args.limit]

    ok = skip = err = 0
    t0 = time.time()
    for i, jdir in enumerate(jobs, 1):
        try:
            ch = migrate_job(jdir, args.dest)
            if ch:
                ok += 1
            else:
                skip += 1
        except Exception as exc:
            err += 1
            print(f"ERR {jdir.name}: {exc}", file=sys.stderr)
        if i % 100 == 0 or i == len(jobs):
            print(
                f"progress {i}/{len(jobs)} ok={ok} skip={skip} err={err} "
                f"elapsed={time.time()-t0:.1f}s",
                flush=True,
            )

    print("stats", meta.stats(args.dest))
    return 0 if err == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
