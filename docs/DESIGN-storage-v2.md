# Storage v2: CAS + SQLite (方案 B)

## Why

signac `workspace/<job_id>/{OUTCAR,CONTCAR,...}` ≈ **7 files × N jobs**.
Whole-cache move/backup is O(files) on NFS and was unacceptable at ~10⁴ jobs.

## Layout

```text
$VASP_CACHE_ROOT/          # default /mnt/shared/vasp_cache
  meta.sqlite              # content_hash → metadata + object map
  cas/
    ab/cd/<sha256>         # immutable blobs (OUTCAR, CONTCAR, …)
  mapping.yaml             # optional lab overlay
```

## Identity

Generation-5 `content_hash` is the input-intent identity: POSCAR geometry,
KPOINTS, normalized protocol, and hard INCAR fields. `CONTCAR` is an output
object and optional result geometry metadata.
`put` defaults to strict same-key output verification; explicit `skip` and
`overwrite` modes are available.

## API

`put` / `has` / `fetch` / `query` / `stats` unchanged for callers.
Backend is `cas+sqlite` (`stats()["backend"]`).

## Migration

Legacy signac tree is **not** auto-read.

```bash
python scripts/migrate_signac_to_cas.py \
  --src ~/.vasp_cache \
  --dest /mnt/shared/vasp_cache
# optional: --limit 100 for cost probe
```

## Archive

`export-archive` / `import-archive` pack `meta.sqlite` + `cas/` (format `vasp-cache-archive-v2`).

## Non-goals (v2)

- GC of unreferenced CAS objects (add later)
- Compression inside CAS (optional zstd later)
- Dual-read of signac workspace
