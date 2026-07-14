# vasp-cache Design: signac Backend + Black-Box I/O

> Date: 2026-07-14 (amended: Mapping Profile)  
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
| Identity | **Mapping Profile** → hard `content_hash` (tunable critical fields + `key_generation`); default profile starts from legacy sop fingerprint keys and is **not** sacred |
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
- Neural / learned embedding models for keys  
- Soft-distance **retrieval API** as a v1 deliverable (config + distance helper OK; ANN/search UI later)  
- Compatibility layer for legacy maggma JSONStore cache  
- Silent change of hard-key semantics without bumping `key_generation`

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
  mapping.py       # load/merge Mapping Profile; mapping_digest
  fingerprint.py   # content_hash(dir, mapping=None); soft feature vector helpers
  data/
    mapping.default.yaml
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
  "profile_id": str,
  "key_generation": int,
  "mapping_digest": str,    # hash of resolved critical mapping
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

## 7. Identity: Mapping Profile + hard `content_hash`

Keys are **not** a fixed hard-coded string forever. They come from a **Mapping Profile**:
a tunable rule set that maps VASP inputs → (1) hard cache key, (2) optional soft features.

No neural embedding models. Defaults may be wrong for a lab; **adjustment is first-class**.

### 7.1 Two layers

| Layer | Role | Adjust freely? |
|-------|------|----------------|
| **Hard key** | `put` / `has` / `fetch` identity; must not false-positive | Change only with **`key_generation` bump** (old hits stop matching) |
| **Soft map** | Tunable “nearness” features/weights (HSE far, NSW close) | Anytime; does **not** change stored keys |

Conceptual model:

```text
inputs --φ--> features
  critical features + key_generation --> content_hash  (exact KV key)
  soft features + weights           --> optional distance d(·,·)
```

### 7.2 Profile sources (merge order, later wins)

1. Built-in package default: `vasp_cache/data/mapping.default.yaml`
2. User/lab file: `$VASP_CACHE_MAPPING` or `~/.vasp_cache/mapping.yaml`
3. API: `content_hash(dir, mapping=...)` / `put(..., mapping=...)`

### 7.3 Profile schema (v1)

```yaml
version: 1
profile_id: "default"
key_generation: 1

critical:
  structure:
    method: formula          # v1 default (legacy-compatible); geom_hash recommended later
  kpoints:
    method: grid             # grid | gamma | band-structure | nokpt (legacy behavior)
  potcar:
    method: species_token    # legacy PAW_ token list
  incar:
    keys:
      - ENCUT
      - PREC
      - ISMEAR
      - SIGMA
      - ISIF
      - LDAU
      - LDAUTYPE
      - LDAUU
      - LDAUJ
      - LDAUL
      - GGA
      - IVDW
      - LASPH
      - METAGGA
    # labs SHOULD add for safety, e.g.:
    # - LHFCALC
    # - HFSCREEN
    # - ISPIN

soft:
  NSW:  {scale: 100, weight: 1.0}
  NELM: {scale: 50, weight: 0.5}
  # optional: map HSE-like flags for soft distance only
  # LHFCALC: {kind: cat, weight: 1.0e6}

buckets: {}
# example: ENCUT: 10
```

### 7.4 Hard key construction

```text
content_hash = H(
  key_generation,
  canonicalize(critical features per profile)
)
```

v1 **default critical extraction** mirrors legacy sop string form for continuity when
`structure.method=formula` and the default incar key list is used:

```text
legacy_body = structure_tag + "_" + kpoints_tag + "_" + incar_fp + "_" + potcar_fp
content_hash = f"{key_generation}:{legacy_body}"   # or sha256 of the same parts
```

Implementer may use stable `sha256` of a canonical JSON of critical parts **as long as**
default profile + generation produce **documented, tested** stability. Prefer including
`key_generation` in the hashed payload.

Public API:

```python
load_mapping(path: Path | None = None) -> MappingProfile
content_hash(src_dir: Path, mapping: MappingProfile | None = None) -> str
mapping_digest(mapping: MappingProfile) -> str
soft_vector(src_dir: Path, mapping: MappingProfile | None = None) -> dict[str, float]
soft_distance(a: dict, b: dict, mapping: MappingProfile | None = None) -> float
```

### 7.5 Adjustment rules (required behavior)

