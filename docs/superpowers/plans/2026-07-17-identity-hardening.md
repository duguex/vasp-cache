# Identity Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move vasp-cache to a generation-5 POSCAR-based input-intent identity that distinguishes VASP protocols, prevents same-key output clobbering by default, and inventories legacy collisions before any cleanup.

**Architecture:** Add one input-only protocol parser in the fingerprint/mapping layer. `mapping_digest()` and `has()` use the same parser and POSCAR source; `summarize_calc()` remains an output/provenance parser and is never called by identity code. Put conflict handling in `api.put()` before CAS writes, comparing source OUTCAR SHA-256 with the existing immutable CAS digest. Rework rehashing into a two-phase inventory/apply flow that never resolves collisions with last-write-wins.

**Tech Stack:** Python 3.10+, pymatgen INCAR/KPOINTS/Structure parsers, SQLite/CAS, argparse, pytest, YAML.

## Global Constraints

- Primary identity is `POSCAR + KPOINTS + input-only protocol fingerprint + existing hard INCAR keys`.
- `CONTCAR` is an output object and optional `result_geom_hash`; it is never the primary identity source.
- The protocol parser must not read `OUTCAR`, `vasprun.xml`, `TaskDoc`, or call `summarize_calc()`.
- Effective defaults: absent `NSW=0`; absent `IBRION=-1` when effective `NSW<=0`, else `0`; absent `ISIF=0` for effective `IBRION=0` or `LHFCALC=.TRUE.`, else `2`.
- `calc_mode` values are `static`, `relaxation`, `md`, `phonon`, or `unknown`; numeric effective fields remain in the identity token.
- Default mapping generation changes from `4` to `5`.
- New identity-aware puts require POSCAR and must not silently fall back to CONTCAR.
- `put(..., on_conflict="strict")` is the default; valid modes are `strict`, `skip`, and `overwrite`.
- Strict output conflicts are rejected before any `cas.put_file`; identical OUTCAR bytes are idempotent.
- Provenance is metadata, not identity; existing provenance preflight remains independent.
- Legacy rehash is inventory-first and non-destructive on collisions.
- Do not delete random perturbation data in this implementation.
- No production code is written before its new test has failed for the intended reason.
- Run focused tests after each task; run the full suite once at the end. Do not run formatters or linters as a substitute for tests.

---

### Task 1: Add failing input-intent identity tests

**Files:**
- Modify: `tests/test_mapping.py`
- Create: `tests/test_identity.py`
- Modify: `tests/conftest.py` only if a POSCAR-only or CONTCAR-different fixture helper is needed

**Interfaces:**
- Consumes: current `mapping_digest()`, `content_hash()`, and test fixtures.
- Produces: red tests defining generation-5 input-only identity and protocol separation.

- [ ] **Step 1: Write the failing POSCAR/CONTCAR tests**

Add a fixture scenario with identical POSCAR/KPOINTS/INCAR and different
CONTCAR contents. Assert that `mapping_digest(completed_dir)` equals
`mapping_digest(input_only_dir)` when both POSCAR files match, and that changing
only CONTCAR does not change the primary hash.

Add a test that removes POSCAR while leaving CONTCAR and asserts the new identity
path raises a clear `IdentityInputError` (or returns the exact documented skip
result once that exception is defined). Do not accept a hash based on CONTCAR.

- [ ] **Step 2: Write the failing protocol matrix**

Use the same POSCAR/KPOINTS and vary only INCAR protocol values:

```python
@pytest.mark.parametrize(
    ("incar", "mode"),
    [
        ("", "static"),
        ("NSW = 0\nIBRION = -1\n", "static"),
        ("NSW = 100\nIBRION = 2\n", "relaxation"),
        ("NSW = 100\nIBRION = 0\n", "md"),
        ("NSW = 100\nIBRION = 3\n", "md"),
        ("IBRION = 6\n", "phonon"),
    ],
)
def test_input_protocol_identity_contains_effective_mode(...):
    ...
```

Assert that all protocol variants produce distinct generation-5 hashes except
explicit and omitted forms with the same effective values. Assert that changing
`NSW=1` to `NSW=100` changes the hash.

- [ ] **Step 3: Write the failing input-only dependency test**

Monkeypatch `vasp_cache.parse.summarize_calc` and `emmet.core.tasks.TaskDoc` to
raise if called, then invoke `mapping_digest(input_only_dir)`. The test must
still compute a hash from POSCAR/INCAR/KPOINTS.

- [ ] **Step 4: Run the red identity tests**

Run:

```bash
pytest tests/test_identity.py tests/test_mapping.py -q
```

Expected: failures show generation `4`, CONTCAR preference, unchanged soft NSW
hashing, missing protocol helper, or missing POSCAR policy. Existing tests that
assert generation `4` are expected to fail and will be updated only after the
new behavior is implemented.

---

### Task 2: Implement input-only protocol and generation-5 mapping

**Files:**
- Modify: `src/vasp_cache/fingerprint.py`
- Modify: `src/vasp_cache/mapping.py`
- Modify: `src/vasp_cache/data/mapping.default.yaml`
- Modify: `tests/test_identity.py`
- Modify: `tests/test_mapping.py`

