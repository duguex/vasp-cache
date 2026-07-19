# Schema migration: old index.sqlite blocks v0.3.0 `has()`/`put()`

**Date:** 2026-07-19
**Severity:** P1

## Problem

A pre-existing `index.sqlite` from an earlier vasp-cache version causes
`sqlite3.OperationalError: no such column: final_energy` when v0.3.0 code
calls `has()` or `put()`. The old table lacks columns (`final_energy`,
`converged_ionic`, etc.) that the v0.3.0 schema expects.

The `CREATE TABLE IF NOT EXISTS` in `_create_schema` does not alter an
existing table, so schema drift between versions silently corrupts operation.

## Repro

```bash
# Create old-format index.sqlite (or reuse any pre-v0.3.0 one)
vasp-cache --root /tmp/vc has /some/dir    # fails with "no such column: final_energy"
```

## Desired fix

- Detect schema version mismatch on connect (e.g., `PRAGMA user_version` or
  column introspection) and either:
  - Auto-migrate (ALTER TABLE ADD COLUMN for missing columns), or
  - Raise a clear error telling the user to delete/recreate the database
- At minimum, `_create_schema` should handle the case where the table exists
  but with different columns.

## Workaround

Delete the old `index.sqlite` and let vasp-cache create a fresh one:

```bash
rm /path/to/cache/index.sqlite
```