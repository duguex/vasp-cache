"""Structured extraction from OUTCAR and vasprun.xml via pymatgen."""

from __future__ import annotations

import zlib
from pathlib import Path
from typing import Any


def _compress(data: bytes) -> bytes:
    return zlib.compress(data, level=6)


def _decompress(data: bytes) -> bytes:
    return zlib.decompress(data)


def _extract_outcar(path: Path) -> dict[str, Any]:
    """Extract fields from original OUTCAR via pymatgen.Outcar."""
    result: dict[str, Any] = {
        "final_energy": None, "total_mag": None,
        "electrostatic_potentials": None,
    }
    try:
        from pymatgen.io.vasp.outputs import Outcar
        o = Outcar(str(path))
        if o.final_energy is not None:
            result["final_energy"] = float(o.final_energy)
        if o.total_mag is not None:
            result["total_mag"] = float(o.total_mag)
        eps = o.electrostatic_potential
        if eps is not None:
            result["electrostatic_potentials"] = [float(p) for p in eps]
    except Exception:
        pass
    return result


def _extract_vasprun(path: Path) -> dict[str, Any]:
    """Extract fields from vasprun.xml via pymatgen.Vasprun."""
    result: dict[str, Any] = {
        "n_ionic_steps": None,
        "converged_ionic": None,
        "converged_electronic": None,
        "final_structure_json": None,
        "final_energy": None,
    }
    try:
        from pymatgen.io.vasp.outputs import Vasprun
        v = Vasprun(str(path), parse_dos=False, parse_eigen=False)
        result["n_ionic_steps"] = len(v.ionic_steps)
        result["converged_ionic"] = int(v.converged_ionic)
        result["converged_electronic"] = int(v.converged_electronic)
        final_s = v.final_structure
        result["final_structure_json"] = (
            final_s.as_dict() if final_s is not None else None
        )
        result["final_energy"] = (
            float(v.final_energy) if v.final_energy is not None else None
        )
    except Exception:
        pass
    return result
