# LAN Materials Atlas Web Dashboard Design

## Status

Approved design for an interactive, read-only LAN dashboard over the existing
VASP cache.

## Goal

Expose the real cache contents through a browser without requiring users to
page through CLI output. The dashboard is a local/LAN observability surface for
researchers, not a write-capable workflow UI or a materials-property truth
service.

## Users and deployment

Primary users are members of a trusted laboratory LAN inspecting a shared VASP
cache over a browser. The first deployment is a single Python process:

```bash
vasp-cache web --root /mnt/shared/vasp_cache --host 0.0.0.0 --port 8765
```

Defaults:

- bind to `127.0.0.1` unless `--host` is explicitly supplied;
- read-only data access;
- no application login or token for the trusted-LAN first version;
- no write, delete, put, rehash, repair, or GC endpoint;
- explicit warning in the UI that the server is unauthenticated and should not
  be exposed beyond a trusted network.

The server must be stoppable with normal process signals and must not spawn a
background daemon implicitly.

## Visual direction

**Materials Atlas:** an editorial research catalog rather than a generic admin
panel.

- warm paper/ivory background;
- ink-black typography;
- cobalt blue for links, selected filters, and primary actions;
- terracotta for warnings and legacy-data signals;
- serif display typography paired with monospace numerical metadata;
- restrained borders, catalog-like labels, and dense but readable tables;
- responsive layout that remains usable on a laptop browser over SSH/LAN.

The memorable element is the transition from a high-level “atlas” summary to a
calculation-family detail drawer: a formula family is a browsable research
object, while each calculation remains an auditable identity/CAS record.

## Scope

### In scope

1. A Python HTTP server with a static frontend.
2. Fast SQLite-only overview data.
3. Interactive, server-side-filtered entry search.
4. Entry detail drawer/page with identity and CAS object facts.
5. Read-only object and orphan views based on existing collectors.
6. URL-persisted filter state and manual refresh.
7. JSON API tests and browser smoke tests.

### Out of scope

- user accounts, passwords, SSO, or multi-tenant isolation;
- mutations of any kind;
- full OUTCAR/vasprun content rendering;
- data-quality audit implementation from issue 0022;
- automatic CAS scanning on every page load;
- charting that implies physical validity or ranking beyond stored metadata;
- React/Vite/Node build tooling or a new runtime dependency.

## Backend architecture

Use Python's standard-library `ThreadingHTTPServer` and a small request handler.
Static assets and API routes share the same process:

```text
Browser
  ├── GET /                    static Materials Atlas shell
  ├── GET /assets/*            static CSS/JS
  ├── GET /api/overview        inspection.overview()
  ├── GET /api/entries         inspection.entries(filters)
  ├── GET /api/entry/<hash>    inspection.entry(hash)
  └── GET /api/objects         inspection.objects(orphans_only)
```

The handler must:

- resolve one configured cache root at startup;
- call existing read-only inspection collectors;
- return JSON with `Content-Type: application/json; charset=utf-8`;
- reject unsupported methods with `405`;
- return `404` for unknown routes or missing entries;
- return structured `400` errors for invalid filter values;
- never call write-capable metadata connections;
- never serve arbitrary filesystem paths or source directories.

`/api/overview` is SQLite-only and must return `storage_scan: false`. CAS
object size/orphan scans are explicit through the objects view and must not run
on initial dashboard load.

### API contracts

`GET /api/overview?top_formulas=20`

Returns the structured result of `inspection.overview()` including:

```json
{
  "entries": 106348,
  "formulas": 9416,
  "with_energy": 104921,
  "with_bandgap": 0,
  "converged": 106348,
  "provenance": {"unknown": 106348},
  "key_generations": {"4": 106146},
  "profile_ids": {"default": 106348},
  "top_formulas": [{"formula": "C214N", "entries": 46367}],
  "storage_scan": false
}
```

`GET /api/entries`

