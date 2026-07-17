"""CLI for vasp-cache."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _add_query_options(parser: argparse.ArgumentParser) -> None:
    """Add the common metadata query filters to *parser*."""
    parser.add_argument("--formula", "-f", help="exact chemical formula, e.g. GaN or SiC")
    parser.add_argument("--functional", help="substring match in tags (e.g. PBE, HSE)")
    parser.add_argument("--tags", help="substring match in tags field")
    parser.add_argument("--bandgap-min", type=float, dest="bandgap_min")
    parser.add_argument("--lattice-max", type=float, dest="lattice_max")
    parser.add_argument("--min-energy", type=float, dest="min_energy")
    parser.add_argument("--max-energy", type=float, dest="max_energy")
    convergence = parser.add_mutually_exclusive_group()
    convergence.add_argument(
        "--all",
        action="store_true",
        help="include unconverged rows (default: converged only)",
    )
    convergence.add_argument(
        "--converged-only",
        action="store_true",
        help="include only converged rows (the default)",
    )
    parser.add_argument(
        "--provenance",
        choices=("canonical", "sampled", "unknown", "all"),
        default="canonical",
        help="provenance filter (default: canonical)",
    )
    parser.add_argument("--limit", "-n", type=int, default=20)
    parser.add_argument("--offset", type=int, default=0)


def _add_output_flags(parser: argparse.ArgumentParser, *, collection: bool) -> None:
    outputs = parser.add_mutually_exclusive_group()
    outputs.add_argument("--json", action="store_true", help="print JSON")
    if collection:
        outputs.add_argument("--jsonl", action="store_true", help="print one JSON object per line")


def _converged_only(args: argparse.Namespace) -> bool:
    return not args.all or args.converged_only


def _query_kwargs(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "formula": args.formula,
        "functional": args.functional,
        "tags": args.tags,
        "bandgap_min": args.bandgap_min,
        "lattice_max": args.lattice_max,
        "min_energy": args.min_energy,
        "max_energy": args.max_energy,
        "converged_only": _converged_only(args),
        "provenance": args.provenance,
    }


def _render_jsonl(rows: list[dict[str, Any]]) -> None:
    for row in rows:
        print(json.dumps(row, default=str, sort_keys=True, separators=(",", ":")))


def _render_entries_table(rows: list[dict[str, Any]]) -> None:
    if not rows:
        print("0 entries")
        return
    print(f"{len(rows)} entr{'y' if len(rows) == 1 else 'ies'}")
    print(
        f"{'formula':<16} {'E(eV)':>14} {'gap':>8} {'conv':>4} "
        f"{'prov':<10} {'nsites':>6} {'objects':>7}  content_hash"
    )
    for row in rows:
        energy = row.get("total_energy")
        energy_s = f"{energy:.6f}" if isinstance(energy, (int, float)) else "-"
        gap = row.get("bandgap")
        gap_s = f"{gap:.3f}" if isinstance(gap, (int, float)) else "-"
        convergence = "Y" if row.get("converged") else "N"
        nsites = row.get("nsites") if row.get("nsites") is not None else "-"
        print(
            f"{str(row.get('formula') or '-'):<16} {energy_s:>14} {gap_s:>8} "
            f"{convergence:>4} {str(row.get('provenance') or '-'):<10} "
            f"{str(nsites):>6} {str(row.get('object_count', 0)):>7}  "
            f"{row.get('content_hash', '')}"
        )


def _render_objects_table(rows: list[dict[str, Any]]) -> None:
    if not rows:
        print("0 objects")
        return
    print(f"{len(rows)} object{'s' if len(rows) != 1 else ''}")
    print(f"{'digest':<64} {'size':>10} {'refs':>6} {'orphan':>6} logical_names")
    for row in rows:
        size = row.get("size") if row.get("size") is not None else "-"
        names = ",".join(row.get("logical_names") or []) or "-"
        print(
            f"{row.get('digest', ''):<64} {str(size):>10} "
            f"{row.get('reference_count', 0):>6} {str(bool(row.get('orphan'))):>6} {names}"
        )


def _render_summary_table(payload: dict[str, Any]) -> None:
    for key in (
        "entries",
        "formulas",
        "converged",
        "with_energy",
        "cas_objects",
        "cas_bytes",
        "referenced_objects",
        "referenced_bytes",
        "orphan_objects",
        "orphan_bytes",
        "provenance",
        "key_generations",
        "profile_ids",
    ):
        print(f"{key}: {payload.get(key)}")


def _render_overview_table(payload: dict[str, Any]) -> None:
    for key in (
        "entries",
        "formulas",
        "with_energy",
        "with_bandgap",
        "converged",
        "provenance",
        "key_generations",
        "profile_ids",
        "energy_range",
        "cached_at_range",
        "storage_scan",
    ):
        print(f"{key}: {payload.get(key)}")
    print("top_formulas:")
    for row in payload.get("top_formulas", []):
        print(f"  {row['formula']}: {row['entries']}")


def _render_entry_table(payload: dict[str, Any]) -> None:
    for key in sorted(k for k in payload if k != "objects"):
        print(f"{key}: {payload[key]}")
    print("objects:")
    for name, obj in sorted((payload.get("objects") or {}).items()):
        print(
            f"  {name}: digest={obj.get('digest')} size={obj.get('size')} "
            f"present={obj.get('present')} location={obj.get('location')}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vasp-cache", description="VASP calculation cache")
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="log more (-v INFO, -vv DEBUG)",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_put = sub.add_parser("put", help="Ingest a complete VASP calculation")
    p_put.add_argument("dir", type=Path)
    p_put.add_argument("-r", "--recursive", action="store_true")
    p_put.add_argument(
        "--provenance",
        choices=("canonical", "sampled", "unknown"),
        default=None,
        help="explicit calculation provenance",
    )
    p_put.add_argument(
        "--on-conflict",
        choices=("strict", "skip", "overwrite"),
        default="strict",
        help="same-hash output policy (default: strict)",
    )

    p_fetch = sub.add_parser("fetch", help="Restore outputs from cache into input dir")
    p_fetch.add_argument("dir", type=Path)

    p_has = sub.add_parser("has", help="Check cache hit for input dir")
    p_has.add_argument("dir", type=Path)

    p_query = sub.add_parser(
        "query",
        help="Query cache metadata (e.g. vasp-cache query --formula GaN)",
    )
    _add_query_options(p_query)
    _add_output_flags(p_query, collection=False)

    p_inspect = sub.add_parser("inspect", help="Read-only cache inspection views")
    inspect_sub = p_inspect.add_subparsers(dest="inspect_cmd", required=True)

    p_overview = inspect_sub.add_parser(
        "overview", help="Show fast SQLite-only aggregate metadata"
    )
    p_overview.add_argument("--top-formulas", type=int, default=10)
    _add_output_flags(p_overview, collection=False)

    p_summary = inspect_sub.add_parser("summary", help="Show aggregate cache storage and metadata counts")
    _add_output_flags(p_summary, collection=False)

    p_entries = inspect_sub.add_parser("entries", help="List filtered cache metadata entries")
    _add_query_options(p_entries)
    _add_output_flags(p_entries, collection=True)

    p_entry = inspect_sub.add_parser("entry", help="Show one metadata entry and its CAS objects")
    p_entry.add_argument("content_hash")
    _add_output_flags(p_entry, collection=False)

    p_objects = inspect_sub.add_parser("objects", help="List physical CAS objects and references")
    p_objects.add_argument("--orphans-only", action="store_true", help="show only unreferenced objects")
    _add_output_flags(p_objects, collection=True)

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

    from vasp_cache.logutil import setup_logging

    if args.cmd != "inspect":
        if args.verbose >= 2:
            setup_logging("DEBUG")
        elif args.verbose >= 1:
            setup_logging("INFO")
        else:
            setup_logging("WARNING")

    if args.cmd == "put":
        from vasp_cache.api import put

        if args.recursive:
            import logging
            log = logging.getLogger("vasp_cache.cli")
            n = 0
            n_err = 0
            for outcar in Path(args.dir).rglob("OUTCAR"):
                try:
                    ch = put(
                        outcar.parent,
                        provenance=args.provenance,
                        on_conflict=args.on_conflict,
                    )
                except Exception:
                    n_err += 1
                    log.exception("put failed %s", outcar.parent)
                    continue
                if ch:
                    n += 1
                    print(ch)
            print(f"cached {n} calculations errors={n_err}", file=sys.stderr)
            return 1 if n_err else 0
        ch = put(
            args.dir,
            provenance=args.provenance,
            on_conflict=args.on_conflict,
        )
        if ch is None:
            print("skip: not usable (use -v for reason)", file=sys.stderr)
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
        from vasp_cache import meta
        from vasp_cache.paths import cache_root

        query_limit = max(0, args.limit) + max(0, args.offset)
        rows = meta.query_entries(
            cache_root(),
            **_query_kwargs(args),
            limit=query_limit,
        )
        rows = rows[max(0, args.offset) : max(0, args.offset) + max(0, args.limit)]
        if args.json:
            print(json.dumps(rows, indent=2, default=str))
        else:
            if not rows:
                print("0 hits")
                return 0
            print(f"{len(rows)} hit(s)")
            print(
                f"{'formula':<16} {'E(eV)':>14} {'gap':>8} {'conv':>4} "
                f"{'prov':<10} {'nsites':>6}  content_hash"
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
                    f"{str(r.get('formula') or '-'):<16} {e_s:>14} {g_s:>8} "
                    f"{conv:>4} {str(r.get('provenance') or '-'):<10} "
                    f"{str(ns):>6}  {ch}"
                )
        return 0

    if args.cmd == "inspect":
        from vasp_cache.inspection import entry, entries, objects, overview, summary
        from vasp_cache.paths import cache_root
        root = cache_root()

        if args.inspect_cmd == "overview":
            payload = overview(root, top_formulas=args.top_formulas)
            if args.json:
                print(json.dumps(payload, indent=2, default=str))
            else:
                _render_overview_table(payload)
            return 0
        if args.inspect_cmd == "summary":
            payload = summary(root)
            if args.json:
                print(json.dumps(payload, indent=2, default=str))
            else:
                _render_summary_table(payload)
            return 0
        if args.inspect_cmd == "entries":
            kwargs = _query_kwargs(args)
            
            
            rows = entries(root, **kwargs, limit=args.limit, offset=args.offset)
            if args.json:
                print(json.dumps(rows, indent=2, default=str))
            elif args.jsonl:
                _render_jsonl(rows)
            else:
                _render_entries_table(rows)
            return 0
        if args.inspect_cmd == "entry":
            payload = entry(root, args.content_hash)
            if payload is None:
                print(f"entry not found: {args.content_hash}", file=sys.stderr)
                return 1
            if args.json:
                print(json.dumps(payload, indent=2, default=str))
            else:
                _render_entry_table(payload)
            return 0
        if args.inspect_cmd == "objects":
            rows = objects(root, orphans_only=args.orphans_only)
            if args.json:
                print(json.dumps(rows, indent=2, default=str))
            elif args.jsonl:
                _render_jsonl(rows)
            else:
                _render_objects_table(rows)
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
