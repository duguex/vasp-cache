(v2 issue — references deleted modules/features; see issues/README.md for v3 status)

# Classify and guard unprovenanced sampled single-point calculations

**Date:** 2026-07-16  
**Severity:** High — wrong representative-result reuse  
**Component:** ingest, metadata, formula lookup, provenance  
**GitHub:** https://github.com/duguex/vasp-cache/issues/22

## Status

Open.

## Problem

The cache currently accepts a completed `OUTCAR` without reliable calculation
provenance. Exact geometry identity prevents structure-key collisions, but it
does not distinguish a reusable canonical calculation from an unprovenanced
random fixed-geometry single point.

Formula lookup is risky: `meta.query_entries()` orders rows by `cached_at DESC`,
and `get_meta(formula=...)` returns the first row. A recent sampled result can
therefore be presented as the representative material result.

`NSW=0` cannot identify random data: valid static energy or band calculations
also use `NSW=0`. INCAR alone cannot prove random provenance.

## Proposed policy

- Preserve canonical static calculations and converged ionic relaxations.
- Classify reliably detectable MD and phonon/finite-displacement modes
  explicitly, with a documented sampled-storage/query policy.
- Add an explicit provenance manifest or ingest option for `canonical`,
  `sampled`, and `unknown` roles.
- Do not silently promote unmarked sampled/unknown data to a canonical formula
  result; prefer skip/quarantine or explicit sampled opt-in.
- Keep exact-hash reuse for intentionally reproducible protocols.
- Preserve existing entries and exact `has`/`fetch` behavior. Any migration is
  non-destructive and marks legacy provenance as `unknown`.

## Acceptance criteria

- [ ] Canonical static (`NSW=0`) fixture is accepted and queryable.
- [ ] Canonical ionic relaxation (`IBRION=1/2`, effective `NSW>0`) is accepted;
      ionic convergence is separate from OUTCAR completion.
- [ ] `IBRION=3` is classified as damped-MD/ionic-dynamics, not ordinary
      relaxation.
- [ ] MD and phonon/finite-displacement handling and sampled policy are tested.
- [ ] Explicit `sampled` provenance is honored; unknown data is not canonical
      by default.
- [ ] No rule rejects all `NSW=0` static calculations.
- [ ] Formula lookup cannot silently select the newest sampled/unknown row as
      the representative result.
- [ ] Existing database entries and exact `has`/`fetch` remain usable.
- [ ] Tests cover effective INCAR defaults, provenance precedence, query
      filtering, and legacy entries.

## Non-goals

- Do not infer random perturbations solely from formula, path keywords, or
  current file modes.
- Do not delete the existing cache during classification.
- Do not require relaxation for every valid static or sampled calculation.

## Related implementation points

- `src/vasp_cache/api.py`: ingest and formula shortcut.
- `src/vasp_cache/meta.py`: `cached_at DESC` ordering and metadata fields.
- `src/vasp_cache/parse.py`: current completion checks.
- `docs/IDENTITY.md`: exact structure identity contract.
