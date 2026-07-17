# Cache Inspection and Transparency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only `vasp-cache inspect` CLI that exposes metadata rows, CAS object references, storage totals, and orphan status without mutating the cache.

**Architecture:** Add a focused `vasp_cache.inspection` data-collection module. It will reuse `meta`, `cas`, and existing query behavior, return structured dictionaries, and avoid creating a cache root/database for an absent cache. Keep table/JSON/JSONL rendering in the CLI layer. Add the smallest metadata iterator needed to count references without exposing SQLite schema details to the CLI.

**Tech Stack:** Python 3.10+, argparse, SQLite, existing CAS + SQLite backend, pytest.

## Global Constraints

- `inspect` is read-only: it must not modify metadata, CAS objects, `cached_at`, or source calculations.
- Missing cache roots must produce zero-valued reports without creating a directory or SQLite database.
- Primary identity remains generation-5 POSCAR/KPOINTS/normalized-protocol/hard-INCAR identity.
- Entry detail reports CAS digest, size, and presence; it must not read full blob contents.
- Orphan means a CAS object with zero references from metadata object maps at inspection time.
- Existing `put`, `has`, `fetch`, `query`, `status`, and archive commands remain behaviorally unchanged.
- Human-readable output is the default; JSON is supported for every view and JSONL for collection views.
- No Web UI, automatic repair, GC, full OUTCAR search, or embedding search is part of this change.
- New production behavior follows test-first development: each behavior gets a failing test before implementation.

---

## Task 1: Build structured inspection collectors

**Files:**
- Create: `src/vasp_cache/inspection.py`
- Modify: `src/vasp_cache/meta.py` — add a read-only metadata iterator/helper
- Test: `tests/test_inspection.py`

**Interfaces:**
- Consumes: existing `meta`, `cas`, `api.query`, and cache-root resolution.
- Produces:
  - `summary(cache_root: Path) -> dict[str, Any]`
  - `entries(cache_root: Path, *, formula: str | None = None, functional: str | None = None, tags: str | None = None, bandgap_min: float | None = None, lattice_max: float | None = None, min_energy: float | None = None, max_energy: float | None = None, converged_only: bool = False, provenance: str = "canonical", limit: int = 20, offset: int = 0) -> list[dict[str, Any]]`
  - `entry(cache_root: Path, content_hash: str) -> dict[str, Any] | None`
  - `objects(cache_root: Path, *, orphans_only: bool = False) -> list[dict[str, Any]]`

### Step 1: Write failing collector tests

Create `tests/test_inspection.py` with deterministic synthetic fixtures:

```python
def test_summary_empty_cache_does_not_create_database(tmp_path: Path):
    root = tmp_path / "missing"
    result = summary(root)
    assert result["entries"] == 0
    assert result["cas_objects"] == 0
    assert not root.exists()


def test_summary_counts_entries_and_storage(cache_root: Path, tmp_path: Path):
    _reset_project()
    calc = write_complete_calc(tmp_path / "calc")
    assert put(calc, provenance="canonical")
    result = summary(cache_root)
    assert result["entries"] == 1
    assert result["provenance"]["canonical"] == 1
    assert result["cas_objects"] >= 1
    assert result["referenced_objects"] == result["cas_objects"]


def test_entry_reports_object_sizes_and_presence(cache_root: Path, tmp_path: Path):
    _reset_project()
    calc = write_complete_calc(tmp_path / "calc")
    content_hash = put(calc, provenance="canonical")
    detail = entry(cache_root, content_hash)
    outcar = detail["objects"]["OUTCAR"]
    assert outcar["digest"]
    assert outcar["size"] == (calc / "OUTCAR").stat().st_size
    assert outcar["present"] is True


def test_objects_reports_orphan_without_mutating_it(cache_root: Path):
    orphan = cas.put_bytes(cache_root, b"unreferenced")
    result = objects(cache_root, orphans_only=True)
    assert [row["digest"] for row in result] == [orphan]
    assert cas.has_object(cache_root, orphan)
```

Also test a deleted CAS object is reported with `present == False`, and a
missing content hash returns `None` without creating a database.

