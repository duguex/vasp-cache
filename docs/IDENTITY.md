# Identity contract (content_hash)

**Status:** active · **key_generation:** `5` · **profile:** package `mapping.default.yaml`

## What is identity?

`content_hash` / `mapping_digest` decides whether two calculation directories are
the **same cached result**. Format:

```text
{key_generation}:{POSCAR geometry}_{kpoints}_{protocol}_{incar_hard}_{pot_token}
```

Example prefix: `5:…`.

## Hard fields (change ⇒ different hash)

| Field | Default (gen 5) | Notes |
|-------|-----------------|--------|
| Structure | `geom_hash` from **POSCAR** | POSCAR is the input-intent source; CONTCAR is never used for primary identity |
| KPOINTS | on | mesh / gamma / line-mode tag |
| Input protocol | on | normalized effective NSW/IBRION/ISIF, calc mode, and protocol fields |
| INCAR hard keys | ENCUT, PREC, ISMEAR, SIGMA, ISIF, LDAU*, GGA, IVDW, LASPH, METAGGA, LHFCALC, HFSCREEN, ISPIN, LSORBIT | Protocol normalization is independently hard; soft fields remain for tuning metadata |
| POTCAR | **off** | File not stored; missing POTCAR does not affect default hash. Token fixed `default` |

Lab overlays: `$VASP_CACHE_ROOT/mapping.yaml` or `VASP_CACHE_MAPPING`.  
Any change to the hard section requires **`key_generation` strictly greater than** the packaged default, then rehash/re-ingest.

## Soft fields

Nearness / tags only. Not part of `content_hash`.

## Ingest eligibility (orthogonal to identity)

| Rule | Behavior |
|------|----------|
| Converged OUTCAR required | Unconverged → `put` returns `None` |
| `MAX_LATTICE` (default 25 Å) | Larger `max_abc` skipped |
| No POTCAR in CAS | Never stored |

## Conflict policy (same key, new put)

`put(..., on_conflict="strict")` is the default. Strict mode compares the
source OUTCAR digest with the existing immutable CAS object before any CAS
write, raising `CacheConflictError` when bytes differ. Same-byte puts are
idempotent. Use `on_conflict="skip"` to retain the existing entry without
writing, or `on_conflict="overwrite"` only when replacing the output is
intentional.

## Structure files and input intent

The primary identity requires the original **POSCAR**, plus KPOINTS and INCAR.
Input-only `has()` calls must carry that same POSCAR; a result-only directory
with only CONTCAR cannot prove the original input intent. CONTCAR is stored as
an output and may produce optional `result_geom_hash` metadata, but it is never
the primary identity source.

## Changing identity safely

1. Edit mapping overlay or package default.
2. Bump `key_generation`.
3. Inventory before rewriting:
   `python scripts/rehash_meta_cas.py --root $VASP_CACHE_ROOT`
4. Apply only safe, non-colliding groups explicitly:
   `python scripts/rehash_meta_cas.py --root $VASP_CACHE_ROOT --apply`
5. Old generation prefixes will not `has`-match until rehashed.

## Non-goals

- Niggli/origin standardization (open research; not required for current gen 5).
- Soft similarity search as identity (separate feature).  
- Auto-migrate of legacy JSONStore (`~/.vasp_sop/meta.json` is not read).

## INCAR hard audit

See [INCAR_HARD_AUDIT.md](./INCAR_HARD_AUDIT.md) (gen 5 keys).
