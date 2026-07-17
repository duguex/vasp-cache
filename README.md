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

vasp-cache put <dir> [--provenance canonical|sampled|unknown] [--on-conflict strict|skip|overwrite]
vasp-cache put -r <root> [--provenance canonical|sampled|unknown] [--on-conflict strict|skip|overwrite]
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

Read-only Materials Atlas dashboard:

```bash
vasp-cache web [--root DIR] [--host HOST] [--port PORT]
```

The dashboard defaults to the configured `VASP_CACHE_ROOT`, listens on
`localhost:8765`, and serves only fixed static assets plus read-only metadata
APIs. Use `--host 0.0.0.0` (or another non-loopback host) only when LAN access
is intended; the CLI prints an explicit warning for non-loopback binding.

Omitted provenance is classified conservatively. Formula queries default to
`canonical`; `sampled` and `unknown` require an explicit filter, while
`provenance="all"` is the explicit all-candidates view. Exact `has()` and
`fetch()` remain provenance-independent.

### Read-only inspection

The `inspect` command family is a read-only observability surface for the cache.
It reads metadata from SQLite and storage facts from CAS without creating,
rewriting, or deleting cache state. Use these views to understand both the
logical metadata entries and the physical objects they reference:

```bash
vasp-cache inspect overview --top-formulas 20
vasp-cache inspect summary
vasp-cache inspect entries --formula GaN --provenance all --limit 50
vasp-cache inspect entries --jsonl --limit 1000
vasp-cache inspect entry 5:...
vasp-cache inspect objects --orphans-only
```

`overview` is the fast SQLite-only aggregate view: it reports entry/formula
counts, energy and convergence coverage, provenance and identity-generation
distributions, top formulas, and cached/energy ranges. It deliberately does
not scan CAS and reports `storage_scan: false`.

`summary` additionally scans metadata references and physical CAS objects for
storage totals, so it is more expensive on large caches. `entries` lists
filtered metadata rows. `entry` shows one complete metadata record and, for
each logical output, its CAS digest, size, presence, and relative CAS location;
this makes the metadata-to-CAS relationship explicit. `objects` reports
physical CAS objects and their metadata references. `--orphans-only` only
reports unreferenced objects; it never deletes them.

Inspection is observational only: it does not repair missing objects, run
health checks, or perform garbage collection. Future `health` and `gc`
commands will require separate explicit workflows. The existing `status`
command remains a quick stats/preview view; use `inspect overview` for fast
whole-database context and the other inspect views for detail.

## Cache root

Default: **`/mnt/shared/vasp_cache`** (shared NFS, not under `$HOME`)  
Override: `VASP_CACHE_ROOT` or `override_cache_root(path)`.

Default mapping profile: package `mapping.default.yaml` (`geom_hash`, normalized input protocol, `key_generation: 5`).

User overlay: `$VASP_CACHE_ROOT/mapping.yaml` or `VASP_CACHE_MAPPING`.

- The primary identity uses POSCAR + KPOINTS + normalized input protocol + hard INCAR fields.
- CONTCAR is an output/result geometry, not primary identity; result-only directories cannot prove input intent.
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

## Identity and migration

See `docs/IDENTITY.md` for the generation-5 input-intent contract. Rehashing is
inventory-first and non-destructive by default:

```bash
python scripts/rehash_meta_cas.py --root /path/to/cache
python scripts/rehash_meta_cas.py --root /path/to/cache --apply
```

Only non-colliding groups are applied; collisions remain available for review.

## License

MIT
