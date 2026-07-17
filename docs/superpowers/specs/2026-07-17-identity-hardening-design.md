# Identity Hardening Design

**Date:** 2026-07-17  
**Status:** Approved design; implementation follows separately.  
**Scope:** Separate exact calculation protocols, preserve put/has consistency, and
prevent same-key output overwrite before random-data cleanup.

## Problem

The active mapping profile uses geometry, KPOINTS, and selected INCAR hard keys
for `content_hash`. `NSW` is soft and `IBRION` is currently absent from the
identity profile. Therefore a fixed-geometry static calculation and an ionic
relaxation can produce the same hash when their other hard inputs match.

The current structure fingerprint prefers `CONTCAR` over `POSCAR`. A completed
calculation directory can therefore hash differently from an input-only submit
directory even when both represent the same intended job. Conversely, once two
runs share a hash, the previous last-write-wins behavior can replace one
OUTCAR/object set with another.

These conditions make it unsafe to delete unclassified or sampled data before
identity semantics are repaired and old-key collisions are inventoried.

## Goals

1. Make static, relaxation, MD, and phonon protocols distinct exact identities.
2. Ensure `put()` on a completed directory and `has()` on its input-only copy
   use the same primary structure source.
3. Keep `CONTCAR` available as a restored output and record its result geometry
   without making it the primary input identity.
4. Reject different OUTCAR payloads for the same strict protocol before any CAS
   write by default.
5. Bump the mapping generation and provide collision-safe rehash behavior.
6. Preserve exact output reuse after identity migration.
7. Delay deletion of random perturbation data until collision inventory is
   complete.

## Non-goals

- Do not add a second full result database in this round.
- Do not make provenance part of `content_hash`; provenance is a role label,
  not an input protocol.
- Do not require every calculation to be relaxed.
- Do not infer random perturbation solely from `NSW=0`, formula, or directory
  names.
- Do not silently merge old entries that collide under the new identity.

## Primary identity: input intent hash

The primary `content_hash` becomes an input intent identity:

```text
POSCAR + KPOINTS + input-only protocol fingerprint + existing hard INCAR keys
```

`POSCAR` is the required primary structure source for new identity-aware puts
and for `has()`/`fetch()` input directories. `CONTCAR` is never preferred for
the primary identity. If a new calculation directory has no POSCAR, it cannot
prove the original input intent and must not silently fall back to CONTCAR for
an identity-aware ingest; the implementation should skip or raise a clear
identity-input error according to the existing put error contract.

The completed directory may still store `CONTCAR` in CAS and restore it through
`fetch()`. If present, its geometry is recorded as:

```text
result_geom_hash = hash(CONTCAR)
```

`result_geom_hash` is metadata for result grouping and collision analysis; it is
not used by `has()` or primary exact lookup.

## Input-only protocol fingerprint

Add one shared helper used by both `mapping_digest()` and all callers that need
the primary hash:

```python
def input_protocol_identity(src_dir: Path) -> dict[str, Any]:
    """Parse INCAR/KPOINTS/POSCAR only; never read OUTCAR or TaskDoc."""
```

The helper must read only:

- `INCAR`;
- `KPOINTS`;
- `POSCAR`/structure input needed by the existing geometry fingerprint.

It must not call `summarize_calc()`, `TaskDoc`, or any OUTCAR parser. This is
required because `has()` normally receives an input-only directory.

The normalized protocol identity contains at least:

```text
calc_mode
nsw
ibrion
isif
nfree (when present and protocol-relevant)
```

The effective values follow the VASP-dependent defaults already defined for
provenance parsing:

- absent `NSW` → `0`;
- absent `IBRION` → `-1` when effective `NSW <= 0`, otherwise `0`;
- absent `ISIF` → `0` when effective `IBRION == 0` or `LHFCALC=.TRUE.`,
  otherwise `2`.

Mode normalization is deterministic:

| Effective condition | `calc_mode` |
|---|---|
| `IBRION` 5–8 | `phonon` |
| `NSW > 0` and `IBRION` 0 or 3 | `md` |
| `NSW > 0` and `IBRION` 1 or 2 | `relaxation` |
| `NSW <= 0` and not phonon | `static` |
| otherwise | `unknown` |

The numeric effective fields remain in the token in addition to `calc_mode`,
so distinct protocols cannot collapse merely because they share a mode label.
Missing or malformed input protocol values must produce a deterministic
`unknown` token or an explicit identity-input error; they must never silently
reuse an OUTCAR-derived fallback.

