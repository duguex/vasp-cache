"""Legacy VASP content fingerprint — input-hash matching vasp_sop semantics."""

from __future__ import annotations

import json
import re
from pathlib import Path

from vasp_cache.errors import IdentityInputError

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


def _as_int(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def input_protocol_identity(src_dir: Path) -> dict[str, object]:
    """Parse INCAR/POSCAR protocol inputs without reading outputs."""
    src_dir = Path(src_dir)
    poscar = src_dir / "POSCAR"
    if not poscar.is_file():
        raise IdentityInputError(f"identity requires POSCAR: {src_dir}")
    try:
        from pymatgen.core.structure import Structure

        Structure.from_file(str(poscar))
    except Exception as exc:
        raise IdentityInputError(f"invalid POSCAR: {poscar}") from exc

    incar_path = src_dir / "INCAR"
    if not incar_path.is_file():
        incar: dict[str, object] = {}
    else:
        try:
            from pymatgen.io.vasp.inputs import Incar

            incar = dict(Incar.from_file(str(incar_path)))
        except Exception as exc:
            raise IdentityInputError(f"invalid INCAR: {incar_path}") from exc

    nsw = _as_int(incar.get("NSW", 0))
    if nsw is None:
        raise IdentityInputError(f"invalid NSW in {incar_path}")
    raw_ibrion = incar.get("IBRION")
    ibrion = _as_int(raw_ibrion)
    if ibrion is None and raw_ibrion is None:
        ibrion = -1 if nsw <= 0 else 0
    if ibrion is None:
        raise IdentityInputError(f"invalid IBRION in {incar_path}")
    raw_isif = incar.get("ISIF")
    isif = _as_int(raw_isif)
    if isif is None and raw_isif is None:
        isif = 0 if ibrion == 0 or bool(incar.get("LHFCALC", False)) else 2
    if isif is None:
        raise IdentityInputError(f"invalid ISIF in {incar_path}")
    nfree = _as_int(incar.get("NFREE"))

    if ibrion in (5, 6, 7, 8):
        mode = "phonon"
    elif nsw > 0 and ibrion in (0, 3):
        mode = "md"
    elif nsw > 0 and ibrion in (1, 2):
        mode = "relaxation"
    elif nsw <= 0:
        mode = "static"
    else:
        mode = "unknown"
    return {
        "calc_mode": mode,
        "nsw": nsw,
        "ibrion": ibrion,
        "isif": isif,
        "nfree": nfree,
    }


def input_protocol_fingerprint(src_dir: Path) -> str:
    """Serialize the input-only protocol identity deterministically."""
    return json.dumps(
        input_protocol_identity(Path(src_dir)),
        sort_keys=True,
        separators=(",", ":"),
    )


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


def _structure_tag(
    src_dir: Path,
    method: str | bool = "formula",
    structure_file: str | None = None,
) -> str:
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
    candidates = (
        (src_dir / structure_file,)
        if structure_file is not None
        else (src_dir / "CONTCAR", src_dir / "POSCAR")
    )
    for cand in candidates:
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


def result_geometry_hash(src_dir: Path) -> str | None:
    """Return a CONTCAR geometry hash without affecting primary identity."""
    contcar = Path(src_dir) / "CONTCAR"
    if not contcar.is_file():
        return None
    value = _structure_tag(
        Path(src_dir), method="geom_hash", structure_file="CONTCAR"
    )
    return None if value == "unknown" else value


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