**Interfaces:**
- Consumes: POSCAR/INCAR/KPOINTS input directories.
- Produces:
  - `input_protocol_identity(src_dir) -> dict[str, Any]`;
  - `input_protocol_fingerprint(src_dir) -> str`;
  - POSCAR-based primary geometry token;
  - generation-5 `mapping_digest()`.

- [ ] **Step 1: Implement input-only parser helpers**

In `fingerprint.py`, implement:

```python
def input_protocol_identity(src_dir: Path) -> dict[str, Any]:
    """Parse only INCAR/KPOINTS/POSCAR protocol inputs."""


def input_protocol_fingerprint(src_dir: Path) -> str:
    """Return a stable serialized protocol token for the hard identity."""
```

Parse INCAR through `pymatgen.io.vasp.inputs.Incar`; apply the dependency-order
defaults exactly. Parse `NFREE` when present. Classify mode in this order:
phonon (`IBRION=5..8`), md (`NSW>0` and `IBRION=0/3`), relaxation
(`NSW>0` and `IBRION=1/2`), static (`NSW<=0`), unknown otherwise. Serialize
sorted JSON with stable separators so equivalent effective inputs have the same
token.

Add an input-only structure helper that requires POSCAR for the primary identity.
Keep the existing result-geometry helper separately for CONTCAR metadata.

- [ ] **Step 2: Update mapping composition and generation**

In `mapping.py`, append the protocol fingerprint to the hard mapping body and
use POSCAR for the primary geometry tag. Add a hard `protocol: true` profile
flag and include it in `_critical_section()` so custom profile validation sees
protocol identity as a critical section.

Update the packaged profile `key_generation: 5`. Keep NSW available in the soft
vector for tuning compatibility, but document that the normalized protocol token
is independently hard. Do not use `summarize_calc()` anywhere in this path.

- [ ] **Step 3: Update mapping tests and verify green**

Update generation assertions from `4` to `5`, replace the old “soft NSW does not
flip hard hash” test with the new protocol identity assertion, and add tests for
custom mappings with/without the protocol flag according to the documented
backward-compatibility rule.

Run:

```bash
pytest tests/test_identity.py tests/test_mapping.py -q
```

Expected: all input-only identity and mapping tests pass.

---

### Task 3: Add failing strict output-conflict tests

**Files:**
- Modify: `tests/test_put_fetch.py`
- Create or modify: `tests/test_identity.py`
- Modify: `src/vasp_cache/errors.py` only after the red test import is established

**Interfaces:**
- Consumes: generation-5 `content_hash` and existing CAS object digests.
- Produces: red tests for `on_conflict` and the public conflict exception.

- [ ] **Step 1: Write the strict conflict tests**

Add a test that puts a complete calculation, changes only OUTCAR bytes while
keeping POSCAR/INCAR/KPOINTS unchanged, and asserts:

```python
with pytest.raises(CacheConflictError):
    put(second, on_conflict="strict")
```

Monkeypatch `vasp_cache.api.cas.put_file` during the second call and assert the
spy is never reached. Verify the first entry’s OUTCAR digest and metadata remain
unchanged.

Add a same-OUTCAR idempotence test: a second strict put succeeds and returns the
same hash.

Add `skip` and `overwrite` tests: skip keeps the original object; overwrite
replaces it only when explicitly requested.

- [ ] **Step 2: Run the red conflict tests**

Run:

```bash
pytest tests/test_identity.py tests/test_put_fetch.py -q
```

Expected: `put()` rejects the new keyword or lacks the public conflict behavior.

---

### Task 4: Implement strict preflight and API/CLI conflict modes

**Files:**
- Modify: `src/vasp_cache/cas.py`
- Modify: `src/vasp_cache/api.py`
- Modify: `src/vasp_cache/cli.py`
- Modify: `src/vasp_cache/errors.py`
- Modify: `tests/test_cli.py`
- Modify: `tests/test_put_fetch.py`

**Interfaces:**
- Consumes: `input_protocol_fingerprint()`, existing entry objects, and CAS digests.
- Produces:
  - `CacheConflictError`;
  - `cas.file_digest(path) -> str`;
  - `put(..., on_conflict: Literal["strict", "skip", "overwrite"] = "strict")`;
  - CLI `put --on-conflict`.

- [ ] **Step 1: Implement the CAS source digest helper**

Add:

```python
def file_digest(src: Path | str) -> str:
    """Return the SHA-256 digest without writing to CAS."""
```

Use the same chunked SHA-256 algorithm as `put_file()`. Test it against the
returned digest from `put_file()` for identical bytes.

- [ ] **Step 2: Implement strict API preflight**

Add `CacheConflictError(ValueError)` to `errors.py`. Validate
`on_conflict` before writing. After computing the new input hash and resolving
provenance, inspect the existing entry:

- no entry: continue;
- `skip`: return existing hash without CAS writes;
- `strict`: require an existing OUTCAR digest and compare it with
  `cas.file_digest(calc_dir / "OUTCAR")`; raise on mismatch;
