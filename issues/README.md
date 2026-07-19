# vasp-cache issues

Local trackers + GitHub: https://github.com/duguex/vasp-cache/issues

## v3 status (2026-07-19)

After v3 rewrite (BLOB + structured extracts, single index.sqlite).

### RESOLVED — v3 addresses the concern

| Local | GitHub | Title | How |
|-------|--------|-------|-----|
| 0002 | #3 | POSCAR vs CONTCAR identity | POSCAR in 5-layer hash, CONTCAR as BLOB |
| 0004 | #5 | INCAR hard-key audit | all INCAR keys normalized into identity |
| 0015 | #16 | Identity contract policy doc | spec §1 + USER.md document 5 layers |

### STALE — references deleted modules/features

| Local | GitHub | Title | Reason |
|-------|--------|-------|--------|
| 0006 | #7 | Push + install standardization | ops-level, not v3-specific |
| 0008 | #9 | Legacy JSONStore cleanup | done |
| 0019 | #20 | JSONStore auto-migrate doc | obsolete: JSONStore removed in v3 |
| 0021 | #22 | Sampled single-point policy | provenance concept removed |
| 0022 | — | CAS integrity audit | CAS backend deleted |

### OPEN — v3 does not address

| Local | GitHub | Title | Priority | Note |
|-------|--------|-------|----------|------|
| 0001 | #2 | Niggli/origin standardization | P0 | only `Structure.sort()`, no reduction |
| 0003 | #4 | POTCAR fingerprint strength | P0 | TITEL species+XC+version parsed; missing regression test |
| 0005 | #6 | Configurable geom_hash precision | P0 | lattice tolerance hardcoded (0.001Å/0.1°) |
| 0007 | #8 | Full vasp-sop regression | P1 | not systematically tested |
| 0009 | #10 | Incremental ingest ops | P1 | rebuild only, no incremental put |
| 0010 | #11 | Concurrent put safety | P1 | BEGIN IMMEDIATE added; WAL/busy-timeout pending |
| 0011 | #12 | Soft similarity search | P2 | not implemented |
| 0012 | #13 | Optional large file archival | P2 | not implemented |
| 0013 | #14 | CI with real data | P2 | not configured |
| 0014 | #15 | Batch put performance | P1 | not measured |
| 0016 | #17 | Archive export/import | P1 | needs v3 rewrite |
| 0017 | #18 | Metadata dump JSONL | P1 | query() partial, no dedicated dump tool |
| 0018 | #19 | I/E/M E2E tests | P0 | not written for v3 |
| 0020 | #21 | put conflict modes (strict/skip/overwrite) | P0 | convergence-priority only |

Labels: `P0` / `P1` / `P2`, plus `identity` / `ops` / `enhancement` / `documentation`.
