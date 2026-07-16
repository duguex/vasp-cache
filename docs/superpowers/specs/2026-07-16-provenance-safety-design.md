# Provenance and Query Safety Design

**Date:** 2026-07-16  
**Issue:** #22  
**Status:** Approved design; implementation follows separately.

## Problem

The cache currently treats a completed `OUTCAR` as sufficient evidence for a
reusable material result. That is not enough to distinguish a canonical static
or relaxation calculation from a sampled, finite-displacement, MD, or otherwise
unprovenanced result.

`get_meta(formula=...)` currently takes the newest metadata row. A recent
sampled or unknown row can therefore become the representative formula result.
The current `converged` field also conflates cache usability, OUTCAR completion,
and parser success; it is not a reliable electronic- or ionic-convergence flag.

A second implementation hazard is parser control flow: `summarize_calc()` may
return from the successful `TaskDoc` path before the regex fallback reads INCAR.
Provenance and effective ionic parameters must therefore be collected by a
separate path that always runs.

## Goals

1. Preserve exact `has()`/`fetch()` reuse semantics.
2. Accept valid canonical static and ionic-relaxation calculations.
3. Distinguish canonical, sampled, and unknown provenance.
4. Prevent formula representative lookup from silently choosing sampled or
   unknown data.
5. Record effective `NSW`, `IBRION`, and `ISIF` independently of TaskDoc.
6. Separate OUTCAR completion, electronic convergence, and ionic convergence.
7. Migrate existing metadata non-destructively.
8. Provide explicit provenance through the Python API and CLI.

## Non-goals

- Inferring random perturbations from formula, path names, or file permissions.
- Treating every `NSW=0` calculation as sampled or rejecting every `NSW=0`
  calculation.
- Changing content-hash identity or input-file generation.
- Deleting, rewriting, or silently discarding existing cache objects.
- Generating new INCAR, KPOINTS, or POTCAR files.

## Chosen approach

Use an independent run-metadata parser before the existing TaskDoc/fallback
summary flow:

```text
_parse_run_metadata(src_dir)
        |
        v
TaskDoc summary, or regex/pymatgen summary
        |
        v
merge summaries; explicit provenance overrides inferred provenance
        |
        v
SQLite metadata entry
```

The independent parser reads only INCAR and OUTCAR and never imports or calls
TaskDoc. Its result is merged into both the successful TaskDoc path and the
fallback path. This prevents a successful TaskDoc parse from bypassing
provenance classification.

The explicit provenance interface is:

```python
from typing import Literal

Provenance = Literal["canonical", "sampled", "unknown"]

put(
    calc_dir,
    *,
    formula=None,
    task_name=None,
    store_inputs=True,
    include=(),
    provenance: Provenance | None = None,
)
```

`None` requests conservative automatic classification. Invalid explicit values
raise `ValueError` before ingesting objects. Recursive CLI ingest passes the
same explicit value to every discovered calculation.

## Effective INCAR values

