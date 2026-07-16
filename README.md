# vasp-cache

Black-box VASP calculation cache: **same inputs → restore outputs without re-running VASP**.

Backend: **CAS + SQLite** (`cas/` objects + `meta.sqlite`). Hard identity is a tunable **Mapping Profile** → `content_hash`. Identical file bytes are stored once.

See `docs/DESIGN-storage-v2.md`. **User guide:** [`docs/USER.md`](docs/USER.md). **Identity contract:** [`docs/IDENTITY.md`](docs/IDENTITY.md). Legacy signac trees migrate with `scripts/migrate_signac_to_cas.py`.

## Roadmap

See [ROADMAP.md](ROADMAP.md) for current positioning and future development directions.

## Applications

### Current: exact calculation reuse

The primary supported use is to run one deterministic VASP calculation once,
then reuse its standard outputs and metadata across workflows and projects when
the input identity matches exactly.

### Planned/partial: related-calculation bootstrap

An existing calculation may be useful as a starting reference for a related
task, but this is not automatic in the current API. A changed INCAR or KPOINTS
normally produces a different identity. `fetch()` restores standard outputs
only; it does not generate new INCAR, KPOINTS, or POTCAR inputs. The workflow
must locate or reconstruct the starting structure and create the new inputs.

## Install

```bash
pip install -e ".[dev]"
```

## Core API

```python
from vasp_cache import put, has, fetch, query, content_hash, load_mapping

put("/path/to/complete_calc", provenance="canonical")
has("/path/to/inputs_only")          # bool
fetch("/path/to/inputs_only")        # restore OUTCAR/CONTCAR/…
query(formula="GaN")                 # canonical only by default
query(formula="GaN", provenance="sampled")
query(formula="GaN", provenance="all")
```

## CLI

```bash
vasp-cache put <dir> [--provenance canonical|sampled|unknown]
vasp-cache put -r <root> [--provenance canonical|sampled|unknown]
vasp-cache fetch <dir>
vasp-cache has <dir>
vasp-cache query --formula GaN                 # canonical only
vasp-cache query --formula GaN --provenance all
vasp-cache status
vasp-cache content-hash <dir>
vasp-cache mapping show
vasp-cache mapping check
vasp-cache export-archive /path/to/cache.tgz [--root DIR]
vasp-cache import-archive /path/to/cache.tgz [--root DIR] [--overwrite]
```

Omitted provenance is classified conservatively. Formula queries default to
`canonical`; `sampled` and `unknown` require an explicit filter, while
`provenance="all"` is the explicit all-candidates view. Exact `has()` and
`fetch()` remain provenance-independent.

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
