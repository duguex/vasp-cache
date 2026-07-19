# vasp-cache design

Design spec: **`docs/superpowers/specs/2026-07-18-v3-layered-identity.md`**

## Summary

| Item | Choice |
|------|--------|
| Backend | SQLite (index.sqlite) |
| Primary I/O | `put(dir)` → `fetch(key, dir)` |
| Key | 6-layer SHA-256 (formula, incar, structure, kpoints, potcar, lattice) |
| Payload | Zlib-compressed BLOBs (OUTCAR, vasprun, CONTCAR) |
| Structured extracts | Energy, magnetism, potentials, convergence |
| Collision | Converged > unconverged; audit table |

## Package layout

```
src/vasp_cache/
  index.py          SQLite schema, put/fetch/rebuild, identity, collision
  api.py            Public API wrapper
  cli.py            CLI (argparse)
  outcar.py         OUTCAR parser/serializer
  vasprun_ast.py    vasprun.xml AST round-trip
  errors.py         IdentityInputError
  paths.py          cache root resolution
  web/              Dashboard (static HTML/JS/CSS)
```

## All docs

| File | Content |
|------|---------|
| README.md | Project overview, quick start |
| docs/USER.md | Full user guide |
| docs/INTEGRATION.md | Integration guide for downstream projects |
| docs/superpowers/specs/2026-07-18-v3-layered-identity.md | Design spec |