### Step 2: Run the red collector tests

Run:

```bash
pytest tests/test_inspection.py -q
```

Expected: collection import or missing-function failures before implementation.

### Step 3: Add read-only metadata iteration

In `meta.py`, add a helper that only reads an existing database:

```python
def iter_entries(cache_root: Path):
    """Yield decoded metadata entries without creating a database."""
```

The helper must first check `db_path(cache_root).is_file()`, return an empty
iterator for an absent database, execute `SELECT * FROM entries`, and decode
rows through the existing `_row_to_dict` path. Do not expose a SQLite cursor to
the CLI.

### Step 4: Implement collectors

In `inspection.py`:

- Add `_has_database(root)` and return zero/empty structures before calling
  helpers that create SQLite connections.
- Build a reference map by iterating metadata `objects` dictionaries. Store for
  each digest its reference count and logical names.
- Use `cas.iter_objects(root)` to enumerate physical CAS files; obtain sizes
  with `Path.stat()` and validate paths through existing CAS helpers.
- `summary()` must return at least:

```python
{
    "entries": int,
    "formulas": int,
    "provenance": {"canonical": int, "sampled": int, "unknown": int},
    "converged": int,
    "with_energy": int,
    "key_generations": list[int],
    "profile_ids": list[str],
    "cas_objects": int,
    "cas_bytes": int,
    "referenced_objects": int,
    "referenced_bytes": int,
    "orphan_objects": int,
    "orphan_bytes": int,
}
```

- `entries()` must preserve current query semantics and add `object_count` to
  each returned row without abbreviating JSON data. Apply `offset` and `limit`
  in the collector or through the metadata query, but never load unbounded rows
  for a bounded request.
- `entry()` must return complete metadata plus normalized object records with
  `name`, `digest`, `size`, `present`, and stable relative CAS location. Return
  `None` for a missing row.
- `objects()` must return `digest`, `size`, `reference_count`, `logical_names`,
  and `orphan`, with deterministic digest ordering and `--orphans-only`
  filtering represented by the function argument.

### Step 5: Run the green collector tests

Run:

```bash
pytest tests/test_inspection.py -q
```

Expected: all collector tests pass, including absent-cache non-mutation and
orphan preservation.

### Step 6: Commit the collector slice

```bash
git add src/vasp_cache/inspection.py src/vasp_cache/meta.py tests/test_inspection.py
git commit -m "feat: add cache inspection collectors"
```

---

## Task 2: Add `inspect` CLI parsing and rendering

**Files:**
- Modify: `src/vasp_cache/cli.py`
- Modify: `tests/test_cli.py`

**Interfaces:**
- Consumes: `vasp_cache.inspection.summary`, `entries`, `entry`, and `objects`.
- Produces CLI commands:

```bash
vasp-cache inspect summary [--json]
vasp-cache inspect entries [existing query filters] [--json|--jsonl]
vasp-cache inspect entry CONTENT_HASH [--json]
vasp-cache inspect objects [--orphans-only] [--json|--jsonl]
```

### Step 1: Write failing CLI tests

Add tests that invoke `main([...])` and capture output:

```python
def test_cli_inspect_summary_json(cache_root: Path, tmp_path: Path, capsys):
    _reset_project()
    put(write_complete_calc(tmp_path / "calc"), provenance="canonical")
    assert main(["inspect", "summary", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["entries"] == 1
    assert payload["cas_objects"] >= 1


def test_cli_inspect_entry_json_has_full_hash_and_objects(
    cache_root: Path, tmp_path: Path, capsys
):
    _reset_project()
    content_hash = put(write_complete_calc(tmp_path / "calc"))
    assert main(["inspect", "entry", content_hash, "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["content_hash"] == content_hash
    assert "OUTCAR" in payload["objects"]


def test_cli_inspect_missing_entry_returns_nonzero(
    cache_root: Path, capsys
):
    assert main(["inspect", "entry", "missing", "--json"]) == 1
    assert "missing" in capsys.readouterr().err
```

