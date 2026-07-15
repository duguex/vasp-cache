"""Public cache API: put / has / fetch / query (CAS + SQLite backend)."""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Any, Iterable

from vasp_cache import cas, meta
from vasp_cache.mapping import content_hash as compute_content_hash
from vasp_cache.mapping import load_mapping, mapping_digest
from vasp_cache.parse import MAX_LATTICE, summarize_calc
from vasp_cache.paths import cache_root

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
    tail_size = 65536
    file_size = path.stat().st_size
    offset = max(0, file_size - tail_size)
    with open(path, "rb") as f:
        f.seek(offset)
        tail = f.read().decode("utf-8", errors="replace")
    energies = re.findall(r"free\s+energy\s+TOTEN\s*=\s*([-\d.]+)", tail)
    energy = float(energies[-1]) if energies else None
    converged = "General timing and accounting" in tail
    # Energy alone is not enough: unconverged runs are not cached.
    usable = converged
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
    usable, _, converged = _outcar_usable(calc_dir)
    if not usable:
        reason = "not_converged_or_missing_outcar"
        logger.info("put skip %s: %s", calc_dir, reason)
        return None

    summary = summarize_calc(calc_dir)
    if summary.get("converged") is False:
        logger.info("put skip %s: summarize_not_converged", calc_dir)
        return None

    if MAX_LATTICE is not None and summary.get("max_abc", 0) > MAX_LATTICE:
        logger.info(
            "put skip %s: max_abc %.1f > MAX_LATTICE %.1f",
            calc_dir,
            summary["max_abc"],
            MAX_LATTICE,
        )
        return None
    ch = compute_content_hash(calc_dir)
    f, tn = _detect_formula_task(calc_dir)
    formula = formula or f
    task_name = task_name or tn
    root = cache_root()

    objects: dict[str, str] = {}
    for name in _OUTPUT_NAMES:
        src = calc_dir / name
        if src.is_file():
            objects[name] = cas.put_file(root, src)
    if "CONTCAR" not in objects and (calc_dir / "POSCAR").is_file():
        objects["CONTCAR"] = cas.put_file(root, calc_dir / "POSCAR")

    if store_inputs:
        for name in _INPUT_NAMES:
            src = calc_dir / name
            if src.is_file():
                objects[name] = cas.put_file(root, src)

    for name in include:
        if name == "POTCAR":
            continue
        src = calc_dir / name
        if src.is_file():
            objects[name] = cas.put_file(root, src)

    if "OUTCAR" not in objects:
        logger.info("put skip %s: outcar_not_stored", calc_dir)
        return None

    m = load_mapping()
    core_keys = {
        "formula",
        "task_name",
        "total_energy",
        "converged",
        "bandgap",
        "nsites",
        "max_abc",
        "tags",
    }
    extra = {k: v for k, v in summary.items() if k not in core_keys}
    meta.upsert_entry(
        root,
        content_hash=ch,
        objects=objects,
        formula=formula,
        task_name=task_name,
        total_energy=summary.get("total_energy"),
        converged=summary.get("converged"),
        bandgap=summary.get("bandgap"),
        nsites=summary.get("nsites"),
        max_abc=summary.get("max_abc"),
        tags=summary.get("tags"),
        source_dir=str(calc_dir.resolve()),
        profile_id=m.get("profile_id", "default"),
        key_generation=m.get("key_generation"),
        mapping_digest=mapping_digest(calc_dir, mapping=m),
        cached_at=time.time(),
        extra=extra or None,
    )
    logger.info("put ok %s hash=%s formula=%s", calc_dir, ch, formula)
    return ch


def has(input_dir: Path | str) -> bool:
    input_dir = Path(input_dir)
    ch = compute_content_hash(input_dir)
    root = cache_root()
    entry = meta.get_entry(root, ch)
    if entry is None:
        logger.info("has miss %s (no meta)", input_dir)
        return False
    out_id = (entry.get("objects") or {}).get("OUTCAR")
    if not out_id or not cas.has_object(root, out_id):
        logger.info("has miss %s (no OUTCAR object)", input_dir)
        return False
    logger.info("has hit %s", input_dir)
    return True


def fetch(input_dir: Path | str) -> bool:
    input_dir = Path(input_dir)
    ch = compute_content_hash(input_dir)
    root = cache_root()
    entry = meta.get_entry(root, ch)
    if entry is None:
        logger.info("fetch miss %s (no meta)", input_dir)
        return False
    objects = entry.get("objects") or {}
    restored = False
    for name in _OUTPUT_NAMES:
        digest = objects.get(name)
        if not digest or not cas.has_object(root, digest):
            continue
        cas.materialize(root, digest, input_dir / name)
        if name == "OUTCAR":
            restored = True
    if restored:
        logger.info("fetch ok %s", input_dir)
    else:
        logger.info("fetch miss %s (no OUTCAR restored)", input_dir)
    return restored


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
    """Semantic query over metadata fields."""
    return meta.query_entries(
        cache_root(),
        formula=formula,
        functional=functional,
        tags=tags_contains,
        calc_type=calc_type,
        bandgap_min=bandgap_min,
        lattice_max=lattice_max,
        converged_only=converged_only,
        limit=limit,
    )


def list_entries(limit: int = 50) -> list[dict[str, Any]]:
    """Most recently cached entries."""
    return meta.list_recent(cache_root(), limit=limit)


def stats() -> dict[str, Any]:
    """Aggregate cache statistics."""
    return meta.stats(cache_root())


def get_meta(
    input_dir: Path | str | None = None,
    *,
    content_hash: str | None = None,
    formula: str | None = None,
    key: str | None = None,
) -> dict[str, Any] | None:
    """Return metadata for a cached calculation, or None."""
    root = cache_root()
    if input_dir is not None:
        ch = compute_content_hash(Path(input_dir))
        return meta.get_entry(root, ch)
    if content_hash is not None:
        return meta.get_entry(root, content_hash)
    if formula is not None:
        rows = meta.query_entries(
            root, formula=formula, converged_only=False, limit=50
        )
        if key is None:
            return rows[0] if rows else None
        for r in rows:
            if key in (r.get("content_hash"), r.get("task_name")):
                return r
        return None
    return None
