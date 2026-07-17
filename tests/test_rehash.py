"""Collision-safe metadata rehash tests."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from conftest import write_complete_calc
from vasp_cache import cas, meta
from vasp_cache.paths import _reset_project

_spec = importlib.util.spec_from_file_location(
    "rehash_meta_cas", Path(__file__).parents[1] / "scripts" / "rehash_meta_cas.py"
)
_rehash = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_rehash)
apply_inventory = _rehash.apply_inventory
inventory_root = _rehash.inventory_root


def _seed_old_entry(root: Path, calc: Path, old_hash: str) -> dict:
    objects = {}
    for name in ("INCAR", "POSCAR", "KPOINTS", "CONTCAR", "OUTCAR"):
        objects[name] = cas.put_file(root, calc / name)
    meta.upsert_entry(
        root,
        content_hash=old_hash,
        objects=objects,
        formula="Si",
        task_name=calc.name,
        cached_at=1.0,
    )
    return objects


def test_rehash_inventory_reports_collision_without_mutation(
    cache_root: Path, tmp_path: Path
):
    _reset_project()
    first = write_complete_calc(tmp_path / "first", energy="-5.0")
    second = write_complete_calc(tmp_path / "second", energy="-6.0")
    _seed_old_entry(cache_root, first, "old-first")
    _seed_old_entry(cache_root, second, "old-second")

    inventory = inventory_root(cache_root)

    assert inventory["collisions"]
    group = next(iter(inventory["collisions"].values()))
    assert set(group["old_hashes"]) == {"old-first", "old-second"}
    assert meta.get_entry(cache_root, "old-first") is not None
    assert meta.get_entry(cache_root, "old-second") is not None
    assert meta.get_entry(cache_root, group["new_hash"]) is None


def test_rehash_apply_rewrites_only_safe_group(
    cache_root: Path, tmp_path: Path
):
    _reset_project()
    calc = write_complete_calc(tmp_path / "single")
    objects = _seed_old_entry(cache_root, calc, "old-single")

    inventory = inventory_root(cache_root)
    result = apply_inventory(cache_root, inventory)

    assert result["applied"] == 1
    new_hash = inventory["safe"][0]["new_hash"]
    entry = meta.get_entry(cache_root, new_hash)
    assert entry is not None
    assert meta.get_entry(cache_root, "old-single") is None
    assert entry["objects"] == objects
    assert cas.read_bytes(cache_root, entry["objects"]["OUTCAR"])
