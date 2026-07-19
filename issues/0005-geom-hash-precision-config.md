# Configurable geom_hash coordinate precision

**Date:** 2026-07-15  
**Severity:** Low–Medium  
**Component:** `_structure_tag` geom_hash path

## Status

Open. Fixed `round(..., 6)` on lattice and frac coords; hash truncated to 16 hex chars of SHA256.

## Problem

- Too coarse → rare false merge of distinct geometries  
- Too fine → noise / restart POSCAR micro-diffs → false miss  
- 16-hex truncation is collision-resistant in practice but not documented  

## Expected

```yaml
hard:
  structure: geom_hash
  structure_decimals: 6   # configurable
  structure_hash_len: 16
```

Document collision bounds and recommended defaults.

## Acceptance

- Config honored in fingerprint  
- Tests at decimals=2 vs 6 for near-identical coords  

## Related

- `docs/superpowers/specs/2026-07-18-v3-layered-identity.md` (5-layer identity)