| Change | Effect |
|--------|--------|
| Edit **soft** scales/weights only | Existing cache hits unchanged; soft distances change |
| Add/remove **critical** INCAR keys, change structure/kpoints/potcar method, change buckets | Tool **must bump `key_generation`** (or refuse until user bumps); new puts use new keys |
| Change `profile_id` alone | Does not change hash unless critical digest changes; still store on job.doc |

CLI (v1):

```text
vasp-cache mapping show
vasp-cache mapping check      # golden pairs: HSE differs hard; NSW-only same hard if soft-only
```

Optional later: `mapping set` mutators. v1 may be edit-yaml + show/check.

### 7.6 Safety

- Every `put` writes `profile_id`, `key_generation`, `mapping_digest` on `job.doc`
- Optional `fetch(..., strict_mapping=True)`: refuse if current digest ≠ stored digest
- Defaults **conservative bias** preferred when extending critical set (more recompute, fewer wrong hits)
- **No** auto-ML tuning of critical fields at runtime

### 7.7 Soft distance (v1 minimal)

- Implement `soft_vector` / `soft_distance` from profile weights (weighted L2 / categorical penalties)
- Example intent: HSE on vs off ≫ NSW 99 vs 100 when those are soft-mapped with large vs small weight
- **Not** required: similarity search CLI, faiss, or fetch-by-neighbor

### 7.8 Discrimination goals

- Hard key: same physical critical inputs → same key; any critical difference → different key
- Prefer false negatives over false positives on hard hits
- Soft map: tunable nearness for human/tooling; never sole authority for file restore

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
    load_mapping,
    soft_vector,
    soft_distance,
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
vasp-cache mapping show
vasp-cache mapping check
```

No `migrate-jsonstore` in v1 (old version abandoned). Operators who need history re-`put` from original calculation directories.

## 11. Configuration

| Mechanism | Effect |
|-----------|--------|
| `VASP_CACHE_ROOT` | project root |
| `VASP_CACHE_MAPPING` | path to Mapping Profile YAML |
| `~/.vasp_cache/mapping.yaml` | user/lab profile overlay |
| `override_cache_root(path)` | tests / temporary roots |
| `put(..., store_inputs=True)` | toggle input file archival |
| `put(..., include=())` | extra filenames to copy |
| `put/has/fetch/content_hash(..., mapping=)` | explicit profile |
| env or const `MAX_LATTICE` | skip huge cells (default 25.0, `None` disables) |

## 12. Testing strategy

| Area | Cases |
|------|-------|
| fingerprint | stable hash under fixed profile; kpoints/incar/potcar change flips hash |
| mapping soft | soft-only field change does not flip hard hash |
| mapping critical | critical change + generation bump flips hash |
| mapping check | golden pairs (HSE vs NSW intent) |
| put/fetch roundtrip | temp dirs; fetch restores OUTCAR bytes |
| put mapping audit | doc has profile_id, key_generation, mapping_digest |
| idempotent put | second put same hash succeeds |
| has false | missing job |
| query | formula / bandgap filters on doc |
| override_cache_root | isolation |
| no vasp_sop import | package import graph |
| CLI smoke | put + fetch + status + mapping show |

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
| Default mapping too coarse/fine | Mapping Profile + key_generation; labs edit YAML |
| Silent critical edits | Force generation bump; store mapping_digest |

## 15. Implementation order

1. Package scaffold + signac project bootstrap  
2. Mapping Profile load/merge + default YAML  
3. fingerprint from profile + soft_vector/distance + tests  
4. put/has/fetch + mapping audit fields on doc  
5. parse → richer job.doc + query/list/stats  
6. CLI (incl. mapping show/check)  
7. vasp-sop adapter + dependency wiring  
8. Docs (README/DESIGN update to match this spec)  

## 16. Success criteria

- [ ] `pip install -e .` provides `vasp_cache` and `vasp-cache` CLI  
- [ ] Roundtrip: put complete calc → wipe OUTCAR → fetch restores OUTCAR content  
- [ ] Default profile hard hash is stable and documented (legacy-compatible body + generation)  
- [ ] Soft-only mapping edits do not change `content_hash`; critical edits require/bump `key_generation`  
- [ ] `put` records `profile_id`, `key_generation`, `mapping_digest` on job.doc  
- [ ] `vasp-cache mapping show` / `mapping check` work  
- [ ] vasp-sop tests that use cache pass against adapter (with overrides)  
- [ ] No import of `vasp_sop` from `vasp_cache`  
- [ ] No code path reads legacy `meta.json`/`blobs.json`  
