#!/usr/bin/env python3
"""Verify vasp-cache against real VASP calculation directories.

Examples:
  python scripts/verify_real_calcs.py \\
    /mnt/shared/home/2sidesniddle/vasp/2025_undergo_spin_defect/ZnO/cpd/ZnO_mp-2133

  REAL_VASP_CALC_ROOT=... python scripts/verify_real_calcs.py --discover 3
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

# Allow running from repo without install
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

from vasp_cache.api import fetch, get_meta, has, put  # noqa: E402
from vasp_cache.mapping import content_hash  # noqa: E402
from vasp_cache.paths import override_cache_root  # noqa: E402


def _complete(d: Path) -> bool:
    need = ("INCAR", "KPOINTS", "OUTCAR", "POTCAR")
    if not d.is_dir() or not all((d / f).is_file() for f in need):
        return False
    if not ((d / "CONTCAR").is_file() or (d / "POSCAR").is_file()):
        return False
    return (d / "OUTCAR").stat().st_size >= 10_000


def discover(root: Path, n: int) -> list[Path]:
    out: list[Path] = []
    for outcar in root.rglob("OUTCAR"):
        d = outcar.parent
        if d.name == "output":
            continue
        if not _complete(d):
            continue
        out.append(d)
        if len(out) >= n:
            break
    return out


def verify_one(calc: Path) -> None:
    print(f"==> {calc}")
    if not _complete(calc):
        raise SystemExit(f"incomplete calc: {calc}")
    original = (calc / "OUTCAR").read_bytes()
    ch = put(calc)
    if not ch:
        raise SystemExit("put returned None")
    print(f"    put hash={ch[:80]}...")
    meta = get_meta(calc)
    print(
        f"    energy={meta.get('total_energy')} formula={meta.get('formula')} "
        f"nsites={meta.get('nsites')} parsed_by={meta.get('parsed_by')}"
    )
    with tempfile.TemporaryDirectory() as td:
        work = Path(td) / "work"
        work.mkdir()
        for name in ("INCAR", "POSCAR", "CONTCAR", "KPOINTS", "POTCAR"):
            src = calc / name
            if src.is_file():
                shutil.copy2(src, work / name)
        assert content_hash(work) == content_hash(calc)
        assert has(work)
        assert fetch(work)
        restored = (work / "OUTCAR").read_bytes()
        if restored != original:
            raise SystemExit("OUTCAR bytes mismatch after fetch")
    print("    fetch OK (OUTCAR bytes match)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("dirs", nargs="*", type=Path, help="complete VASP calc directories")
    ap.add_argument(
        "--discover",
        type=int,
        default=0,
        help="auto-pick N complete calcs under REAL_VASP_CALC_ROOT",
    )
    ap.add_argument(
        "--cache-root",
        type=Path,
        default=None,
        help="isolated cache root (default: temp dir)",
    )
    args = ap.parse_args()

    dirs = list(args.dirs)
    if args.discover:
        root = Path(
            os.environ.get(
                "REAL_VASP_CALC_ROOT",
                "/mnt/shared/home/2sidesniddle/vasp/2025_undergo_spin_defect",
            )
        )
        dirs.extend(discover(root, args.discover))
    if not dirs:
        ap.error("provide dirs or --discover N")

    import tempfile

    tmp = None
    if args.cache_root:
        override_cache_root(args.cache_root)
        cache_root = args.cache_root
    else:
        tmp = tempfile.TemporaryDirectory()
        cache_root = Path(tmp.name) / "cache"
        override_cache_root(cache_root)
    print(f"cache root: {cache_root}")
    try:
        for d in dirs:
            verify_one(d.resolve())
    finally:
        override_cache_root(None)
        if tmp:
            tmp.cleanup()
    print("ALL OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
