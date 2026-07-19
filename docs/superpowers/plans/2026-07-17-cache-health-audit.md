# Cache Health Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only, diffable cache health report that separates fast metadata quality from explicit CAS completeness scanning without mutating the cache.

**Architecture:** Add `vasp_cache.health` as a collector over the existing read-only SQLite and CAS helpers. The default report is SQLite-only and fast; `scan_cas=True` performs an explicit streaming CAS walk with progress callbacks and reports missing references, physical objects, shared references, orphan objects, bytes, and path consistency. Expose the collector through `vasp-cache inspect health` and a thin offline `scripts/audit_cache.py` wrapper.

**Tech Stack:** Python 3.10+, SQLite read-only connections, existing CAS layout, argparse, pytest, JSON.

## Global Constraints

- Health inspection is read-only and must not create, migrate, rewrite, delete, compact, or repair metadata or CAS.
- Missing cache roots return a zero-valued report without creating files or directories.
- Default health mode is SQLite-only; CAS scanning requires explicit `--scan-cas`.
- CAS scan progress is emitted to stderr by the CLI/script and the collector supports a bounded `max_objects` argument for deterministic/offline slices.
- Missing metadata references and orphan physical objects are separate categories.
- Raw metadata values and source paths remain available in bounded anomaly samples; no energy value is relabeled or deleted.
- JSON output is deterministic (`sort_keys=True`); no Web UI changes are part of this slice.
- New behavior follows TDD: each production behavior has a failing test first.

---

### Task 1: Define the health report and read-only collectors

**Files:**
- Create: `src/vasp_cache/health.py`
- Test: `tests/test_health.py`
- Reuse: `src/vasp_cache/meta.py`, `src/vasp_cache/cas.py`, `src/vasp_cache/inspection.py`

**Interfaces:**
- `health_report(cache_root: Path, *, scan_cas: bool = False, max_objects: int | None = None, energy_min: float | None = None, energy_max: float | None = None, progress: Callable[[int], None] | None = None) -> dict[str, Any]`
- Report keys: `schema_version`, `cache_root`, `metadata`, `cas`, `energy`, and `scan`.
- `metadata` includes `entries`, `missing_formula`, `missing_energy`, `missing_convergence`, `missing_objects`, `provenance`, `provenance_source`, `key_generations`, `profile_ids`, `missing_identity`, and bounded `samples`.
- `cas` includes `scan_performed`, `physical_objects`, `physical_bytes`, `referenced_objects`, `referenced_bytes`, `missing_references`, `orphan_objects`, `orphan_bytes`, `shared_reference_objects`, `path_mismatches`, `limited`.
- `energy` includes raw `min`, `max`, `missing`, configured bounds, `outliers`, and bounded raw samples containing `content_hash`, `formula`, `total_energy`, and `source_dir`.

- [ ] **Step 1: Write failing fixture tests**

Create a fixture with one valid entry, two metadata entries sharing one CAS digest, one missing referenced digest, and one physical orphan. Assert:

```python
def test_health_fast_report_is_read_only_and_separates_metadata(cache_root, tmp_path):
    before = snapshot_tree(cache_root)
    report = health_report(cache_root)
    assert report["scan"]["mode"] == "metadata"
    assert report["metadata"]["entries"] == 3
    assert report["cas"]["scan_performed"] is False
    assert report["energy"]["missing"] == 1
    assert snapshot_tree(cache_root) == before


def test_health_cas_scan_reports_missing_orphan_and_shared_references(cache_root):
    report = health_report(cache_root, scan_cas=True)
    assert report["cas"]["missing_references"] == 1
    assert report["cas"]["orphan_objects"] == 1
    assert report["cas"]["shared_reference_objects"] == 1
    assert report["cas"]["referenced_objects"] == 2
    assert report["cas"]["limited"] is False


def test_health_cas_scan_limit_reports_progress_and_is_bounded(cache_root):
    seen = []
    report = health_report(cache_root, scan_cas=True, max_objects=1, progress=seen.append)
    assert report["cas"]["limited"] is True
    assert seen and seen[-1] == 1
```

Also assert an absent root returns zero metadata/CAS counts and does not create the root, and configured `energy_min`/`energy_max` marks only out-of-range rows while preserving raw samples.

- [ ] **Step 2: Run the red tests**

Run:

```bash
PYTHONPATH=src pytest tests/test_health.py -q
```

Expected: collection failure because `vasp_cache.health` and `health_report` do not exist.

- [ ] **Step 3: Implement metadata-only health collection**

Use `meta.db_path()` and `meta.connect_readonly()`; return zero values before opening a missing database. Iterate rows once, count missing fields and provenance/identity distributions, build a reference map from decoded `objects`, and retain at most 20 deterministic samples per anomaly class. Never call `meta.connect()` or schema setup.

- [ ] **Step 4: Implement explicit streaming CAS scan**

