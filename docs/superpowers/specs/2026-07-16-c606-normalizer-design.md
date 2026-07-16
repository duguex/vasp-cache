# c606 permission wrapper

## Goal

Wrap the previously verified permission commands without mixing permission repair
with cache writes.

## Usage

```bash
scripts/normalize_c606.sh [ROOT] [INGEST_USER] [CACHE_ROOT]
```

Defaults are `/mnt/shared/home/c606`, `duguex`, and `/mnt/shared/vasp_cache`.
The wrapper finds directories containing `OUTCAR`, sets those calculation
directories to `755`, and sets only `OUTCAR`, `CONTCAR`, `vasprun.xml`, `INCAR`,
`POSCAR`, and `KPOINTS` to `644`. It leaves `run.sh`, `POTCAR`, credentials,
home metadata, and unrelated files unchanged.

## Execution boundary

Stop the whole-home reingest and every other writer before running the wrapper.
It is a short path-based command wrapper, not a concurrent-tree repair tool.
Run it with credentials authorized to modify the c606 files. It does not run
reingest; after the whole-home writer exits, execute the printed command as the
ingest user.

The c606 shell or batch environment must separately use `umask 022` for future
files. The wrapper does not edit another user's environment.