The independent parser resolves effective values in dependency order, rather
than applying independent constants. These rules follow the VASP Wiki
definitions for [IBRION](https://www.vasp.at/wiki/index.php/IBRION) and
[ISIF](https://www.vasp.at/wiki/index.php/ISIF):

1. `NSW = parsed NSW` or `0` when `NSW` is absent.
2. `IBRION = parsed IBRION`; when absent, use `-1` if effective `NSW <= 0`
   and `0` otherwise.
3. `ISIF = parsed ISIF`; when absent, use `0` if effective `IBRION == 0` or
   `LHFCALC` is true, and `2` otherwise.

The resolver must retain whether a value was explicit or defaulted, even though
the stored query fields contain the effective integer values. If INCAR is
missing or cannot be parsed and no reliable fallback exists, the value is
`None`; the classifier must then prefer `unknown` rather than inventing a
calculation role.

## Automatic provenance classification

Precedence is:

1. Explicit `provenance` passed to `put()`.
2. Reliably detectable calculation mode from effective INCAR values and
   recognizable output metadata.
3. `unknown`.

Automatic rules:

| Condition | Inferred provenance | Rationale |
|---|---|---|
| `IBRION` is `0` or `3` and effective `NSW > 0` | `sampled` | MD / ionic dynamics |
| `IBRION` is `5`, `6`, `7`, or `8` | `sampled` | phonon / finite displacement |
| `NFREE >= 2` or an equivalent explicit phonon marker | `sampled` | finite-displacement calculation |
| `IBRION` is `1` or `2` and effective `NSW > 0` | `canonical` | ordinary ionic relaxation |
| all other cases, including unmarked `NSW=0` | `unknown` | INCAR cannot prove provenance |

`IBRION=0` and `IBRION=3` are both sampled only when `NSW > 0`; no ionic
trajectory is implied by `NSW=0`. A valid static calculation must use
`provenance="canonical"` when it needs to participate in canonical formula
representative selection.

## Independent status parsing

The run-metadata parser returns these fields without depending on TaskDoc:

- `outcar_complete: bool | None`: recognized VASP normal-completion marker;
- `electronic_converged: bool | None`: recognized electronic convergence marker;
- `ionic_converged: bool | None`: recognized ionic convergence marker;
- `nsw: int | None`;
- `ibrion: int | None`;
- `isif: int | None`;
- `provenance: Provenance` after explicit override/classification.

Unknown status is represented as `None`, not as false. The existing
`converged` field remains for compatibility and continues to gate cache
usability; documentation must not describe it as proof of electronic or ionic
convergence.

OUTCAR marker matching is conservative. Normal completion may use the existing
`General timing and accounting` marker. Electronic and ionic status detection
must only return true/false for recognized VASP markers; absence of a marker
returns unknown when the output does not provide enough evidence.

## Metadata storage and migration

Add explicit SQLite columns for query-critical provenance and status fields:

- `provenance TEXT NOT NULL DEFAULT 'unknown'`;
- `provenance_source TEXT NOT NULL DEFAULT 'legacy'` with values `explicit`,
  `inferred`, or `legacy`;
- `outcar_complete INTEGER`;
- `electronic_converged INTEGER`;
- `ionic_converged INTEGER`;
- `nsw INTEGER`;
- `ibrion INTEGER`;
- `isif INTEGER`.

On connection, inspect `PRAGMA table_info(entries)` and add missing columns with
`ALTER TABLE`. Existing rows receive `provenance='unknown'` and
`provenance_source='legacy'`; no existing row is deleted or rehashed. Upsert and
row conversion must preserve booleans as `bool | None`, expose effective numeric
values as integers or `None`, and expose the provenance source for diagnostics.

Provenance must not be stored only in `extra_json`, because representative
selection and filtering require a reliable indexed/queryable field.

## Duplicate content-hash provenance merge

`content_hash` remains one logical entry. Re-ingesting the same hash must merge
provenance deliberately instead of letting the existing last-write-wins upsert
silently change the role:

- explicit provenance has higher authority than inferred provenance;
- inferred provenance has higher authority than legacy `unknown`;
- incoming `unknown` never replaces an existing non-unknown role;
- incoming inferred provenance may promote legacy `unknown`, but never replaces
  an explicit role;
- incoming explicit provenance may promote or replace an inferred/legacy role;
- two different explicit non-unknown roles raise `ProvenanceConflictError`
  before CAS objects or metadata are written;
- two different inferred non-unknown roles also raise
  `ProvenanceConflictError`; the existing row remains unchanged;
- same-role re-ingest keeps the role and updates ordinary metadata according to
  the separate #20 conflict policy.

The `put()` sequence must enforce this before any CAS write:

1. Validate explicit provenance and parse the run summary.
2. Compute `content_hash` and read the existing metadata entry, if any.
3. Resolve the provenance merge and raise `ProvenanceConflictError` on a
   rejected role conflict.
4. Only after the preflight succeeds, write output/input files with
   `cas.put_file`.
5. Commit the resolved metadata update.

This ordering prevents rejected duplicate ingests from leaving CAS objects with
no metadata. A rejected role conflict leaves both the existing metadata and CAS
object set unchanged.


## Query behavior

Extend metadata filtering with an explicit filter type:

```python
ProvenanceFilter = Literal["canonical", "sampled", "unknown", "all"]

query(..., provenance: ProvenanceFilter = "canonical")
```

`query()` defaults to `canonical` for every query shape, including
`query(formula=...)`. Returned rows always expose `provenance`. Non-canonical
rows require an explicit `provenance="sampled"`, `provenance="unknown"`, or
`provenance="all"` argument; there is no implicit all-provenance mode.

The CLI query command accepts
`--provenance {canonical,sampled,unknown,all}`, defaults to `canonical`, and
prints provenance in JSON and compact output. Therefore the common
`vasp-cache query --formula GaN` command cannot select a sampled or unknown row
without an explicit opt-in.

Formula representative lookup uses the same filter and defaults to canonical:

```python
get_meta(..., formula=formula, provenance="canonical")
```

`provenance="all"` is the explicit all-candidates mode. Exact lookup by input
directory or content hash ignores this representative policy and remains
usable for every stored row.

## Error and compatibility behavior

- Missing or incomplete OUTCAR continues to skip `put()` as before.
- Read/parse exceptions continue to propagate through `put()`; recursive CLI
  ingest records the error and continues to the next calculation.
- Explicit provenance validation occurs before object writes.
- Existing `has()` and `fetch()` do not filter by provenance.
- Existing metadata is retained and classified as `unknown` until a caller
  explicitly re-ingests it with a provenance value.

## Test contract

Add deterministic tests for:

1. Independent INCAR parsing when TaskDoc succeeds and returns an energy.
2. Effective-default matrix: absent `NSW` gives `0`; absent `IBRION` gives
   `-1` when effective `NSW <= 0` and `0` when effective `NSW > 0`; absent
   `ISIF` gives `0` for effective `IBRION=0` or `LHFCALC=.TRUE.` and `2`
   otherwise.
3. `IBRION=0` with `NSW>0` classified as sampled MD.
4. `IBRION=3` with `NSW>0` classified as sampled MD.
5. `IBRION=5` through `8` classified as sampled phonon/finite displacement.
6. `IBRION=1/2` with `NSW>0` classified as canonical relaxation.
7. Explicit `canonical`, `sampled`, and `unknown` precedence over inference.
8. Unmarked `NSW=0` classified as unknown without rejecting the cache entry.
9. Separate OUTCAR, electronic, and ionic status fields.
10. Canonical-only default formula representative selection in both API and CLI.
11. Explicit provenance query filtering, including `provenance="all"`.
12. Same-hash re-ingest preserves an explicit role when the incoming role is
    automatic or `unknown`.
13. Same-hash explicit role conflict fails before CAS writes and leaves no
    orphan CAS object or metadata mutation.
14. Legacy SQLite rows migrating to `unknown` without object loss.
15. Existing exact `has()` and `fetch()` behavior.

## Documentation changes

Update `README.md`, `docs/USER.md`, and `ROADMAP.md` after implementation to
document:

- explicit `put(..., provenance=...)` and CLI usage;
- conservative automatic classification;
- canonical-only formula representative lookup;
- the distinction between exact output reuse and related-calculation bootstrap;
- the fact that `fetch()` never creates new INCAR/KPOINTS/POTCAR inputs.

## Acceptance

Issue #22 is complete when all test-contract cases pass, the existing suite
passes, legacy metadata remains readable, formula representative lookup cannot
silently return the newest sampled/unknown row, duplicate role conflicts are
rejected before CAS writes, and TaskDoc-successful real calculations still
carry effective INCAR/OUTCAR provenance metadata.
