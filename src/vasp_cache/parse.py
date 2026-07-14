"""VASP calculation directory summary — extract energy, structure, tags.

Tries ``emmet`` TaskDoc first, falls back to direct regex + pymatgen parsing.
"""

from __future__ import annotations

import logging
import re as _re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: Skip calculations whose max lattice vector exceeds this (|None| to disable).
MAX_LATTICE: float | None = 25.0


# ---------------------------------------------------------------------------
# Tag extraction helpers
# ---------------------------------------------------------------------------


def _extract_tags(
    incar: Any = None,
    kpoints: Any = None,
    structure: Any = None,
    sga: Any = None,
) -> str:
    """Build a comma-separated tag string from INCAR / KPOINTS / structure.

    Ported from ``vasp_sop.core.cache._extract_tags``.
    """
    from pymatgen.io.vasp.inputs import Incar, Kpoints

    tags: list[str] = []

    if structure is not None:
        comp = structure.composition
        tags.append(comp.formula.replace(" ", ""))

    if kpoints is not None:
        style = kpoints.style
        kpts = kpoints.kpts[0] if kpoints.kpts else (0, 0, 0)
        if style == Kpoints.supported_modes.Gamma and max(kpts) <= 1:
            tags.append("gamma")
        elif style == Kpoints.supported_modes.Line_mode:
            tags.append("band-structure")
        else:
            tags.append("".join(str(k) for k in kpts[:3]))

    if incar is None:
        return ",".join(tags) if tags else ""

    gga = (incar.get("GGA") or "").strip().upper()
    metagga = (incar.get("METAGGA") or "").strip().upper()
    hfcalc = bool(incar.get("LHFCALC"))
    hfscreen = incar.get("HFSCREEN", 0)
    ldau = bool(incar.get("LDAU"))
    ivdw = incar.get("IVDW", 0)
    spin = incar.get("ISPIN", 1)
    lsorbit = bool(incar.get("LSORBIT"))
    ibrion = incar.get("IBRION", 0)
    nfree = incar.get("NFREE", 0)
    lepsilon = bool(incar.get("LEPSILON"))
    loptics = bool(incar.get("LOPTICS"))
    lcalcpol = bool(incar.get("LCALCPOL"))
    ldipol = bool(incar.get("LDIPOL"))
    encut = incar.get("ENCUT", 0)

    if gga == "PE":
        tags.append("PBE")
    elif gga == "PS":
        tags.append("PBEsol")
    elif gga:
        tags.append(gga)
    if metagga == "SCAN":
        tags.append("SCAN")
    elif metagga == "R2SCAN":
        tags.append("R2SCAN")
    elif metagga:
        tags.append(f"metaGGA({metagga})")

    if encut:
        if encut >= 600:
            tags.append("high-encut")
        elif encut <= 300:
            tags.append("low-encut")

    if hfcalc:
        tags.append("hybrid")
        tags.append("HSE" if hfscreen > 0 else "PBE0")

    if ldau:
        tags.append("DFT+U")
    if ivdw:
        tags.append("DFT-D")

    if spin == 2:
        tags.append("spin")
    if lsorbit:
        tags.append("spin-orbit")

    if ibrion in (5, 6, 7, 8) or nfree >= 2:
        tags.append("phonon")
    if loptics:
        tags.append("optics")
    if lepsilon:
        tags.append("dielectric")
    if lcalcpol:
        tags.append("polarization")
    if ldipol:
        tags.append("dipole")

    return ",".join(tags) if tags else "default"


# ---------------------------------------------------------------------------
# Main summary
# ---------------------------------------------------------------------------


