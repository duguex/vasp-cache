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



def test_cli_put_and_status(tmp_path: Path, capsys):
    """vasp-cache put prints key; status prints JSON counts."""
    cache = tmp_path / "cache"
    write_complete_calc(tmp_path / "calc")
    rc = main(["--root", str(cache), "put", str(tmp_path / "calc")])
    assert rc == 0
    key = capsys.readouterr().out.strip()
    assert len(key) == 64  # SHA-256 hex
    # status
    rc = main(["--root", str(cache), "status"])
    assert rc == 0
    out = capsys.readouterr().out
    assert '"entries": 1' in out


def test_cli_has_hit_and_miss(tmp_path: Path, capsys):
    """vasp-cache has returns true/false and exit code."""
    cache = tmp_path / "cache"
    write_complete_calc(tmp_path / "calc")
    # other has different INCAR → different identity
    other = tmp_path / "other"
    other.mkdir()
    from conftest import write_complete_calc as wcc, MINIMAL_INCAR
    from vasp_cache.index import normalize_incar
    (other / "POSCAR").write_text(
        "Si\n1.0\n5.43 0 0\n0 5.43 0\n0 0 5.43\nSi\n2\nDirect\n0 0 0\n0.25 0.25 0.25\n")
    (other / "INCAR").write_text("ENCUT = 400\n")
    (other / "KPOINTS").write_text("Automatic mesh\n0\nGamma\n1 1 1\n")
    (other / "POTCAR").write_text("   TITEL  = PAW_PBE Si 05Jan2001\n")
    for name in ("OUTCAR", "CONTCAR", "vasprun.xml"):
        (other / name).write_bytes(b"fake " + name.encode())
    # index calc, not other
    main(["--root", str(cache), "put", str(tmp_path / "calc")])
    # has hit
    rc = main(["--root", str(cache), "has", str(tmp_path / "calc")])
    assert rc == 0
    assert "true" in capsys.readouterr().out
    # has miss (different ENCUT → different key)
    rc = main(["--root", str(cache), "has", str(other)])
    assert rc == 1
    assert "false" in capsys.readouterr().out


def test_cli_fetch_roundtrip(tmp_path: Path, capsys):
    """vasp-cache fetch restores outputs from key."""
    cache = tmp_path / "cache"
    write_complete_calc(tmp_path / "calc")
    main(["--root", str(cache), "put", str(tmp_path / "calc")])
    key = capsys.readouterr().out.strip()
    dest = tmp_path / "restored"
    rc = main(["--root", str(cache), "fetch", key, str(dest)])
    assert rc == 0
    assert "hit" in capsys.readouterr().out
    for f in ("OUTCAR", "CONTCAR", "vasprun.xml", "POSCAR", "INCAR", "KPOINTS"):
        assert (dest / f).is_file(), f"missing {f}"
