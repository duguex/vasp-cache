# vasp-cache

Black-box VASP calculation cache: **same inputs → restore outputs without re-running VASP**.

Backend: single **SQLite** file (`index.sqlite`) with zlib-compressed BLOB storage. Identity is a 6-layer SHA-256 hash over formula, INCAR, structure, kpoints, POTCAR metadata, and lattice parameters.

## Install

```bash
pip install -e ".[dev]"
```

## API

```python
from vasp_cache import put, has, fetch, query, rebuild, stats

key = put("/path/to/complete_calc")
has("/path/to/inputs_only")           # bool — identity check
fetch(key, "/path/to/output_dir")     # restore outputs (POTCAR = TITEL stub)
query(formula="CsEuCl3")              # list entries
rebuild("/source/root", exclude=["*backup*"])  # bulk import
stats()                               # entry/formula/BLOB counts
```

## CLI

```bash
vasp-cache --root /path/to/cache put /path/to/calc
vasp-cache --root /path/to/cache fetch <key> /path/to/dest
vasp-cache --root /path/to/cache query --formula CsEuCl3 --json
vasp-cache --root /path/to/cache rebuild /source/root --exclude "*backup*"
vasp-cache --root /path/to/cache status
```

## Cache root

Default: `~/.cache/vasp_cache`
Override: `--root` flag or `VASP_CACHE_ROOT` env var.

## Storage

| File | Storage | Fetch |
|------|---------|-------|
| POSCAR | `structure_json` | semantic reconstruction |
| INCAR | `incar_json` | semantic reconstruction |
| KPOINTS | `kpoints_json` | semantic reconstruction |
| POTCAR | `potcar_json` | TITEL stub (identity placeholder) |
| OUTCAR | BLOB (zlib) | byte-identical |
| vasprun.xml | BLOB (zlib) | byte-identical |
| CONTCAR | BLOB (zlib) | byte-identical |

Extraction columns (queryable): `final_energy`, `total_mag`, `electrostatic_potentials`, `n_ionic_steps`, `converged_ionic`, `converged_electronic`.

## Collision handling

Same identity, multiple candidates:
1. Converged beats unconverged
2. Existing representative is not replaced by equal-quality candidate
3. Discarded candidates recorded in `discarded_candidates` audit table

## License

MIT
