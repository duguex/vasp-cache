"""Strict same-key output conflict tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import write_complete_calc
from vasp_cache import cas, meta
from vasp_cache.api import put
from vasp_cache.errors import CacheConflictError
from vasp_cache.paths import _reset_project


def test_strict_conflict_rejects_before_cas_write(
    cache_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _reset_project()
    first = write_complete_calc(tmp_path / "first", energy="-5.0")
    second = write_complete_calc(tmp_path / "second", energy="-6.0")
    first_hash = put(first, provenance="canonical")
    before = meta.get_entry(cache_root, first_hash)
    assert before is not None

    def unexpected_cas_write(*_args, **_kwargs):
        raise AssertionError("CAS write occurred before strict conflict check")

    import vasp_cache.api as api_module

    monkeypatch.setattr(api_module.cas, "put_file", unexpected_cas_write)
    with pytest.raises(CacheConflictError):
        put(second, provenance="canonical", on_conflict="strict")

    after = meta.get_entry(cache_root, first_hash)
    assert after is not None
    assert after["objects"] == before["objects"]
    assert cas.read_bytes(cache_root, before["objects"]["OUTCAR"]).endswith(
        b"-5.0 eV\n General timing and accounting\n"
    )


def test_strict_same_outcar_is_idempotent(cache_root: Path, tmp_path: Path):
    _reset_project()
    first = write_complete_calc(tmp_path / "first", energy="-5.0")
    second = write_complete_calc(tmp_path / "second", energy="-5.0")

    first_hash = put(first, provenance="canonical")
    second_hash = put(second, provenance="canonical", on_conflict="strict")

    assert second_hash == first_hash


def test_skip_and_overwrite_are_explicit_modes(cache_root: Path, tmp_path: Path):
    _reset_project()
    first = write_complete_calc(tmp_path / "first", energy="-5.0")
    second = write_complete_calc(tmp_path / "second", energy="-6.0")

    first_hash = put(first, provenance="canonical")
    put(second, provenance="canonical", on_conflict="skip")
    skipped = meta.get_entry(cache_root, first_hash)
    assert skipped is not None
    skipped_outcar = skipped["objects"]["OUTCAR"]
    assert b"-5.0 eV" in cas.read_bytes(cache_root, skipped_outcar)

    put(second, provenance="canonical", on_conflict="overwrite")
    overwritten = meta.get_entry(cache_root, first_hash)
    assert overwritten is not None
    overwritten_outcar = overwritten["objects"]["OUTCAR"]
    assert b"-6.0 eV" in cas.read_bytes(cache_root, overwritten_outcar)
