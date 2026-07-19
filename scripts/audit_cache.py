"""Run a read-only cache health audit without changing the cache."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC = _REPO_ROOT / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from vasp_cache.health import health_report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a read-only vasp-cache health audit")
    parser.add_argument("--root", type=Path, required=True, help="cache root to inspect")
    parser.add_argument("--scan-cas", action="store_true", help="scan physical CAS objects")
    parser.add_argument("--max-objects", type=int, default=None)
    parser.add_argument("--energy-min", type=float, default=None)
    parser.add_argument("--energy-max", type=float, default=None)
    parser.add_argument("--json", action="store_true", help="print the complete JSON report")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = args.root.expanduser().resolve()
    progress = None
    if args.scan_cas:
        def progress(count: int) -> None:
            print(f"CAS objects scanned: {count}", file=sys.stderr)

    try:
        payload = health_report(
            root,
            scan_cas=args.scan_cas,
            max_objects=args.max_objects,
            energy_min=args.energy_min,
            energy_max=args.energy_max,
            progress=progress,
        )
    except Exception as exc:
        print(f"cache health audit failed: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(payload, indent=2, default=str, sort_keys=True))
    else:
        metadata = payload["metadata"]
        cas_report = payload["cas"]
        print(
            f"health: mode={payload['scan']['mode']} "
            f"entries={metadata['entries']} missing_objects={metadata['missing_objects']}"
        )
        if args.scan_cas:
            print(
                f"CAS: physical={cas_report['physical_objects']} "
                f"missing={cas_report['missing_references']} "
                f"orphans={cas_report['orphan_objects']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
