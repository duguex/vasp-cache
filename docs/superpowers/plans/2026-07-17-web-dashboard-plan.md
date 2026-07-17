# LAN Materials Atlas Web Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an interactive, read-only LAN web dashboard for browsing the VASP cache through a Materials Atlas interface.

**Architecture:** Add a standard-library `ThreadingHTTPServer` with fixed static assets and four JSON API route families backed only by read-only inspection collectors. Add a `vasp-cache web` CLI command with safe localhost defaults and explicit LAN binding. Use vanilla HTML/CSS/JavaScript with no new runtime dependency or external asset.

**Tech Stack:** Python 3.10+, `http.server`, `urllib.parse`, SQLite read-only inspection collectors, static HTML/CSS/JavaScript, pytest, browser smoke testing.

## Global Constraints

- The web server is read-only: no put, delete, rehash, repair, or GC endpoint exists.
- Default bind host is `127.0.0.1`; LAN access requires explicit `--host 0.0.0.0` or another supplied host.
- No authentication is included in the trusted-LAN first version; the UI visibly warns that the service is unauthenticated.
- API handlers must use existing read-only inspection collectors and never write or migrate SQLite.
- The server must never expose arbitrary filesystem paths or raw source files.
- Initial page load uses SQLite-only `overview`; it must not scan CAS.
- `summary`/`objects` CAS scans are explicit and labeled as slower operations.
- Frontend visual direction is Materials Atlas: warm paper/ivory, ink text, cobalt interactions, terracotta warnings, serif display typography, monospace numerical metadata.
- No React, Vite, Node, CDN, remote font, or new runtime dependency.
- New behavior follows TDD: each production contract has a failing test before implementation.
- Existing CLI commands and inspection collectors retain their current behavior.

---

## Task 1: Implement read-only HTTP API and static asset serving

**Files:**
- Create: `src/vasp_cache/web_server.py`
- Test: `tests/test_web_server.py`

**Interfaces:**
- Consumes: `vasp_cache.inspection.overview`, `entries`, `entry`, and `objects`.
- Produces:
  - `create_server(cache_root: Path, host: str, port: int) -> ThreadingHTTPServer`
  - `serve(cache_root: Path, host: str = "127.0.0.1", port: int = 8765) -> None`
  - `GET /api/overview?top_formulas=N`
  - `GET /api/entries` with existing filters and `limit`/`offset`
  - `GET /api/entry/<content_hash>`
  - `GET /api/objects?orphans_only=true`
  - fixed static routes `/`, `/app.js`, `/styles.css`

### Step 1: Write failing API tests

Create tests using a temporary cache root and an ephemeral server port. Start
`create_server()` in a test thread and make requests with `urllib.request`.
Cover these behaviors before implementing:

```python
def test_overview_api_returns_sqlite_only_payload(cache_root, tmp_path):
    _reset_project()
    put(write_complete_calc(tmp_path / "calc"), provenance="canonical")
    response = request_json(server_url + "/api/overview?top_formulas=5")
    assert response["entries"] == 1
    assert response["storage_scan"] is False


def test_entries_api_filters_and_paginates(cache_root, tmp_path):
    _reset_project()
    put(write_complete_calc(tmp_path / "first"), provenance="canonical")
    second = write_complete_calc(tmp_path / "second", energy="-4.0")
    (second / "INCAR").write_text((second / "INCAR").read_text() + "\nENCUT=400\n")
    put(second, provenance="sampled")
    response = request_json(
        server_url + "/api/entries?provenance=all&limit=1&offset=1"
    )
    assert len(response["rows"]) == 1
    assert response["limit"] == 1
    assert response["offset"] == 1
    assert isinstance(response["has_more"], bool)


def test_entry_api_returns_detail_and_missing_hash_is_404(cache_root, tmp_path):
    _reset_project()
    content_hash = put(write_complete_calc(tmp_path / "calc"))
    detail = request_json(server_url + "/api/entry/" + quote(content_hash))
    assert detail["content_hash"] == content_hash
    assert "OUTCAR" in detail["objects"]
    assert request_status(server_url + "/api/entry/missing") == 404


def test_unsupported_method_and_route_are_rejected(cache_root):
    assert request_status(server_url + "/missing") == 404
    assert request_status(server_url + "/api/overview", method="POST") == 405
```

Also test invalid numeric/filter query values return `400` JSON with an `error`
field, the absent cache root is not created, and `/etc/passwd` or another
arbitrary path is never served.

