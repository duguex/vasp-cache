"""Read-only collectors for cache metadata and CAS storage inspection."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from vasp_cache import cas, meta


def _has_database(root: Path) -> bool:
    """Return whether the metadata database already exists."""
    return meta.db_path(root).is_file()


def _empty_summary() -> dict[str, Any]:
    return {
        "entries": 0,
        "formulas": 0,
        "provenance": {"canonical": 0, "sampled": 0, "unknown": 0},
        "converged": 0,
        "with_energy": 0,
        "key_generations": [],
        "profile_ids": [],
        "cas_objects": 0,
        "cas_bytes": 0,
        "referenced_objects": 0,
        "referenced_bytes": 0,
        "orphan_objects": 0,
        "orphan_bytes": 0,
    }


def _reference_map(root: Path) -> dict[str, dict[str, Any]]:
    """Collect CAS references without opening a missing metadata database."""
    references: dict[str, dict[str, Any]] = {}
    if not _has_database(root):
        return references
    for record in meta.iter_entries(root):
        for name, digest in (record.get("objects") or {}).items():
            if not isinstance(digest, str):
                continue
            normalized = digest.lower()
            reference = references.setdefault(
                normalized, {"count": 0, "names": set()}
            )
            reference["count"] += 1
            reference["names"].add(str(name))
    return references


def _physical_objects(root: Path) -> dict[str, Path]:
    """Return valid physical CAS objects keyed by their canonical digest."""
    physical: dict[str, Path] = {}
    for digest, path in cas.iter_objects(root):
        normalized = digest.lower()
        try:
            expected = cas.object_path(root, normalized)
        except ValueError:
            continue
        if path.resolve() != expected.resolve():
            continue
        physical[normalized] = path
    return physical


def _relative_location(root: Path, digest: str) -> str | None:
    try:
        path = cas.object_path(root, digest)
    except ValueError:
        return None
    return path.resolve().relative_to(Path(root).resolve()).as_posix()


def _object_info(root: Path, name: str, digest: str) -> dict[str, Any]:
    """Normalize one metadata object reference for an entry report."""
    location = _relative_location(root, digest)
    if location is None:
        return {
            "name": name,
            "digest": digest,
            "size": None,
            "present": False,
            "location": None,
        }
    path = cas.object_path(root, digest)
    present = cas.has_object(root, digest)
    return {
        "name": name,
        "digest": digest,
        "size": path.stat().st_size if present else None,
        "present": present,
        "location": location,
    }


def summary(cache_root: Path) -> dict[str, Any]:
    """Return aggregate metadata, reference, and physical CAS statistics."""
    root = Path(cache_root)
    result = _empty_summary()
    records = list(meta.iter_entries(root)) if _has_database(root) else []

    formulas = set()
    key_generations = set()
    profile_ids = set()
    for record in records:
        formula = record.get("formula")
        if formula is not None:
            formulas.add(formula)
        provenance = record.get("provenance") or "unknown"
        if provenance not in result["provenance"]:
            provenance = "unknown"
        result["provenance"][provenance] += 1
        if record.get("converged") is True:
            result["converged"] += 1
        if record.get("total_energy") is not None:
            result["with_energy"] += 1
        generation = record.get("key_generation")
        if generation is not None:
            key_generations.add(int(generation))
        profile = record.get("profile_id")
        if profile is not None:
            profile_ids.add(str(profile))

    result["entries"] = len(records)
    result["formulas"] = len(formulas)
    result["key_generations"] = sorted(key_generations)
    result["profile_ids"] = sorted(profile_ids)

    references = _reference_map(root)
    physical = _physical_objects(root)
    sizes = {digest: path.stat().st_size for digest, path in physical.items()}
    result["cas_objects"] = len(physical)
    result["cas_bytes"] = sum(sizes.values())
    result["referenced_objects"] = len(references)
    result["referenced_bytes"] = sum(
        sizes.get(digest, 0) for digest in references
    )
    orphan_digests = set(physical) - set(references)
    result["orphan_objects"] = len(orphan_digests)
    result["orphan_bytes"] = sum(sizes[digest] for digest in orphan_digests)
    return result


def entries(
    cache_root: Path,
    *,
    formula: str | None = None,
    functional: str | None = None,
    tags: str | None = None,
    bandgap_min: float | None = None,
    lattice_max: float | None = None,
    min_energy: float | None = None,
    max_energy: float | None = None,
    converged_only: bool = False,
    provenance: str = "canonical",
    limit: int = 20,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Return filtered metadata rows with object counts and pagination."""
    root = Path(cache_root)
    if not _has_database(root):
        return []
    limit = max(0, int(limit))
    offset = max(0, int(offset))
    if limit == 0:
        return []
    rows = meta.query_entries(
        root,
        formula=formula,
        functional=functional,
        tags=tags,
        bandgap_min=bandgap_min,
        lattice_max=lattice_max,
        min_energy=min_energy,
        max_energy=max_energy,
        converged_only=converged_only,
        provenance=provenance,  # type: ignore[arg-type]
        limit=offset + limit,
    )
    rows = rows[offset : offset + limit]
    for row in rows:
        row["object_count"] = len(row.get("objects") or {})
    return rows


def entry(cache_root: Path, content_hash: str) -> dict[str, Any] | None:
    """Return complete metadata and normalized object details for one entry."""
    root = Path(cache_root)
    if not _has_database(root):
        return None
    record = meta.get_entry(root, content_hash)
    if record is None:
        return None
    normalized = dict(record)
    normalized["objects"] = {
        name: _object_info(root, name, digest)
        for name, digest in sorted((record.get("objects") or {}).items())
        if isinstance(digest, str)
    }
    return normalized


def objects(cache_root: Path, *, orphans_only: bool = False) -> list[dict[str, Any]]:
    """Return deterministic physical and referenced CAS object accounting."""
    root = Path(cache_root)
    references = _reference_map(root)
    physical = _physical_objects(root)
    digests = sorted(set(physical) | set(references))
    result: list[dict[str, Any]] = []
    for digest in digests:
        reference = references.get(digest, {"count": 0, "names": set()})
        orphan = digest not in references
        if orphans_only and not orphan:
            continue
        path = physical.get(digest)
        result.append(
            {
                "digest": digest,
                "size": path.stat().st_size if path is not None else None,
                "reference_count": reference["count"],
                "logical_names": sorted(reference["names"]),
                "orphan": orphan,
            }
        )
    return result
