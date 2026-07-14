# Production cutover: vasp-cache (signac)

## What changed

| Before | After |
|--------|--------|
| Results in `~/.vasp_sop/meta.json` + `blobs.json` | Results in `~/.vasp_cache` (signac workspace) |
| Logic inside `vasp_sop.core.cache` | Package `vasp-cache`; sop is a thin adapter |
| No automatic migration of old JSONStore | Re-ingest with `put` / `put -r` |

MP download cache stays under `~/.vasp_sop/mp_cache`.  
JobStore (`jobs.db`) stays under `~/.vasp_sop`.

## Install

```bash
pip install -e ~/vasp_cache
pip install -e ~/vasp_sop   # already depends on vasp-cache
```

## Verify

```bash
cd ~/vasp_cache && pytest -q -m 'not real_data'
pytest -m real_data -q   # needs spin-defect NFS paths

vasp-cache status
python scripts/verify_real_calcs.py --discover 3
```

## Re-ingest production trees

Old `meta.json` is **not** read. Populate the new cache from known calc roots:

```bash
export VASP_CACHE_ROOT=~/.vasp_cache   # default

# example: one material tree
vasp-cache put -r /mnt/shared/home/2sidesniddle/vasp/2025_undergo_spin_defect/ZnO

# or a few high-value roots
for d in GaN BaS AlN ZnO; do
  vasp-cache put -r "/mnt/shared/home/2sidesniddle/vasp/2025_undergo_spin_defect/$d" || true
done

vasp-cache status
vasp-cache query --formula ZnO
```

Only directories with a usable OUTCAR are stored. Incomplete or huge-lattice cells may be skipped (`MAX_LATTICE`).

## Mapping profile

Default is conservative/legacy-compatible. Lab overrides:

```bash
# edit ~/.vasp_cache/mapping.yaml  (critical changes need key_generation bump)
vasp-cache mapping show
vasp-cache mapping check
```

## Rollback (emergency)

1. Keep using disk OUTCARs as source of truth (cache is not the only copy).  
2. Pin an older `vasp-sop` that still embeds JSONStore **only if** you still have that commit; current main does not.  
3. Prefer re-ingest + fix over rollback.

## Do not

- Point re-ingest at abandoned archives (e.g. old MnPS3 trees).  
- Expect silent dual-read of `~/.vasp_sop/meta.json`.
