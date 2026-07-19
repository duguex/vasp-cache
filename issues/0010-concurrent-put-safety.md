(v2 issue — written for signac/CAS/mapping architecture; see issues/README.md for v3 status)

# Concurrent multi-process put safety

**Date:** 2026-07-15  
**Severity:** Medium — data races under batch ProcessPool  
**Component:** signac project / `put`

## Status

Open. In-process lock for store init only; multi-process writers not serialized.

## Problem

vasp-sop batch can put from many workers. JSON/signac file stores can corrupt or lose updates without external locking or single-writer queue.

## Expected

- Document: single-writer recommended for v1  
- Or: file lock around `put` / job.init+copy  
- Or: queue puts to one process  

## Acceptance

- Documented concurrency model  
- If lock: test two processes put different hashes without corruption  

## Related

- `vasp_sop` ProcessPoolExecutor batch  
- DESIGN concurrency section
