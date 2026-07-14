# vasp-cache Design: signac Backend + Black-Box I/O

> Date: 2026-07-14  
> Status: approved for planning (user decisions locked)  
> Repo: `vasp-cache` (`~/vasp_cache`)

## 1. Goal

Provide a **tool-agnostic VASP calculation cache** such that:

- **Ingest:** given a **complete** VASP calculation directory, store it once.
- **Query (primary):** given **VASP input files**, return **VASP output files** (black box: same as “already ran”).
- **Query (secondary):** list/filter cached entries by lightweight metadata (formula, energy, tags, …).

One sentence: **compute once; later, inputs → outputs without re-running VASP.**

## 2. Locked decisions

| Decision | Choice |
|----------|--------|
| Backend | **signac** (dependency, not reimplemented CAS) |
| Primary I/O | Black box: `put(full calc)` / `fetch(inputs → write outputs)` |
| Storage payload | **Original files** in signac job workspace (not parsed JSON blobs as sole payload) |
| Identity | `content_hash` of inputs (same fingerprint semantics as current `vasp_sop.core.cache._content_hash`) |
| Metadata | signac `job.document` (searchable) |
| Default files stored | `OUTCAR`, `CONTCAR` (or final structure), `vasprun.xml` if present; default also store `INCAR`/`POSCAR`/`KPOINTS` for audit |
| POTCAR | **Not stored by default** (size + license) |
| Large optional files | `WAVECAR` / `CHGCAR` **opt-in only** |
| VASP native HDF5 | Not primary store; may archive `vaspout.h5` if present later |
| Old JSONStore (`meta.json` / `blobs.json` / `~/.vasp_sop` cache) | **Abandoned** — no runtime read fallback, no required migrate path in v1 |
| vasp-sop | Depends on `vasp-cache`; thin adapter for old names |
| MP download cache | Stays in vasp-sop (`MP_CACHE`), not this package |
| Job submission state | Stays in vasp-sop JobStore, not this package |

### 2.1 Explicit non-goals (v1)

- Job scheduling / “submitted” tracking  
- Formation-energy analysis  
- INCAR generation  
- NFS multi-writer strong consistency guarantees  
- Changing `content_hash` formula  
- Compatibility layer for legacy maggma JSONStore cache  

## 3. Survey summary (why this shape)

| System | Pattern | Relevance |
|--------|---------|-----------|
| **signac** | statepoint hash → job directory of files + job document | Closest black-box model; chosen backend |
| **AiiDA** | repository stores raw files; dump restores inputs/outputs | Validates file-first payload; too heavy as dependency |
| **FireWorks FilePad** | file bytes + metadata index | Same two-layer idea |
| **atomate / emmet TaskDoc** | parsed Mongo documents | Good for property query; weak as OUTCAR black box |
| **VASP `vaspout.h5`** | per-run optional output | Cannot unify historical OUTCAR-only calcs |

Implication: primary path must be **files addressed by input identity**; parsed fields are secondary index material only.

## 4. Architecture

```
                    ┌──────────────────────────────────────┐
  complete calc ──► │ put()                                │
                    │  content_hash(inputs)                │
                    │  signac open_job({content_hash}).init│
                    │  copy outputs (+ optional inputs)    │
                    │  write job.doc summary               │
                    └──────────────────────────────────────┘

  input-only dir ──► │ has() / fetch()                      │
                    │  content_hash(inputs)                │
                    │  open_job → if workspace has OUTCAR  │
                    │  fetch: copy outputs into dir        │
                    └──────────────────────────────────────┘

  filters ─────────► │ query() via project.find_jobs(doc.*) │
                    └──────────────────────────────────────┘
```

Package layout (implementation target):

```
vasp_cache/
  __init__.py      # public API re-exports
  paths.py         # CACHE_ROOT, override_cache_root, get_project()
  fingerprint.py   # content_hash, incar/potcar fingerprints
  parse.py         # optional summary extraction (TaskDoc + regex)
  api.py           # put, has, fetch, get_meta, query, list_entries, stats
  cli.py           # vasp-cache CLI
```

Dependency direction: **vasp-sop → vasp-cache → signac / pymatgen / emmet-core**.  
vasp-cache must **not** import vasp_sop.

