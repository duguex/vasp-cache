# vasp-cache issues

Tracked gaps relative to project goals (2026-07-15).

## P0 — identity / correctness

| ID | Title |
|----|--------|
| [0001](0001-crystallographic-standardization.md) | Crystallographic standardization (Niggli/origin) |
| [0002](0002-poscar-vs-contcar-identity.md) | POSCAR vs CONTCAR identity policy |
| [0003](0003-potcar-fingerprint-strength.md) | Stronger POTCAR fingerprint |
| [0004](0004-incar-hard-key-audit.md) | INCAR hard-key audit |
| [0005](0005-geom-hash-precision-config.md) | geom_hash precision config |
| [0015](0015-policy-doc-identity-contract.md) | Identity contract policy doc |

## P1 — production / ops

| ID | Title |
|----|--------|
| [0006](0006-push-and-install-standardization.md) | Push remote + install path |
| [0007](0007-sop-full-regression.md) | Full vasp-sop regression |
| [0008](0008-legacy-jsonstore-cleanup.md) | Legacy JSONStore cleanup |
| [0009](0009-incremental-ingest-ops.md) | Incremental ingest ops |
| [0010](0010-concurrent-put-safety.md) | Concurrent put safety |
| [0014](0014-batch-cache-put-performance.md) | Batch cache put performance (sop) |

## P2 — enhancements

| ID | Title |
|----|--------|
| [0011](0011-soft-similarity-search.md) | Soft similarity search |
| [0012](0012-optional-large-blobs.md) | Optional large file archival |
| [0013](0013-ci-real-data-optional.md) | Optional CI real_data |

## Done / baseline (context, not open work)

- signac black-box package + CLI  
- Mapping Profile + key_generation  
- geom_hash default (gen 2) + full spin_defect reingest  
- real_data tests; MnPS3 archive removed  
