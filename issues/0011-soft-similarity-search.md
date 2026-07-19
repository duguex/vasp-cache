(v2 issue — written for signac/CAS/mapping architecture; see issues/README.md for v3 status)

# Soft similarity search (productization)

**Date:** 2026-07-15  
**Severity:** Low — enhancement  
**Component:** `soft_vector` / `soft_distance` / CLI

## Status

Open. Soft map exists; no user-facing “find similar calcs” workflow.

## Expected

- CLI: `vasp-cache similar <dir> [--k 10]`  
- Hard filter first (same structure hash or formula), then soft rank  
- Never auto-fetch on soft similarity alone  

## Acceptance

- CLI + tests with fixtures  
- Docs: hard vs soft  

## Related

- Mapping Profile soft section  
- Design discussion on tunable nearness (not ML embeddings)
