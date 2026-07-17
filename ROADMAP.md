# vasp-cache Roadmap

## Current Position

`vasp-cache` is an exact VASP calculation cache, not a general materials-property
truth database. Its primary value is to avoid running the same deterministic
calculation twice and to reuse cache-standard outputs across projects.

Implemented core:

- CAS + SQLite storage;
- geometry-aware generation-5 content identity;
- POSCAR/KPOINTS/normalized-protocol input intent hashing;
- `put`, `has`, `fetch`, `query`, and CLI workflows;
- standard output reuse for `OUTCAR`, `CONTCAR`, and `vasprun.xml`;
- provenance-aware ingest with independent INCAR/OUTCAR metadata parsing;
- canonical-only formula queries by default, with explicit sampled/unknown/all filters;
- duplicate provenance preflight before CAS writes;
- strict/skip/overwrite output conflict modes, with strict preflight before CAS writes;
- optional `result_geom_hash` metadata for CONTCAR;
- collision-safe, inventory-first metadata rehashing;
- metadata query and cache archive support.

A whole-home ingest is an operational data instance, not the acceptance criterion
for the core project. Random one-off perturbation results are not canonical
material results.

### Identity and migration safety

Generation-5 identity and conflict semantics are implemented. Rehashing is
inventory-first; `--apply` rewrites only safe non-colliding groups. Collision
resolution and provenance review remain operational responsibilities before
any cleanup of legacy or sampled data.

See [Issues #2–#6](https://github.com/duguex/vasp-cache/issues) and
[Issue #21](https://github.com/duguex/vasp-cache/issues/21).

### Related-calculation bootstrap (conditional)

This is a planned/partial capability, not current automatic behavior. A changed
INCAR or KPOINTS normally has a different identity, and `fetch()` only restores
standard outputs. It does not generate new INCAR, KPOINTS, or POTCAR inputs.
The workflow must locate or reconstruct the starting structure and create the
new inputs. If implemented, the minimum should be an explicit content-hash/
object export operation for a reference `CONTCAR` or standard output; it must
not silently turn a related calculation into an exact cache hit.

## Later

- incremental ingest, retry, and resume operations;
- CAS garbage collection and storage monitoring;
- batch ingest performance improvements;
- optional large-object compression;
- similarity search after provenance and identity semantics are reliable;
- stronger integration adapters for downstream workflows.

## Not Planned

- job scheduling or queue management;
- automatic VASP input generation;
- automatic structure relaxation;
- formation-energy or other domain-specific physical analysis;
- treating random, unprovenanced perturbation single points as canonical cache
  results;
- making whole `/mnt/shared/home` ingestion a completion requirement.

## Decision Principles

1. Exact reuse before semantic similarity.
2. Provenance before ranking or automatic selection.
3. Preserve valid static and relaxation calculations; do not reject all `NSW=0`
   calculations.
4. Keep sampled data separate from canonical material results.
5. Do not add workflow automation unless it removes a demonstrated repeated cost.