def summarize_calc(src_dir: Path) -> dict[str, Any]:
    """Parse a VASP calculation directory and return a summary dict.

    Tries ``emmet.core.tasks.TaskDoc.from_directory`` first; falls back to
    direct regex + pymatgen parsing when TaskDoc is unavailable or fails.

    Returns keys:
        converged, total_energy, bandgap, formula_pretty, nsites,
        space_group, a, b, c, max_abc, calc_type, tags, parsed_by
    """
    outcar_path = src_dir / "OUTCAR"
    if not outcar_path.is_file():
        return {
            "converged": False,
            "total_energy": None,
            "bandgap": None,
            "formula_pretty": None,
            "nsites": None,
            "space_group": None,
            "a": 0.0,
            "b": 0.0,
            "c": 0.0,
            "max_abc": 0.0,
            "calc_type": None,
            "tags": "",
            "parsed_by": "fallback",
        }

    # -- Try TaskDoc.from_directory first --------------------------------
    try:
        from emmet.core.tasks import TaskDoc  # type: ignore[import-untyped]

        doc = TaskDoc.from_directory(src_dir, store_additional_json=False)

        a, b, c = (0.0, 0.0, 0.0)
        if doc.output and doc.output.structure:
            a, b, c = doc.output.structure.lattice.abc

        result = {
            "converged": doc.state == "successful",
            "total_energy": doc.output.energy if doc.output else None,
            "bandgap": doc.output.bandgap if doc.output else None,
            "formula_pretty": doc.formula_pretty,
            "nsites": doc.nsites,
            "space_group": doc.symmetry.crystal_system if doc.symmetry else None,
            "a": a,
            "b": b,
            "c": c,
            "max_abc": max(a, b, c),
            "calc_type": str(doc.calc_type) if doc.calc_type else None,
            "tags": _tags_from_doc(doc),
            "parsed_by": "TaskDoc",
        }
        if result["total_energy"] is not None:
            return result
    except Exception as exc:
        logger.debug(
            "TaskDoc parse failed for %s: %s, falling back to regex", src_dir, exc
        )

    # -- Regex fallback ---------------------------------------------------
    from pymatgen.io.vasp.inputs import Incar, Kpoints
    from pymatgen.io.vasp.outputs import Outcar  # noqa: F401 — keep importable
    from pymatgen.core.structure import Structure
    # Tail-read OUTCAR for bounded memory (files can be GB)
    tail_size = 65536  # 64 KB
    file_size = outcar_path.stat().st_size
    offset = max(0, file_size - tail_size)
    with open(outcar_path, "rb") as f:
        f.seek(offset)
        text = f.read().decode("utf-8", errors="replace")
    total_energy: float | None = None
    converged = False
    all_e = _re.findall(r"free\s+energy\s+TOTEN\s*=\s*([-\d.]+)", text)
    if all_e:
        total_energy = float(all_e[-1])
    if "General timing and accounting" in text[-4096:]:
        converged = True

    n_sites: int | None = None
    formula_pretty: str | None = None
    space_group: str | None = None
    struct: Structure | None = None
    _sga: SpacegroupAnalyzer | None = None
    a, b, c = 0.0, 0.0, 0.0
    for cand in (src_dir / "CONTCAR", src_dir / "POSCAR"):
        if cand.is_file():
            try:
                struct = Structure.from_file(str(cand))
                n_sites = struct.num_sites
                formula_pretty = struct.composition.reduced_formula
                a, b, c = struct.lattice.abc
            except Exception:
                continue
            try:
                _sga = SpacegroupAnalyzer(struct, symprec=0.1)
                space_group = _sga.get_space_group_symbol()
            except Exception:
                pass  # space_group stays None
            break

    incar: Incar | None = None
    incar_path = src_dir / "INCAR"
    if incar_path.is_file():
        try:
            incar = Incar.from_file(str(incar_path))
        except Exception:
            pass

    kpts: Kpoints | None = None
    tags = _extract_tags(incar=incar, kpoints=kpts, structure=struct, sga=_sga)

    return {
        "converged": converged,
        "total_energy": total_energy,
        "bandgap": None,
        "formula_pretty": formula_pretty,
        "nsites": n_sites,
        "space_group": space_group,
        "a": a,
        "b": b,
        "c": c,
        "max_abc": max(a, b, c),
        "calc_type": None,
        "tags": tags,
        "parsed_by": "regex",
    }


def _tags_from_doc(doc) -> str:
    """Extract a tag string from a TaskDoc object."""
    tags: list[str] = []
    run_type = getattr(doc, "run_type", None)
    calc_type = getattr(doc, "calc_type", None)

    tag_map = {"GGA": "PBE", "GGA+U": "DFT+U", "HSE": "HSE"}
    if run_type and run_type.value in tag_map:
        tags.append(tag_map[run_type.value])
    elif run_type:
        tags.append(str(run_type.value))

    ct = str(calc_type) if calc_type else ""
    if "Static" in ct:
        tags.append("static")
    elif "Relax" in ct:
        tags.append("relax")

    if hasattr(doc, "symmetry") and doc.symmetry:
        tags.append(
            doc.symmetry.crystal_system.lower()
            if hasattr(doc.symmetry, "crystal_system")
            else "unknown"
        )

    return ",".join(tags) if tags else "default"
