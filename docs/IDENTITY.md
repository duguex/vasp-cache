# Identity contract (content_hash)

**Status:** active · **key_generation:** `4` · **profile:** package `mapping.default.yaml`

## What is identity?

`content_hash` / `mapping_digest` decides whether two calculation directories are
the **same cached result**. Format:

```text
{key_generation}:{structure}_{kpoints}_{incar_hard}_{pot_token}
```

Example prefix: `3:…`.

## Hard fields (change ⇒ different hash)

| Field | Default (gen 3) | Notes |
|-------|-----------------|--------|
| Structure | `geom_hash` | Prefer **CONTCAR** over POSCAR when both exist; fractional coords rounded in hash |
| KPOINTS | on | mesh / gamma / line-mode tag |
| INCAR hard keys | ENCUT, PREC, ISMEAR, SIGMA, ISIF, LDAU*, GGA, IVDW, LASPH, METAGGA, LHFCALC, HFSCREEN, ISPIN, LSORBIT | Soft keys (NSW, NELM, EDIFF, …) do **not** change identity |
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

**Last-write-wins:** same `content_hash` upserts metadata and may replace object pointers.  
No silent dual versions; no automatic raise on byte mismatch.  
If you need strict compare, call `has` + compare OUTCAR digests externally (future: `on_conflict=strict`).

## Structure file choice

For geometry in the hard key: **CONTCAR if present, else POSCAR**.  
Inputs-only workdirs used for `has`/`fetch` should carry the same structure file the original job used for hashing (usually POSCAR/CONTCAR consistent with the calc).

## Changing identity safely

1. Edit mapping overlay or package default.  
2. Bump `key_generation`.  
3. `python scripts/rehash_meta_cas.py --root $VASP_CACHE_ROOT` **or** full re-`put`.  
4. Old generation prefixes will not `has`-match until rehashed.

## Non-goals

- Niggli/origin standardization (open research; not required for current gen 3).  
- Soft similarity search as identity (separate feature).  
- Auto-migrate of legacy JSONStore (`~/.vasp_sop/meta.json` is not read).

## INCAR hard audit

See [INCAR_HARD_AUDIT.md](./INCAR_HARD_AUDIT.md) (gen 4 keys).
