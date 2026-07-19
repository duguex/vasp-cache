(SUPERSEDED by v3-layered-identity.md) # Fresh Formula

**Status:** Approved by the explicit implementation request to discard the old database and rebuild from the target tree.

## Contract

The fresh index identity is:

```text
SHA256(canonical_json({"formula": POSCAR.reduced_formula,
                      "incar": normalize(INCAR)}))
```

`normalize(INCAR)` uppercases keys, sorts keys, strips leading/trailing value whitespace, and collapses repeated internal whitespace. All parsed INCAR keys are retained. POSCAR contributes only its reduced chemical formula, as explicitly requested; different structures with the same formula and INCAR intentionally share an identity.

The rebuild scanner recursively accepts only directories containing both `POSCAR` and `INCAR` where POSCAR parsing yields a formula. Missing or malformed input directories are skipped. Output files are optional for admission. For each identity, the index stores the formula, normalized INCAR, every source directory that produced the identity, and the existing standard-output paths (`OUTCAR`, `CONTCAR`, `vasprun.xml`) for each source.

## Storage

A fresh SQLite database is created at the configured cache root. The schema contains only identity, formula, normalized INCAR, source directories, output paths, and timestamps. No legacy migration, provenance fields, CAS objects, or schema compatibility layer is used. Rebuild removes the old fresh-index database before creating the new one.

## Operations

- `rebuild(root)`: scan and replace the index.
- `put(directory)`: index one valid calculation directory.
- `has(directory)`: compute the identity and check for an index row.
- `fetch(directory)`: compute the identity and copy indexed output files that exist; return success only when at least one output is restored.
- `query(formula=...)`: query formula and identity metadata.

## Exclusions and limits

The index is intentionally a lightweight filesystem index. It does not infer scientific validity, convergence, calculation type, pseudopotential identity, structure identity, or output completeness. Source paths must remain accessible for fetch; moving source directories requires a future explicit reindex.
