(v2 issue — written for signac/CAS/mapping architecture; see issues/README.md for v3 status)

# Full vasp-sop regression against vasp-cache adapter

**Date:** 2026-07-15  
**Severity:** High — pipeline confidence  
**Component:** vasp-sop + vasp-cache adapter

## Status

Open. Cache-focused tests pass (56 pass / 1 skip). Full suite (batch/cli/defect/production) not treated as gate after cutover.

## Problem

Adapter changed `cache_lookup` / `vasp_results_put` / restore semantics (file restore, no blobs, geom_hash keys). Batch dry-run and production paths may still assume old behavior.

## Expected

- Run full `pytest tests/` in vasp-sop with editable vasp-cache  
- Fix failures or explicitly skip with linked issue  
- At least one `vasp-sop batch run … --dry-run` on a small project using new cache  

## Acceptance

- Green full suite or tracked failures  
- Dry-run log attached showing cache hit/skip without TaskDoc storm (see also sop issues 0006)  

## Related

- `vasp_sop/issues/0006-batch-cache-put-blocks-advance.md`  
- `vasp_sop/core/cache.py` adapter
