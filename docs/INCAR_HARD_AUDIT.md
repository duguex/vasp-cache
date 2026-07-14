# INCAR hard-key audit (issue #5)

**Date:** 2026-07-15  
**Decision:** Expand hard set; **key_generation 3 → 4**.  
**Lab evidence:** prod tags dominated by spin / PBEsol / defect supercells; rare hybrid; some DFT+U.

## Principle

Hard = **physically different result if changed**, for the same structure+KPOINTS.  
Soft = numerical/convergence knobs that should not split the cache.  
Ignore = noise or covered elsewhere.

## Table

| Key | Role | Decision | Notes |
|-----|------|----------|--------|
| ENCUT | plane-wave cutoff | **hard** | keep |
| PREC | precision preset | **hard** | keep |
| ISMEAR / SIGMA | smearing | **hard** | keep |
| ISIF | stress/relax mode | **hard** | keep |
| GGA | functional family | **hard** | PBEsol vs PBE |
| METAGGA | SCAN/r2SCAN… | **hard** | keep |
| LASPH | aspherical | **hard** | keep |
| LDAU / LDAUTYPE / LDAUU / LDAUJ / LDAUL | DFT+U | **hard** | keep |
| IVDW | vdW flavor | **hard** | keep |
| LHFCALC / HFSCREEN | hybrid | **hard** | keep |
| AEXX | hybrid mix | **hard** | **add** (HSE/PBE0) |
| ISPIN | spin polarized | **hard** | keep; lab is spin-heavy |
| LSORBIT | SOC | **hard** | keep |
| LNONCOLLINEAR | noncollinear | **hard** | **add** |
| MAGMOM | initial/constraint mag | **hard** | **add** (defect spin) |
| NUPDOWN | fixed mag moment | **hard** | **add** |
| NELECT | electron count / charge | **hard** | **add** (charged defects) |
| LMAXMIX | mixer / U related | **hard** | **add** |
| NSW / NELM / NELMIN / EDIFF | SCF/ionic effort | **soft** | keep soft |
| EDIFFG | ionic stop | **soft** | soft |
| ALGO / LREAL / ADDGRID / ENAUG | numerics | **ignore** | rarely redefine “same calc” for cache |
| IBRION / POTIM | optimizer | **ignore** | path differs, end state keyed by structure |
| LWAVE / LCHARG | IO | **ignore** | |

## Prod snapshot (approx.)

- `spin` / PBEsol dominate tags  
- HSE rare; SOC/SCAN ~0 in tags  
- Defect-like formulas common → **NELECT / MAGMOM / NUPDOWN** matter more than hybrid extras  

## Generation bump

Hard set expanded ⇒ `key_generation: 4`.  
Rehash: `python scripts/rehash_meta_cas.py --root /mnt/shared/vasp_cache`.
