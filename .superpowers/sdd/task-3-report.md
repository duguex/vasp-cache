# Task 3 report: CLI and packaging

## Status

Implemented the `vasp-cache web` CLI entry point for the approved read-only LAN Materials Atlas dashboard and packaged its fixed web assets in wheels and source distributions.

## Implementation

- Added `web` subcommand options:
  - `--root` (defaults to `paths.cache_root()`, preserving `VASP_CACHE_ROOT` behavior)
  - `--host` (defaults to `localhost`)
  - `--port` (defaults to `8765`)
- Wired the command to `vasp_cache.web_server.serve(cache_root=..., host=..., port=...)`.
- Added an explicit stderr warning for non-loopback hosts while leaving the server read-only.
- Excluded `web` from logging setup so absent-root startup does not create cache/log directories.
- Added package-data patterns for `web/*.html`, `web/*.js`, and `web/*.css`.
- Documented the dashboard command, defaults, read-only scope, and LAN warning in `README.md` and `docs/USER.md`.
- Added focused CLI side-effect/warning tests and a packaging declaration test before implementation.

## Verification

Failing-first tests:

```text
PYTHONPATH=src python3 -m pytest tests/test_cli.py -k 'web' -q
FAILED before implementation: web command/module path was not available.
PYTHONPATH=src python3 -m pytest tests/test_packaging.py -q
FAILED before implementation: web assets were not declared in package-data.
```

Focused tests after implementation:

```text
PYTHONPATH=src python3 -m pytest tests/test_cli.py -k 'web' tests/test_packaging.py tests/test_web_server.py -q
13 passed, 13 deselected, 9 warnings
```

The warnings are existing third-party `emmet` deprecation warnings.

Packaging smoke:

```text
python3 -m build --wheel --sdist --outdir /tmp/vasp-cache-task3-dist
SUCCESS
wheel asset inspection: wheel-assets-ok
```

CLI smoke:

```text
PYTHONPATH=src python3 -m vasp_cache.cli --help
PYTHONPATH=src python3 -m vasp_cache.cli web --help
SUCCESS; absent configured root remained absent
```

A real web CLI process was started with an absent root and port `0`, verified not to create that root, then stopped cleanly.

## Concerns

- `web_server.serve()` intentionally blocks until interrupted; the CLI returns only after server shutdown.
- Non-loopback binding is warned but not prohibited, as required for explicit LAN use.
- `python -m build` emits an existing setuptools license-table deprecation warning; asset inclusion succeeds.