### Step 2: Run red API tests

```bash
PYTHONPATH=src pytest tests/test_web_server.py -q
```

Expected: import or missing-route failures because `web_server.py` does not yet
exist.

### Step 3: Implement request parsing and handlers

Implement a fixed route table. Parse query parameters with `urllib.parse`; use
explicit conversion helpers that raise a controlled `400` response for invalid
integers/floats/booleans. Do not pass arbitrary query keys into SQL.

Use a request handler factory carrying the resolved `cache_root`. JSON responses
must set:

```text
Content-Type: application/json; charset=utf-8
Cache-Control: no-store
```

For `/api/entries`, call `inspection.entries()` with the existing filters and
return `has_more = len(rows) == limit` when `limit > 0`. For `/api/entry`, URL
unquote the hash exactly once and return `404` when the collector returns
`None`. For `/api/objects`, parse `orphans_only` strictly from `true/false/1/0`.

Serve only the package-owned static files. Resolve each file from the package
web directory and reject every path not in the fixed route table.

### Step 4: Implement server lifecycle

`create_server()` must return a configured `ThreadingHTTPServer` without starting
it, allowing tests to manage lifecycle. `serve()` calls `serve_forever()` and
closes the server on shutdown. The server must not create a cache root merely by
starting against a missing root.

### Step 5: Run green API tests

```bash
PYTHONPATH=src pytest tests/test_web_server.py -q
```

Expected: all route, error, no-mutation, and static-file tests pass.

### Step 6: Commit the backend slice

```bash
git add src/vasp_cache/web_server.py tests/test_web_server.py
git commit -m "feat: add read-only cache web API"
```

---

## Task 2: Build the Materials Atlas frontend

**Files:**
- Create: `src/vasp_cache/web/index.html`
- Create: `src/vasp_cache/web/app.js`
- Create: `src/vasp_cache/web/styles.css`
- Modify: `src/vasp_cache/web_server.py` if static MIME/route handling needs it
- Test: `tests/test_web_server.py` for static asset responses

**Interfaces:**
- Consumes: Task 1 API routes and JSON shapes.
- Produces: responsive interactive dashboard with overview, filters, catalog,
and detail drawer.

### Step 1: Add failing static and browser smoke checks

Extend API tests to assert `/` contains `MATERIALS ATLAS`, `/app.js` has a
JavaScript content type, and `/styles.css` has a CSS content type. Add a browser
smoke script or test fixture that verifies:

1. summary metrics render;
2. formula filtering changes catalog rows;
3. pagination changes rows without navigation;
4. clicking a row opens a detail drawer;
5. empty results show a visible state;
6. no browser action calls a write route.

Run the static/API tests before creating assets and record the expected failure.

### Step 2: Implement the HTML shell

Create an accessible page with:

- masthead `VASP CACHE / MATERIALS ATLAS`;
- read-only and unauthenticated-LAN warning badges;
- overview metric rail;
- formula-family section;
- filter panel;
- catalog table with semantic table headers;
- detail drawer with close button and keyboard escape handling;
- loading, error, and empty-result states.

Use no external assets. Use real labels from the current cache such as
`entries`, `formulas`, `generation`, `provenance`, and `storage scan`.

### Step 3: Implement client-side state and interactions

In `app.js`:

- fetch `/api/overview` on initial load;
- fetch `/api/entries` with debounced filter changes;
- preserve filters in `URLSearchParams` and reset offset on filter changes;
- render `has_more` pagination controls;
- fetch `/api/entry/<hash>` on row click and render the detail drawer;
- copy content hash/source path using the Clipboard API with visible fallback;
- label object scans as potentially slower and run them only when requested;
- show factual warnings for legacy generations, incomplete provenance, absent
  bandgap, and `storage_scan: false`;
- never infer scientific validity or render raw output blobs.

### Step 4: Implement Materials Atlas visual system

In `styles.css`:

- define CSS variables for ivory, ink, cobalt, terracotta, muted rule, and
  monospace data color;
- use a distinctive serif display face available locally or a safe system
  fallback without remote font loading;
- use monospace for hashes, counts, energies, and paths;
- create catalog labels, fine rules, density-controlled table rows, and a
  responsive right-side drawer;
- ensure visible focus states, sufficient contrast, and keyboard navigation;
- avoid generic dashboard cards, purple gradients, and full-bleed analytics
  decoration.

### Step 5: Run browser/static verification

