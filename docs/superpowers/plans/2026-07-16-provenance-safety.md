# Provenance Safety Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Issue #22 so provenance and convergence metadata are parsed independently of TaskDoc, explicit provenance is safe across duplicate ingests, and canonical-only query defaults prevent sampled or unknown results from becoming representatives.

**Architecture:** Keep the existing `parse.py` summary flow, but add an independent INCAR/OUTCAR run-metadata pass that executes before both the TaskDoc and regex branches. Add explicit provenance/status columns to SQLite with non-destructive migration. `api.put()` computes the content hash and resolves provenance against any existing entry before writing a single CAS object; only the resolved metadata is upserted after CAS writes succeed.

**Tech Stack:** Python 3.10+, pymatgen/emmet parsing, SQLite, argparse, pytest.

## Global Constraints

- Effective VASP defaults are dependency-based: `NSW` absent → `0`; `IBRION` absent → `-1` when effective `NSW <= 0`, otherwise `0`; `ISIF` absent → `0` when effective `IBRION == 0` or `LHFCALC=.TRUE.`, otherwise `2`.
- `IBRION=0` and `IBRION=3` with `NSW>0` are sampled MD/ionic dynamics; `IBRION=5..8` are sampled phonon/finite-displacement; `IBRION=1/2` with `NSW>0` are canonical relaxations.
- Unmarked `NSW=0` remains accepted but is `unknown` unless the caller explicitly supplies `provenance="canonical"`.
- Explicit provenance has precedence over inferred provenance; automatic or unknown input must not downgrade an explicit stored role.
- Provenance conflicts must be rejected before any `cas.put_file` call.
- `query()` and CLI `query` default to `provenance="canonical"`; `provenance="all"` is the explicit all-provenance opt-in.
- Existing exact `has()` and `fetch()` behavior, content hashes, and stored CAS objects remain compatible.
- No production code is written before its new test has failed for the intended reason.
- Do not run formatters, linters, or project-wide suites until the final verification task.

---

### Task 1: Establish canonical query test contract

**Files:**
- Modify: `tests/test_query.py`
- Modify: `tests/test_put_fetch.py` only where a test later relies on formula-query visibility
- Test: existing query tests plus new query provenance cases in `tests/test_query.py`

**Interfaces:**
- Consumes: current `put()` and `query()` calls.
- Produces: failing tests that define explicit canonical fixture setup and the safe query default.

- [ ] **Step 1: Update existing representative-query fixtures first**

Change every existing test that expects a newly ingested fixture to appear in a formula query from:

```python
ch = put(calc)
```

to:

```python
ch = put(calc, provenance="canonical")
```

At minimum update `test_query_by_formula`, and use the same explicit role in any new fixture whose result is asserted through the default query path. Do not change exact `has()`/`fetch()` fixtures merely to make them canonical; those operations must remain provenance-independent.

- [ ] **Step 2: Add the canonical-default and explicit-all tests**

Add a test that creates one canonical fixture and one sampled fixture with the same formula but different INCAR identity:

```python
def test_query_defaults_to_canonical_and_all_is_explicit(
    cache_root: Path, tmp_path: Path
):
    _reset_project()
    canonical = write_complete_calc(tmp_path / "canonical")
    put(canonical, provenance="canonical")

    sampled = write_complete_calc(tmp_path / "sampled")
    (sampled / "INCAR").write_text("NSW = 4\nIBRION = 0\n")
    put(sampled, provenance="sampled")

    default_rows = query(formula="Si", converged_only=False)
    assert {row["provenance"] for row in default_rows} == {"canonical"}

    sampled_rows = query(formula="Si", provenance="sampled", converged_only=False)
    assert len(sampled_rows) == 1
    assert sampled_rows[0]["provenance"] == "sampled"

    all_rows = query(formula="Si", provenance="all", converged_only=False)
    assert {row["provenance"] for row in all_rows} == {"canonical", "sampled"}
```

- [ ] **Step 3: Run the red test**

Run:

```bash
pytest tests/test_query.py -q
```

Expected: the existing explicit-provenance calls fail with `TypeError: put() got an unexpected keyword argument 'provenance'`, and the new query test cannot pass until the API and metadata filter exist. Do not edit production code in this task.

---

### Task 2: Add independent INCAR/OUTCAR run metadata

**Files:**
- Modify: `src/vasp_cache/parse.py`
- Modify: `tests/test_parse.py`
- Modify: `tests/conftest.py` only to add small deterministic OUTCAR/INCAR writers needed by the tests

**Interfaces:**
- Consumes: `Path` calculation directories and existing `summarize_calc()` output.
- Produces: summary keys `outcar_complete`, `electronic_converged`, `ionic_converged`, `nsw`, `ibrion`, `isif`, and inferred `provenance`.

- [ ] **Step 1: Write independent-parser tests**

