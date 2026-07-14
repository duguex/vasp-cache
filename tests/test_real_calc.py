"""Integration tests against real VASP calculation directories.

These are **not** synthetic fixtures. They read complete calculation trees
from production/shared data (or paths listed in REAL_VASP_CALC_DIRS).

Skip when data is unavailable so default CI without NFS still works:

    pytest -m real_data
    REAL_VASP_CALC_DIRS=/path/a:/path/b pytest -m real_data
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from vasp_cache.api import fetch, get_meta, has, put, query, stats
from vasp_cache.mapping import content_hash
from vasp_cache.paths import _reset_project, override_cache_root

pytestmark = pytest.mark.real_data

_REQUIRED = ("INCAR", "KPOINTS", "OUTCAR", "POTCAR")
_DEFAULT_ROOT = Path(
    os.environ.get(
        "REAL_VASP_CALC_ROOT",
        "/mnt/shared/home/2sidesniddle/vasp/2025_undergo_spin_defect",
    )
)

# Prefer modest, well-known complete calcs (not MnPS3 — abandoned)
_DEFAULT_DIRS = [
    _DEFAULT_ROOT / "ZnO" / "cpd" / "ZnO_mp-2133",
    _DEFAULT_ROOT / "SrTe" / "unitcell" / "dos",
    _DEFAULT_ROOT / "BaS" / "unitcell" / "dos",
]


def _is_complete_calc(d: Path) -> bool:
    if not d.is_dir():
        return False
    if not all((d / f).is_file() for f in _REQUIRED):
        return False
    if not ((d / "CONTCAR").is_file() or (d / "POSCAR").is_file()):
        return False
    try:
        if (d / "OUTCAR").stat().st_size < 10_000:
            return False
    except OSError:
        return False
    return True


def _discover_dirs() -> list[Path]:
    env = os.environ.get("REAL_VASP_CALC_DIRS", "").strip()
    if env:
        dirs = [Path(p) for p in env.split(":") if p.strip()]
        return [d for d in dirs if _is_complete_calc(d)]

    found = [d for d in _DEFAULT_DIRS if _is_complete_calc(d)]
    return found


REAL_DIRS = _discover_dirs()


def pytest_generate_tests(metafunc):
    if "real_calc_dir" in metafunc.fixturenames:
        if not REAL_DIRS:
            metafunc.parametrize(
                "real_calc_dir",
                [
                    pytest.param(
                        None,
                        marks=pytest.mark.skip(
                            reason=(
                                "No real VASP calc dirs found. "
                                "Set REAL_VASP_CALC_DIRS or mount spin_defect data."
                            )
                        ),
                    )
                ],
            )
        else:
            metafunc.parametrize(
                "real_calc_dir",
                REAL_DIRS,
                ids=[p.name for p in REAL_DIRS],
            )


@pytest.fixture
def isolated_cache(tmp_path: Path):
    root = tmp_path / "real_vasp_cache"
    _reset_project()
    override_cache_root(root)
    yield root
    _reset_project()
    override_cache_root(None)


def test_real_put_has_fetch_roundtrip(real_calc_dir: Path, isolated_cache: Path, tmp_path: Path):
    """put real calc → wipe OUTCAR → fetch restores identical bytes."""
    assert real_calc_dir is not None
    outcar = real_calc_dir / "OUTCAR"
    original = outcar.read_bytes()
    assert len(original) > 10_000

    ch = put(real_calc_dir)
    assert ch is not None
    assert has(real_calc_dir) is True

    meta = get_meta(real_calc_dir)
    assert meta is not None
    assert meta.get("total_energy") is not None
    assert meta.get("content_hash") == ch
    assert meta.get("mapping_digest")

    # Work dir with same inputs, no outputs
    work = tmp_path / f"work_{real_calc_dir.name}"
    work.mkdir()
    for name in ("INCAR", "POSCAR", "CONTCAR", "KPOINTS", "POTCAR"):
        src = real_calc_dir / name
        if src.is_file():
            shutil.copy2(src, work / name)
    # Prefer POSCAR if CONTCAR missing in work already handled
    if not (work / "POSCAR").is_file() and (work / "CONTCAR").is_file():
        shutil.copy2(work / "CONTCAR", work / "POSCAR")

    assert content_hash(work) == content_hash(real_calc_dir)
    assert has(work) is True
    assert fetch(work) is True
    restored = (work / "OUTCAR").read_bytes()
    assert restored == original


def test_real_query_after_put(real_calc_dir: Path, isolated_cache: Path):
    """After putting a real calc, query/stats see it."""
    ch = put(real_calc_dir)
    assert ch is not None
    meta = get_meta(real_calc_dir)
    formula = meta.get("formula")
    assert formula
    rows = query(formula=formula, converged_only=False, limit=50)
    hashes = {r.get("content_hash") for r in rows}
    assert ch in hashes
    s = stats()
    assert s["entries"] >= 1
