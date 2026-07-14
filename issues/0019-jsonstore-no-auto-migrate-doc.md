# Explicitly document: no auto-migrate from JSONStore

**Date:** 2026-07-15  
**Severity:** Low — docs / expectations  
**Component:** README, CUTOVER, DESIGN

## Status

Open (behavior already: no code path). Needs a crisp user-facing statement and pointer to re-put.

## Problem

Users with `~/.vasp_sop/meta.json` + `blobs.json` may expect one-click upgrade.

## Expected

- README + CUTOVER: “Results migrate only by re-`put` from source calculation directories.”  
- Optional: detect legacy files and print warning + size on `vasp-cache status`  
- Link to `issues/0008-legacy-jsonstore-cleanup.md`  

## Acceptance

- [ ] Docs updated  
- [ ] Optional status warning (nice-to-have)  

## Related

- `issues/0008-legacy-jsonstore-cleanup.md`