When `scan_cas` is true, iterate `cas.iter_objects(root)`, stop after `max_objects` when provided, validate each physical path against `cas.object_path(root, digest)`, accumulate bytes and digest sets, and compare against metadata references. Count missing references separately from orphans. Call `progress(count)` after each scanned object and once at the bounded endpoint. Do not hash file contents in the first version; `path_mismatches` is the layout/digest-path invariant, while content hashing remains a future offline verification mode.

- [ ] **Step 5: Run green health tests**

Run:

```bash
PYTHONPATH=src pytest tests/test_health.py -q
```

Expected: all health fixture tests pass, including absent-root non-mutation and bounded scan behavior.

- [ ] **Step 6: Commit the collector slice**

```bash
git add src/vasp_cache/health.py tests/test_health.py
git commit -m "feat: add read-only cache health collector"
```

---

### Task 2: Expose health through CLI and offline script

**Files:**
- Modify: `src/vasp_cache/cli.py`
- Create: `scripts/audit_cache.py`
- Modify: `tests/test_cli.py`
- Test: `tests/test_health.py`

**Interfaces:**
- CLI: `vasp-cache inspect health [--scan-cas] [--max-objects N] [--energy-min E] [--energy-max E] [--json]`
- Script: `python scripts/audit_cache.py --root ROOT [--scan-cas] [--max-objects N] [--energy-min E] [--energy-max E] [--json]`
- Human output is concise; JSON prints the complete deterministic report. CAS progress goes to stderr and never contaminates JSON stdout.

- [ ] **Step 1: Write failing CLI tests**

Add tests that monkeypatch `health_report` and assert parsed options, JSON output, and progress separation. Add an absent-root CLI test that verifies `inspect health --json` does not create the root. Add a script subprocess test for metadata-only mode.

- [ ] **Step 2: Run the red CLI tests**

Run:

```bash
PYTHONPATH=src pytest tests/test_cli.py -q -k health
```

Expected: argparse rejects the new command before implementation.

- [ ] **Step 3: Add CLI parsing and rendering**

Register `inspect health`, import the collector lazily, forward all options, print progress to stderr only when scanning CAS, and serialize JSON using the existing `default=str` convention and sorted keys.

- [ ] **Step 4: Add the offline wrapper**

Keep `scripts/audit_cache.py` dependency-free beyond the package. Insert the repository `src` path when run from a checkout, parse the same options, call the collector, and return nonzero only for argument errors or collector failures. Never write a report into the cache root.

- [ ] **Step 5: Run green CLI/script tests**

Run:

```bash
PYTHONPATH=src pytest tests/test_cli.py -q -k health
PYTHONPATH=src python scripts/audit_cache.py --root /tmp/missing-health-root --json
```

Expected: tests pass and the script prints zero-valued JSON without creating `/tmp/missing-health-root`.

- [ ] **Step 6: Commit the CLI slice**

```bash
git add src/vasp_cache/cli.py scripts/audit_cache.py tests/test_cli.py tests/test_health.py
git commit -m "feat: expose cache health audit"
```

---

### Task 3: Document audit boundaries and verify against the shared cache

**Files:**
- Modify: `docs/USER.md`
- Modify: `issues/0022-cache-data-quality-audit.md`
- Test: `tests/test_health.py`

- [ ] **Step 1: Add documentation assertions**

Document the distinction:

```text
overview = fast SQLite aggregates
health = read-only metadata quality report; CAS scan only with --scan-cas
summary = legacy full storage summary and may be slower
GC/repair = not implemented
```

Document that energy bounds are review flags only, not scientific validity judgments, and that progress/bounded scans are intended for the large shared cache.

- [ ] **Step 2: Run a fast real-cache audit**

Run:

```bash
PYTHONPATH=src python scripts/audit_cache.py --root /mnt/shared/vasp_cache --json
```

Confirm it returns quickly, reports the observed 106k-scale metadata, all-unknown provenance, generation distribution, missing metadata fields, and `scan_performed: false` without mutating the cache.

- [ ] **Step 3: Run a bounded real CAS audit**

Run:

```bash
PYTHONPATH=src python scripts/audit_cache.py --root /mnt/shared/vasp_cache --scan-cas --max-objects 1000 --json
```

Confirm stderr contains progress and JSON reports `limited: true`; do not claim full CAS totals from a bounded run.

- [ ] **Step 4: Run focused verification**

```bash
PYTHONPATH=src pytest tests/test_health.py tests/test_cli.py tests/test_inspection.py -q
python -m compileall -q src tests scripts
```

- [ ] **Step 5: Commit docs and audit completion notes**

```bash
git add docs/USER.md issues/0022-cache-data-quality-audit.md
 git commit -m "docs: define cache health audit boundaries"
```

---

### Task 4: Final regression verification

- [ ] Run `PYTHONPATH=src pytest -q`.
- [ ] Run `git diff --check`.
- [ ] Confirm no Web UI files changed in this slice.
- [ ] Record remaining limitation: content digest verification is not part of the first health pass; path/layout consistency and object presence are audited, while full blob hashing remains an explicit future mode.
