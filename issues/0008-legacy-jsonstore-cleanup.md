(v2 issue — references deleted modules/features; see issues/README.md for v3 status)

# Cleanup legacy ~/.vasp_sop meta.json / blobs.json

**Date:** 2026-07-15  
**Severity:** Low — ops hygiene  
**Component:** ops / docs

## Status

Open. Runtime no longer reads JSONStore results cache; files may still occupy disk under `~/.vasp_sop/`.

## Problem

- Confusion: which is source of truth  
- Disk: large `blobs.json` / `cache.db.bak`  
- Accidental tooling still pointing at old paths  

## Expected

- Document archive/delete procedure in CUTOVER  
- Optional script: detect unused meta/blobs, print size, require `--i-know` to delete  
- Keep `mp_cache/` and `jobs.db`  

## Acceptance

- CUTOVER section + safe cleanup command  
- No code path references meta.json for results  

## Related

- `docs/CUTOVER.md`
