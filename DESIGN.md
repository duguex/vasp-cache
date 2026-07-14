# vasp-cache design

Canonical design: **`docs/superpowers/specs/2026-07-14-vasp-cache-signac-design.md`**.

Implementation plan: **`docs/superpowers/plans/2026-07-14-vasp-cache-signac.md`**.

## Summary

| Item | Choice |
|------|--------|
| Backend | signac Project |
| Primary I/O | `put(complete calc)` / `fetch(inputs → outputs)` |
| Key | Mapping Profile → hard `content_hash` |
| Soft map | Tunable weights (not ML embeddings) |
| Payload | Original OUTCAR/CONTCAR/… in job workspace |
| Legacy maggma JSONStore | Abandoned |

## Package layout

```
src/vasp_cache/
  paths.py         cache root + get_project()
  mapping.py       profile load + digest + soft distance
  fingerprint.py   critical field extraction helpers
  parse.py         summarize_calc for job.doc
  api.py           put/has/fetch/query/…
  cli.py           vasp-cache CLI
  data/mapping.default.yaml
```
