# vasp-cache User Guide

## Install

```bash
pip install vasp-cache
# or editable:
pip install -e ".[dev]"
```

Requires Python ≥ 3.10, pymatgen ≥ 2023.0.

## Architecture

vasp-cache is a **single SQLite file** that stores VASP calculation outputs
for reuse. It does not connect to VASP, Slurm, or any HPC scheduler. It is a
file-level cache layer:

```
                              ┌─────────────────┐
  VASP run completes   →      │   vasp-cache    │
                              │  ┌───────────┐  │      ┌──────────┐
  OUTCAR, vasprun,      put() │  │index.sqlite│  │fetch │  file    │
  CONTCAR, POTCAR, ... ──────→│  │ (BLOB+JSON)│──│─────→│  dir     │
                              │  └───────────┘  │      └────┬─────┘
                              └─────────────────┘           │
                                                      any VASP tool
                                                      (pydefect, vasp-sop,
                                                       crisp, pymatgen, ...)
```

## Quick start

```python
from vasp_cache import put, has, fetch, query

key = put("/path/to/vasp_calc")
assert has("/path/to/vasp_calc")  # same identity?
fetch(key, "/tmp/restored")
```

```bash
vasp-cache --root ~/my_cache put /path/to/vasp_calc
vasp-cache --root ~/my_cache fetch <key> /tmp/restored
vasp-cache --root ~/my_cache query --formula CsEuCl3 --json
```

## Cache root

Default: `~/.cache/vasp_cache/`
Override: `VASP_CACHE_ROOT` env var or `--root` CLI flag.

SQLite file: `<root>/index.sqlite`

## What gets stored

7 files are required for admission:

| File | Storage | Fetch fidelity |
|------|---------|---------------|
| POSCAR | Structured JSON | Semantic (no comments/format) |
| INCAR | Structured JSON | Semantic |
| KPOINTS | Structured JSON | Semantic |
| POTCAR | Structured JSON | TITEL stub only |
| OUTCAR | zlib BLOB | Byte-identical |
| vasprun.xml | zlib BLOB | Byte-identical |
| CONTCAR | zlib BLOB | Byte-identical |

## Queryable columns

These are extracted at `put()` time and available via SQL/API query:

- `final_energy` (eV)
- `total_mag` (total magnetization)
- `electrostatic_potentials` (per-atom JSON array)
- `n_ionic_steps`
- `converged_ionic` (0/1)
- `converged_electronic` (0/1)

## Identity

Two calculations share an identity if these 5 layers match:

1. **formula** — `Structure.from_file(POSCAR).composition.reduced_formula`
2. **incar** — canonical INCAR dict (sorted keys, normalized whitespace)
3. **kpoints** — `Kpoints.as_dict()` (mesh, mode, shift)
4. **potcar** — species list + XC functional (+ optional version date)
5. **lattice** — {a, b, c, alpha, beta, gamma}, rounded to 0.001 Å / 0.1°

## Collision handling

When multiple calculations produce the same identity:

1. Converged (converged_ionic=1) beats unconverged
2. Existing representative is never replaced by equal-quality candidate
3. Discarded candidates recorded in `discarded_candidates` table with
   reason, energy, and convergence info

## API reference

```python
# Core
put(directory, root=None) -> str | None     # returns identity_key or None
has(directory, root=None) -> bool
fetch(identity_key, target_dir, root=None) -> bool
query(formula=None, root=None, limit=100) -> list[dict]
rebuild(source_root, root=None, exclude=None) -> dict[str, int]
stats(root=None) -> dict[str, int | str]

# Identity
identity_for_directory(directory) -> Identity
normalize_incar(path) -> dict[str, str]
```
