# vasp-cache Roadmap

## Current Position

`vasp-cache` is an exact VASP calculation cache, not a general materials-property
truth database. Its primary value is to avoid running the same deterministic
calculation twice and to reuse cache-standard outputs across projects.

Implemented core:

- CAS + SQLite storage;
- geometry-aware content identity;
- `put`, `has`, `fetch`, `query`, and CLI workflows;
- standard output reuse for `OUTCAR`, `CONTCAR`, and `vasprun.xml`;
- metadata query and cache archive support.

A whole-home ingest is an operational data instance, not the acceptance criterion
for the core project. Random one-off perturbation results are not canonical
material results.

## Next

### Provenance and query safety

Track calculation role and quality separately from file completion:

- `canonical`, `sampled`, and `unknown` provenance roles;
- effective `NSW`, `IBRION`, and `ISIF` values;
- separate electronic, ionic, and OUTCAR-completion status;
- explicit handling for MD, phonon/finite-displacement, and sampled data;
- prevent formula lookup from selecting the newest sampled or unknown row as the
  representative result.

See [Issue #22](https://github.com/duguex/vasp-cache/issues/22).

### Identity correctness

Harden the identity contract before adding broad semantic search:

- POSCAR/CONTCAR identity policy;
- INCAR hard-key audit;
- POTCAR fingerprint policy;
- geometry-hash precision and structure standardization;
- conflict handling when the same key produces different outputs.

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
