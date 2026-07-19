"""5-layer identity: formula + INCAR + KPOINTS + POTCAR + lattice."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from itertools import permutations
from pathlib import Path
from typing import Any

from vasp_cache.errors import IdentityInputError


@dataclass(frozen=True)
class Identity:
    key: str
    formula: str
    incar: dict[str, str]
    structure_json: str
    kpoints: dict[str, Any]
    potcar: dict[str, Any]
    lattice: dict[str, Any]


def normalize_incar(path: Path | str) -> dict[str, str]:
    """Return sorted canonical INCAR dict, preserving value text."""
    path = Path(path)
    if not path.is_file():
        raise IdentityInputError(f"identity requires INCAR: {path}")
    text = path.read_text("utf-8")
    values: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "!", "//")):
            continue
        delim = "=" if "=" in stripped else ";"
        if delim not in stripped:
            continue
        key, _, val = stripped.partition(delim)
        key = key.strip().upper()
        val = val.strip()
        for cm in (" #", "\t#", " !", "\t!"):
            if cm in val:
                val = val[:val.index(cm)].strip()
                break
        val = " ".join(val.split())
        if key and val:
            values[key] = val
    if not values:
        raise IdentityInputError(f"INCAR contains no parameters: {path}")
    return dict(sorted(values.items()))


def normalize_kpoints(path: Path | str) -> dict[str, Any]:
    """Canonical KPOINTS dict for identity and reconstruction."""
    path = Path(path)
    if not path.is_file():
        raise IdentityInputError(f"identity requires KPOINTS: {path}")
    try:
        from pymatgen.io.vasp.inputs import Kpoints
        k = Kpoints.from_file(str(path))
        return dict(k.as_dict())
    except Exception as exc:
        raise IdentityInputError(f"invalid KPOINTS: {path}") from exc


def normalize_potcar(path: Path | str) -> dict[str, Any]:
    """Extract POTCAR identity tokens."""
    path = Path(path)
    if not path.is_file():
        raise IdentityInputError(f"identity requires POTCAR: {path}")
    data = path.read_bytes()
    entries: list[dict[str, str]] = []
    for m in re.finditer(
        rb"TITEL\s*=\s*PAW(?:_PKJ)?_(\S+)\s+(\S+)\s*(?:(\d{2}\w{3}\d{4}))?",
        data,
    ):
        xc = m.group(1).decode("ascii")
        elem = m.group(2).decode("ascii")
        version = m.group(3).decode("ascii") if m.group(3) else ""
        entries.append({"element": elem, "xc": xc, "version": version})
    if not entries:
        raise IdentityInputError(f"POTCAR: no TITEL found: {path}")
    return {
        "entries": entries,
        "species": [e["element"] for e in entries],
        "xc": entries[0]["xc"],
    }


def normalize_lattice(structure_dict: dict[str, Any]) -> dict[str, Any]:
    """Canonical lattice parameters, invariant under basis permutation."""
    lat = structure_dict.get("lattice", {})
    mat = lat.get("matrix", [[1, 0, 0], [0, 1, 0], [0, 0, 1]])

    def _len(v):
        return math.sqrt(sum(x * x for x in v))

    def _angle(v1, v2):
        n1, n2 = _len(v1), _len(v2)
        if n1 == 0.0 or n2 == 0.0:
            raise IdentityInputError(
                "degenerate lattice: zero-length vector")
        dot = sum(x * y for x, y in zip(v1, v2))
        return math.degrees(math.acos(
            max(-1.0, min(1.0, dot / (n1 * n2)))
        ))

    def _params(a, b, c):
        return (
            round(_len(a), 3), round(_len(b), 3), round(_len(c), 3),
            round(_angle(b, c), 1),
            round(_angle(a, c), 1),
            round(_angle(a, b), 1),
        )

    # enumerate 6 permutations of lattice vectors, pick lexicographically smallest
    best = None
    for (i, j, k) in permutations([0, 1, 2]):
        params = _params(mat[i], mat[j], mat[k])
        if best is None or params < best:
            best = params

    return {"a": best[0], "b": best[1], "c": best[2],
            "alpha": best[3], "beta": best[4], "gamma": best[5]}


def _structure_from_poscar(path: Path | str) -> tuple[str, str]:
    path = Path(path)
    if not path.is_file():
        raise IdentityInputError(f"identity requires POSCAR: {path}")
    try:
        from pymatgen.core.structure import Structure
        structure = Structure.from_file(str(path))
    except Exception as exc:
        raise IdentityInputError(f"invalid POSCAR: {path}") from exc
    formula = structure.composition.reduced_formula
    if not formula:
        raise IdentityInputError(f"POSCAR has no chemical formula: {path}")
    structure.sort()
    structure_json = json.dumps(
        structure.as_dict(), sort_keys=True, default=str,
    )
    return formula, structure_json


def identity_for_directory(directory: Path | str) -> Identity:
    directory = Path(directory)
    formula, structure_json = _structure_from_poscar(directory / "POSCAR")
    incar = normalize_incar(directory / "INCAR")
    kpoints = normalize_kpoints(directory / "KPOINTS")
    potcar = normalize_potcar(directory / "POTCAR")
    lattice = normalize_lattice(json.loads(structure_json))
    payload = json.dumps(
        {"formula": formula, "incar": incar,
         "kpoints": kpoints, "potcar": potcar, "lattice": lattice},
        ensure_ascii=True, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return Identity(
        hashlib.sha256(payload).hexdigest(), formula, incar, structure_json,
        kpoints, potcar, lattice,
    )
