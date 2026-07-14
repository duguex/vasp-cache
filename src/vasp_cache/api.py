from __future__ import annotations

import logging
import re
import shutil
import time
from pathlib import Path
from typing import Any, Iterable

from vasp_cache.mapping import content_hash, load_mapping, mapping_digest
from vasp_cache.parse import summarize_calc
from vasp_cache.paths import get_project

logger = logging.getLogger(__name__)

_OUTPUT_NAMES = ("OUTCAR", "CONTCAR", "vasprun.xml")
_INPUT_NAMES = ("INCAR", "POSCAR", "KPOINTS")  # no POTCAR


def _detect_formula_task(src_dir: Path) -> tuple[str, str]:
    name = src_dir.name
    if "_mp-" in name:
        formula = name.split("_mp-", 1)[0]
        return formula, name
    formula = "unknown"
    for cand in (src_dir / "CONTCAR", src_dir / "POSCAR"):
        if cand.is_file():
            try:
                from pymatgen.core.structure import Structure

                formula = Structure.from_file(str(cand)).composition.reduced_formula
                break
            except Exception:
                continue
    return formula, name


def _outcar_usable(src_dir: Path) -> tuple[bool, float | None, bool]:
    """Return (usable, energy, converged).

    Reads only the tail (64 KB) of OUTCAR for bounded memory.
    """
    path = src_dir / "OUTCAR"
    if not path.is_file():
        alt = src_dir / "output" / "OUTCAR"
        path = alt if alt.is_file() else path
    if not path.is_file():
        return False, None, False
    # Tail-read for bounded memory (OUTCAR can be GB)
    tail_size = 65536  # 64 KB
    file_size = path.stat().st_size
    offset = max(0, file_size - tail_size)
    with open(path, "rb") as f:
        f.seek(offset)
        tail = f.read().decode("utf-8", errors="replace")
    energies = re.findall(r"free\s+energy\s+TOTEN\s*=\s*([-\d.]+)", tail)
    energy = float(energies[-1]) if energies else None
    converged = "General timing and accounting" in tail
    usable = converged or energy is not None
    return usable, energy, converged


def put(
    calc_dir: Path | str,
    *,
    formula: str | None = None,
    task_name: str | None = None,
    store_inputs: bool = True,
    include: Iterable[str] = (),
) -> str | None:
    calc_dir = Path(calc_dir)
    usable, energy, converged = _outcar_usable(calc_dir)
    if not usable:
        logger.debug("skip put %s: no usable OUTCAR", calc_dir)
        return None

    ch = content_hash(calc_dir)
    f, tn = _detect_formula_task(calc_dir)
    formula = formula or f
    task_name = task_name or tn

    project = get_project()
    job = project.open_job({"content_hash": ch}).init()

    # outputs
    for name in _OUTPUT_NAMES:
        src = calc_dir / name
        if src.is_file():
            shutil.copy2(src, job.fn(name))
    if not Path(job.fn("CONTCAR")).is_file() and (calc_dir / "POSCAR").is_file():
        shutil.copy2(calc_dir / "POSCAR", job.fn("CONTCAR"))

    if store_inputs:
        for name in _INPUT_NAMES:
            src = calc_dir / name
            if src.is_file():
                shutil.copy2(src, job.fn(name))

    for name in include:
        src = calc_dir / name
        if src.is_file():
            shutil.copy2(src, job.fn(name))

    # mapping audit fields
    m = load_mapping()
    job.doc["profile_id"] = m.get("profile_id", "default")
    job.doc["key_generation"] = m["key_generation"]
    job.doc["mapping_digest"] = mapping_digest(calc_dir, mapping=m)

    # rich doc via summarize_calc
    summary = summarize_calc(calc_dir)
    for k, v in summary.items():
        job.doc[k] = v
    job.doc["formula"] = formula
    job.doc["task_name"] = task_name
    job.doc["source_dir"] = str(calc_dir.resolve())
    job.doc["cached_at"] = time.time()
    return ch


def has(input_dir: Path | str) -> bool:
    input_dir = Path(input_dir)
    ch = content_hash(input_dir)
    project = get_project()
    job = project.open_job({"content_hash": ch})
    if job not in project:
        return False
    return Path(job.fn("OUTCAR")).is_file()


def fetch(input_dir: Path | str) -> bool:
    input_dir = Path(input_dir)
    if not has(input_dir):
        return False
    ch = content_hash(input_dir)
    job = get_project().open_job({"content_hash": ch})
    restored = False
    for name in _OUTPUT_NAMES:
        src = Path(job.fn(name))
        if src.is_file():
            shutil.copy2(src, input_dir / name)
            if name == "OUTCAR":
                restored = True
    return restored
