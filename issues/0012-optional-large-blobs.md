# Optional archival of large VASP files

**Date:** 2026-07-15  
**Severity:** Low  
**Component:** `put(..., include=)`

## Status

Open. Default stores OUTCAR/CONTCAR/vasprun(+inputs); not WAVECAR/CHGCAR.

## Expected

- Document size impact  
- Profile or CLI flags: `--include CHGCAR,WAVECAR`  
- Maybe refuse WAVECAR over size limit  

## Acceptance

- Documented defaults + flag  
- Test include copies extra file  

## Related

- api.put `include` parameter
