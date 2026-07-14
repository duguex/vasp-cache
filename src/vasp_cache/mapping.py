"""Mapping Profile — profile-driven hard/soft VASP input fingerprint.

A Mapping Profile controls which INCAR keys are *hard* (affect the mapping
digest used for cache dedup) vs *soft* (affect only a separate soft vector
used for ranking/tuning queries).

The default profile is legacy-compatible with ``vasp_sop``.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from vasp_cache.fingerprint import (
    _incar_fingerprint,
    _potcar_fingerprint,
    _structure_tag,
)

# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

_DEFAULT_MAPPING_PATH = Path(__file__).parent / "data" / "mapping.default.yaml"


def load_mapping(path: str | Path | None = None) -> dict[str, Any]:
    """Load a Mapping Profile.

    Parameters
    ----------
    path :
        * ``None`` — load the built-in default profile.
        * ``str | Path`` — load YAML from a custom file path.

    Returns
    -------
    dict
        Profile dictionary with keys ``key_generation``, ``hard``, ``soft``.
    """
    if path is None:
        path = _DEFAULT_MAPPING_PATH

    import yaml

    with open(path) as f:
        mapping = yaml.safe_load(f)

    # Enforce key-generation bump policy for non-default mappings
    if path.resolve() != _DEFAULT_MAPPING_PATH.resolve():
        _validate_key_generation(mapping)

    return mapping
# ---------------------------------------------------------------------------
# Key-generation bump policy
# ---------------------------------------------------------------------------

_BUILTIN_DEFAULT: dict[str, Any] | None = None


def _critical_section(mapping: dict[str, Any]) -> dict[str, Any]:
    """Extract the hard (critical) fields for equality comparison.

    The critical section controls which inputs affect the mapping digest.
    Changing any of these relative to the default profile requires a
    ``key_generation`` bump.
    """
    hard = mapping.get("hard", {})
    return {
        "structure": hard.get("structure", True),
        "kpoints": hard.get("kpoints", True),
        "potcar": hard.get("potcar", True),
        "incar": sorted(hard.get("incar", [])),
    }


def _load_builtin_default() -> dict[str, Any]:
    """Return the built-in default mapping (cached)."""
    global _BUILTIN_DEFAULT
    if _BUILTIN_DEFAULT is None:
        import yaml
        with open(_DEFAULT_MAPPING_PATH) as f:
            _BUILTIN_DEFAULT = yaml.safe_load(f)
    return _BUILTIN_DEFAULT


def _validate_key_generation(mapping: dict[str, Any]) -> None:
    """Bump policy: critical edits require ``key_generation > default``.

    If the *critical* section of *mapping* (the ``hard`` fields that determine
    which inputs enter the mapping digest) differs from the built-in default,
    then ``key_generation`` **must** be strictly greater than the default's
    ``key_generation``.

    Soft-only changes — those affecting only ``soft.incar`` — do **not**
    require a bump.

    Raises
    ------
    ValueError
        When the critical section differs but ``key_generation`` was not bumped.
    """
    default = _load_builtin_default()
    default_cs = _critical_section(default)
    resolved_cs = _critical_section(mapping)

    if resolved_cs == default_cs:
        return  # Only soft fields changed — no bump needed.

    default_gen = default.get("key_generation", 1)
    resolved_gen = mapping.get("key_generation", 0)

    if resolved_gen <= default_gen:
        raise ValueError(
            f"Mapping profile changes critical fields (hard section: "
            f"structure / kpoints / potcar / incar keys) from the default, "
            f"but key_generation={resolved_gen} is not strictly greater than "
            f"the default's key_generation={default_gen}. "
            f"Set key_generation to at least {default_gen + 1}."
        )


# ---------------------------------------------------------------------------
# Hard mapping digest
# ---------------------------------------------------------------------------


def _compute_hard_body(
    src_dir: Path,
    mapping: dict[str, Any],
) -> str:
    """Legacy-style body computed with only *hard*-significant fields.

    Structure, kpoints, INCAR hard keys, and POTCAR are each conditionally
    included according to the mapping profile.
    """
    from pymatgen.io.vasp.inputs import Kpoints

    src_dir = Path(src_dir)
    hard = mapping.get("hard", {})

    # --- structure tag ---
    # hard.structure: geom_hash | formula | true | false
    struct_cfg = hard.get("structure", True)
    if struct_cfg in (False, "false", "none", "off", 0, "0"):
        struct_tag = "nostruct"
    else:
        method = "geom_hash" if struct_cfg is True else str(struct_cfg)
        # bare true kept as formula for backward custom YAMLs that set structure: true
        if struct_cfg is True:
            method = "formula"
        struct_tag = _structure_tag(src_dir, method=method)
    # --- kpoints tag ---
    kpoints_tag = "nokpt"
    if hard.get("kpoints", True):
        kpoints_path = src_dir / "KPOINTS"
        if kpoints_path.is_file():
            try:
                kpts = Kpoints.from_file(str(kpoints_path))
                style = kpts.style
                grid = kpts.kpts[0] if kpts.kpts else (0, 0, 0)
                if style == Kpoints.supported_modes.Gamma and max(grid) <= 1:
                    kpoints_tag = "gamma"
                elif style == Kpoints.supported_modes.Line_mode:
                    kpoints_tag = "band-structure"
                else:
                    kpoints_tag = "".join(str(k) for k in grid[:3])
            except Exception:
                pass

    # --- INCAR fingerprint (hard keys only) ---
    incar_keys = tuple(hard.get("incar", []))
    incar_fp = (
        _incar_fingerprint(src_dir, keys=incar_keys)
        if incar_keys
        else "default"
    )

    # --- POTCAR fingerprint ---
    if hard.get("potcar", True):
        potcar_fp = _potcar_fingerprint(src_dir)
    else:
        # Not part of identity: fixed token so missing POTCAR is irrelevant
        potcar_fp = "default"

    return f"{struct_tag}_{kpoints_tag}_{incar_fp}_{potcar_fp}"


def mapping_digest(
    src_dir: str | Path,
    mapping: dict[str, Any] | str | Path | None = None,
) -> str:
    """Hard mapping digest with key-generation prefix.

    ``f"{key_generation}:{body}"`` — the body includes only fields marked
    as *hard* in the profile.  Soft-only changes leave this digest unchanged.
    """
    src_dir = Path(src_dir)

    if mapping is None:
        resolved = load_mapping()
    elif isinstance(mapping, (str, Path)):
        resolved = load_mapping(mapping)
    else:
        resolved = mapping

    # Enforce key-generation bump policy (catches raw dicts passed directly)
    _validate_key_generation(resolved)

    body = _compute_hard_body(src_dir, resolved)
    return f"{resolved['key_generation']}:{body}"


def content_hash(
    src_dir: str | Path,
    mapping: dict[str, Any] | str | Path | None = None,
) -> str:
    """Profile-driven content hash (alias for ``mapping_digest``).

    When no *mapping* is provided the **default** profile is used, which
    prepends ``1:`` to the legacy body — making it distinguishable from
    the bare fingerprint produced by ``vasp_cache.fingerprint.content_hash``.
    """
    return mapping_digest(src_dir, mapping=mapping)


# ---------------------------------------------------------------------------
# Soft vector API
# ---------------------------------------------------------------------------


def soft_vector(
    src_dir: str | Path,
    mapping: dict[str, Any] | str | Path | None = None,
) -> dict[str, Any]:
    """Extract soft INCAR values as a dict.

    Only keys listed in the profile ``soft.incar`` section are included.
    Keys absent from INCAR get ``None``.
    """
    src_dir = Path(src_dir)

    if mapping is None:
        resolved = load_mapping()
    elif isinstance(mapping, (str, Path)):
        resolved = load_mapping(mapping)
    else:
        resolved = mapping

    from pymatgen.io.vasp.inputs import Incar

    incar_path = src_dir / "INCAR"
    if not incar_path.is_file():
        return {}

    try:
        incar = Incar.from_file(str(incar_path))
    except Exception:
        return {}

    soft_keys = resolved.get("soft", {}).get("incar", [])
    return {k: incar.get(k) for k in soft_keys}


def soft_distance(v1: dict[str, Any], v2: dict[str, Any]) -> float:
    """Euclidean distance between two soft vectors.

    Missing keys and non-numeric values are treated as ``0``.
    """
    all_keys = sorted(set(v1) | set(v2))
    if not all_keys:
        return 0.0

    vec_a: list[float] = []
    vec_b: list[float] = []
    for k in all_keys:
        try:
            vec_a.append(float(v1.get(k)) if v1.get(k) is not None else 0.0)
        except (ValueError, TypeError):
            vec_a.append(0.0)
        try:
            vec_b.append(float(v2.get(k)) if v2.get(k) is not None else 0.0)
        except (ValueError, TypeError):
            vec_b.append(0.0)

    return math.sqrt(sum((x - y) ** 2 for x, y in zip(vec_a, vec_b)))
