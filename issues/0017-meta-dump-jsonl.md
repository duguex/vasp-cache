# Metadata dump / export (JSONL)

**Date:** 2026-07-15  
**Severity:** Medium — analytics / audit  
**Component:** CLI `query` / new `dump-meta`

## Status

Open. `query` / `status` / `list_entries` exist but no full-catalog dump format for offline analysis or migration of **index only**.

## Problem

- Cannot easily ship “what’s in the cache” without the multi-GB file payload  
- Hard to diff two caches or build external indexes  

## Expected

```bash
vasp-cache dump-meta --jsonl > catalog.jsonl
vasp-cache dump-meta --jsonl --formula GaN
```

Each line: `content_hash`, formula, energy, tags, source_dir, key_generation, mapping_digest, relative paths of stored files (optional).

Note: **reload-from-jsonl alone cannot restore OUTCAR**; payload still needs archive or original dirs. Document that clearly.

## Acceptance

- [ ] CLI + Python API  
- [ ] Test against fixture cache: line count == entries, required keys present  
- [ ] Docs: dump-meta vs export-archive  

## Related

- `issues/0016-archive-export-import.md`
