# Equivalent Structure representations produce different identity keys

**Date:** 2026-07-19
**Type:** Feature request
**Severity:** P2 (blocks cross-project cache reuse for equivalent structures)

## Problem

Two `pymatgen.Structure` representations that are structurally equivalent
(`Structure.matches() == True`) produce different identity keys when their
crystallographic axes are permuted. This prevents cache hits across projects
that use the same material but with different axis ordering from MP.

## Minimal reproduction

```python
from pymatgen.core.structure import Structure
from vasp_cache.index import identity_for_directory
from pathlib import Path
import tempfile, shutil, os

# Create two directories with identical INCAR/KPOINTS/POTCAR
# but POSCARs that are axis-permuted variants of the same CsEuCl3 structure.
d1 = Path(tempfile.mkdtemp()) / "a"
d2 = Path(tempfile.mkdtemp()) / "b"
d1.mkdir(parents=True); d2.mkdir(parents=True)

# POSCAR 1: a=7.848, b=7.964, c=11.211
# POSCAR 2: a=7.964, b=11.211, c=7.848 (same lattice, permuted axes)

s1 = Structure.from_file("poscar_abc.txt")   # MP ordering
s2 = Structure.from_file("poscar_bca.txt")   # pymatgen-reordered after prepare_inputs

assert s1.matches(s2)  # True — pymatgen considers them equivalent

# Write identical INCAR, KPOINTS, POTCAR to both dirs
for f in ("INCAR", "KPOINTS", "POTCAR"):
    shutil.copy(shared / f, d1 / f)
    shutil.copy(shared / f, d2 / f)

shutil.copy(poscar_abc, d1 / "POSCAR")
shutil.copy(poscar_bca, d2 / "POSCAR")

id1 = identity_for_directory(d1)
id2 = identity_for_directory(d2)

assert id1.key != id2.key  # Different keys — cache miss
```

Root cause: `identity_for_directory` hashes `Structure.as_dict()` which includes
fractional coordinates. Axis permutation changes both lattice vectors AND atomic
positions in the dict, producing a different hash despite structural equivalence.

## Desired behavior

`identity_for_directory` should produce the same key for structures that
`pymatgen.Structure.matches()` considers equivalent. This could be achieved by
normalizing the structure representation (e.g., via `Structure.get_reduced_structure()`
or lattice standardization) before computing the structure hash.

## Impact

- vasp-sop: CPD target directory POSCAR (MP download) and structure_opt POSCAR
  (pymatgen-normalized after input generation) are axis-permuted variants of the
  same CsEuCl3 structure. Cache miss between them means structure_opt
  calculations must be re-run for every new project even though identical
  results exist in cache.
- Any workflow that passes structures through pymatgen (which may reorder axes
  during `Structure.from_file` → `Structure.to(fmt="poscar")`) will produce
  non-matching identities.

## Non-goals

- Lattice tolerance/soft matching (separate concern)
- Full symmetry-equivalence checking (too expensive for identity computation)