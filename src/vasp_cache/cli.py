"""Command-line interface for the fresh calculation index."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from vasp_cache import api


def _root(args: argparse.Namespace) -> Path | None:
    return args.root.resolve() if args.root is not None else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vasp-cache")
    parser.add_argument("--root", type=Path, default=None, help="index directory")
    sub = parser.add_subparsers(dest="command", required=True)

    rebuild = sub.add_parser("rebuild", help="replace the index from a source tree")
    rebuild.add_argument("source", type=Path)
    rebuild.add_argument("--exclude", action="append", default=None, help="glob pattern to skip")
    rebuild.add_argument("--json", action="store_true")

    put = sub.add_parser("put", help="index one calculation directory")
    put.add_argument("directory", type=Path)
    put.add_argument("--overwrite", action="store_true",
                     help="force replace even if existing entry is equal quality")

    has = sub.add_parser("has", help="check an exact identity")
    has.add_argument("directory", type=Path)

    fetch = sub.add_parser("fetch", help="restore indexed output files")
    fetch.add_argument("key", help="identity key or source directory")
    fetch.add_argument("target", type=Path, help="output directory")

    query = sub.add_parser("query", help="query indexed calculations")
    query.add_argument("--formula", "-f")
    query.add_argument("--limit", "-n", type=int, default=100)
    query.add_argument("--converged-only", action="store_true",
                       help="only show ionically converged entries")
    query.add_argument("--json", action="store_true")
    sub.add_parser("status", help="show index counts")

    args = parser.parse_args(argv)
    root = _root(args)
    if args.command == "rebuild":
        payload = api.rebuild(args.source, root=root, exclude=args.exclude)
        if args.json:
            print(json.dumps(payload, sort_keys=True))
        else:
            print(
                f"indexed {payload['identities']} identities; "
                f"{payload['done']} stored, "
                f"{payload['skipped']} skipped"
            )
        return 0
    if args.command == "put":
        key = api.put(args.directory, root=root, overwrite=args.overwrite)
        if key is None:
            print("skip: invalid calculation inputs", file=sys.stderr)
            return 1
        print(key)
        return 0
    if args.command == "has":
        hit = api.has(args.directory, root=root)
        print("true" if hit else "false")
        return 0 if hit else 1
    if args.command == "fetch":
        hit = api.fetch(args.key, args.target, root=root)
        print("hit" if hit else "miss")
        return 0 if hit else 1
    if args.command == "query":
        rows = api.query(args.formula, root=root, limit=args.limit,
                         converged_only=args.converged_only)
        print(json.dumps(rows, indent=2, sort_keys=True) if args.json else len(rows))
        return 0
    payload = api.stats(root=root)
    print(json.dumps(payload, sort_keys=True))
    return 0
