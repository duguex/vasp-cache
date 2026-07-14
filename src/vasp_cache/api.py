from __future__ import annotations

import logging
import re
import shutil
import time
from pathlib import Path
from typing import Any, Iterable

from vasp_cache.mapping import content_hash as compute_content_hash, load_mapping, mapping_digest
from vasp_cache.parse import MAX_LATTICE, summarize_calc
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
    usable, _, _ = _outcar_usable(calc_dir)
    if not usable:
        logger.debug("skip put %s: no usable OUTCAR", calc_dir)
        return None

    # Summarize early to check lattice limit; reuse dict later
    summary = summarize_calc(calc_dir)
    if MAX_LATTICE is not None and summary.get("max_abc", 0) > MAX_LATTICE:
        logger.debug(
            "skip put %s: max_abc %.1f > MAX_LATTICE %.1f",
            calc_dir,
            summary["max_abc"],
            MAX_LATTICE,
        )
        return None

    ch = compute_content_hash(calc_dir)
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

    # rich doc (reuse pre-computed summary)
    for k, v in summary.items():
        job.doc[k] = v
    job.doc["formula"] = formula
    job.doc["task_name"] = task_name
    job.doc["source_dir"] = str(calc_dir.resolve())
    job.doc["cached_at"] = time.time()
    return ch


def has(input_dir: Path | str) -> bool:
    input_dir = Path(input_dir)
    ch = compute_content_hash(input_dir)
    project = get_project()
    job = project.open_job({"content_hash": ch})
    if job not in project:
        return False
    return Path(job.fn("OUTCAR")).is_file()


def fetch(input_dir: Path | str) -> bool:
    input_dir = Path(input_dir)
    if not has(input_dir):
        return False
    ch = compute_content_hash(input_dir)
    job = get_project().open_job({"content_hash": ch})
    restored = False
    for name in _OUTPUT_NAMES:
        src = Path(job.fn(name))
        if src.is_file():
            shutil.copy2(src, input_dir / name)
            if name == "OUTCAR":
                restored = True
    return restored


def _job_row(job) -> dict[str, Any]:
    row = dict(job.doc)
    row["content_hash"] = job.sp.get("content_hash")
    return row


def query(
    formula: str | None = None,
    functional: str | None = None,
    calc_type: str | None = None,
    tags_contains: str | None = None,
    bandgap_min: float | None = None,
    lattice_max: float | None = None,
    converged_only: bool = True,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Semantic query over job.document fields."""
    project = get_project()
    filt: dict[str, Any] = {}
    if formula:
        filt["doc.formula"] = formula
    if calc_type:
        filt["doc.calc_type"] = calc_type
    if bandgap_min is not None:
        filt["doc.bandgap"] = {"$gte": bandgap_min}
    if lattice_max is not None:
        filt["doc.max_abc"] = {"$lte": lattice_max}
    if converged_only:
        filt["doc.converged"] = True

    rows: list[dict[str, Any]] = []
    for job in project.find_jobs(filt if filt else None):
        row = _job_row(job)
        tags = str(row.get("tags") or "")
        if functional and functional not in tags:
            continue
        if tags_contains and tags_contains not in tags:
            continue
        rows.append(row)
        if len(rows) >= limit:
            break
    return rows


def list_entries(limit: int = 50) -> list[dict[str, Any]]:
    """Most recently cached entries (by cached_at if present)."""
    project = get_project()
    rows = [_job_row(job) for job in project]
    rows.sort(key=lambda r: float(r.get("cached_at") or 0), reverse=True)
    return rows[:limit]


def stats() -> dict[str, Any]:
    """Aggregate cache statistics."""
    project = get_project()
    n = 0
    formulas: set[str] = set()
    converged = 0
    for job in project:
        n += 1
        doc = job.doc
        if doc.get("formula"):
            formulas.add(str(doc["formula"]))
        if doc.get("converged"):
            converged += 1
    return {
        "entries": n,
        "formulas": len(formulas),
        "converged": converged,
    }


def get_meta(
    input_dir: Path | str | None = None,
    *,
    content_hash: str | None = None,
    formula: str | None = None,
    key: str | None = None,
) -> dict[str, Any] | None:
    """Return metadata for a cached calculation, or None."""
    project = get_project()
    if input_dir is not None:
        ch = compute_content_hash(Path(input_dir))
        job = project.open_job({"content_hash": ch})
        if job not in project:
            return None
        return _job_row(job)

    if content_hash is not None:
        job = project.open_job({"content_hash": content_hash})
        if job not in project:
            return None
        return _job_row(job)

    if formula is not None and key is not None:
        for job in project.find_jobs({"doc.formula": formula}):
            sp_ch = job.sp.get("content_hash")
            tn = job.doc.get("task_name")
            if key in (sp_ch, tn, f"{formula}_mp-{key}"):
                return _job_row(job)
        return None

    return None
