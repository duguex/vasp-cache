(SUPERSEDED by v3-layered-identity spec) # Fresh Formula–INCAR Index Implementation Plan

> **This plan describes an intermediate design that pre-dates v3. The current v3 contract is in `docs/superpowers/specs/2026-07-18-v3-layered-identity.md`.**
> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox syntax.

**Goal:** Replace the old cache architecture with a fresh SQLite filesystem index keyed by normalized INCAR plus POSCAR formula and rebuild it from the CsEuCl3 tree.

**Architecture:** Add one small identity/index layer with deterministic INCAR normalization and POSCAR formula extraction. Store grouped identities and source/output paths in a new SQLite database; public API and CLI call this layer directly. Delete obsolete provenance, migration, CAS, dashboard, and inspection surfaces rather than preserving compatibility shims.

**Tech Stack:** Python 3.10+, SQLite, pymatgen POSCAR parsing, argparse, pytest.

## Global Constraints

- Identity is exactly normalized INCAR plus POSCAR reduced formula.
- Scanner requires POSCAR, INCAR, and a parseable formula; VASP outputs are optional for indexing.
- Rebuild starts from a fresh database and does not migrate old metadata.
- Do not reuse the old provenance or CAS implementation.

---

### Task 1: Replace identity and index core

**Files:**
- Create: `src/vasp_cache/index.py`
- Replace: `src/vasp_cache/meta.py`
- Replace: `src/vasp_cache/api.py`
- Replace: `src/vasp_cache/__init__.py`
- Modify: `src/vasp_cache/paths.py` only if cache-root reset support is required
- Test: `tests/test_fresh_index.py`

- [ ] Test INCAR normalization, formula extraction, deterministic identity, malformed-input skipping, duplicate grouping, fresh rebuild, query, has, and fetch.
- [ ] Implement normalization and SQLite schema with no legacy columns.
- [ ] Implement recursive scanner and grouped source/output records.
- [ ] Implement `put`, `rebuild`, `has`, `fetch`, and `query`.
- [ ] Run focused tests.

### Task 2: Replace CLI and remove obsolete surfaces

**Files:**
- Replace: `src/vasp_cache/cli.py`
- Delete or rewrite: obsolete source modules, old tests, old scripts, and old web/dashboard files that expose the removed architecture
- Test: `tests/test_fresh_cli.py`

- [ ] Expose `rebuild`, `put`, `has`, `fetch`, and `query` without provenance, CAS, or migration arguments.
- [ ] Add JSON output for rebuild/query results.
- [ ] Test CLI rebuild against temporary trees and verify empty/malformed directories are excluded.

### Task 3: Rebuild target database

**Files:**
- Runtime output: configured fresh cache root

- [ ] Run rebuild against `/mnt/shared/home/2sidesniddle/vasp/2025_undergo_spin_defect/CsEuCl3`.
- [ ] Record indexed identity count, source-directory count, formula distribution, and skipped-directory count.
- [ ] Verify the empty `CsEuCl3_mp-*` directories are absent.

### Task 4: Final verification and documentation

**Files:**
- Replace: `README.md`, `DESIGN.md`, `docs/USER.md`
- Delete: provenance/CAS migration specifications and stale issue docs

- [ ] Document the fresh identity and rebuild command.
- [ ] Search active source/tests/docs for removed provenance/CAS APIs.
- [ ] Run focused tests and the final project test command.
- [ ] Smoke-test query and fetch against the rebuilt index.
