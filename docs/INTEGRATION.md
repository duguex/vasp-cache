# Integration Guide

How to add vasp-cache to an existing VASP workflow tool (crisp, vasp-sop, pydefect, etc.).

## Design principle

vasp-cache is **file-compatible, not code-coupled**. It does not import
or subclass any downstream tool. Integration works by placing cached output
files on disk so existing file-based parsers work unchanged.

## Integration patterns

### After VASP completes (put)

```python
from vasp_cache import put

key = put("/path/to/finished_vasp_calc", root="/shared/cache")
if key:
    print(f"cached: {key}")
```

```bash
vasp-cache --root /shared/cache put /path/to/finished_calc
```

### Before VASP starts (check + fetch)

```python
from vasp_cache import has, fetch, identity_for_directory

ROOT = "/shared/cache"
calc_dir = "/path/to/planned_calc"

try:
    ident = identity_for_directory(calc_dir)
except Exception:
    ident = None

if ident and has(calc_dir, root=ROOT):
    fetch(ident.key, calc_dir, root=ROOT, into_existing=True)
    # outputs restored — skip VASP, proceed to downstream analysis
else:
    submit_vasp_job(calc_dir)
```

```bash
# Requires pre-computed key (from put output or query)
KEY=$(vasp-cache --root /shared/cache put /path/to/calc)
vasp-cache --root /shared/cache fetch "$KEY" /path/to/output
```

## File contract

`fetch(key, dir)` creates:

| File | Fidelity | Notes |
|------|----------|-------|
| OUTCAR | Byte-identical | vasp-sop `check_converged`, pymatgen `Outcar()` |
| vasprun.xml | Byte-identical | pymatgen `Vasprun()` |
| CONTCAR | Byte-identical | `Structure.from_file()` |
| POSCAR | Semantic | No velocity columns, no comments |
| INCAR | Semantic | No comments, normalized whitespace |
| KPOINTS | Semantic | From canonical dict |
| POTCAR | TITEL stub | Identity placeholder — not usable for VASP |

## Consumer verification

Verified against a real CsEuCl3 unitcell calculation after `fetch()`:

| Tool | Interface | Result |
|------|-----------|--------|
| vasp-sop | `check_converged(dir)` | ✅ |
| vasp-sop | `check_task_complete(dir)` | ✅ |
| crisp | `check_task_complete(dir)` | ✅ |
| pydefect | `pydefect_vasp mce -d dir` | ✅ |
| pydefect | `pydefect_vasp cr -d dir` | ✅ |

## Shared cache (NFS)

```bash
vasp-cache --root /mnt/shared/vasp_cache put /path/to/calc
```

SQLite supports concurrent readers; concurrent writes are serialized
by SQLite's built-in locking.

## Dependencies

```toml
dependencies = ["vasp-cache>=0.3.0"]
```

vasp-cache requires `pymatgen>=2023.0` (installed automatically).
