(v2 issue — references deleted modules/features; see issues/README.md for v3 status)

# Push vasp-cache/vasp-sop and standardize install path

**Date:** 2026-07-15  
**Severity:** High — operational (local-only otherwise)  
**Component:** release / ops

## Status

Open. Work is on local `main` (ahead of `origin`); not all machines share the package.

## Problem

- Other hosts/agents still on old code or empty install  
- Editable path `pip install -e ~/vasp_cache` is workstation-specific  

## Expected

- `git push origin main` for `vasp-cache` and adapter commits on `vasp-sop`  
- Documented install: version pin or git URL  
- Optional: tag `v0.1.0` / `v0.2.0` after geom_hash gen2  

## Acceptance

- Remote main contains signac + gen2 mapping  
- Fresh clone install instructions in README/CUTOVER verified once  

## Related

- `docs/CUTOVER.md`
