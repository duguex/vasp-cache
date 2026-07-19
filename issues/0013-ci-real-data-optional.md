(v2 issue — written for signac/CAS/mapping architecture; see issues/README.md for v3 status)

# Optional CI job for real_data tests

**Date:** 2026-07-15  
**Severity:** Low  
**Component:** CI / tests

## Status

Open. `pytest -m real_data` works locally with NFS spin-defect paths; no CI config in repo.

## Expected

- Default CI: `-m 'not real_data'`  
- Optional nightly / manual job with `REAL_VASP_CALC_DIRS` secrets or mounted data  
- Skip cleanly when paths missing  

## Acceptance

- CI config (GitHub Actions or local script) documented  
- real_data never blocks PR without data  

## Related

- `tests/test_real_calc.py`  
- `scripts/verify_real_calcs.py`