Accepts existing metadata filters: `formula`, `functional`, `tags`,
`bandgap_min`, `lattice_max`, `min_energy`, `max_energy`, `converged_only`,
`provenance`, `limit`, and `offset`. Defaults to canonical provenance,
newest-first ordering, and bounded page size. Returns:

```json
{"rows": [...], "limit": 50, "offset": 0, "has_more": true}
```

`GET /api/entry/<content_hash>` returns the complete normalized entry detail
already defined by the CLI collector, including logical object name, digest,
size, presence, and stable CAS-relative location.

`GET /api/objects?orphans_only=true` returns the existing normalized object
records. This is an explicit, potentially slower request and must be labeled as
such in the UI.

## Frontend behavior

### Initial view

The first screen contains:

1. a masthead with `VASP CACHE / MATERIALS ATLAS`, read-only badge, current
   cache root label, and refresh timestamp;
2. a summary rail with entries, formulas, energy coverage, convergence coverage,
   and legacy generation/provenance warnings;
3. a “formula families” section using top-formula data;
4. a searchable catalog table with server-side pagination;
5. a compact status note: “Storage scan not included in overview.”

No CAS scan is triggered during initial render.

### Search and filters

- Formula search is the primary field and supports exact/substring behavior
  matching the API contract.
- First-version filters are formula, functional/tags, bandgap, lattice,
  energy, convergence, and provenance. Task name and content hash remain
  detail-only fields; content hashes are opened through the detail route.
- Filters update after a short debounce and reset offset to zero.
- The current filter state is encoded in the URL query string.
- Empty results show the active filters and a clear-filters action.
- Loading, error, and stale-data states are explicit; no silent empty fallback.

### Entry detail

Clicking a row opens a right-side drawer on wide screens and a full-screen panel
on narrow screens. It shows:

- formula, task name, energy, convergence, nsites, lattice maximum;
- content hash, key generation, profile ID, mapping digest;
- provenance and provenance source;
- source directory as text only, never a clickable filesystem link;
- CAS object list with digest, byte size, present/missing status;
- a copy-to-clipboard action for content hash and source path.

### Data-quality signals

The first version shows factual signals only:

- `legacy generation detected` when generation 2/4 rows are present;
- `provenance coverage incomplete` when unknown/legacy rows are present;
- `bandgap unavailable` when the overview count is zero;
- `storage scan not run` when `storage_scan` is false.

It must not label energy values as invalid or claim CAS health until issue 0022
is implemented.

## Static assets and packaging

Place web assets under a package-owned directory such as:

```text
src/vasp_cache/web/
  index.html
  app.js
  styles.css
```

Update package data configuration so installed distributions include the assets.
The frontend uses no external CDN, remote font, or network asset; LAN use must
work in an isolated environment.

## Testing and verification

### Backend tests

- overview endpoint returns quickly and does not invoke CAS collectors;
- entries endpoint applies formula/provenance/energy filters and pagination;
- entry endpoint returns normalized object facts and 404 for missing hashes;
- objects endpoint passes orphan filtering and remains read-only;
- unsupported methods/routes return correct status codes;
- invalid query parameters return structured 400 responses;
- server binds localhost by default and accepts explicit LAN host/port;
- no API route creates a missing cache root or SQLite database.

### Browser tests

Use Playwright against a temporary cache root and local server:

1. overview loads summary cards and top formula families;
2. entering a formula and applying a filter updates the table;
3. pagination changes rows without a full page reload;
4. clicking a row opens detail and shows CAS object status;
5. empty results and API errors render visible states;
6. refresh preserves or intentionally resets URL filters according to the
   documented behavior;
7. browser cannot trigger a write endpoint because none exists.

## Acceptance

The feature is complete when a researcher can start the server on a trusted LAN,
open the dashboard, see the full-cache aggregate within a short interval,
search/filter the 100k+ entry catalog interactively, open a complete calculation
record, and understand which facts are metadata-only versus CAS-scanned—without
any mutation or hidden filesystem exposure.
