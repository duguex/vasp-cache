from __future__ import annotations

import json
from pathlib import Path

from conftest import write_complete_calc
from vasp_cache.cli import main


def test_cli_rebuild_and_query(tmp_path: Path, capsys):
    source = tmp_path / "source"
    cache = tmp_path / "cache"
    write_complete_calc(source / "calc")

    assert main(["--root", str(cache), "rebuild", str(source), "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["identities"] == 1

    assert main(
        ["--root", str(cache), "query", "--formula", "Si", "--json"]
    ) == 0
    rows = json.loads(capsys.readouterr().out)
    assert len(rows) == 1
    assert rows[0]["formula"] == "Si"


def test_cli_rebuild_excludes_backup_source(tmp_path: Path, capsys):
    source = tmp_path / "src"
    cache = tmp_path / "cache"
    write_complete_calc(source / "valid")
    write_complete_calc(source / "backup_old" / "calc")

    assert main([
        "--root", str(cache), "rebuild", str(source),
        "--exclude", "*backup*", "--json",
    ]) == 0
    report = json.loads(capsys.readouterr().out)

    assert report["identities"] == 1
    assert main(
        ["--root", str(cache), "query", "--formula", "Si", "--json"]
    ) == 0
    rows = json.loads(capsys.readouterr().out)
    assert len(rows) == 1
    assert "/backup_old/" not in rows[0].get("source_path", "")
