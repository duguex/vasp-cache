# Publish identity contract (policy doc)

**Date:** 2026-07-15  
**Severity:** Medium — alignment  
**Component:** docs

## Status

Resolved. Identity contract documented in `docs/superpowers/specs/2026-07-18-v3-layered-identity.md` §1 and `docs/USER.md` §Identity.

## Expected

Single short policy: `docs/IDENTITY.md` covering:
1. 5-layer identity: formula, incar, kpoints, potcar, lattice
2. Atom order and origin shift do not affect identity (structure not hashed)
3. POSCAR provides formula + lattice for identity; CONTCAR is output BLOB only
4. All INCAR keys participate equally (normalized whitespace, no selective hard/soft)

## Acceptance

- Doc linked from README  
- Reviewed against code  

## Related

- All P0 fingerprint issues  