Add tests for the dependent defaults and mode classification. The default matrix must cover:

```python
@pytest.mark.parametrize(
    ("incar", "expected"),
    [
        ("", {"nsw": 0, "ibrion": -1, "isif": 2}),
        ("NSW = 4\n", {"nsw": 4, "ibrion": 0, "isif": 0}),
        ("NSW = 4\nIBRION = 1\n", {"nsw": 4, "ibrion": 1, "isif": 2}),
        ("NSW = 4\nIBRION = 1\nLHFCALC = .TRUE.\n", {"nsw": 4, "ibrion": 1, "isif": 0}),
    ],
)
def test_effective_incar_defaults(tmp_path: Path, incar: str, expected: dict[str, int]):
    src = write_complete_calc(tmp_path / "calc")
    (src / "INCAR").write_text(incar)
    summary = summarize_calc(src)
    assert {key: summary[key] for key in expected} == expected
```

Add parameterized classification tests for `IBRION=0`, `3`, `5`, `6`, `7`, `8`, `1`, and `2` with appropriate `NSW`. Add an unmarked `NSW=0` case that asserts `provenance == "unknown"`.

Add a TaskDoc-success regression test that patches `emmet.core.tasks.TaskDoc.from_directory` to return a minimal successful document with a non-`None` energy while the directory INCAR contains `NSW=4`, `IBRION=0`. Assert that `summarize_calc()` still returns `nsw == 4`, `ibrion == 0`, and `provenance == "sampled"`. The patch only forces the already-supported TaskDoc branch; the assertion exercises the real independent parser.

Add status tests using deterministic OUTCAR text: normal completion sets `outcar_complete=True`; recognized electronic/ionic markers populate their respective fields; an absent marker is `None`, not `False`.

- [ ] **Step 2: Run the red parser tests**

Run:

```bash
pytest tests/test_parse.py -q
```

Expected: failures identify missing summary keys or helper behavior, not fixture syntax errors.

- [ ] **Step 3: Implement the independent parser**

In `parse.py`, add a helper with one responsibility:

```python
def _parse_run_metadata(src_dir: Path) -> dict[str, Any]:
    """Parse effective INCAR values and conservative OUTCAR statuses."""
```

The helper must:

1. Read only the bounded OUTCAR tail used by the existing completion logic.
2. Parse INCAR with `pymatgen.io.vasp.inputs.Incar`; if the file is absent, apply documented defaults; if parsing fails, retain `None` for values that cannot be trusted.
3. Resolve values in order `NSW → IBRION → ISIF`, including `LHFCALC` in the ISIF decision.
4. Classify modes exactly as specified in the global constraints.
5. Return `None` for unrecognized convergence status rather than treating absence as false.

Call `_parse_run_metadata(src_dir)` at the start of `summarize_calc()`. Merge its keys into the TaskDoc result before the existing early return and into the regex fallback result before returning. Do not duplicate the logic inside the fallback branch.

- [ ] **Step 4: Run the green parser tests**

Run:

```bash
pytest tests/test_parse.py -q
```

Expected: all parser tests pass, including the forced TaskDoc-success path.

---

### Task 3: Add SQLite provenance fields, migration, and query filtering

**Files:**
- Modify: `src/vasp_cache/meta.py`
- Modify: `tests/test_query.py`
- Create: `tests/test_provenance.py` for metadata migration and merge-focused tests

**Interfaces:**
- Consumes: parser summary fields and `content_hash`.
- Produces: `provenance`, `provenance_source`, status fields, `ProvenanceFilter`, migration behavior, and a preflight merge result.

- [ ] **Step 1: Write metadata and migration tests**

Add tests that assert new rows expose all explicit fields and that an old SQLite schema is upgraded on first connection. The old-schema test must create an `entries` table without the new columns, insert one row with valid `objects_json`, then call `meta.connect(root)` and assert:

```python
entry = meta.get_entry(root, old_hash)
assert entry["provenance"] == "unknown"
assert entry["provenance_source"] == "legacy"
assert entry["objects"] == {"OUTCAR": "existing-digest"}
```

Add query filter assertions for `canonical`, `sampled`, `unknown`, and `all`; `all` must omit the provenance WHERE clause while every other value uses an exact equality predicate.

- [ ] **Step 2: Run the red metadata tests**

Run:

```bash
pytest tests/test_query.py tests/test_provenance.py -q
```

Expected: failures show missing schema fields, filter parameters, or migration behavior.

- [ ] **Step 3: Extend schema and migration**

Add these columns to `_SCHEMA` and add a connection-time migration based on `PRAGMA table_info(entries)`:

```sql
provenance TEXT NOT NULL DEFAULT 'unknown',
provenance_source TEXT NOT NULL DEFAULT 'legacy',
outcar_complete INTEGER,
electronic_converged INTEGER,
ionic_converged INTEGER,
nsw INTEGER,
ibrion INTEGER,
isif INTEGER
```

