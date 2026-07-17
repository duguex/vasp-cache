"""CLI smoke tests."""

from __future__ import annotations

import json
from pathlib import Path

from conftest import write_complete_calc, write_minimal_inputs
from vasp_cache.cli import main
from vasp_cache.api import query
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


def test_cli_query_defaults_canonical_and_all_opt_in(
    cache_root: Path, tmp_path: Path, capsys
):
    _reset_project()
    canonical = write_complete_calc(tmp_path / "canonical")
    sampled = write_complete_calc(tmp_path / "sampled")
    (sampled / "INCAR").write_text("NSW = 4\nIBRION = 0\n")

    assert main(["put", "--provenance", "canonical", str(canonical)]) == 0
    assert main(["put", "--provenance", "sampled", str(sampled)]) == 0

    capsys.readouterr()
    assert main(["query", "--formula", "Si", "--json"]) == 0
    default_rows = json.loads(capsys.readouterr().out)
    assert {row["provenance"] for row in default_rows} == {"canonical"}

    assert main(["query", "--formula", "Si", "--provenance", "all", "--json"]) == 0
    all_rows = json.loads(capsys.readouterr().out)
    assert {row["provenance"] for row in all_rows} == {"canonical", "sampled"}


def test_cli_recursive_put_provenance_applies_to_all_entries(
    cache_root: Path, tmp_path: Path
):
    _reset_project()
    root = tmp_path / "tree"
    write_complete_calc(root / "first")
    second = write_complete_calc(root / "second")
    (second / "KPOINTS").write_text(
        (second / "KPOINTS").read_text().replace("4 4 4", "3 3 3")
    )

    assert main(
        ["put", "-r", "--provenance", "sampled", str(root)]
    ) == 0

    sampled_rows = query(
        formula="Si", provenance="sampled", converged_only=False, limit=10
    )
    all_rows = query(formula="Si", provenance="all", converged_only=False, limit=10)
    assert len(sampled_rows) == 2
    assert {row["provenance"] for row in sampled_rows} == {"sampled"}
    assert {row["content_hash"] for row in all_rows} >= {
        row["content_hash"] for row in sampled_rows
    }


def test_cli_put_conflict_modes_are_explicit(
    cache_root: Path, tmp_path: Path
):
    _reset_project()
    first = write_complete_calc(tmp_path / "first", energy="-5.0")
    second = write_complete_calc(tmp_path / "second", energy="-6.0")

    assert main(["put", "--provenance", "canonical", str(first)]) == 0
    assert main(
        [
            "put",
            "--provenance",
            "canonical",
            "--on-conflict",
            "skip",
            str(second),
        ]
    ) == 0
    assert main(
        [
            "put",
            "--provenance",
            "canonical",
            "--on-conflict",
            "overwrite",
            str(second),
        ]
    ) == 0


def test_cli_inspect_summary_json(cache_root: Path, tmp_path: Path, capsys):
    _reset_project()
    from vasp_cache.api import put

    put(write_complete_calc(tmp_path / "calc"), provenance="canonical")
    capsys.readouterr()
    assert main(["inspect", "summary", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["entries"] == 1
    assert payload["cas_objects"] >= 1


def test_cli_inspect_entry_json_has_full_hash_and_objects(
    cache_root: Path, tmp_path: Path, capsys
):
    _reset_project()
    from vasp_cache.api import put

    content_hash = put(write_complete_calc(tmp_path / "calc"))
    assert content_hash is not None
    capsys.readouterr()
    assert main(["inspect", "entry", content_hash, "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["content_hash"] == content_hash
    assert "OUTCAR" in payload["objects"]


def test_cli_inspect_missing_entry_returns_nonzero(cache_root: Path, capsys):
    assert main(["inspect", "entry", "missing", "--json"]) == 1
    assert "missing" in capsys.readouterr().err


def test_cli_inspect_entries_table_and_jsonl(cache_root: Path, tmp_path: Path, capsys):
    _reset_project()
    from vasp_cache.api import put

    put(write_complete_calc(tmp_path / "calc"), provenance="canonical")
    capsys.readouterr()
    assert main(["inspect", "entries"]) == 0
    table = capsys.readouterr().out
    assert "Si" in table

    assert main(["inspect", "entries", "--jsonl"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines
    assert all(json.loads(line)["content_hash"] for line in lines)


def test_cli_inspect_objects_jsonl_orphans_only(
    cache_root: Path, tmp_path: Path, capsys
):
    _reset_project()
    from vasp_cache import cas
    from vasp_cache.api import put

    put(write_complete_calc(tmp_path / "calc"), provenance="canonical")
    orphan = cas.put_bytes(cache_root, b"orphan")
    capsys.readouterr()
    assert main(["inspect", "objects", "--orphans-only", "--jsonl"]) == 0
    lines = capsys.readouterr().out.splitlines()
    payload = [json.loads(line) for line in lines]
    assert [row["digest"] for row in payload] == [orphan]
    assert payload[0]["orphan"] is True
