# Strengthen POTCAR fingerprint

**Date:** 2026-07-15  
**Severity:** Medium — wrong reuse across PP versions  
**Component:** `_potcar_fingerprint`

## Status

Open. Current: regex `PAW_\w+\s+(\S+)` species tokens; missing file → `nopot`.

## Problem

- Different POTCAR dates/libraries can share species tokens → false positive risk.  
- Many dirs without POTCAR all get `nopot` → weaker discrimination when combined with other coarse fields.  
- Production put does not require POTCAR presence for a hit.

## Expected

- Prefer TITEL / VRHFIN + date lines (or hash of POTCAR header blocks)  
- Config: `hard.potcar: species | titel | sha256_head`  
- Optional: refuse `has`/`fetch` success when stored entry had POTCAR and query dir lacks matching fingerprint  

## Acceptance

- Two POTCARs same element different TITEL → different hard hash  
- Tests with fixture POTCAR headers  
- Mapping generation bump if default method changes  

## Related

- Mapping Profile `hard.potcar`
