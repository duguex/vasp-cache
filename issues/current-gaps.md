# vasp-cache current gaps (2026-07-19)

v3 core architecture is sound. Remaining gaps:

## Identity correctness — RESOLVED in 513659d

~~Structure coordinates were included in the identity hash, causing false
misses from coordinate noise.~~ Fixed: 5-layer identity (formula, incar,
kpoints, potcar, lattice). Structure not hashed. Lattice rounding 0.001 Å / 0.1°.

## Engineering

| Gap | Severity | Note |
|-----|----------|------|
| No CI | P2 | 32 unit tests run manually |
| Concurrent safety | P1 | BEGIN IMMEDIATE added; WAL pending |
| Batch perf | P1 | Not measured |
| Archive export/import | P1 | Needs v3 rewrite |
| Metadata dump | P1 | query() partial only |

## Identity edge cases

| Gap | Severity | Note |
|-----|----------|------|
| POTCAR version regression test | P0 | species+XC+version parsed; no same-element/different-version test |
| Lattice precision | P0 | 0.001 Å/0.1° rounding hardcoded, not configurable |
## Not planned

- Niggli/primitive cell reduction — supercell size = different DFT calc
- Origin standardization — structure not in identity hash
- Mapping profiles / key_generation — removed in v3