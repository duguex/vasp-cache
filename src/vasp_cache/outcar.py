"""OUTCAR parser + serializer for spec §4.1."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_TIMING_MARK = "General timing and accounting"
_TAG_RE = re.compile(r"^\s*(\w+)\s*=\s*(.+)", re.M)
_FORCE_HDR = re.compile(
    r"POSITION\s+TOTAL-FORCE \(eV/Angst\)\n\s*-+\n(.*?)\n\s*-+", re.DOTALL
)
_FORCE_LINE = re.compile(
    r"^\s*([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+"
    r"([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)"
)


def parse(path: Path | str) -> dict[str, Any]:
    path = Path(path)
    text = path.read_text(errors="replace")

    from pymatgen.io.vasp.outputs import Outcar
    outcar = Outcar(str(path))

    final = outcar.final_energy
    if final is None:
        raise ValueError("final_energy parse failed")

    timing = _TIMING_MARK in text
    if not timing:
        raise ValueError("timing marker not found")

    params = _parse_run_tags(text)
    forces = _parse_forces(text)
    if not forces:
        raise ValueError("no TOTAL-FORCE blocks found")

    return {
        "final_energy": final,
        "timing_found": timing,
        "run_params": params,
        "total_forces": forces,
    }


def _parse_run_tags(text: str) -> dict[str, float | int | str | None]:
    keys = ["NSW", "IBRION", "EDIFFG", "ISIF", "ENCUT",
            "PREC", "ISMEAR", "SIGMA", "ISPIN"]
    result: dict[str, Any] = {k: None for k in keys}
    head = text[:65536]
    tail = text[-8192:]
    for section in (head, tail):
        for m in _TAG_RE.finditer(section):
            k = m.group(1).upper()
            if k in result and result[k] is None:
                raw = m.group(2).strip().split()[0]
                try:
                    result[k] = (float(raw) if "." in raw
                                 or "e" in raw.lower() else int(raw))
                except ValueError:
                    result[k] = raw
    return result


def _parse_forces(text: str) -> list[dict[str, Any]]:
    blocks = []
    for step, m in enumerate(_FORCE_HDR.finditer(text)):
        atoms = []
        for line in m.group(1).strip().split("\n"):
            fm = _FORCE_LINE.match(line)
            if fm:
                vals = [float(fm.group(i)) for i in range(1, 7)]
                atoms.append({
                    "px": vals[0], "py": vals[1], "pz": vals[2],
                    "fx": vals[3], "fy": vals[4], "fz": vals[5],
                })
        if atoms:
            blocks.append({"step": step, "atoms": atoms})
    return blocks


def serialize(data: dict[str, Any]) -> str:
    lines = []

    params = data["run_params"]
    for tag in ("NSW", "IBRION", "EDIFFG", "ISIF", "ENCUT",
                "PREC", "ISMEAR", "SIGMA", "ISPIN"):
        v = params.get(tag)
        if v is not None:
            lines.append(f"   {tag} = {v}")

    for block in data["total_forces"]:
        lines.append(
            " POSITION                                       "
            "TOTAL-FORCE (eV/Angst)"
        )
        lines.append(" " + "-" * 83)
        for a in block["atoms"]:
            lines.append(
                f" {a['px']:>12.6f} {a['py']:>12.6f} {a['pz']:>12.6f} "
                f"{a['fx']:>12.6f} {a['fy']:>12.6f} {a['fz']:>12.6f}"
            )
        lines.append(" " + "-" * 83)

    e = data["final_energy"]
    lines.append(f"  free  energy   TOTEN  =     {e:.8f} eV")
    lines.append("")
    lines.append(" General timing and accounting")
    lines.append("")

    return "\n".join(lines)
