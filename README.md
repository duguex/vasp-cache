# vasp-cache

Black-box VASP calculation cache: **same inputs → restore outputs without re-running VASP**.

Backend: **CAS + SQLite** (`cas/` objects + `meta.sqlite`). Hard identity is a tunable **Mapping Profile** → `content_hash`. Identical file bytes are stored once.

See `docs/DESIGN-storage-v2.md`. Legacy signac trees migrate with `scripts/migrate_signac_to_cas.py`.

## Install

```bash
pip install -e ".[dev]"
```

## Core API

```python
from vasp_cache import put, has, fetch, query, content_hash, load_mapping

put("/path/to/complete_calc")          # returns content_hash or None
has("/path/to/inputs_only")            # bool
fetch("/path/to/inputs_only")          # restore OUTCAR/CONTCAR/…
query(formula="GaN")                   # metadata search
```

## CLI

```bash
vasp-cache put <dir>
vasp-cache put -r <root>
vasp-cache fetch <dir>
vasp-cache has <dir>
vasp-cache query --formula GaN
vasp-cache status
vasp-cache content-hash <dir>
vasp-cache mapping show
vasp-cache mapping check
vasp-cache export-archive /path/to/cache.tgz [--root DIR]
vasp-cache import-archive /path/to/cache.tgz [--root DIR] [--overwrite]
```

## Cache root

Default: **`/mnt/shared/vasp_cache`** (shared NFS, not under `$HOME`)  
Override: `VASP_CACHE_ROOT` or `override_cache_root(path)`.

## Mapping profile

Default: package `mapping.default.yaml` (`geom_hash`, `key_generation: 2`).

User overlay: `$VASP_CACHE_ROOT/mapping.yaml` or `VASP_CACHE_MAPPING`.

- Soft weights change nearness only.
- Critical edits require bumping `key_generation`.

## Real calculation verification

Synthetic unit tests always run. Real OUTCAR trees use production **spin-defect** data (not abandoned archives):

```bash
# integration tests (needs NFS path or REAL_VASP_CALC_DIRS)
pytest -m real_data -v

# one-shot script
python scripts/verify_real_calcs.py /path/to/complete_calc
python scripts/verify_real_calcs.py --discover 5
```

Default discovery root: `REAL_VASP_CALC_ROOT` or  
`/mnt/shared/home/2sidesniddle/vasp/2025_undergo_spin_defect`.

## Design

See `docs/superpowers/specs/2026-07-14-vasp-cache-signac-design.md`.

## License

MIT
