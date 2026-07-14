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
    """Extract POTCAR pseudopotential species tokens.

    Missing file → ``default`` (same convention as empty INCAR hard keys).
    Callers that disable hard.potcar never use this value.
    """
    potcar_path = src_dir / "POTCAR"
    if not potcar_path.is_file():
        return "default"
    try:
        text = potcar_path.read_text()
        pp_ids = re.findall(r"PAW_\w+\s+(\S+)", text)
        return ",".join(pp_ids) if pp_ids else "unknown"
    except Exception:
        return "unknown"


def _structure_tag(src_dir: Path, method: str | bool = "formula") -> str:
    """Structure contribution to the hard key.

    Parameters
    ----------
    method:
        ``"formula"`` / ``True`` — composition formula only (legacy, coarse).
        ``"geom_hash"`` — sha256 of rounded lattice + sites (recommended).
        ``False`` / ``"false"`` / ``"none"`` — omit (returns ``"nostruct"``).
    """
    if method in (False, "false", "none", "off", 0, "0"):
        return "nostruct"

    from pymatgen.core.structure import Structure

    use_geom = method in ("geom_hash", "geometry", "geom", "structure_hash")
    struct = None
    for cand in (src_dir / "CONTCAR", src_dir / "POSCAR"):
        if cand.is_file():
            try:
                struct = Structure.from_file(str(cand))
                break
            except Exception:
                continue
    if struct is None:
        return "unknown"

    if not use_geom:
        # formula / True / anything else → legacy formula tag
        return struct.composition.formula.replace(" ", "")

    import hashlib
    import json

    lat = [[round(float(x), 6) for x in row] for row in struct.lattice.matrix.tolist()]
    sites = sorted(
        (
            str(site.specie),
            round(float(site.frac_coords[0]), 6),
            round(float(site.frac_coords[1]), 6),
            round(float(site.frac_coords[2]), 6),
        )
        for site in struct
    )
    payload = json.dumps({"lattice": lat, "sites": sites}, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


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
