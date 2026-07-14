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

from vasp_cache.fingerprint import _incar_fingerprint, _potcar_fingerprint

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
        return yaml.safe_load(f)


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
    from pymatgen.core.structure import Structure
    from pymatgen.io.vasp.inputs import Kpoints

    src_dir = Path(src_dir)
    hard = mapping.get("hard", {})

    # --- structure tag ---
    struct_tag = "unknown"
    if hard.get("structure", True):
        for cand in (src_dir / "CONTCAR", src_dir / "POSCAR"):
            if cand.is_file():
                try:
                    struct = Structure.from_file(str(cand))
                    struct_tag = struct.composition.formula.replace(" ", "")
                    break
                except Exception:
                    continue

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
    potcar_fp = "nopot"
    if hard.get("potcar", True):
        potcar_fp = _potcar_fingerprint(src_dir)

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
