"""CLI for vasp-cache."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vasp-cache", description="VASP calculation cache")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_put = sub.add_parser("put", help="Ingest a complete VASP calculation")
    p_put.add_argument("dir", type=Path)
    p_put.add_argument("-r", "--recursive", action="store_true")

    p_fetch = sub.add_parser("fetch", help="Restore outputs from cache into input dir")
    p_fetch.add_argument("dir", type=Path)

    p_has = sub.add_parser("has", help="Check cache hit for input dir")
    p_has.add_argument("dir", type=Path)

    p_query = sub.add_parser(
        "query",
        help="Query cache metadata (e.g. vasp-cache query --formula GaN)",
    )
    p_query.add_argument("--formula", "-f", help="exact chemical formula, e.g. GaN or SiC")
    p_query.add_argument("--functional", help="substring match in tags (e.g. PBE, HSE)")
    p_query.add_argument("--tags", help="substring match in tags field")
    p_query.add_argument("--bandgap-min", type=float, dest="bandgap_min")
    p_query.add_argument("--lattice-max", type=float, dest="lattice_max")
    p_query.add_argument(
        "--all",
        action="store_true",
        help="include unconverged rows (default: converged only)",
    )
    p_query.add_argument("--limit", "-n", type=int, default=20)
    p_query.add_argument(
        "--json",
        action="store_true",
        help="print full JSON (default: compact table)",
    )

    sub.add_parser("status", help="Show cache stats")

    p_ch = sub.add_parser("content-hash", help="Print content_hash for a directory")
    p_ch.add_argument("dir", type=Path)

    p_map = sub.add_parser("mapping", help="Mapping profile tools")
    map_sub = p_map.add_subparsers(dest="map_cmd", required=True)
    map_sub.add_parser("show", help="Show resolved mapping profile")
    map_sub.add_parser("check", help="Run golden-pair mapping checks")

    p_exp = sub.add_parser("export-archive", help="Export whole cache to tar.gz")
    p_exp.add_argument("dest", type=Path, help="output .tar.gz path")
    p_exp.add_argument("--root", type=Path, default=None, help="cache root to export")

    p_imp = sub.add_parser("import-archive", help="Import whole cache from tar.gz")
    p_imp.add_argument("archive", type=Path, help="input .tar.gz path")
    p_imp.add_argument("--root", type=Path, default=None, help="destination cache root")
    p_imp.add_argument(
        "--overwrite",
        action="store_true",
        help="replace existing destination cache contents",
    )

    args = parser.parse_args(argv)

    if args.cmd == "put":
        from vasp_cache.api import put

        if args.recursive:
            n = 0
            for outcar in Path(args.dir).rglob("OUTCAR"):
                ch = put(outcar.parent)
                if ch:
                    n += 1
                    print(ch)
            print(f"cached {n} calculations", file=sys.stderr)
            return 0
        ch = put(args.dir)
        if ch is None:
            print("skip: not usable", file=sys.stderr)
            return 1
        print(ch)
        return 0

    if args.cmd == "fetch":
        from vasp_cache.api import fetch

        ok = fetch(args.dir)
        print("hit" if ok else "miss")
        return 0 if ok else 1

    if args.cmd == "has":
        from vasp_cache.api import has

        ok = has(args.dir)
        print("true" if ok else "false")
        return 0 if ok else 1

    if args.cmd == "query":
        from vasp_cache.api import query

        rows = query(
            formula=args.formula,
            functional=args.functional,
            tags_contains=args.tags,
            bandgap_min=args.bandgap_min,
            lattice_max=args.lattice_max,
            converged_only=not args.all,
            limit=args.limit,
        )
        if args.json:
            print(json.dumps(rows, indent=2, default=str))
        else:
            if not rows:
                print("0 hits")
                return 0
            print(f"{len(rows)} hit(s)")
            print(
                f"{'formula':<16} {'E(eV)':>14} {'gap':>8} {'conv':>4} {'nsites':>6}  content_hash"
            )
            for r in rows:
                e = r.get("total_energy")
                e_s = f"{e:.6f}" if isinstance(e, (int, float)) else str(e)
                g = r.get("bandgap")
                g_s = f"{g:.3f}" if isinstance(g, (int, float)) else "-"
                conv = "Y" if r.get("converged") else "N"
                ns = r.get("nsites") if r.get("nsites") is not None else "-"
                ch = str(r.get("content_hash") or "")[:56]
                print(
                    f"{str(r.get('formula') or '-'):<16} {e_s:>14} {g_s:>8} {conv:>4} {str(ns):>6}  {ch}"
                )
        return 0

    if args.cmd == "status":
        from vasp_cache.api import list_entries, stats

        s = stats()
        print(json.dumps(s, indent=2))
        for e in list_entries(limit=10):
            print(
                f"  {e.get('formula')}  E={e.get('total_energy')}  "
                f"{str(e.get('content_hash'))[:48]}"
            )
        return 0

    if args.cmd == "content-hash":
        from vasp_cache.mapping import content_hash

        print(content_hash(args.dir))
        return 0

    if args.cmd == "mapping":
        from vasp_cache.mapping import load_mapping

        if args.map_cmd == "show":
            m = load_mapping()
            print(json.dumps(m if isinstance(m, dict) else getattr(m, "__dict__", str(m)), indent=2, default=str))
            try:
                print("profile ok", file=sys.stderr)
            except Exception as exc:
                print(exc, file=sys.stderr)
                return 1
            return 0
        if args.map_cmd == "check":
            load_mapping()
            print("mapping check: default profile loads OK")
            return 0

    if args.cmd == "export-archive":
        from vasp_cache.archive import export_archive

        path = export_archive(args.dest, root=args.root)
        print(path)
        return 0

    if args.cmd == "import-archive":
        from vasp_cache.archive import import_archive

        man = import_archive(args.archive, root=args.root, overwrite=args.overwrite)
        print(json.dumps(man, indent=2, default=str))
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
