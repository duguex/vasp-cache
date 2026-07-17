# Cache Inspection and Transparency Design

## Status

Approved design for the first database-transparency surface.

## Goal

Make the real contents of a vasp-cache instance inspectable without reading
SQLite or CAS internals directly. The first surface is a read-only CLI suitable
for local use and SSH/HPC environments.

The feature must expose both sides of the storage model:

```text
SQLite metadata entry -> logical object name -> CAS digest -> object file
```

It must not silently mutate metadata, CAS objects, or source calculations.

## Scope

### In scope

Add an `inspect` CLI command with these read-only views:

```bash
vasp-cache inspect summary
vasp-cache inspect entries [filters]
vasp-cache inspect entry CONTENT_HASH
vasp-cache inspect objects
```

The first implementation should prioritize:

1. `summary`: database counts, provenance/convergence distribution, CAS object
   count and byte totals, and referenced-versus-unreferenced storage totals.
2. `entries`: paginated metadata rows using existing query filters and stable
   table/JSON output.
3. `entry`: complete metadata for one content hash plus every logical object,
   digest, byte size, and existence state.
4. `objects`: CAS inventory with digest, size, reference count, and orphan
   status.

All views support machine-readable JSON. Collection views should also support
JSONL where streaming is useful. Human-readable tables are the default.

### Explicitly out of scope

- Web server or browser UI.
- Automatic repair or deletion.
- CAS garbage collection; that belongs to a later explicit `gc` command.
- Full OUTCAR text search or embedding-based similarity search.
- Re-parsing every output on every inspection request.
- Treating an inspect report as a materials-property truth database.

## User-facing behavior

### Summary

`inspect summary` reports:

- entry count;
- distinct formula count;
- provenance counts;
- converged and energy-present counts;
- distinct key generations and profile IDs represented in the database;
- total CAS object count and bytes;
- referenced object count and bytes;
- orphan object count and bytes.

Missing cache roots and empty caches are valid states and produce zero-valued
reports rather than tracebacks. Inspection must not create a cache directory or
SQLite database merely to display an absent cache.

### Entries

`inspect entries` reuses current metadata filters wherever possible:

- formula;
- functional/tags;
- bandgap and energy bounds;
- lattice bound;
- convergence;
- provenance;
- limit and offset.

Rows include at least:

- content hash;
- formula;
- total energy;
- bandgap;
- convergence;
- provenance;
- atom count;
- object count;
- cached timestamp.

Default ordering is newest first, matching the existing metadata query. JSON
output must preserve complete row values rather than the abbreviated table hash.

### Entry detail

`inspect entry CONTENT_HASH` prints the complete metadata row and a normalized
object report. Each object report contains:

- logical name (`OUTCAR`, `CONTCAR`, `POSCAR`, etc.);
- SHA-256 digest;
- byte size when present;
- CAS path or a stable relative object location;
- `present` boolean.

A missing metadata row exits nonzero and reports the requested hash clearly.
A missing CAS object is reported as data-health information, not hidden.

### CAS objects

`inspect objects` lists each object known under the CAS root, including:

- digest;
- byte size;
- number of metadata references;
- referenced logical names when bounded output is requested;
- orphan boolean.

`--orphans-only` restricts the collection to objects with zero metadata
references. The command is read-only. It must never remove an orphan or rewrite
a row.

## Architecture

Keep rendering separate from data collection:

```text
inspection service/helpers
  ├── collect summary from SQLite + CAS
  ├── collect entry metadata and object status
  ├── collect CAS reference inventory
  └── render table / JSON / JSONL
       ▲
       │
     CLI parser
```

The inspection layer should call existing `meta`, `cas`, and API query helpers
rather than opening SQLite schema details from the CLI. CAS reference counting
may use a focused metadata-layer helper because it requires scanning all object
maps. The helper must return structured dictionaries so table and JSON output
share exactly the same data.

No long-lived process, cache daemon, or new storage backend is introduced.

- Inspection is read-only and must not change `cached_at` or metadata rows.
- Inspection must not create a missing cache root or database as a side effect.
- CAS object existence checks must use the existing validated digest/path logic.
- Summary and object inventory may scan the CAS once per invocation.
- Entry listing must remain bounded by `limit` and `offset`.
- Entry detail must not read full blob contents; stat/existence checks are enough.
- JSON serialization must handle existing non-JSON-native values consistently,
  using the project’s current `default=str` convention where necessary.
- Orphan classification is observational: an object is orphaned only when no
  metadata object map references its digest at inspection time.

## CLI compatibility

Existing commands remain unchanged. `inspect` is additive and uses the same
cache-root resolution and logging setup as the rest of the CLI.

Proposed examples:

```bash
vasp-cache inspect summary
vasp-cache inspect entries --formula GaN --provenance all --limit 50
vasp-cache inspect entries --jsonl --limit 1000
vasp-cache inspect entry 5:...
vasp-cache inspect objects --orphans-only
```

The exact short option spellings may follow existing CLI conventions, but the
long forms and read-only semantics are part of the contract.

## Testing strategy

Tests must cover observable behavior:

1. Empty-cache summary returns zero counts.
2. Ingested entries appear in summary and entries output.
3. Existing query filters and provenance selection apply to entries.
4. JSON output contains complete, non-abbreviated hashes and metadata.
5. Entry detail reports object digests, sizes, and present/missing state.
6. CAS object inventory counts shared objects once and reports references.
7. An unreferenced CAS object is reported as orphan and remains untouched.
8. Missing content hash exits nonzero with a useful message.
9. Human output remains deterministic enough for CLI smoke tests.

Health auditing, repair, GC, and a web view require separate designs after this
read-only inspection surface is used against real cache data.
