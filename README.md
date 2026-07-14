# vasp-cache

Black-box VASP calculation cache: **same inputs → restore outputs without re-running VASP**.

Backend: [signac](https://signac.readthedocs.io/). Hard identity is a tunable **Mapping Profile** → `content_hash`. Payload is original files in the job workspace.

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
```

## Cache root

Default: `~/.vasp_cache`  
Override: `VASP_CACHE_ROOT` or `override_cache_root(path)`.

## Mapping profile

Default: package `mapping.default.yaml` (legacy-compatible critical INCAR keys + `key_generation`).

User overlay: `~/.vasp_cache/mapping.yaml` or `VASP_CACHE_MAPPING`.

- Soft weights change nearness only.
- Critical edits require bumping `key_generation`.

## Design

See `docs/superpowers/specs/2026-07-14-vasp-cache-signac-design.md`.

## License

MIT
