(RESOLVED in v3 — all INCAR keys participate in 5-layer identity; body describes original v2 problem)

# Audit INCAR keys for hard mapping

**Date:** 2026-07-15  
**Severity:** Medium  
**Component:** `mapping.default.yaml` hard.incar

## Status

Open. Default includes ENCUT/PREC/ISMEAR/…/METAGGA plus LHFCALC/HFSCREEN/ISPIN/LSORBIT (gen 2).

## Problem

Lab-critical switches that change results may still be missing (examples to validate):

- `ALGO`, `LREAL`, `ADDGRID`, `ENAUG`  
- `MAGMOM` / constrained magnetism  
- `IVDW` already present; van der Waals flavors  
- Hybrid extras beyond HFSCREEN  
- `LDAUU` lists already present  

Missing keys → false positive cache hits across physically different runs.

## Expected

- Written audit table: key → affects energy/forces/bandgap? → hard/soft/ignore  
- Update default profile + `key_generation` if hard set expands  
- Tests for at least 3 keys that flip hash when changed  

## Acceptance

- Doc in `docs/` or Mapping Profile comments  
- PR changing default keys only with generation bump  

## Related

- gen2 mapping.default.yaml
