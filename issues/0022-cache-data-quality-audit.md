# Cache data-quality audit and CAS integrity report

**Date:** 2026-07-17  
**Severity:** High — data trust / storage integrity  
**Component:** `inspect`, `meta.sqlite`, CAS, audit/reporting

## Status

Open. The current shared cache contains 106,348 entries, mostly generation-4
records, and all existing rows report `provenance=unknown`. The fast overview
also exposes a very wide total-energy range that requires validation rather than
being silently treated as correct.

## Problem

The cache can currently answer exact lookup and metadata queries, but it does
not yet provide a bounded, complete audit of the actual stored data:

- metadata rows may use legacy key generations and legacy provenance defaults;
- metadata object references may point to missing CAS objects;
- physical CAS objects may be orphaned and consume space without any metadata
  reference;
- CAS byte totals and reference totals require a full filesystem scan that is
  too slow for the current large cache when run synchronously;
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

- [ ] A fixture audit covers a valid entry, a missing referenced object, and an
      orphan object with shared CAS references.
- [ ] Real-cache report gives exact counts for metadata rows, generations,
      provenance sources, physical objects, referenced objects, missing refs,
      orphan objects, and bytes.
- [ ] Report verifies digest/path consistency and does not mutate metadata or
      CAS state.
- [ ] Audit handles the current large cache without an unbounded synchronous
      command timeout; progress or resumability is documented and tested.
- [ ] Energy anomaly reporting preserves raw evidence and does not delete or
      relabel entries automatically.
- [ ] JSON/JSONL output is stable enough for diffing between audit runs.
- [ ] User documentation explains the difference between `overview`, `health`,
      `summary`, and future `gc` workflows.

## Related

- `issues/0017-meta-dump-jsonl.md` — full-catalog metadata export
- `issues/0016-archive-export-import.md` — cache snapshot and relocation
- `issues/0019-jsonstore-no-auto-migrate-doc.md` — legacy migration boundary
- `issues/0020-put-conflict-policy.md` — same-key output integrity
