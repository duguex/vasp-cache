"""Passive file logging."""

from __future__ import annotations

from pathlib import Path

from conftest import write_complete_calc, write_minimal_inputs, write_minimal_outcar
from vasp_cache.api import has, put
from vasp_cache.logutil import log_path, reset_for_tests
from vasp_cache.paths import _reset_project, override_cache_root


def test_put_writes_log_file_without_setup(tmp_path: Path, monkeypatch):
    reset_for_tests()
    root = tmp_path / "cache"
    root.mkdir()
    log_file = tmp_path / "diag.log"
    monkeypatch.setenv("VASP_CACHE_LOG_FILE", str(log_file))
    monkeypatch.setenv("VASP_CACHE_ROOT", str(root))
    _reset_project()
    override_cache_root(root)

    calc = write_complete_calc(tmp_path / "c")
    put(calc)
    has(calc)

    assert log_file.is_file()
    text = log_file.read_text()
    assert "put ok" in text
    assert "has hit" in text


def test_put_skip_in_log_file(tmp_path: Path, monkeypatch):
    reset_for_tests()
    root = tmp_path / "cache"
    root.mkdir()
    log_file = tmp_path / "diag2.log"
    monkeypatch.setenv("VASP_CACHE_LOG_FILE", str(log_file))
    _reset_project()
    override_cache_root(root)

    d = write_minimal_inputs(tmp_path / "bad")
    write_minimal_outcar(d, converged=False)
    assert put(d) is None
    assert "put skip" in log_file.read_text()
