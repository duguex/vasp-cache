from __future__ import annotations

from pathlib import Path

from vasp_cache.fingerprint import content_hash

from conftest import write_minimal_inputs, MINIMAL_POSCAR, MINIMAL_INCAR, MINIMAL_KPOINTS


def test_content_hash_stable(tmp_path: Path):
    d = write_minimal_inputs(tmp_path / "a")
    h1 = content_hash(d)
    h2 = content_hash(d)
    assert h1 == h2
    # Structure tag includes Si
    assert "Si" in h1 or "Si2" in h1 or "Si" in h1
    # INCAR fingerprint includes ENCUT
    assert "ENCUT=520" in h1 or "ENCUT=520.0" in h1


def test_kpoints_change_changes_hash(tmp_path: Path):
    d = write_minimal_inputs(tmp_path / "a")
    h0 = content_hash(d)
    (d / "KPOINTS").write_text(
        "Automatic mesh\n0\nGamma\n2 2 2\n0 0 0\n"
    )
    assert content_hash(d) != h0


def test_missing_inputs_still_returns_string(tmp_path: Path):
    d = tmp_path / "empty"
    d.mkdir()
    h = content_hash(d)
    assert isinstance(h, str)
    assert "unknown" in h or "nokpt" in h or "default" in h


def test_incar_change_changes_hash(tmp_path: Path):
    """Changing a critical INCAR key flips the hash."""
    d = write_minimal_inputs(tmp_path / "a")
    h0 = content_hash(d)
    (d / "INCAR").write_text(MINIMAL_INCAR.replace("ENCUT = 520", "ENCUT = 600"))
    assert content_hash(d) != h0


def test_potcar_change_changes_hash(tmp_path: Path):
    """Changing POTCAR species flips the hash."""
    d = write_minimal_inputs(tmp_path / "a")
    h0 = content_hash(d)
    (d / "POTCAR").write_text(
        "  PAW_PBE Ge 05Jan2001\n   4.00000000000000\n"
    )
    assert content_hash(d) != h0


def test_structure_change_changes_hash(tmp_path: Path):
    """Different structure flips the hash."""
    d = write_minimal_inputs(tmp_path / "a")
    h0 = content_hash(d)
    # Replace with GaAs structure
    gaas_poscar = """\
GaAs
1.0
5.65 0 0
0 5.65 0
0 0 5.65
Ga As
2 2
Direct
0 0 0
0.25 0.25 0.25
0.5 0.5 0.5
0.75 0.75 0.75
"""
    (d / "POSCAR").write_text(gaas_poscar)
    (d / "CONTCAR").write_text(gaas_poscar)
    assert content_hash(d) != h0


def test_concar_preferred_over_poscar(tmp_path: Path):
    """CONTCAR content is used over POSCAR when both exist."""
    d = write_minimal_inputs(tmp_path / "a")
    # CONTCAR currently matches POSCAR (Si2)
    h_si = content_hash(d)
    # Replace CONTCAR with something different
    gaas_poscar = """\
GaAs
1.0
5.65 0 0
0 5.65 0
0 0 5.65
Ga As
2 2
Direct
0 0 0
0.25 0.25 0.25
0.5 0.5 0.5
0.75 0.75 0.75
"""
    (d / "CONTCAR").write_text(gaas_poscar)
    assert content_hash(d) != h_si
    # Should now contain Ga2As2 (pymatgen reduced formula)
    assert "Ga2As2" in content_hash(d)