## Mapping generation

The default mapping changes from generation 4 to generation 5. The hard mapping
body includes the normalized input protocol token. Existing hard INCAR keys,
KPOINTS, and POSCAR geometry rules remain unless a separate identity issue
changes them.

Any custom mapping that changes the hard section must use a generation greater
than the packaged generation. The mapping profile and `docs/IDENTITY.md` must
show that `NSW`/`IBRION` are no longer soft/ignored for the primary protocol
identity; the normalized protocol token is the canonical representation.

## Strict same-key conflict policy

`put()` gains an explicit conflict mode with strict as the default:

```python
put(
    calc_dir,
    *,
    on_conflict: Literal["strict", "skip", "overwrite"] = "strict",
)
```

Behavior when an entry already exists for the new hash:

- `strict`: hash the source `OUTCAR` before any `cas.put_file`; if it differs
  from the existing OUTCAR CAS digest, raise a public conflict exception and
  leave metadata and CAS unchanged; identical bytes are idempotent;
- `skip`: return the existing hash without writing new objects;
- `overwrite`: retain the old last-write-wins behavior as an explicit migration
  escape hatch, with an INFO warning.

The CLI exposes the same choices. Recursive ingest passes the selected mode to
every calculation. Provenance role conflicts remain independently enforced;
`on_conflict` controls output-payload conflicts, not provenance authority.

The preflight order is mandatory:

```text
validate options
→ parse input-only protocol
→ compute content_hash
→ read existing metadata
→ compare provenance and OUTCAR digest
→ only then write CAS objects
→ upsert metadata
```

## Rehash and migration

`scripts/rehash_meta_cas.py` must use the new POSCAR-based input-only identity
and must not resolve collisions with last-write-wins.

Migration behavior:

1. Materialize stored input objects from CAS.
2. Compute the generation-5 identity from POSCAR/INCAR/KPOINTS only.
3. Group old rows by new hash.
4. Report groups with multiple old rows or incompatible OUTCAR/result geometry.
5. Write non-colliding rows safely.
6. Leave colliding old rows unchanged or place them in an explicit quarantine
   report until an operator chooses a resolution.

Migration must be restartable and must not delete source rows or CAS objects on
collision. A dry-run/inventory mode is required before destructive cleanup.

## Random perturbation cleanup gate

No random-data deletion is part of the identity migration itself. Cleanup is
allowed only after:

- generation-5 rehash inventory completes;
- same-hash static/relaxation conflicts are enumerated;
- entries have provenance and result geometry metadata where available;
- canonical fixed-structure static calculations are separated from sampled or
  unknown perturbation data;
- a retained archive or quarantine copy exists for unresolved records.

Only explicitly identified random perturbation records may then be removed.
The rule must not be “delete every record without relaxation.”

## Test contract

Add deterministic tests for:

1. POSCAR is used for both completed `put()` and input-only `has()` hashing;
   differing CONTCAR does not change the primary hash.
2. Missing POSCAR does not silently fall back to CONTCAR for new identity-aware
   ingest.
3. Input-only protocol parsing never reads OUTCAR or TaskDoc.
4. Static (`NSW=0`, effective `IBRION=-1`) and relaxation (`NSW>0`,
   `IBRION=1/2`) produce different hashes.
5. Different NSW values under the same relaxation mode produce different hashes.
6. MD (`IBRION=0/3`) and phonon (`IBRION=5..8`) produce different hashes from
   static and relaxation.
7. Effective dependent defaults produce stable hashes for explicit and omitted
   default values where the effective protocol is equivalent.
8. Same strict hash and identical OUTCAR succeeds idempotently.
9. Same strict hash and different OUTCAR raises before any CAS write.
10. `skip` preserves the first payload and `overwrite` is explicit.
11. Recursive CLI passes `on_conflict` and provenance consistently.
12. Generation-5 custom mapping requires the generation bump.
13. Rehash inventory reports collisions without deleting source rows or objects.
14. `result_geom_hash` records CONTCAR without changing primary input identity.
15. Existing exact `has()`/`fetch()` behavior remains valid after migration.

## Acceptance

Identity hardening is complete when generation-5 input intent hashes distinguish
static/relaxation/MD/phonon protocols, `put()` and input-only `has()` agree on
POSCAR-based identity, strict payload conflicts cannot overwrite CAS or
metadata, rehash collisions are non-destructive and reportable, and the full
suite passes. Random perturbation deletion remains a separate, post-inventory
operation.