## 5. I/O contracts

### 5.1 Complete calculation directory (put input)

Minimum expected:

```
calc_dir/
  INCAR
  POSCAR or CONTCAR
  KPOINTS
  POTCAR          # used for fingerprint only; not stored by default
  OUTCAR          # required for successful put
  CONTCAR         # preferred final structure
  vasprun.xml     # optional
```

### 5.2 Input directory (has / fetch input)

Enough to compute the same `content_hash` as put-time inputs:

```
input_dir/
  INCAR, POSCAR|CONTCAR, KPOINTS, POTCAR
  # OUTCAR may be absent
```

### 5.3 fetch output (side effect on disk)

On success, `input_dir` contains at least:

- `OUTCAR`
- `CONTCAR` (if present in the job workspace)

and `vasprun.xml` if it was stored.

Return: `True` if OUTCAR was written (or already present from cache copy); `False` if no cache hit.

### 5.4 put return

- Success: `content_hash: str`
- Skip (not a usable converged/energy result): `None`
- Hard errors (unreadable path, etc.): raise

Idempotent: putting the same hash again updates/refreshes files and doc (or no-ops if already complete — implementer chooses one; tests must lock behavior). **Recommended:** overwrite outputs + refresh doc (last writer wins).

## 6. signac data model

### 6.1 Project root

- Default: `Path.home() / ".vasp_cache"`
- Override: env `VASP_CACHE_ROOT` or `override_cache_root(path)`
- On first use: `signac.init_project(root=...)` if not already a project

### 6.2 State point (identity only)

```python
{"content_hash": "<string>"}
```

Rationale: preserves existing uniqueness semantics; avoids accidental job split if derived fields disagree.

### 6.3 Job workspace files

| File | Default |
|------|---------|
| `OUTCAR` | store |
| `CONTCAR` | store (from CONTCAR, else POSCAR final structure if needed) |
| `vasprun.xml` | store if exists |
| `INCAR`, `POSCAR`, `KPOINTS` | store if exist (`store_inputs=True` default) |
| `POTCAR` | **off** by default |
| `WAVECAR`, `CHGCAR`, … | off; future `include=` patterns |

### 6.4 Job document (search index)

```python
{
  "formula": str,
  "task_name": str,
  "total_energy": float | None,
  "bandgap": float | None,
  "converged": bool | 0 | 1,
  "calc_type": str | None,
  "nsites": int | None,
  "formula_pretty": str | None,
  "space_group": str | None,
  "a": float, "b": float, "c": float, "max_abc": float,
  "tags": str,              # comma-separated
  "source_dir": str,        # absolute path at put time (informational only)
  "parsed_by": str,         # TaskDoc | regex | fallback
  "cached_at": float,       # unix time
}
```

Secondary query uses signac namespaces, e.g.:

```python
project.find_jobs({
  "doc.formula": "GaN",
  "doc.bandgap": {"$gte": 2.0},
  "doc.converged": True,
})
```

Public `query()` maps familiar kwargs (`formula`, `functional`→tags regex, `bandgap_min`, …) onto `find_jobs` filters.

## 7. Fingerprint (`content_hash`)

Port from `vasp_sop.core.cache` without semantic change:

```
content_hash = structure_tag + "_" + kpoints_tag + "_" + incar_fp + "_" + potcar_fp
```

- structure: CONTCAR/POSCAR composition formula (spaces removed)  
- kpoints: grid string / `gamma` / `band-structure` / `nokpt`  
- incar keys: ENCUT, PREC, ISMEAR, SIGMA, ISIF, LDAU*, GGA, IVDW, LASPH, METAGGA  
- potcar: species token list from POTCAR  

Public: `content_hash(path) -> str`.

## 8. Summary parsing

Used only to fill `job.doc` (not as primary payload).

1. Prefer `TaskDoc.from_directory` when available  
2. Fallback: OUTCAR regex energy + convergence marker + pymatgen structure  
3. **Must not** import `vasp_sop`

Skip put when no usable energy and not converged (same intent as current cache).

`MAX_LATTICE` / lattice filter: **optional**, configurable; default can match 25.0 Å skip for oversized cells, or leave disabled in pure cache package — **v1 default: keep 25.0 skip with override**, so sop behavior does not regress.

