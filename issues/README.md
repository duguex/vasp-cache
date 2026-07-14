# vasp-cache issues

Local markdown trackers + GitHub: https://github.com/duguex/vasp-cache/issues

| Local | GitHub | Title | Priority |
|-------|--------|-------|----------|
| [0001](0001-crystallographic-standardization.md) | [#2](https://github.com/duguex/vasp-cache/issues/2) | Structure standardization (Niggli / origin) | P0 |
| [0002](0002-poscar-vs-contcar-identity.md) | [#3](https://github.com/duguex/vasp-cache/issues/3) | POSCAR vs CONTCAR identity | P0 |
| [0003](0003-potcar-fingerprint-strength.md) | [#4](https://github.com/duguex/vasp-cache/issues/4) | Stronger POTCAR fingerprint | P0 |
| [0004](0004-incar-hard-key-audit.md) | [#5](https://github.com/duguex/vasp-cache/issues/5) | INCAR hard-key audit | P0 |
| [0005](0005-geom-hash-precision-config.md) | [#6](https://github.com/duguex/vasp-cache/issues/6) | geom_hash precision config | P0 |
| [0006](0006-push-and-install-standardization.md) | [#7](https://github.com/duguex/vasp-cache/issues/7) | Push + install standardization | P1 |
| [0007](0007-sop-full-regression.md) | [#8](https://github.com/duguex/vasp-cache/issues/8) | Full vasp-sop regression | P1 |
| [0008](0008-legacy-jsonstore-cleanup.md) | [#9](https://github.com/duguex/vasp-cache/issues/9) | Legacy JSONStore cleanup | P1 |
| [0009](0009-incremental-ingest-ops.md) | [#10](https://github.com/duguex/vasp-cache/issues/10) | Incremental ingest ops | P1 |
| [0010](0010-concurrent-put-safety.md) | [#11](https://github.com/duguex/vasp-cache/issues/11) | Concurrent put safety | P1 |
| [0011](0011-soft-similarity-search.md) | [#12](https://github.com/duguex/vasp-cache/issues/12) | Soft similarity search | P2 |
| [0012](0012-optional-large-blobs.md) | [#13](https://github.com/duguex/vasp-cache/issues/13) | Optional large file archival | P2 |
| [0013](0013-ci-real-data-optional.md) | [#14](https://github.com/duguex/vasp-cache/issues/14) | Optional CI real_data | P2 |
| [0014](0014-batch-cache-put-performance.md) | [#15](https://github.com/duguex/vasp-cache/issues/15) | Batch cache put performance | P1 |
| [0015](0015-policy-doc-identity-contract.md) | [#16](https://github.com/duguex/vasp-cache/issues/16) | Identity contract policy doc | P0 |
| [0016](0016-archive-export-import.md) | [#17](https://github.com/duguex/vasp-cache/issues/17) | Whole-cache archive export/import | P1 |
| [0017](0017-meta-dump-jsonl.md) | [#18](https://github.com/duguex/vasp-cache/issues/18) | Metadata dump JSONL | P1 |
| [0018](0018-ie-migrate-e2e-tests.md) | [#19](https://github.com/duguex/vasp-cache/issues/19) | I/E/M E2E tests | P0 |
| [0019](0019-jsonstore-no-auto-migrate-doc.md) | [#20](https://github.com/duguex/vasp-cache/issues/20) | Doc: no JSONStore auto-migrate | P1 |
| [0020](0020-put-conflict-policy.md) | [#21](https://github.com/duguex/vasp-cache/issues/21) | put conflict policy (key same, value differs) | P0 |

Labels: `P0` / `P1` / `P2`, plus `identity` / `ops` / `enhancement` / `documentation`.

## Baseline (done, not open)

- signac black-box package + CLI  
- Mapping Profile + key_generation  
- geom_hash default (gen 2) + full spin_defect reingest  
- real_data tests; MnPS3 archive removed  
- Single-calc put→fetch tested; **whole-DB I/E/M product still open (#17–#19)**  