Create an index on `provenance`. Migration uses `ALTER TABLE ... ADD COLUMN`, commits once, and never rewrites or deletes CAS objects. `_row_to_dict()` converts nullable status integers to `bool | None` and keeps `nsw`, `ibrion`, and `isif` as integers or `None`.

Extend `upsert_entry()` with the new fields and include them in INSERT/UPDATE statements. Keep the existing `converged` column and semantics for compatibility.

- [ ] **Step 4: Implement exact query-filter semantics**

Define:

```python
ProvenanceFilter = Literal["canonical", "sampled", "unknown", "all"]
```

Add `provenance: ProvenanceFilter = "canonical"` to `query_entries()`. Add `provenance = ?` for the three stored roles; add no clause for `"all"`; reject invalid values with `ValueError`. Update `list_recent()` to pass `provenance="all"` so status output remains a complete recent-entry view.

- [ ] **Step 5: Implement preflight provenance merge**

Add a public exception and a read-only preflight helper:

```python
class ProvenanceConflictError(ValueError):
    """The same content hash has incompatible provenance roles."""


def preflight_provenance(
    cache_root: Path,
    content_hash: str,
    incoming: str,
    incoming_source: str,
) -> tuple[str, str]:
    """Resolve the stored role before any CAS write."""
```

Implement the approved authority order: explicit > inferred > legacy; unknown never replaces a non-unknown role; explicit replaces inferred/legacy; different non-unknown roles at the same authority raise `ProvenanceConflictError`. The helper performs no writes, so the API can call it after hashing and before `cas.put_file`.

- [ ] **Step 6: Run the green metadata tests**

Run:

```bash
pytest tests/test_query.py tests/test_provenance.py -q
```

Expected: schema migration, query filters, and preflight merge tests pass.

---

### Task 4: Wire API ingest, explicit provenance, and CAS preflight ordering

**Files:**
- Modify: `src/vasp_cache/api.py`
- Modify: `src/vasp_cache/__init__.py`
- Modify: `tests/test_provenance.py`
- Modify: `tests/test_put_fetch.py` only for compatibility assertions

**Interfaces:**
- Consumes: independent parser metadata, `meta.preflight_provenance()`, and existing CAS helpers.
- Produces: `put(..., provenance=...)`, safe duplicate merge, public `ProvenanceConflictError`, and unchanged exact reuse.

- [ ] **Step 1: Write API and duplicate-ingest tests**

Add tests for:

```python
def test_explicit_provenance_is_stored(cache_root: Path, tmp_path: Path):
    calc = write_complete_calc(tmp_path / "calc")
    ch = put(calc, provenance="canonical")
    entry = get_entry(cache_root, ch)
    assert entry["provenance"] == "canonical"
    assert entry["provenance_source"] == "explicit"
```

Add a same-hash regression that first ingests explicit canonical, then ingests the same directory without an explicit role. Assert the stored role remains canonical. Add an explicit canonical followed by explicit sampled case that raises `ProvenanceConflictError` and leaves the existing entry unchanged.

For CAS ordering, wrap `vasp_cache.api.cas.put_file` in a test spy that fails if called during the rejected second ingest. The second ingest must raise before the spy is invoked.

Add tests that explicit `canonical`, `sampled`, and `unknown` override inferred classification and that automatic `IBRION=0`, `NSW>0` is sampled.

- [ ] **Step 2: Run the red API tests**

Run:

```bash
pytest tests/test_provenance.py tests/test_put_fetch.py -q
```

Expected: the new keyword argument and exception behavior fail before production changes; existing exact reuse tests continue to pass or fail only where the new signature is intentionally missing.

- [ ] **Step 3: Add explicit provenance validation and preflight to `put()`**

Add the keyword-only parameter:

```python
provenance: Provenance | None = None
```

Validate it before parsing or writing objects. In `_put_impl()`:

1. Run existing usability checks and `summarize_calc()`.
2. Select explicit provenance when supplied; otherwise use `summary["provenance"]` and source `"inferred"`.
3. Compute `content_hash`.
4. Call `meta.preflight_provenance()` and retain the resolved role/source.
5. Only then execute any `cas.put_file` calls.
6. Pass resolved role/source and all status fields to `meta.upsert_entry()`.

The preflight must occur before the existing object loop at current `api.py` lines 123–142. Add new summary keys to the metadata-column set so they are not duplicated in `extra_json`. Re-export `ProvenanceConflictError` and the `Provenance` type alias from `vasp_cache.__init__` if needed by callers.

- [ ] **Step 4: Make formula metadata lookup canonical by default**

Add `provenance: ProvenanceFilter = "canonical"` to `api.query()` and pass it to `meta.query_entries()`. Add the same keyword to `get_meta()`; exact directory/content-hash lookup ignores it, while formula lookup passes it to the metadata query. `provenance="all"` is the only all-candidate path.

