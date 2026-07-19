# Define identity structure file: POSCAR vs CONTCAR

**Date:** 2026-07-15  
**Severity:** High — incorrect hit/miss on pipeline submit vs result  
**Component:** `_structure_tag`, `put` / `has` / `fetch`

## Status

Open. Current code prefers **CONTCAR then POSCAR** for structure fingerprint.

## Problem

- **Submit-time** dirs often have POSCAR only (pre-VASP).  
- **Completed** dirs have CONTCAR (relaxed geometry).  
- If `put` keys off CONTCAR and later `has` runs on a fresh input POSCAR of the same job recipe, hashes may **not** match even when the calculation is “the same job intent.”

Conversely, fingerprinting only POSCAR loses distinction between different relaxed endpoints.

## Expected

Document and implement an explicit policy, one of:

| Policy | `put` uses | `has` uses |
|--------|------------|------------|
| A. Result geometry | CONTCAR | CONTCAR only (inputs without CONTCAR never hit) |
| B. Input geometry | POSCAR | POSCAR |
| C. Dual key | store both; hit if either matches | try POSCAR then CONTCAR |
| D. Intent hash | recipe inputs only (POSCAR+INCAR+…) | same; ignore CONTCAR |

Recommend choosing with vasp-sop batch semantics (skip-before-submit vs restore-after).

## Acceptance

- Spec paragraph in DESIGN/CUTOVER  
- Tests for chosen policy  
- sop adapter documents which policy batch uses  

## Related

- `vasp_sop` batch cache_lookup before submit
