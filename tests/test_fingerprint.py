from __future__ import annotations

from pathlib import Path

from vasp_cache.mapping import content_hash
from vasp_cache.fingerprint import content_hash as legacy_content_hash

from conftest import write_minimal_inputs, MINIMAL_POSCAR, MINIMAL_INCAR, MINIMAL_KPOINTS


def test_content_hash_stable(tmp_path: Path):
    d = write_minimal_inputs(tmp_path / "a")
    h1 = content_hash(d)
    h2 = content_hash(d)
    assert h1 == h2
    assert h1.startswith("4:")
    # INCAR fingerprint includes ENCUT
    assert "ENCUT=520" in h1 or "ENCUT=520.0" in h1
    assert "_default" in h1  # potcar not in identity


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


def test_potcar_ignored_by_default_mapping(tmp_path: Path):
    """Default profile has hard.potcar=false: POTCAR presence/species do not affect hash."""
    d = write_minimal_inputs(tmp_path / "a")
    h0 = content_hash(d)
    (d / "POTCAR").write_text(
        "  PAW_PBE Ge 05Jan2001\n   4.00000000000000\n"
    )
    assert content_hash(d) == h0
    (d / "POTCAR").unlink()
    assert content_hash(d) == h0


def test_potcar_change_changes_hash_when_enabled(tmp_path: Path):
    """With hard.potcar=true, changing POTCAR species flips the hash."""
    d = write_minimal_inputs(tmp_path / "a")
    mapping = {
        "key_generation": 5,
        "hard": {
            "structure": "geom_hash",
            "kpoints": True,
            "potcar": True,
            "incar": ["ENCUT", "PREC", "ISMEAR", "SIGMA", "ISIF", "GGA", "LASPH", "ISPIN"],
        },
        "soft": {"incar": []},
    }
    h0 = content_hash(d, mapping=mapping)
    (d / "POTCAR").write_text(
        "  PAW_PBE Ge 05Jan2001\n   4.00000000000000\n"
    )
    assert content_hash(d, mapping=mapping) != h0


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


def test_nelect_change_changes_hash(tmp_path: Path):
    """Charged defects: NELECT is hard (gen4 audit)."""
    d = write_minimal_inputs(tmp_path / "a")
    h0 = content_hash(d)
    (d / "INCAR").write_text(MINIMAL_INCAR + "\nNELECT = 8\n")
    assert content_hash(d) != h0


def test_magmom_change_changes_hash(tmp_path: Path):
    d = write_minimal_inputs(tmp_path / "a")
    h0 = content_hash(d)
    (d / "INCAR").write_text(MINIMAL_INCAR + "\nMAGMOM = 2*1\n")
    assert content_hash(d) != h0


def test_aexx_change_changes_hash(tmp_path: Path):
    d = write_minimal_inputs(tmp_path / "a")
    h0 = content_hash(d)
    (d / "INCAR").write_text(MINIMAL_INCAR + "\nAEXX = 0.25\n")
    assert content_hash(d) != h0
