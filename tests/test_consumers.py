"""C4/C5 consumer verification — API-level tests.

API-level = pymatgen objects + vasp-sop functions + regex patterns.
CLI-level = pydefect_vasp mce / crisp check_task_complete subprocess.
CLI tests not included in this file (require full environment).
"""

from pathlib import Path
import pytest

from vasp_cache.outcar import parse as parse_outcar, serialize as serialize_outcar
from vasp_cache.vasprun_ast import parse_to_ast, write_xml

_CALC = Path(
    "/mnt/shared/home/2sidesniddle/vasp/2025_undergo_spin_defect/"
    "CsEuCl3/unitcell/structure_opt"
)


@pytest.fixture
def calc_dir():
    return _CALC


@pytest.fixture
def rebuilt_dir(tmp_path, calc_dir):
    """Copy all input files, then rebuild OUTCAR and vasprun from cache."""
    import shutil
    for name in ("POSCAR", "INCAR", "KPOINTS", "POTCAR",
                 "OUTCAR", "CONTCAR"):
        shutil.copy2(calc_dir / name, tmp_path / name)
    # rebuild
    outcar_data = parse_outcar(calc_dir / "OUTCAR")
    (tmp_path / "OUTCAR").write_text(serialize_outcar(outcar_data))
    ast = parse_to_ast(calc_dir / "vasprun.xml")
    write_xml(ast, tmp_path / "vasprun.xml")
    return tmp_path


def test_outcar_rebuilt_has_toten_in_tail(rebuilt_dir):
    import re
    tail = (rebuilt_dir / "OUTCAR").read_text()[-4096:]
    m = re.search(r"free\s+energy\s+TOTEN\s*=\s*([-\d.]+)", tail)
    assert m
    assert abs(float(m.group(1)) - (-117.26795414)) < 1e-6


def test_outcar_rebuilt_passes_vasp_sop_check_converged(rebuilt_dir):
    import sys
    sys.path.insert(0, "/home/duguex/vasp_sop")
    from vasp_sop.vasp.io import check_converged
    assert check_converged(rebuilt_dir) is True


def test_vasprun_rebuilt_parsed_by_pymatgen(rebuilt_dir):
    from pymatgen.io.vasp.outputs import Vasprun
    v = Vasprun(str(rebuilt_dir / "vasprun.xml"))
    assert v.final_energy is not None
    assert v.converged_ionic is True
    assert len(v.ionic_steps) == 34


def test_vasprun_roundtrip_preserves_structure_and_incar(calc_dir):
    from pymatgen.io.vasp.outputs import Vasprun
    ast = parse_to_ast(calc_dir / "vasprun.xml")
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / "vasprun.xml"
        write_xml(ast, tmp)
        orig = Vasprun(str(calc_dir / "vasprun.xml"))
        reb = Vasprun(str(tmp))
        assert orig.final_energy == reb.final_energy
        assert len(orig.ionic_steps) == len(reb.ionic_steps)
        assert orig.converged_ionic == reb.converged_ionic
        assert str(orig.kpoints) == str(reb.kpoints)
        assert orig.initial_structure.composition.reduced_formula == \
            reb.initial_structure.composition.reduced_formula
