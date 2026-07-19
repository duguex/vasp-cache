(v2 issue — written for signac/CAS/mapping architecture; see issues/README.md for v3 status)

# Batch path: cache put must not block advance

**Date:** 2026-07-15  
**Severity:** High — throughput  
**Component:** vasp-sop batch + vasp-cache put  
**Also track in:** `vasp_sop/issues/0006-batch-cache-put-blocks-advance.md`

## Status

Open (cross-repo). Even with vasp-cache, `TaskDoc`/parse-heavy put on every orphan/poll can stall batch.

## Expected

- Skip put when hard hash already in cache (`has`)  
- Prefer light meta extract or background queue  
- Metrics: put time per cycle  

## Acceptance

- Dry-run or timed batch cycle without multi-minute TaskDoc storms  
- Link/close sop#0006 when fixed  

## Related

- sop issue 0006  
- `scripts/reingest_tree.py --skip-existing`
