# E2E tests for import / export / migration

**Date:** 2026-07-15  
**Severity:** High — closes the “whole I/E/M untested” gap  
**Component:** tests/

## Status

Open. Covered today:

- Single-calc **put → fetch** (fixture + real_data)  
- Full-tree **reingest** (ops, not packaged as migrate test)  

Not covered:

- Archive round-trip  
- Cache root move  
- Generation bump migration playbook as automated test  

## Expected

Pytest module e.g. `tests/test_archive_migrate.py` (no NFS required):

1. **Archive round-trip:** put A,B → export-archive → new root import → stats equal → fetch A OUTCAR bytes  
2. **Root relocate:** put → copy/move root via API or env → has/fetch still work  
3. **Generation bump (light):** with two mappings (gen N formula vs gen N+1 geom), document that old keys miss; optional re-put restores  

Mark heavy cases `@pytest.mark.slow` if needed.

## Acceptance

- [ ] CI runs archive round-trip on every PR (`-m 'not real_data'`)  
- [ ] CUTOVER links to these tests as the definition of “migration works”  

## Related

- `issues/0016-archive-export-import.md`  
- `issues/0017-meta-dump-jsonl.md`  
- `scripts/reingest_tree.py`