Also test table output contains the formula and that `--jsonl` emits one valid
JSON object per line for entries and objects. Test `--orphans-only` through the
CLI, not only through the collector.

### Step 2: Run the red CLI tests

Run:

```bash
pytest tests/test_cli.py -q
```

Expected: argparse rejects the new `inspect` command before implementation.

### Step 3: Add parser branches and shared query options

Add an `inspect` parser with required subcommands. Reuse one helper for the
existing query filters and the new `entries` command so formula, functional,
tags, bandgap, lattice, convergence, provenance, limit, and offset do not drift
between `query` and `inspect entries`.

`inspect entry` takes one positional `content_hash`. `inspect objects` takes
`--orphans-only`. Add `--json` to summary/detail and `--json` plus `--jsonl` to
collection commands; reject both output flags together with argparse error.

### Step 4: Implement deterministic renderers

Keep collection functions structured and render in CLI helpers:

- JSON: `json.dumps(payload, indent=2, default=str)`;
- JSONL: one compact JSON object per line, no header;
- tables: stable headers and deterministic ordering;
- missing detail: print `entry not found: HASH` to stderr and return `1`;
- successful commands return `0` even when a detail reports a missing CAS object,
  because missing objects are data-health information in a read-only view.

Do not print full OUTCAR content. Show logical names, digests, sizes, and state.

### Step 5: Run the green CLI tests

Run:

```bash
pytest tests/test_cli.py tests/test_inspection.py -q
```

Expected: all new table, JSON, JSONL, missing-entry, and orphan-view tests pass;
existing CLI tests remain green.

### Step 6: Commit the CLI slice

```bash
git add src/vasp_cache/cli.py tests/test_cli.py
git commit -m "feat: add cache inspect CLI"
```

---

## Task 3: Document the transparency workflow

**Files:**
- Modify: `README.md`
- Modify: `docs/USER.md`
- Modify: `docs/IDENTITY.md` only if the final inspect output adds identity fields

**Interfaces:**
- Consumes: the stable CLI commands from Task 2.
- Produces user-facing examples and explicit read-only/health boundaries.

### Step 1: Add documentation tests/checks

Use text review rather than brittle source-text tests. Confirm every documented
command is present in `argparse` help and every example uses the actual long
option names.

### Step 2: Document the command family

Add examples:

```bash
vasp-cache inspect summary
vasp-cache inspect entries --formula GaN --provenance all --limit 50
vasp-cache inspect entries --jsonl --limit 1000
vasp-cache inspect entry 5:...
vasp-cache inspect objects --orphans-only
```

Document that inspect is read-only, entry detail links metadata to CAS objects,
and orphan reporting does not delete anything. Explain that `inspect` is an
observability surface, while future `health` and `gc` commands require separate
explicit workflows.

### Step 3: Check documentation consistency

Run:

```bash
git diff --check
```

Search the changed documentation for stale claims that `status` is the only
complete database view or that inspection performs cleanup automatically.

### Step 4: Commit the documentation slice

```bash
git add README.md docs/USER.md docs/IDENTITY.md
git commit -m "docs: document cache inspection"
```

---

## Task 4: Full verification and smoke scenario

**Files:**
- All files from Tasks 1–3.

### Step 1: Run focused verification

```bash
pytest tests/test_inspection.py tests/test_cli.py tests/test_query.py -q
```

Expected: all inspection, CLI, and existing query tests pass.

### Step 2: Run the full suite

```bash
pytest -q
```

Expected: all existing and new tests pass; dependency deprecation warnings may
remain but must not become failures.

### Step 3: Run the real read-only smoke scenario

Against a temporary cache root:

```bash
vasp-cache inspect summary --json
vasp-cache inspect entries --jsonl --limit 10
vasp-cache inspect objects --json
```

Verify that the JSON parses, entry rows include complete hashes, object rows
include sizes/reference counts, and the commands do not change metadata row
counts or CAS object counts.

### Step 4: Validate final boundaries

Run:

```bash
python -m compileall -q src tests scripts
```

Confirm manually that no command added by this plan deletes CAS objects,
rewrites metadata, creates a missing cache root, or reads full output blobs.

