"""Read-only cache health collection over metadata and the optional CAS walk."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Callable

from vasp_cache import cas, meta

_SAMPLE_LIMIT = 20


def _sample(record: dict[str, Any]) -> dict[str, Any]:
    """Keep the raw fields required for bounded anomaly samples."""
    return {
        "content_hash": record.get("content_hash"),
        "formula": record.get("formula"),
        "total_energy": record.get("total_energy"),
        "source_dir": record.get("source_dir"),
    }


def _add_sample(samples: dict[str, list[dict[str, Any]]], key: str, record: dict[str, Any]) -> None:
    # Rows are sorted before truncation in _metadata_report. Keeping all rows here
    # would defeat the bounded-memory property for a large shared cache, so the
    # deterministic top-N hashes are maintained incrementally instead.
    item = _sample(record)
    values = samples[key]
    values.append(item)
    values.sort(key=lambda value: str(value.get("content_hash") or ""))
    del values[_SAMPLE_LIMIT:]


def _metadata_report(
    root: Path, energy_min: float | None, energy_max: float | None
) -> tuple[dict[str, Any], Counter[str], dict[str, Any]]:
    metadata: dict[str, Any] = {
        "entries": 0,
        "missing_formula": 0,
        "missing_energy": 0,
        "missing_convergence": 0,
        "missing_objects": 0,
        "provenance": {"canonical": 0, "sampled": 0, "unknown": 0},
        "provenance_source": {"explicit": 0, "inferred": 0, "legacy": 0},
        "key_generations": {},
        "profile_ids": {},
        "missing_identity": 0,
        "samples": {
            "missing_formula": [],
            "missing_energy": [],
            "missing_convergence": [],
            "missing_objects": [],
            "missing_identity": [],
        },
    }
    references: Counter[str] = Counter()
    energies: list[float] = []
    outlier_samples: list[dict[str, Any]] = []
    missing_energy = 0
    if meta.db_path(root).is_file():
        for record in meta.iter_entries(root):
            metadata["entries"] += 1
            if record.get("formula") is None:
                metadata["missing_formula"] += 1
                _add_sample(metadata["samples"], "missing_formula", record)
            energy = record.get("total_energy")
            if energy is None:
                metadata["missing_energy"] += 1
                missing_energy += 1
                _add_sample(metadata["samples"], "missing_energy", record)
            elif isinstance(energy, (int, float)):
                energies.append(energy)
                if ((energy_min is not None and energy < energy_min) or
                        (energy_max is not None and energy > energy_max)):
                    outlier_samples.append(_sample(record))
            if record.get("converged") is None:
                metadata["missing_convergence"] += 1
                _add_sample(metadata["samples"], "missing_convergence", record)

            objects = record.get("objects")
            object_values = objects.values() if isinstance(objects, dict) else ()
            valid_reference = False
            for digest in object_values:
                if isinstance(digest, str):
                    references[digest.lower()] += 1
                    valid_reference = True
            if not valid_reference:
                metadata["missing_objects"] += 1
                _add_sample(metadata["samples"], "missing_objects", record)

            provenance = str(record.get("provenance") or "unknown")
            metadata["provenance"][provenance] = metadata["provenance"].get(provenance, 0) + 1
            source = str(record.get("provenance_source") or "legacy")
            metadata["provenance_source"][source] = metadata["provenance_source"].get(source, 0) + 1

            generation = record.get("key_generation")
            if generation is not None:
                generation_key = str(generation)
                metadata["key_generations"][generation_key] = (
                    metadata["key_generations"].get(generation_key, 0) + 1
                )
            profile = record.get("profile_id")
            if profile is not None:
                profile_key = str(profile)
                metadata["profile_ids"][profile_key] = metadata["profile_ids"].get(profile_key, 0) + 1
            if generation is None or profile is None:
                metadata["missing_identity"] += 1
                _add_sample(metadata["samples"], "missing_identity", record)

    for key in ("provenance", "provenance_source", "key_generations", "profile_ids"):
        metadata[key] = dict(sorted(metadata[key].items()))
    outlier_samples.sort(key=lambda value: str(value.get("content_hash") or ""))
    energy = {
        "min": min(energies) if energies else None,
        "max": max(energies) if energies else None,
        "missing": missing_energy,
        "configured_min": energy_min,
        "configured_max": energy_max,
        "outliers": len(outlier_samples),
        "samples": outlier_samples[:_SAMPLE_LIMIT],
    }
    return metadata, references, energy


def _scan_cas(
    root: Path,
    references: Counter[str],
    *,
    max_objects: int | None,
    progress: Callable[[int], None] | None,
) -> dict[str, Any]:
    if max_objects is not None and max_objects < 0:
        raise ValueError("max_objects must be non-negative")
    physical: dict[str, tuple[Path, int, bool]] = {}
    limited = False
    count = 0
    iterator = cas.iter_objects(root)
    for digest, path in iterator:
        if max_objects is not None and count >= max_objects:
            limited = True
            break
        normalized = digest.lower()
        try:
            expected = cas.object_path(root, normalized)
            matches = path.resolve() == expected.resolve()
        except (OSError, ValueError):
            matches = False
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        physical[normalized] = (path, size, matches)
        count += 1
        if progress is not None:
            progress(count)
    physical_digests = set(physical)
    reference_digests = set(references)
    referenced_physical = physical_digests & reference_digests
    orphan_digests = physical_digests - reference_digests
    return {
        "scan_performed": True,
        "physical_objects": len(physical),
        "physical_bytes": sum(value[1] for value in physical.values()),
        "referenced_objects": len(reference_digests),
        "referenced_bytes": sum(physical[digest][1] for digest in referenced_physical),
        "missing_references": len(reference_digests - physical_digests),
        "orphan_objects": len(orphan_digests),
        "orphan_bytes": sum(physical[digest][1] for digest in orphan_digests),
        "shared_reference_objects": sum(count > 1 for count in references.values()),
        "path_mismatches": sum(not value[2] for value in physical.values()),
        "limited": limited,
    }


def health_report(
    cache_root: Path,
    *,
    scan_cas: bool = False,
    max_objects: int | None = None,
    energy_min: float | None = None,
    energy_max: float | None = None,
    progress: Callable[[int], None] | None = None,
) -> dict[str, Any]:
    """Return a deterministic, read-only health report for *cache_root*."""
    root = Path(cache_root)
    metadata, references, energy = _metadata_report(root, energy_min, energy_max)
    if scan_cas:
        cas_report = _scan_cas(root, references, max_objects=max_objects, progress=progress)
        scan = {"mode": "cas", "max_objects": max_objects}
    else:
        cas_report = {
            "scan_performed": False,
            "physical_objects": 0,
            "physical_bytes": 0,
            "referenced_objects": len(references),
            "referenced_bytes": 0,
            "missing_references": 0,
            "orphan_objects": 0,
            "orphan_bytes": 0,
            "shared_reference_objects": sum(count > 1 for count in references.values()),
            "path_mismatches": 0,
            "limited": False,
        }
        scan = {"mode": "metadata", "max_objects": None}
    return {
        "schema_version": 1,
        "cache_root": str(root),
        "metadata": metadata,
        "cas": cas_report,
        "energy": energy,
        "scan": scan,
    }


__all__ = ["health_report"]
