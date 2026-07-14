# Structure standardization for hard key (Niggli / origin)

**Date:** 2026-07-15  
**Severity:** Medium–High — scientific false negatives (duplicate compute)  
**Component:** `fingerprint._structure_tag` / Mapping Profile `hard.structure`

## Status

Open. Current default: `geom_hash` of rounded lattice matrix + fractional sites (sorted). Atom **order** permutation is stable; crystallographic equivalence is **not**.

## Problem

The same physical crystal can yield different `content_hash` under:

- Origin translation of all atoms
- Lattice vector reordering / equivalent cell settings
- Orientation related by lattice automorphism / symmetry

Impact: unnecessary recompute (`has` miss), not typically wrong `fetch` (false positive).

## Expected

Optional (or default) standardization before hash, e.g.:

1. Niggli (or standard primitive) reduction  
2. Canonical origin choice  
3. Then sort sites + hash  

Configurable via Mapping Profile, with `key_generation` bump when enabled.

## Acceptance

- Documented equivalence classes  
- Tests: translate structure by lattice vector → same hard hash when standardization on  
- Re-ingest note when generation bumps  

## Related

- `issues/0002-poscar-vs-contcar-identity.md`  
- gen2 geom_hash fix (commit `1b05b1c`)