## 9. Public Python API

```python
from vasp_cache import (
    put,
    has,
    fetch,
    get_meta,
    query,
    list_entries,
    stats,
    content_hash,
    override_cache_root,
)
```

### 9.1 vasp-sop adapter

`vasp_sop.core.cache` becomes thin:

| Legacy name | Forwards to |
|-------------|-------------|
| `vasp_results_put` | `put` |
| `vasp_results_get` | `get_meta` by formula/key (see below) |
| `cache_lookup` | `get_meta` if has else None (or has-only where only boolean needed) |
| `restore_from_cache` | `fetch` |
| `query` | `query` |
| `list_cache` | `list_entries` |
| `cache_stats` | `stats` |
| `override_cache_root` | same |
| `MP_CACHE` / `POSCAR_CACHE` | remain local Path constants under sop paths |

`vasp_results_get(formula, key)` compatibility: scan jobs with `doc.formula` and match `content_hash` / `task_name` / `{formula}_mp-{key}` — implemented in adapter or as `get_meta` helpers in vasp-cache.

## 10. CLI

Entry point: `vasp-cache`

```
vasp-cache put <dir>
vasp-cache put -r <root>          # recursive: find converged calc dirs
vasp-cache fetch <dir>
vasp-cache has <dir>
vasp-cache query --formula GaN [--functional HSE] ...
vasp-cache status
vasp-cache content-hash <dir>
```

No `migrate-jsonstore` in v1 (old version abandoned). Operators who need history re-`put` from original calculation directories.

## 11. Configuration

| Mechanism | Effect |
|-----------|--------|
| `VASP_CACHE_ROOT` | project root |
| `override_cache_root(path)` | tests / temporary roots |
| `put(..., store_inputs=True)` | toggle input file archival |
| `put(..., include=())` | extra filenames to copy |
| env or const `MAX_LATTICE` | skip huge cells (default 25.0, `None` disables) |

## 12. Testing strategy

| Area | Cases |
|------|-------|
| fingerprint | stable hash; kpoints/incar/potcar change flips hash |
| put/fetch roundtrip | temp dirs; fetch restores OUTCAR bytes |
| idempotent put | second put same hash succeeds |
| has false | missing job |
| query | formula / bandgap filters on doc |
| override_cache_root | isolation |
| no vasp_sop import | package import graph |
| CLI smoke | put + fetch + status |

Fixtures: minimal fake OUTCAR/INCAR/POSCAR/KPOINTS/POTCAR text files (no real VASP binary).

## 13. Migration / cutover for vasp-sop

1. Publish/install editable `vasp-cache`  
2. Replace sop cache implementation with adapter + dependency  
3. Point production at empty or new `~/.vasp_cache`  
4. Re-ingest needed calcs via `vasp-cache put -r <old_calc_trees>` as needed  
5. Delete reliance on `~/.vasp_sop/meta.json` / `blobs.json` for result cache  

JobStore / `jobs.db` paths currently under `~/.vasp_sop` stay; only **results cache** moves conceptually to `~/.vasp_cache`.

## 14. Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Many inode job dirs | Accept signac model; revisit packing only at large scale |
| Schema detection only sees `content_hash` | All human filters on `doc.*` |
| Concurrent put same hash | Idempotent put; document limitation |
| signac major versions | Pin `signac>=2.0,<3` |
| Re-ingest cost after abandoning old store | One-time `put -r` from known trees; acceptable per “舍弃旧版” |

## 15. Implementation order

1. Package scaffold + signac project bootstrap  
2. fingerprint + put/has/fetch + tests  
3. parse → job.doc + query/list/stats  
4. CLI  
5. vasp-sop adapter + dependency wiring  
6. Docs (README/DESIGN update to match this spec)  

## 16. Success criteria

- [ ] `pip install -e .` provides `vasp_cache` and `vasp-cache` CLI  
- [ ] Roundtrip: put complete calc → wipe OUTCAR → fetch restores OUTCAR content  
- [ ] `content_hash` matches prior sop semantics on sample inputs  
- [ ] vasp-sop tests that use cache pass against adapter (with overrides)  
- [ ] No import of `vasp_sop` from `vasp_cache`  
- [ ] No code path reads legacy `meta.json`/`blobs.json`  
