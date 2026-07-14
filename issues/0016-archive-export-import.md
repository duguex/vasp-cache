# Whole-cache archive export / import

**Date:** 2026-07-15  
**Severity:** High — ops / portability  
**Component:** CLI + storage root  
**GitHub:** (to be linked)

## Status

Open. Today the only “full DB move” is manual copy/tar of `VASP_CACHE_ROOT` (`~/.vasp_cache`). No first-class command or tests.

## Problem

Users need to:

- Back up the cache  
- Move between machines  
- Restore after disk failure  

Without a defined archive format, migration is ad hoc and untested.

## Expected

```bash
vasp-cache export-archive /path/to/cache.tgz
vasp-cache import-archive /path/to/cache.tgz [--root DIR]
```

Behavior:

- Export packs the active cache root (`.signac` + `workspace` + optional `mapping.yaml`)  
- Import extracts to target root and is usable immediately as `VASP_CACHE_ROOT`  
- Refuse silent merge into non-empty incompatible roots (or document merge policy)  
- Progress + checksum (e.g. file count / `stats()` snapshot in archive manifest)

## Acceptance

- [ ] CLI commands exist and documented in README/CUTOVER  
- [ ] Test: put 2 fixtures → export → empty tmp root import → `stats` match → `fetch` OUTCAR bytes match  
- [ ] Manifest records `key_generation` / mapping digest of exporter  

## Related

- `docs/CUTOVER.md`  
- `issues/0017-meta-dump-jsonl.md`  
- `issues/0018-ie-migrate-e2e-tests.md`
