"""Audit JSONL + diagnostic logging."""

from __future__ import annotations

import json
from pathlib import Path

from conftest import write_complete_calc, write_minimal_inputs, write_minimal_outcar
from vasp_cache.api import fetch, has, put
from vasp_cache.audit import reset_for_tests, set_audit_log, setup_logging
from vasp_cache.paths import _reset_project, override_cache_root


def _read_events(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    out = []
    for line in path.read_text().splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out


def test_put_has_fetch_audit_jsonl(tmp_path: Path, cache_root: Path):
    reset_for_tests()
    setup_logging("WARNING")
    audit_path = tmp_path / "audit.jsonl"
    set_audit_log(audit_path)
    _reset_project()
    override_cache_root(cache_root)

    calc = write_complete_calc(tmp_path / "calc", energy="-3.0")
    ch = put(calc)
    assert ch is not None
    assert has(calc) is True
    work = write_minimal_inputs(tmp_path / "work")
    # same structure/inputs as calc for hash match
    for name in ("INCAR", "POSCAR", "KPOINTS", "POTCAR"):
        (work / name).write_bytes((calc / name).read_bytes())
    assert fetch(work) is True

    events = _read_events(audit_path)
    kinds = [e["event"] for e in events]
    assert "put_ok" in kinds
    assert "has_hit" in kinds
    assert "fetch_ok" in kinds
    put_ev = next(e for e in events if e["event"] == "put_ok")
    assert put_ev["content_hash"] == ch
    assert "host" in put_ev and "pid" in put_ev and "ts" in put_ev


def test_put_skip_unconverged_audited(tmp_path: Path, cache_root: Path):
    reset_for_tests()
    audit_path = tmp_path / "a.jsonl"
    set_audit_log(audit_path)
    _reset_project()
    override_cache_root(cache_root)

    d = write_minimal_inputs(tmp_path / "bad")
    write_minimal_outcar(d, energy="-1.0", converged=False)
    assert put(d) is None
    events = _read_events(audit_path)
    assert any(e["event"] == "put_skip" for e in events)
    skip = next(e for e in events if e["event"] == "put_skip")
    assert "reason" in skip


def test_has_miss_audited(tmp_path: Path, cache_root: Path):
    reset_for_tests()
    audit_path = tmp_path / "m.jsonl"
    set_audit_log(audit_path)
    _reset_project()
    override_cache_root(cache_root)

    d = write_minimal_inputs(tmp_path / "only")
    assert has(d) is False
    events = _read_events(audit_path)
    assert any(e["event"] == "has_miss" for e in events)
