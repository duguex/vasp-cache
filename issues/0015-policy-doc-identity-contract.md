# Publish identity contract (policy doc)

**Date:** 2026-07-15  
**Severity:** Medium — alignment  
**Component:** docs

## Status

Open. Implementation details scattered (DESIGN, CUTOVER, issues).

## Expected

Single short policy: `docs/IDENTITY.md` covering:

1. Hard key composition (gen2: geom_hash + kpoints + potcar + incar set)  
2. Equivalence: atom order yes; origin shift no (until #0001)  
3. POSCAR vs CONTCAR policy (depends on #0002)  
4. Soft vs hard  
5. Generation bump rules  

## Acceptance

- Doc linked from README  
- Reviewed against code  

## Related

- All P0 fingerprint issues  
