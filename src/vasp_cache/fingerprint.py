"""Legacy VASP content fingerprint — input-hash matching vasp_sop semantics."""

from __future__ import annotations

import re
from pathlib import Path

_INCAR_FINGERPRINT_KEYS = (
    "ENCUT", "PREC", "ISMEAR", "SIGMA", "ISIF",
    "LDAU", "LDAUTYPE", "LDAUU", "LDAUJ", "LDAUL",
    "GGA", "IVDW", "LASPH", "METAGGA",
)


def _incar_fingerprint(src_dir: Path, keys: tuple[str, ...] = _INCAR_FINGERPRINT_KEYS) -> str:
    """Extract a deterministic fingerprint from selected INCAR keys."""
    incar_path = src_dir / "INCAR"
    if not incar_path.is_file():
        return "default"
    try:
        from pymatgen.io.vasp.inputs import Incar
        incar = Incar.from_file(str(incar_path))
    except Exception:
        return "default"
    parts = []
    for k in keys:
        v = incar.get(k)
        if v is not None:
            parts.append(f"{k}={v}")
    return "|".join(parts) if parts else "default"


def _potcar_fingerprint(src_dir: Path) -> str:
    """Extract POTCAR pseudopotential species tokens."""
    potcar_path = src_dir / "POTCAR"
    if not potcar_path.is_file():
        return "nopot"
    try:
        text = potcar_path.read_text()
        pp_ids = re.findall(r"PAW_\w+\s+(\S+)", text)
        return ",".join(pp_ids) if pp_ids else "unknown"
    except Exception:
        return "unknown"


def content_hash(src_dir: Path) -> str:
    """Deterministic fingerprint of VASP *inputs* in *src_dir*.

    This is the legacy hash without a key_generation prefix or mapping
    profile — matches vasp_sop semantics directly.
    """
    from pymatgen.core.structure import Structure
    from pymatgen.io.vasp.inputs import Kpoints

    src_dir = Path(src_dir)

    # --- structure tag ---
    struct_tag = "unknown"
    # CONTCAR preferred over POSCAR (reflects last completed geometry)
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

    # --- incar + potcar fingerprints ---
    incar_fp = _incar_fingerprint(src_dir)
    potcar_fp = _potcar_fingerprint(src_dir)

    return f"{struct_tag}_{kpoints_tag}_{incar_fp}_{potcar_fp}"
