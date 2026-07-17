# Task 3: Health documentation and shared-cache audit

## Status

Complete for the first health pass. Updated `docs/USER.md` to distinguish the
read-only health workflow from the existing inspect views, and updated issue
0022 with the implemented acceptance items and remaining limitations.

## Real-cache commands

Both commands were run from the web-dashboard worktree with `PYTHONPATH=src`:

```bash
PYTHONPATH=src python scripts/audit_cache.py \
  --root /mnt/shared/vasp_cache --json
PYTHONPATH=src python scripts/audit_cache.py \
  --root /mnt/shared/vasp_cache --scan-cas --max-objects 1000 --json
```

Fast metadata-only JSON observations:

- `cache_root`: `/mnt/shared/vasp_cache`; `scan.mode`: `metadata`; CAS scan was
  not performed (`scan_performed: false`).
- Metadata entries: `106348`.
- Key generations: `2: 202`, `4: 106146`; profile ID `default: 106348`.
- Provenance: `unknown: 106348` (`canonical: 0`, `sampled: 0`); provenance
  source: `legacy: 106348` (`explicit: 0`, `inferred: 0`).
- Missing energy: `1427`; missing formula, convergence, identity, objects, and
  malformed identity: all `0`.
- Raw energy range: minimum `-44574871.44160828`, maximum `1807.40802621`;
  no configured bounds and no configured outlier flags (`outliers: 0`). These
  values are review evidence, not scientific-validity judgments.
- Metadata reference aggregates include `referenced_objects: 335923` and
  `shared_reference_objects: 29584`; this mode does not provide physical CAS
  totals.

Bounded CAS JSON observations:

- `scan.mode: cas`, `scan.max_objects: 1000`, `cas.limited: true`.
- Stderr emitted exactly 1,000 progress lines (`CAS objects scanned: 1` through
  `CAS objects scanned: 1000`); JSON remained on stdout.
- The bounded walk saw `physical_objects: 1000` and
  `physical_bytes: 2399452504`; `path_mismatches: 0`.
- Reconciliation-dependent fields were partial/unknown as intended:
  `missing_references`, `orphan_objects`, `orphan_bytes`, `referenced_bytes`,
  and `physical_referenced_objects` were `null`. The bounded run is not a full
  exact CAS audit and must not be used to claim full physical/reference/orphan
  totals. Metadata-only `referenced_objects` (`335923`) and
  `shared_reference_objects` (`29584`) remain available.

## Read-only confirmation and concerns

The commands exited with status 0. A verification wrapper captured root,
`meta.sqlite`, and `cas` inode/size/mtime snapshots before and after both runs;
the snapshots were identical (`unchanged: true`). No output was written under
the cache root.

The first pass checks object presence and canonical CAS path/layout consistency,
not blob contents; it does not hash blob bytes. Bounded CAS totals are partial
and are represented as `null` where unscanned objects prevent reconciliation.
There is no automatic repair, deletion, GC, or migration. `report_timestamp` is
an UTC run-version timestamp for comparing reports, not a cache content-change
or file-modification timestamp.

## Verification

- `PYTHONPATH=src pytest tests/test_health.py -q` — 9 passed (as recorded in the
  collector report).
- Real-cache fast and bounded commands above — both returned JSON successfully;
  bounded progress stayed on stderr.

## Files

- `docs/USER.md`
- `issues/0022-cache-data-quality-audit.md`
- `.superpowers/sdd/task-health-collector-report.md` (focused count corrected
  from 8 to 9)
