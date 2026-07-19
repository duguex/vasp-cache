# Structure standardization — NOT Niggli

**Date:** 2026-07-15  
**Status:** closed (2026-07-19). Niggli reduction does NOT apply to this project.

## Why Niggli is not applicable

1. **Supercell size matters.** A 2×2×2 supercell is a fundamentally different DFT calculation from a 1×1×1 primitive cell — different atom count, k-point mesh, computational cost. Niggli reduction would incorrectly identify them as "same calculation."

2. **Defect systems break periodicity.** The project handles vacancy, interstitial, and substitution calculations. These systems lack full translational symmetry. Niggli reduction assumes perfect crystal periodicity and would produce meaningless results.

3. **VASP identity is about calculation equivalence, not crystal equivalence.** Two physicists studying the same crystal at different cell sizes are doing different calculations. The cache must not conflate them.

## What IS implemented

- **6-permutation lattice vector ordering.** Row permutations {a,b,c} → {b,c,a} etc. preserve the same key. This handles equivalent VASP POSCAR descriptions of the same cell without changing the cell itself.
- **Structure.sort()** for deterministic atomic site ordering within the stored structure.
- Structure coordinates are NOT part of the identity hash (intentionally excluded as coarse identity).

## Related

- Issue #23: 5-layer identity (structure excluded from hash)
- Lattice normalization: `normalize_lattice()` in index.py