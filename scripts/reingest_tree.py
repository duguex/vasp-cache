#!/usr/bin/env python3
"""Re-ingest a VASP tree into vasp-cache with progress and error reporting.

Example:
  python scripts/reingest_tree.py \\
    /mnt/shared/home/2sidesniddle/vasp/2025_undergo_spin_defect \\
    --log /tmp/vasp_cache_reingest.log
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

from vasp_cache.api import has, put, stats  # noqa: E402
from vasp_cache.paths import override_cache_root  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("root", type=Path, help="project root to walk")
    ap.add_argument(
        "--log",
        type=Path,
        default=Path("/tmp/vasp_cache_reingest.log"),
        help="append log path",
    )
    ap.add_argument(
        "--errors-json",
        type=Path,
        default=Path("/tmp/vasp_cache_reingest_errors.json"),
        help="JSON list of failures",
    )
    ap.add_argument(
        "--cache-root",
        type=Path,
        default=None,
        help="override VASP cache root (default: /mnt/shared/vasp_cache)",
    )
    ap.add_argument(
        "--progress-every",
        type=int,
        default=25,
        help="print progress every N OUTCARs seen",
    )
    ap.add_argument(
        "--skip-existing",
        action="store_true",
        help="skip dirs that already cache-hit (resume-friendly)",
    )
    args = ap.parse_args()

    root = args.root.resolve()
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 2

    if args.cache_root:
        override_cache_root(args.cache_root)

    log = args.log
    log.parent.mkdir(parents=True, exist_ok=True)

    def log_line(msg: str) -> None:
        line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
        print(line, flush=True)
        with log.open("a") as f:
            f.write(line + "\n")

    outcars = sorted(root.rglob("OUTCAR"))
    total = len(outcars)
    log_line(f"START root={root} outcars={total} cache_override={args.cache_root}")

    n_ok = n_skip = n_cached = n_err = 0
    errors: list[dict] = []
    t0 = time.time()

    for i, outcar in enumerate(outcars, 1):
        d = outcar.parent
        try:
            if args.skip_existing and has(d):
                n_cached += 1
            else:
                ch = put(d)
                if ch:
                    n_ok += 1
                else:
                    n_skip += 1
        except Exception as exc:
            n_err += 1
            err = {
                "dir": str(d),
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(limit=5),
            }
            errors.append(err)
            log_line(f"ERROR [{i}/{total}] {d}: {exc}")

        if i % args.progress_every == 0 or i == total:
            elapsed = time.time() - t0
            rate = i / elapsed if elapsed > 0 else 0
            eta = (total - i) / rate if rate > 0 else 0
            try:
                st = stats()
            except Exception as exc:
                st = {"error": str(exc)}
            log_line(
                f"PROGRESS {i}/{total} ok={n_ok} skip={n_skip} cached={n_cached} "
                f"err={n_err} rate={rate:.2f}/s eta={eta/60:.1f}min stats={st}"
            )

    elapsed = time.time() - t0
    args.errors_json.write_text(json.dumps(errors, indent=2))
    log_line(
        f"DONE ok={n_ok} skip={n_skip} cached={n_cached} err={n_err} "
        f"elapsed={elapsed/60:.1f}min errors_json={args.errors_json}"
    )
    try:
        log_line(f"FINAL_STATS {stats()}")
    except Exception as exc:
        log_line(f"FINAL_STATS_ERROR {exc}")

    return 1 if n_err else 0


if __name__ == "__main__":
    raise SystemExit(main())
