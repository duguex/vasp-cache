# vasp-cache Roadmap

## Current Position

`vasp-cache` is an exact VASP calculation cache: avoid re-running deterministic
VASP calculations. Single SQLite backend (index.sqlite) with zlib-compressed BLOBs.

Implemented in v3 (0.3.0):

- 5-layer identity: formula, incar, kpoints, potcar, lattice
- BLOB storage: OUTCAR, vasprun.xml, CONTCAR byte-identical on fetch
- Structured extraction: energy, magnetism, potentials, convergence
- Collision handling: converged > unconverged; audit table
- `put`, `has`, `fetch`, `query`, `rebuild`, `stats` API + CLI
- 32 unit tests
- CLI consumers verified: vasp-sop, pydefect mce/cr, crisp

## Later

- `on_conflict=strict|skip|overwrite` modes for put()
- Archive export/import (needs v3 rewrite)
- Batch performance measurement
- CI configuration
- Concurrent safety hardening (WAL, busy_timeout)
- POTCAR version regression test
- Full vasp-sop regression testing
- Metadata dump tooling

## Not Planned

- Niggli/primitive cell reduction (supercell size = different DFT calc)
- Origin standardization (structure not in identity hash)
- Mapping profiles / key_generation (removed in v3)
- Job scheduling or queue management
- Automatic VASP input generation
- Whole-home ingest as completion criterion