- `overwrite`: log an explicit warning and continue.

This check must happen before the first `cas.put_file`. Same-byte strict puts
remain idempotent. Include `result_geom_hash` from CONTCAR in metadata after the
preflight, but never use it as the primary hash.

- [ ] **Step 3: Wire CLI and recursive propagation**

Add `--on-conflict {strict,skip,overwrite}` to `put`, defaulting to strict, and
pass it for both single and recursive ingest. Add CLI tests for strict rejection,
explicit overwrite, and recursive option propagation.

- [ ] **Step 4: Run the green API/CLI tests**

Run:

```bash
pytest tests/test_identity.py tests/test_put_fetch.py tests/test_cli.py -q
```

Expected: strict, skip, overwrite, CAS ordering, and recursive propagation pass.

---

### Task 5: Rework rehash into collision-safe inventory/apply

**Files:**
- Modify: `scripts/rehash_meta_cas.py`
- Create or modify: `tests/test_rehash.py`
- Modify: `docs/IDENTITY.md`

**Interfaces:**
- Consumes: old metadata rows and CAS input objects.
- Produces: collision inventory and explicit apply mode without last-write-wins.

- [ ] **Step 1: Write the failing rehash collision test**

Create a temporary cache with two old entries that map to the same generation-5
POSCAR/protocol hash but have different OUTCAR digests. Run the inventory API or
CLI and assert it reports the group with both old hashes and does not delete,
rewrite, or overwrite either row/object.

Add a non-collision test that applies a rehash and asserts the new key and all
metadata/object pointers remain readable.

- [ ] **Step 2: Implement two-phase rehash**

Refactor `rehash_root()` into:

```python
def inventory_root(root: Path, *, limit: int = 0) -> dict[str, Any]: ...
def apply_inventory(root: Path, inventory: dict[str, Any]) -> dict[str, Any]: ...
```

The default CLI action is inventory/dry-run. Add `--apply` for non-colliding
rewrites. Group rows by new hash before any write. If a group contains multiple
old rows or differing output digests, report it and do not apply that group.
Never delete an old row or CAS object because of a collision.

- [ ] **Step 3: Verify migration behavior**

Run:

```bash
pytest tests/test_rehash.py -q
python scripts/rehash_meta_cas.py --root /tmp/cache
python scripts/rehash_meta_cas.py --root /tmp/cache --apply
```

Expected: default inventory is non-destructive; `--apply` changes only safe,
non-colliding groups.

---

### Task 6: Update identity, user, and roadmap documentation

**Files:**
- Modify: `docs/IDENTITY.md`
- Modify: `README.md`
- Modify: `docs/USER.md`
- Modify: `ROADMAP.md`

**Interfaces:**
- Consumes: generation-5 API, CLI, and migration behavior.
- Produces: consistent user-facing identity and cleanup guidance.

- [ ] **Step 1: Document the generation-5 contract**

Document:

```text
primary identity = POSCAR + KPOINTS + normalized input protocol + hard INCAR
CONTCAR = output/result geometry, not primary identity
```

Explicitly state that input-only `has()` must carry the same POSCAR used by the
original job, and that result-only directories without POSCAR cannot prove input
intent.

- [ ] **Step 2: Document conflict modes and cleanup gate**

Add examples:

```bash
vasp-cache put DIR --on-conflict strict
vasp-cache put DIR --on-conflict skip
vasp-cache put DIR --on-conflict overwrite
python scripts/rehash_meta_cas.py --root ROOT
python scripts/rehash_meta_cas.py --root ROOT --apply
```

State that random perturbation cleanup occurs only after inventory and collision
resolution, and that “no relaxation” alone is not a deletion criterion.

- [ ] **Step 3: Verify docs**

Run:

```bash
git diff --check
```

Search changed docs for stale claims that `CONTCAR` is primary identity or that
`NSW`/`IBRION` differences necessarily already produce different generation-4
hashes.

---

### Task 7: Full verification and commit

**Files:**
- All implementation, test, and documentation files from Tasks 1–6.

- [ ] **Step 1: Run focused verification**

```bash
pytest tests/test_identity.py tests/test_mapping.py tests/test_put_fetch.py tests/test_cli.py tests/test_rehash.py -q
```

- [ ] **Step 2: Run the full suite**

```bash
pytest -q
```

Expected: all synthetic tests pass. Real-data tests may remain environment-gated
according to the existing marker policy.

- [ ] **Step 3: Run the input-only smoke scenario**

Create a completed directory with POSCAR/CONTCAR, put it with strict mode, create
an input-only copy containing POSCAR/INCAR/KPOINTS, and assert `has()` is true.
Change only CONTCAR in the completed directory and assert the primary hash is
unchanged. Change NSW/IBRION and assert the primary hash changes.

- [ ] **Step 4: Validate state and commit**

```bash
python -m compileall -q src tests scripts
git diff --check
git add src tests scripts docs README.md ROADMAP.md
git commit -m "feat: harden calculation identity"
git push origin main
```

Do not add or modify the pre-existing untracked
`issues/0006-spin-nupdown-mapping.md`.
