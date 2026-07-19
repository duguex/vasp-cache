# Cache data-quality audit and CAS integrity report

**Date:** 2026-07-17  
**Severity:** High — data trust / storage integrity  
**Component:** `inspect`, `meta.sqlite`, CAS, audit/reporting

First health pass implemented. The default report is a read-only, fast SQLite
metadata-quality report, and `health --scan-cas` is an explicit streaming CAS
walk with progress and an optional object bound. The fast real-cache run
observed 106,348 metadata entries, generations 2/4, all rows with
`provenance=unknown` and `provenance_source=legacy`, and 1,427 missing energies.
The current evidence ran only a bounded 1,000-object CAS scan, observing 1,000
physical objects and 2,399,452,504 scanned bytes, with reconciliation totals
marked partial (`null`). An unbounded `health --scan-cas` run supports exact
physical, reference, missing-reference, and orphan totals when completed; no
full shared-cache audit result is claimed from the bounded evidence.

First health pass implemented. The default report is a read-only, fast SQLite
metadata-quality report, and `--scan-cas` is an explicit streaming CAS walk with
progress and an optional object bound. The fast real-cache run observed 106,348
metadata entries, generations 2/4, all rows with `provenance=unknown` and
`provenance_source=legacy`, and 1,427 missing energies. A bounded 1,000-object
CAS run observed 1,000 physical objects and 2,399,452,504 scanned bytes, and
correctly marked reconciliation totals as partial (`null`). A full exact
real-cache CAS audit has not been run, so full physical/reference/orphan counts
and bytes remain open.

The wide total-energy range remains a review flag, not a scientific validity
judgment. No metadata or CAS repair/deletion is performed by this audit.

## Problem

The cache now has a read-only health report, but the current shared-cache
evidence is bounded rather than a full audit result:

- metadata rows may use legacy key generations and legacy provenance defaults;
- metadata object references may point to missing CAS objects;
- physical CAS objects may be orphaned and consume space without any metadata
  reference;
- the current evidence scanned only 1,000 CAS objects; an unbounded
  `health --scan-cas` run supports exact physical/reference/orphan totals when
  completed, but no full shared-cache result is claimed here;
- extreme metadata values, such as total-energy outliers, are visible but not
  yet classified as valid, suspicious, or malformed.

This is a transparency and trust gap. It is not a request to delete data or to
reject calculations based on energy alone.

## Scope

### Required audit dimensions

1. **Metadata identity and provenance**
   - count entries by `key_generation` and `profile_id`;
   - count `provenance` and `provenance_source` values;
   - report legacy/defaulted rows separately from explicitly classified rows;
   - report missing or malformed identity fields;
   - do not silently rewrite generation or provenance values.

2. **CAS completeness and size**
   - count physical CAS objects and total bytes;
   - count unique referenced physical objects and referenced bytes;
   - identify metadata references whose CAS object is missing;
   - identify orphan CAS objects and their bytes;
   - validate digest/path consistency;
   - report shared-object reference counts without double-counting bytes.

3. **Metadata content quality**
   - report counts of missing energy, formula, convergence, and output pointers;
   - report configurable energy-range summaries and suspicious outlier buckets;
   - preserve raw values and source paths for review;
   - bandgap analysis is explicitly out of scope for this issue.

4. **Operational behavior**
   - audit is read-only and must not create or migrate the database;
   - audit must not delete, rewrite, or compact CAS objects;
   - large-cache scans must expose progress and support bounded or resumable
     execution, or provide a documented offline mode;
   - repeated audits should be comparable and versioned by report timestamp and
     cache root.

## Proposed interface

```bash
vasp-cache inspect health
vasp-cache inspect health --json
python scripts/audit_cache.py --root /mnt/shared/vasp_cache --json
```

The first report should separate fast SQLite aggregates from the slower CAS
walk. It must make the following distinction explicit:

```text
missing reference != orphan object
referenced bytes != total physical bytes
legacy provenance default != explicit scientific classification
```

## Acceptance

- [x] Fixture tests cover a valid entry, a missing referenced object, and an
      orphan object with shared CAS references.
- [ ] The fast real-cache report gives exact metadata counts, generations, and
      provenance sources; a full real-cache CAS walk has not been run, so exact
      physical objects, referenced objects, missing refs, orphan objects, and
      bytes are intentionally not claimed here.
- [x] The first pass verifies CAS path/layout consistency and object presence
      for scanned objects and does not mutate metadata or CAS state. It does
      not hash blob contents.
- [x] The audit handles the large cache without an unbounded synchronous health
      command: progress is emitted on CAS scans and `--max-objects` bounds a
      scan. Bounded reconciliation totals are partial/`null` by design.
- [x] Energy anomaly reporting preserves raw evidence and does not delete or
      relabel entries automatically; configured bounds are review flags only.
- [x] JSON output is deterministic (`sort_keys=True`) and stable enough for
      diffing between audit runs.
- [x] User documentation explains `overview`, `health`, `summary`, and that
      GC/repair workflows are not implemented.

Remaining limitations: blob-content hashing and automatic repair/deletion are
not implemented in this first health pass.

## Related

- `issues/0017-meta-dump-jsonl.md` — full-catalog metadata export
- `issues/0016-archive-export-import.md` — cache snapshot and relocation
- `issues/0019-jsonstore-no-auto-migrate-doc.md` — legacy migration boundary
- `issues/0020-put-conflict-policy.md` — same-key output integrity
