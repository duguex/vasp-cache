# Repository Guidelines

## Project Overview

vasp-cache is a black-box VASP calculation cache. Same inputs → restore outputs
without re-running VASP. Single SQLite file (`index.sqlite`) with zlib-compressed
BLOBs. 5-layer SHA-256 identity (formula, incar, kpoints, potcar, lattice).

## Architecture & Data Flow

```
CLI (argparse)  →  api.py (public facade)  →  index.py (SQLite engine)
                     ↑
                __init__.py
                (re-exports)

Data flow:
  put(dir) → identity_for_directory(dir) → 5-layer hash
           → pymatgen Outcar/Vasprun extraction → structured columns
           → read_bytes + zlib.compress → BLOB columns
           → should_replace() collision check → INSERT ON CONFLICT DO UPDATE or discard

  fetch(key, dir) → SELECT BLOBs + JSON columns
                  → zlib.decompress → OUTCAR/vasprun/CONTCAR byte-identical
                  → semantic reconstruction → POSCAR/INCAR/KPOINTS
                  → TITEL stub → POTCAR
```

Module dependency: `cli` → `api` → `index` → `paths`, `errors`.
`outcar.py` and `vasprun_ast.py` are standalone utilities, not imported by `index.py`.

## Key Directories

```
src/vasp_cache/       # Package source (7 modules + web/)
  index.py            # Core: SQLite schema, identity, put/fetch/rebuild, collision
  api.py              # Thin public wrapper over index.py
  cli.py              # argparse CLI (vasp-cache command)
  outcar.py           # OUTCAR parser (pymatgen Outcar + regex forces)
  vasprun_ast.py      # vasprun.xml ET AST roundtrip (comments/PI preserving)
  paths.py            # Cache root resolution (override → env → default)
  errors.py           # IdentityInputError, CacheConflictError, ProvenanceConflictError
  web/                # Static dashboard assets (HTML/JS/CSS)
tests/                # pytest (5 test modules + conftest.py, 27 tests)
  conftest.py         # Shared fixtures, minimal VASP input builders
  test_fresh_index.py # API: identity, put/fetch/query, collision, rebuild
  test_fresh_cli.py   # CLI: rebuild, query via argparse main()
  test_consumers.py   # Consumer verification: pymatgen + vasp-sop
  test_paths.py       # Cache root resolution
  test_packaging.py   # Wheel package-data check
docs/                 # User + integration + spec docs
scripts/              # Utility scripts (some stale post-v3 migration, removed per #25 — see below)
```

## Development Commands

```bash
pip install -e ".[dev]"          # editable install
pytest                           # 27 tests
python -m build --wheel          # → dist/vasp_cache-0.3.0-py3-none-any.whl
```

## Code Conventions

- **Naming**: `snake_case` functions, `PascalCase` classes, `UPPER_CASE` module constants
- **Typing**: `from __future__ import annotations`; `Path | str`, `dict[str, Any]`
- **Error handling**: `IdentityInputError` for admission failures. Extraction failures return `None`. Schema creation is idempotent.
- **Imports**: pymatgen imports are lazy (inside functions), not module top level
- **POTCAR**: identity-only (`species + XC + version`); fetch writes TITEL stub
- **Compression**: zlib level 6, ~92% reduction
- **BLOBs**: OUTCAR/vasprun/CONTCAR as zlib bytes; byte-identical on fetch
- **Semantic files**: POSCAR/INCAR/KPOINTS reconstructed from JSON; no comments/formatting preserved
- **Collision**: converged > unconverged; representative never replaced by equal candidate. `discarded_candidates` audit table

## Important Files

| File | Role |
|------|------|
| `pyproject.toml` | Build (setuptools), deps (pymatgen≥2023.0), entry point `vasp-cache`, v0.3.0 |
| `src/vasp_cache/__init__.py` | Re-exports: put, has, fetch, query, rebuild, stats, get_meta, list_entries, IdentityInputError, override_cache_root, Identity, identity_for_directory |
| `src/vasp_cache/identity.py` | 5-layer identity: Identity dataclass, normalize_*, identity_for_directory |
| `src/vasp_cache/extraction.py` | OUTCAR/vasprun structured extraction via pymatgen |
| `src/vasp_cache/index.py` | Storage engine: schema, put/fetch/rebuild, query, collision |
| `src/vasp_cache/cli.py` | CLI: `vasp-cache {rebuild,put,has,fetch,query,status}` |
| `tests/conftest.py` | Shared fixtures: `cache_root`, `write_minimal_inputs`, `write_complete_calc` |
| `docs/superpowers/specs/2026-07-18-v3-layered-identity.md` | Authoritative v3 design spec |
| `docs/USER.md` | Full user guide |
| `docs/INTEGRATION.md` | Integration guide for crisp/vasp-sop/pydefect |

## Runtime/Tooling

- **Python**: ≥ 3.10
- **Build**: setuptools ≥ 64
- **Runtime dep**: pymatgen ≥ 2023.0
- **Dev dep**: pytest ≥ 7.0
- **Package manager**: pip
- **No linter/formatter/type checker configured**

## Testing & QA

- **Framework**: pytest
- **Fixture isolation**: `cache_root` fixture provides temp directory via `monkeypatch`
- **Mocking**: `monkeypatch.setattr` for collision tests to control `_extract_vasprun`
- **Test data**: synthetic Si POSCAR/INCAR/KPOINTS/POTCAR in tests; consumer tests use real CsEuCl3 on NFS
- **48 tests**: identity/put/fetch/query/rebuild/collision/concurrent/overwrite/lattice + CLI + schema + #26/#29 regression
- **No CI configured**

## Stale Scripts (post-v3 migration)

These import deleted modules and will fail:

- `scripts/audit_cache.py` — `vasp_cache.health`
- `scripts/audit_manifests.py` — `vasp_cache.meta`
- `scripts/rehash_meta_cas.py` — `vasp_cache.meta`, `vasp_cache.cas`
- `scripts/migrate_signac_to_cas.py` — `vasp_cache.cas`, `vasp_cache.meta`
- `scripts/verify_real_calcs.py` — `vasp_cache.mapping`
- `scripts/browser_smoke.py` — `vasp_cache.web_server`
