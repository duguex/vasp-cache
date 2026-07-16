# c606 permission wrapper

## Goal

Wrap the previously verified permission commands without mixing permission repair
with cache writes.

## Usage

```bash
scripts/normalize_c606.sh [ROOT] [INGEST_USER] [CACHE_ROOT]
```

Defaults are `/mnt/shared/home/c606`, `duguex`, and `/mnt/shared/vasp_cache`.
The wrapper normalizes all non-protected directories to `755`, regular files
without any execute bit to `644`, and regular files with an execute bit to
`755`. Symlinks and special files are skipped.

It prunes hidden paths (including `.ssh` and home metadata) and basenames
matching `credentials`, `credential`, `*token*`, `*.pem`, `*.key`, and
`id_rsa*`. These exclusions prevent the wrapper from exposing credentials or
breaking SSH private-key permissions. `run.sh`, `POTCAR`, and other ordinary
non-hidden data files are normalized according to their existing execute bit.

## Execution boundary

Stop the whole-home reingest and every other writer before running the wrapper.
It is a short path-based command wrapper, not a concurrent-tree repair tool.
The broad chmod operation is intentionally limited to the non-protected paths
listed above. Run it with credentials authorized to modify the c606 files. It
does not run reingest; after the whole-home writer exits, execute the printed
command as the ingest user.

The c606 shell or batch environment must separately use `umask 022` for future
files. The wrapper does not edit another user's environment.
