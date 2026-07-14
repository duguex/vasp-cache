from __future__ import annotations

from pathlib import Path

import pytest


MINIMAL_POSCAR = """\
Si
1.0
5.43 0 0
0 5.43 0
0 0 5.43
Si
2
Direct
0 0 0
0.25 0.25 0.25
"""

MINIMAL_INCAR = """\
ENCUT = 520
PREC = Normal
ISMEAR = -5
SIGMA = 0.1
ISIF = 3
GGA = PE
LASPH = .TRUE.
"""

MINIMAL_KPOINTS = """\
Automatic mesh
0
Gamma
4 4 4
0 0 0
"""

MINIMAL_POTCAR = """\
  PAW_PBE Si 05Jan2001
   4.00000000000000
"""


def write_minimal_inputs(d: Path) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    (d / "POSCAR").write_text(MINIMAL_POSCAR)
    (d / "CONTCAR").write_text(MINIMAL_POSCAR)
    (d / "INCAR").write_text(MINIMAL_INCAR)
    (d / "KPOINTS").write_text(MINIMAL_KPOINTS)
    (d / "POTCAR").write_text(MINIMAL_POTCAR)
    return d


def write_minimal_outcar(d: Path, energy: str = "-5.0", converged: bool = True) -> None:
    body = f" free  energy    TOTEN  =    {energy} eV\n"
    if converged:
        body += " General timing and accounting\n"
    (d / "OUTCAR").write_text(body)


def write_complete_calc(d: Path, energy: str = "-5.0") -> Path:
    write_minimal_inputs(d)
    write_minimal_outcar(d, energy=energy, converged=True)
    return d


@pytest.fixture
def cache_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from vasp_cache.paths import _reset_project, override_cache_root

    root = tmp_path / "vasp_cache_root"
    root.mkdir()
    _reset_project()
    monkeypatch.setenv("VASP_CACHE_ROOT", str(root))
    override_cache_root(root)
    yield root
    _reset_project()


LARGE_POSCAR = """\
Large cell
1.0
30.0 0 0
0 30.0 0
0 0 30.0
Si
2
Direct
0 0 0
0.25 0.25 0.25
"""


def write_large_lattice_calc(d: Path, energy: str = "-5.0") -> Path:
    """Write inputs + OUTCAR with an unrealistically large unit cell (> MAX_LATTICE)."""
    d.mkdir(parents=True, exist_ok=True)
    (d / "POSCAR").write_text(LARGE_POSCAR)
    (d / "CONTCAR").write_text(LARGE_POSCAR)
    (d / "INCAR").write_text(MINIMAL_INCAR)
    (d / "KPOINTS").write_text(MINIMAL_KPOINTS)
    (d / "POTCAR").write_text(MINIMAL_POTCAR)
    write_minimal_outcar(d, energy=energy, converged=True)
    return d