- [ ] **Step 5: Run the green API tests**

Run:

```bash
pytest tests/test_provenance.py tests/test_put_fetch.py tests/test_query.py -q
```

Expected: explicit roles, inferred roles, duplicate merge protection, CAS preflight, canonical query default, and exact reuse all pass.

---

### Task 5: Wire CLI provenance options and output

**Files:**
- Modify: `src/vasp_cache/cli.py`
- Modify: `tests/test_cli.py`

**Interfaces:**
- Consumes: API `put(..., provenance=...)` and `query(..., provenance=...)`.
- Produces: `put --provenance`, recursive propagation, query `--provenance`, and visible provenance output.

- [ ] **Step 1: Write CLI red tests**

Add a test that runs:

```python
assert main(["put", "--provenance", "canonical", str(calc)]) == 0
```

Add a test that stores canonical and sampled rows, captures JSON output from `main(["query", "--formula", "Si", "--json"])`, and asserts every returned row is canonical. Repeat with `--provenance all` and assert both roles are present. Add a recursive CLI test that passes one explicit provenance value and verifies all ingested rows receive it.

- [ ] **Step 2: Run the red CLI tests**

Run:

```bash
pytest tests/test_cli.py -q
```

Expected: argparse rejects the new option or the API call lacks the new keyword.

- [ ] **Step 3: Implement CLI options**

Add `--provenance` with choices `canonical`, `sampled`, `unknown` to `put`; pass it in both single-directory and recursive paths. Add query choices `canonical`, `sampled`, `unknown`, `all` with default `canonical`; pass it to `api.query()`. Include a `provenance` column in compact query output while preserving JSON fields.

- [ ] **Step 4: Run the green CLI tests**

Run:

```bash
pytest tests/test_cli.py -q
```

Expected: CLI put, recursive propagation, canonical query default, explicit all opt-in, and compact/JSON output pass.

---

### Task 6: Update user-facing documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/USER.md`
- Modify: `ROADMAP.md`

**Interfaces:**
- Consumes: final API/CLI behavior.
- Produces: documentation that does not imply unknown or sampled rows are canonical and documents explicit all-provenance opt-in.

- [ ] **Step 1: Update usage examples**

Document:

```python
put("/path/to/static", provenance="canonical")
query(formula="Si")                         # canonical by default
query(formula="Si", provenance="sampled")  # explicit sampled view
query(formula="Si", provenance="all")      # explicit all view
```

Add CLI examples for `put --provenance canonical`, `query --provenance sampled`, and `query --provenance all`. Explain that omitted provenance is conservative and that `fetch()` remains exact output restoration only.

- [ ] **Step 2: Verify documentation consistency**

Run:

```bash
git diff --check
```

Search the changed docs for stale claims that `converged` proves electronic/ionic convergence or that formula query returns the newest unrestricted row.

---

### Task 7: Focused, full, and smoke verification

**Files:**
- No new files.

- [ ] **Step 1: Run focused regression suites**

Run:

```bash
pytest tests/test_parse.py tests/test_provenance.py tests/test_query.py tests/test_cli.py -q
```

Expected: all focused tests pass.

- [ ] **Step 2: Run the full synthetic suite**

Run:

```bash
pytest -q
```

Expected: all non-`real_data` tests pass. If an existing test fails because it assumes unrestricted formula query, update that fixture to explicit `provenance="canonical"` rather than weakening the safe default.

- [ ] **Step 3: Run the CLI smoke path**

Run a temporary-directory scenario that ingests one explicit canonical calculation, verifies `query --formula` returns it, ingests a sampled calculation, verifies the default query excludes it, and verifies `--provenance all` exposes it. Also run `has` and `fetch` on the canonical input-only directory.

- [ ] **Step 4: Validate final diff and repository state**

Run:

```bash
git diff --check
git status --short --branch
```

Expected: no whitespace errors; only intended implementation/docs/test files are modified. Preserve the pre-existing untracked `issues/0006-spin-nupdown-mapping.md` unchanged.

---

### Task 8: Commit the implementation

**Files:**
- All intended files from Tasks 1–6.

- [ ] **Step 1: Review changed symbols and public behavior**

Confirm that `put`, `query`, `get_meta`, CLI `put`, and CLI `query` have the documented signatures/defaults; confirm CAS preflight occurs before the first `cas.put_file` call; confirm legacy rows migrate to `unknown`.

- [ ] **Step 2: Commit**

Run:

```bash
git add src/vasp_cache tests README.md docs/USER.md ROADMAP.md
git commit -m "feat: add provenance-aware cache queries"
```

Expected: one commit containing the Issue #22 implementation and its tests/docs, with the existing untracked issue file excluded.
