"""CLI smoke tests."""

from __future__ import annotations

from pathlib import Path

from conftest import write_complete_calc, write_minimal_inputs
from vasp_cache.cli import main
from vasp_cache.paths import _reset_project


def test_cli_put_status(cache_root: Path, tmp_path: Path):
    _reset_project()
    calc = write_complete_calc(tmp_path / "c")
    assert main(["put", str(calc)]) == 0
    assert main(["status"]) == 0
    assert main(["content-hash", str(calc)]) == 0
    assert main(["mapping", "show"]) == 0
    assert main(["mapping", "check"]) == 0


def test_cli_has_fetch(cache_root: Path, tmp_path: Path):
    _reset_project()
    calc = write_complete_calc(tmp_path / "c")
    assert main(["put", str(calc)]) == 0
    work = write_minimal_inputs(tmp_path / "w")
    assert main(["has", str(work)]) == 0
    assert main(["fetch", str(work)]) == 0
    assert (work / "OUTCAR").is_file()
