# Production cutover: vasp-cache (signac)

## What changed

| Before | After |
|--------|--------|
| Results in `~/.vasp_sop/meta.json` + `blobs.json` | Results in **`/mnt/shared/vasp_cache`** (signac; override with `VASP_CACHE_ROOT`) |
| Logic inside `vasp_sop.core.cache` | Package `vasp-cache`; sop is a thin adapter |
| No automatic migration of old JSONStore | Re-ingest with `put` / `put -r` |

MP download cache stays under `~/.vasp_sop/mp_cache`.  
JobStore (`jobs.db`) stays under `~/.vasp_sop`.

## Install

```bash
pip install -e ~/vasp_cache
pip install -e ~/vasp_sop   # already depends on vasp-cache
```

## Cache location

Default root: **`/mnt/shared/vasp_cache`** (NFS shared, **not** under `$HOME`).

```bash
# optional override
export VASP_CACHE_ROOT=/mnt/shared/vasp_cache
```

## Verify

```bash
cd ~/vasp_cache && pytest -q -m 'not real_data'
pytest -m real_data -q   # needs spin-defect NFS paths

vasp-cache status
python scripts/verify_real_calcs.py --discover 3
```

## Re-ingest production trees

Old `meta.json` is **not** read. Populate the cache from known calc roots:

```bash
# default already /mnt/shared/vasp_cache
vasp-cache put -r /mnt/shared/home/2sidesniddle/vasp/2025_undergo_spin_defect/ZnO

# or full tree with progress log
python scripts/reingest_tree.py \
  /mnt/shared/home/2sidesniddle/vasp/2025_undergo_spin_defect \
  --log /tmp/vasp_cache_reingest.log \
  --skip-existing

vasp-cache status
vasp-cache query --formula ZnO
```

Only directories with a usable OUTCAR are stored. Incomplete or huge-lattice cells may be skipped (`MAX_LATTICE`).

## Mapping profile

Default is gen-2 `geom_hash`. Lab overrides:

```bash
# edit /mnt/shared/vasp_cache/mapping.yaml  (critical changes need key_generation bump)
vasp-cache mapping show
vasp-cache mapping check
```

## Rollback (emergency)

1. Keep using disk OUTCARs as source of truth (cache is not the only copy).  
2. Pin an older `vasp-sop` that still embeds JSONStore **only if** you still have that commit; current main does not.  
3. Prefer re-ingest + fix over rollback.

## Do not

- Store the default cache under `$HOME` (use `/mnt/shared/vasp_cache`).  
- Expect silent dual-read of `~/.vasp_sop/meta.json`.  
- Point re-ingest at abandoned archives (e.g. old MnPS3 trees).  
