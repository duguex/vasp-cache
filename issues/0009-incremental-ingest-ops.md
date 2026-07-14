# Incremental ingest / ops playbook

**Date:** 2026-07-15  
**Severity:** Medium — production maintainability  
**Component:** `scripts/reingest_tree.py`, ops

## Status

Open. Full tree reingest works; incremental discipline not standardized.

## Problem

- Full scans are long (~40–60 min) and rewrite duplicates  
- No scheduled incremental for new converged dirs only  
- Disk growth (~11G after gen2 full tree) unmonitored  

## Expected

- Default ops: `reingest_tree.py --skip-existing` after new waves  
- Document progress log / errors JSON locations  
- Optional: only walk dirs newer than N days  
- Disk alert threshold in CUTOVER  

## Acceptance

- CUTOVER or ops doc section  
- `--since` or mtime filter (nice-to-have)  

## Related

- `scripts/reingest_tree.py`  
- gen2 log `/tmp/vasp_cache_reingest_gen2.log`
