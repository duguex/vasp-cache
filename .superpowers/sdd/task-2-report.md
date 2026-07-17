# Task 2 report: Materials Atlas frontend

## Status

Implemented the Task 2 dashboard slice in the web-dashboard worktree. The page is a vanilla HTML/CSS/JavaScript, read-only catalog over the Task 1 routes, with no CDN, remote font, Node, React, or runtime dependency.

## Implementation

- Added `src/vasp_cache/web/index.html` with an accessible masthead, read-only and unauthenticated-LAN badges, overview rail, formula family index, filter form, semantic catalog table, pagination, loading/error/empty regions, and keyboard-dismissible detail drawer.
- Added `src/vasp_cache/web/app.js` with:
  - `/api/overview` and `/api/entries` initial loading;
  - debounced formula, functional, tags, bandgap, lattice, energy, convergence, and provenance filters;
  - URLSearchParams filter/offset state and offset reset on filter changes;
  - server `has_more` pagination without navigation;
  - normalized entry detail loading;
  - keyboard/focus-safe drawer behavior and Escape/close controls;
  - Clipboard API plus visible textarea fallback for content hash/source path;
  - explicit, opt-in `/api/objects` storage scan labeled as potentially slower;
  - factual generation, provenance, bandgap, and storage-scan warnings;
  - escaped text rendering only, with no raw output blob display.
- Added `src/vasp_cache/web/styles.css` with the Materials Atlas visual system: ivory paper, ink, cobalt, terracotta, restrained rules, serif display typography, monospace metadata, responsive table/drawer behavior, visible focus states, and reduced-motion support.
- Extended `tests/test_web_server.py` with failing-first static assertions for dashboard content and JavaScript/CSS MIME types.

## Verification

Red test before assets:

```text
PYTHONPATH=src pytest tests/test_web_server.py::test_static_assets_have_dashboard_content_and_mime_types -q
FAILED: HTTP Error 404 at /
```

Focused backend/static tests after implementation:

```text
PYTHONPATH=src pytest tests/test_web_server.py -q
11 passed, 9 warnings
```

Warnings are existing third-party `emmet` deprecation warnings.

Browser smoke against a temporary seeded cache and local server (`127.0.0.1:8876`):

- Desktop: summary metrics rendered (`27` entries), formula family rendered, and `25` catalog rows loaded.
- Formula filter: `NoSuchFormula` produced `0` rows and a visible empty state; URL became `?formula=NoSuchFormula&provenance=canonical`; restoring `Si` repopulated rows.
- Pagination: next page changed the URL offset to `25`, changed rows, and kept the same document route.
- Detail: clicking a row opened the drawer with identity, source text, and stored object statuses.
- Narrow viewport (`390px`): document scroll width stayed `390px`; drawer occupied the viewport width and opened.
- Browser fetch paths are all GET-only (`/api/overview`, `/api/entries`, `/api/entry/<hash>`, and opt-in `/api/objects`); no write route is present or called.

Additional verification:

```text
python -m py_compile src/vasp_cache/web_server.py
SUCCESS

git diff --check
SUCCESS
```

## Concerns

- The requested browser smoke was exercised with the available browser tool rather than committed as a separate Playwright dependency/test file, preserving the no-new-runtime-dependency constraint.
- The current Task 1 static route/package-data setup serves these source-tree assets. Packaging inclusion remains part of Task 3 as specified by the implementation plan.
