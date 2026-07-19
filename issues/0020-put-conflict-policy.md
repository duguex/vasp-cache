(v2 issue — written for signac/CAS/mapping architecture; see issues/README.md for v3 status)

# put conflict policy when key matches but value differs

**Date:** 2026-07-15  
**Severity:** High — silent data loss / wrong reuse  
**Component:** `api.put`, optional CLI flags  
**GitHub:** (to be linked)

## Status

Open. Current behavior: **last-write-wins**.

```text
put(dir) → content_hash H → open_job({content_hash: H}) → copy2 overwrite OUTCAR/doc
```

No byte compare, no warning, no dual-slot.

## Problem

If two calculation directories produce the **same hard key** but **different OUTCAR** (or energy):

1. Second `put` silently overwrites the first payload  
2. Later `fetch` returns the last writer’s files  
3. Operators cannot tell a conflict happened  

Causes include: remaining fingerprint blind spots, non-deterministic runs, partial OUTCAR, or intentional re-runs with same inputs but different codes/builds.

## Expected

### Modes (API + CLI)

| Mode | Behavior |
|------|----------|
| `overwrite` (current default) | Always replace files + doc; optionally log at INFO |
| `skip` | If job already has OUTCAR, do not write; return existing hash |
| `strict` | If existing OUTCAR present and **bytes (or content hash of file) differ** → raise / return conflict result; do not overwrite |
| `warn` (optional) | Like overwrite but emit explicit warning + increment conflict counter in doc |

Recommend:

```python
put(dir, *, on_conflict: Literal["overwrite", "skip", "strict"] = "overwrite")
```

```bash
vasp-cache put DIR --on-conflict strict|skip|overwrite
```

### Conflict record (strict / warn)

When mismatch detected, record on job.doc or sidecar:

- `conflict_count`, `last_conflict_at`  
- `last_conflict_source_dir`  
- optional `last_outcar_sha256` stored on successful put for cheap compare  

### has / fetch

Unchanged: still key → single job. Policy only affects **put**.

## Acceptance

- [ ] `on_conflict` implemented in `put` + CLI  
- [ ] Tests:  
  - same key same OUTCAR bytes → all modes succeed  
  - same key different OUTCAR → `strict` fails without clobber; `skip` keeps first; `overwrite` keeps second  
- [ ] Doc: default remains `overwrite` for reingest throughput; production batch may use `skip` or `strict`  
- [ ] Optional: `vasp-cache put -r --on-conflict skip` for incremental ingest  

## Non-goals (this issue)

- Multi-version value storage per key  
- Automatic fingerprint repair when conflict fires (file separate issue)  

## Related

- gen2 `geom_hash` (reduces false same-key)  
- `scripts/reingest_tree.py --skip-existing` (partial skip, not conflict detect)  
- `issues/0001`–`0005` identity hardening  
- `issues/0010-concurrent-put-safety.md` (races under concurrent overwrite)  