Use the browser testing tool against a temporary cache root and local server.
Verify the six browser behaviors in Step 1 at desktop and narrow viewport sizes.
Also run:

```bash
PYTHONPATH=src pytest tests/test_web_server.py -q
```

### Step 6: Commit the frontend slice

```bash
git add src/vasp_cache/web src/vasp_cache/web_server.py tests/test_web_server.py
git commit -m "feat: add Materials Atlas dashboard"
```

---

## Task 3: Add CLI command, packaging, and documentation

**Files:**
- Modify: `src/vasp_cache/cli.py`
- Modify: `pyproject.toml`
- Modify: `README.md`
- Modify: `docs/USER.md`
- Modify: `tests/test_cli.py`

**Interfaces:**
- Consumes: `web_server.serve()` from Task 1 and packaged assets from Task 2.
- Produces:

```bash
vasp-cache web
vasp-cache web --root /mnt/shared/vasp_cache
vasp-cache web --host 0.0.0.0 --port 8765
```

### Step 1: Write failing CLI and packaging tests

Add tests that monkeypatch `serve()` and assert parsed defaults:

```python
def test_cli_web_defaults_to_localhost_and_default_port(monkeypatch):
    captured = {}
    monkeypatch.setattr(web_server, "serve", lambda **kwargs: captured.update(kwargs))
    assert main(["web"]) == 0
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 8765
```

Add tests for explicit `--root`, `--host`, and `--port`, and assert `--help`
mentions the unauthenticated trusted-LAN warning. Verify package data includes
`web/index.html`, `web/app.js`, and `web/styles.css` in the built distribution
or package resource lookup.

### Step 2: Run red CLI tests

```bash
PYTHONPATH=src pytest tests/test_cli.py::test_cli_web_defaults_to_localhost_and_default_port -q
```

Expected: argparse rejects the new `web` command before implementation.

### Step 3: Implement CLI and packaging

Add a `web` parser with:

- positional-free command;
- `--root` defaulting to configured `cache_root()`;
- `--host` default `127.0.0.1`;
- `--port` default `8765`;
- concise help text warning that explicit LAN binding is unauthenticated and
  read-only.

Call `serve(root=..., host=..., port=...)`. Add `web/*` to setuptools package
 data. Keep existing logging behavior unchanged for all other commands; web
 startup may use stderr-only logging and must not create cache state before the
 server is serving.

Update README and Chinese user guide with startup, LAN binding, read-only,
filtering, and shutdown instructions. State clearly that no authentication is
provided in the first version.

### Step 4: Run green CLI and packaging checks

```bash
PYTHONPATH=src pytest tests/test_cli.py tests/test_web_server.py -q
python -m compileall -q src tests scripts
```

### Step 5: Commit the integration slice

```bash
git add src/vasp_cache/cli.py pyproject.toml README.md docs/USER.md tests/test_cli.py
git commit -m "feat: expose LAN web dashboard command"
```

---

## Task 4: Full verification and final boundaries

**Files:**
- All implementation, tests, assets, packaging, and docs from Tasks 1–3.

### Step 1: Run focused verification

```bash
PYTHONPATH=src pytest tests/test_web_server.py tests/test_cli.py tests/test_inspection.py -q
```

Expected: all web API, static asset, CLI, overview, and inspection tests pass.

### Step 2: Run the full suite

```bash
PYTHONPATH=src pytest -q
python -m compileall -q src tests scripts
```

Expected: all tests pass; existing dependency deprecation warnings may remain.

### Step 3: Run LAN smoke scenario

Start the server explicitly bound to the LAN interface in a controlled test
network:

```bash
vasp-cache web --root /tmp/vasp-cache-web-smoke --host 127.0.0.1 --port 8765
```

Open the dashboard in a browser and verify overview, filter, pagination, detail,
and visible read-only warning. Stop the process with Ctrl-C and confirm no
metadata or CAS objects changed.

### Step 4: Check documentation and security boundaries

```bash
git diff --check
```

Confirm that:

- default startup is localhost-only;
- explicit LAN warning appears in CLI help and UI;
- no route serves arbitrary filesystem files;
- no write-capable API route exists;
- no remote fonts/CDN are referenced;
- source paths are displayed as text only;
- overview remains CAS-scan-free.

### Step 5: Commit final verification notes

```bash
git add docs/superpowers/specs/2026-07-17-web-dashboard-design.md \
  docs/superpowers/plans/2026-07-17-web-dashboard-plan.md
git commit -m "docs: plan LAN materials atlas dashboard"
```
