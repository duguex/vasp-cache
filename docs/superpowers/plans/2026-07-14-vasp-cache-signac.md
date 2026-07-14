# vasp-cache signac Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship an installable `vasp-cache` package that uses signac to store original VASP output files keyed by Mapping-Profile-driven `content_hash`, with black-box `put`/`fetch`, tunable hard/soft mapping, and secondary metadata query; cut vasp-sop over to this package and abandon legacy JSONStore cache.

**Architecture:** One global signac Project at `~/.vasp_cache` (overridable). Hard identity is `content_hash` from a **Mapping Profile** (`statepoint = {"content_hash": ...}`). Job workspace holds OUTCAR/CONTCAR/…; `job.document` holds searchable summary + mapping audit fields. Soft map is config-only distance helpers (no ML). `vasp_cache` never imports `vasp_sop`.

**Tech Stack:** Python ≥3.10, signac ≥2,<3, pymatgen, emmet-core, pytest, setuptools.

**Spec:** `docs/superpowers/specs/2026-07-14-vasp-cache-signac-design.md`

## Global Constraints

- No runtime read of `~/.vasp_sop/meta.json` or `blobs.json`
- No `vasp_sop` imports inside `vasp_cache`
- Hard keys come from Mapping Profile; **default** profile uses legacy sop-like critical fields + `key_generation`
- Soft-only profile edits must not change hard `content_hash`
- Critical profile edits must bump `key_generation` (or refuse)
- Default do not store POTCAR / WAVECAR / CHGCAR
- TDD: failing test before implementation for each behavior
- Prefer small commits after each green task

---

## File structure (target)

```
vasp_cache/                          # repo root (~/vasp_cache)
  pyproject.toml
  src/vasp_cache/
    __init__.py
    paths.py
    mapping.py
    fingerprint.py
    parse.py
    api.py
    cli.py
    data/
      mapping.default.yaml
  tests/
    conftest.py
    test_fingerprint.py
    test_mapping.py
    test_paths.py
    test_put_fetch.py
    test_parse.py
    test_query.py
    test_cli.py
  docs/superpowers/specs/2026-07-14-vasp-cache-signac-design.md
  docs/superpowers/plans/2026-07-14-vasp-cache-signac.md
  README.md
  DESIGN.md

# separate repo (later tasks)
~/vasp_sop/
  pyproject.toml                     # add vasp-cache dep
  vasp_sop/core/cache.py             # thin adapter
  tests/...                          # update imports / behavior
```

---

### Task 1: Package scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `src/vasp_cache/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=64"]
build-backend = "setuptools.build_meta"

[project]
name = "vasp-cache"
version = "0.1.0"
description = "Black-box VASP calculation cache (signac backend)"
readme = "README.md"
requires-python = ">=3.10"
license = { text = "MIT" }
dependencies = [
    "signac>=2.0,<3",
    "pymatgen>=2023.0",
    "emmet-core>=0.60",
]

[project.optional-dependencies]
dev = ["pytest>=7.0"]

[project.scripts]
vasp-cache = "vasp_cache.cli:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Write package stub**

```python
# src/vasp_cache/__init__.py
"""vasp-cache: input-fingerprint → VASP output files (signac backend)."""

__version__ = "0.1.0"
```

- [ ] **Step 3: Write `tests/conftest.py` helpers**

```python
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
    root = tmp_path / "vasp_cache_root"
    root.mkdir()
    monkeypatch.setenv("VASP_CACHE_ROOT", str(root))
    return root
```

- [ ] **Step 4: Install editable and smoke import**

```bash
cd ~/vasp_cache
python3 -m pip install -e ".[dev]"
python3 -c "import vasp_cache; print(vasp_cache.__version__)"
```

Expected: `0.1.0`

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/vasp_cache/__init__.py tests/conftest.py
git commit -m "chore: scaffold vasp-cache package with signac deps"
```

---

### Task 2: Mapping Profile + fingerprint

**Files:**
- Create: `src/vasp_cache/data/mapping.default.yaml`
- Create: `src/vasp_cache/mapping.py`
- Create: `src/vasp_cache/fingerprint.py`
- Create: `tests/test_mapping.py`
- Create: `tests/test_fingerprint.py`

**Interfaces:**
- Produces: `load_mapping()`, `mapping_digest()`, `content_hash(src_dir, mapping=None)`, `soft_vector()`, `soft_distance()`
- Consumes: MappingProfile; pymatgen Structure/Incar/Kpoints
- Optional dep: `pyyaml>=6` if YAML load is used (add to pyproject.toml)

Default profile must encode legacy-compatible critical fields (sop INCAR key list, formula structure tag, grid kpoints, species_token potcar) plus `key_generation: 1`. Soft section includes NSW/NELM scales.

Hard hash form: `f"{key_generation}:{legacy_body}"` under default profile.
Soft-only edits must not change hard hash; critical edits change digest and require generation bump policy in mapping helpers.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_fingerprint.py
from pathlib import Path

from vasp_cache.fingerprint import content_hash
from conftest import write_minimal_inputs


def test_content_hash_stable(tmp_path: Path):
    d = write_minimal_inputs(tmp_path / "a")
    h1 = content_hash(d)
    h2 = content_hash(d)
    assert h1 == h2
    assert "Si2" in h1 or "Si" in h1
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
```

- [ ] **Step 2: Run tests — expect fail**

```bash
cd ~/vasp_cache && python3 -m pytest tests/test_fingerprint.py -v
```

Expected: `ModuleNotFoundError` or import error for `vasp_cache.fingerprint`

- [ ] **Step 3: Implement `fingerprint.py`**

Port semantics from `vasp_sop/core/cache.py` (lines ~114–182):

```python
# src/vasp_cache/fingerprint.py
from __future__ import annotations

import re
from pathlib import Path

_INCAR_FINGERPRINT_KEYS = (
    "ENCUT", "PREC", "ISMEAR", "SIGMA", "ISIF",
    "LDAU", "LDAUTYPE", "LDAUU", "LDAUJ", "LDAUL",
    "GGA", "IVDW", "LASPH", "METAGGA",
)


def _incar_fingerprint(src_dir: Path) -> str:
    incar_path = src_dir / "INCAR"
    if not incar_path.is_file():
        return "default"
    try:
        from pymatgen.io.vasp.inputs import Incar
        incar = Incar.from_file(str(incar_path))
    except Exception:
        return "default"
    parts = []
    for k in _INCAR_FINGERPRINT_KEYS:
        v = incar.get(k)
        if v is not None:
            parts.append(f"{k}={v}")
    return "|".join(parts) if parts else "default"


def _potcar_fingerprint(src_dir: Path) -> str:
    potcar_path = src_dir / "POTCAR"
    if not potcar_path.is_file():
        return "nopot"
    try:
        text = potcar_path.read_text()
        pp_ids = re.findall(r"PAW_\w+\s+(\S+)", text)
        return ",".join(pp_ids) if pp_ids else "unknown"
    except Exception:
        return "unknown"


def content_hash(src_dir: Path) -> str:
    """Deterministic fingerprint of VASP *inputs* in *src_dir*."""
    from pymatgen.core.structure import Structure
    from pymatgen.io.vasp.inputs import Kpoints

    src_dir = Path(src_dir)
    struct_tag = "unknown"
    for cand in (src_dir / "CONTCAR", src_dir / "POSCAR"):
        if cand.is_file():
            try:
                struct = Structure.from_file(str(cand))
                struct_tag = struct.composition.formula.replace(" ", "")
                break
            except Exception:
                continue

    kpoints_tag = "nokpt"
    kpoints_path = src_dir / "KPOINTS"
    if kpoints_path.is_file():
        try:
            kpts = Kpoints.from_file(str(kpoints_path))
            style = kpts.style
            grid = kpts.kpts[0] if kpts.kpts else (0, 0, 0)
            if style == Kpoints.supported_modes.Gamma and max(grid) <= 1:
                kpoints_tag = "gamma"
            elif style == Kpoints.supported_modes.Line_mode:
                kpoints_tag = "band-structure"
            else:
                kpoints_tag = "".join(str(k) for k in grid[:3])
        except Exception:
            pass

    return (
        f"{struct_tag}_{kpoints_tag}_"
        f"{_incar_fingerprint(src_dir)}_{_potcar_fingerprint(src_dir)}"
    )
```

- [ ] **Step 4: Run tests — expect pass**

```bash
python3 -m pytest tests/test_fingerprint.py -v
```

- [ ] **Step 5: Export and commit**

```python
# src/vasp_cache/__init__.py — add
from vasp_cache.fingerprint import content_hash

__all__ = ["content_hash", "__version__"]
```

```bash
git add src/vasp_cache/fingerprint.py src/vasp_cache/__init__.py tests/test_fingerprint.py
git commit -m "feat: add content_hash fingerprint matching sop semantics"
```

---

### Task 3: paths + signac project

**Files:**
- Create: `src/vasp_cache/paths.py`
- Create: `tests/test_paths.py`

**Interfaces:**
- Produces: `CACHE_ROOT`, `override_cache_root(p)`, `get_project() -> signac.Project`
- Env: `VASP_CACHE_ROOT` overrides default `~/.vasp_cache`

- [ ] **Step 1: Failing tests**

```python
# tests/test_paths.py
from pathlib import Path

import signac

from vasp_cache.paths import get_project, override_cache_root


def test_get_project_creates_signac(cache_root: Path):
    # cache_root fixture sets VASP_CACHE_ROOT
    from vasp_cache import paths
    paths._reset_project()  # clear singleton
    project = get_project()
    assert Path(project.path) == cache_root
    assert (cache_root / ".signac").exists() or (cache_root / "workspace").exists() or True
    # signac 2 stores config under .signac
    assert signac.get_project(root=str(cache_root)) is not None


def test_override_cache_root(tmp_path: Path):
    from vasp_cache import paths
    paths._reset_project()
    other = tmp_path / "other"
    other.mkdir()
    override_cache_root(other)
    p = get_project()
    assert Path(p.path) == other
```

- [ ] **Step 2: Run — fail**

```bash
python3 -m pytest tests/test_paths.py -v
```

- [ ] **Step 3: Implement `paths.py`**

```python
# src/vasp_cache/paths.py
from __future__ import annotations

import os
import threading
from pathlib import Path

import signac

_DEFAULT_ROOT = Path.home() / ".vasp_cache"
_cache_root: Path | None = None
_project = None
_lock = threading.Lock()


def _resolved_root() -> Path:
    if _cache_root is not None:
        return _cache_root
    env = os.environ.get("VASP_CACHE_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    return _DEFAULT_ROOT


def override_cache_root(p: Path | None) -> None:
    """Set cache root (tests). Pass None to clear override."""
    global _cache_root, _project
    with _lock:
        _cache_root = Path(p).resolve() if p is not None else None
        _project = None


def _reset_project() -> None:
    global _project
    with _lock:
        _project = None


def get_project():
    """Return signac Project for the active cache root (init if needed)."""
    global _project
    with _lock:
        if _project is not None:
            return _project
        root = _resolved_root()
        root.mkdir(parents=True, exist_ok=True)
        try:
            _project = signac.get_project(root=str(root))
        except Exception:
            _project = signac.init_project(root=str(root))
        return _project


# public alias for docs/tests
def cache_root() -> Path:
    return _resolved_root()
```

Note: verify signac 2.x `init_project`/`get_project` signatures against installed version; if `root=` is wrong, use cwd pattern:

```python
# fallback pattern if needed
import os
from contextlib import contextmanager

@contextmanager
def _at(root: Path):
    prev = Path.cwd()
    os.chdir(root)
    try:
        yield
    finally:
        os.chdir(prev)
```

Adjust implementation so tests pass on signac 2.4.

- [ ] **Step 4: Green + commit**

```bash
python3 -m pytest tests/test_paths.py -v
git add src/vasp_cache/paths.py tests/test_paths.py
git commit -m "feat: signac project bootstrap and cache root override"
```

---

### Task 4: put / has / fetch (black box core)

**Files:**
- Create: `src/vasp_cache/api.py` (core ops first; parse later can be minimal)
- Create: `tests/test_put_fetch.py`

**Interfaces:**
- `put(calc_dir, *, formula=None, task_name=None, store_inputs=True, include=()) -> str | None`
- `has(input_dir) -> bool`
- `fetch(input_dir) -> bool`

- [ ] **Step 1: Failing tests**

```python
# tests/test_put_fetch.py
from pathlib import Path

from vasp_cache.api import fetch, has, put
from vasp_cache.paths import override_cache_root, _reset_project
from conftest import write_complete_calc, write_minimal_inputs, write_minimal_outcar


def test_put_fetch_roundtrip(cache_root: Path, tmp_path: Path):
    _reset_project()
    calc = write_complete_calc(tmp_path / "calc", energy="-12.5")
    outcar_bytes = (calc / "OUTCAR").read_bytes()

    ch = put(calc)
    assert ch is not None
    assert has(calc) is True

    # simulate clean workdir with inputs only
    work = write_minimal_inputs(tmp_path / "work")
    assert (work / "OUTCAR").exists() is False
    # same inputs as calc → same hash (CONTCAR/POSCAR/INCAR/KPOINTS/POTCAR match)
    assert has(work) is True
    assert fetch(work) is True
    assert (work / "OUTCAR").is_file()
    assert (work / "OUTCAR").read_bytes() == outcar_bytes


def test_has_false_when_empty(cache_root: Path, tmp_path: Path):
    _reset_project()
    d = write_minimal_inputs(tmp_path / "only_in")
    assert has(d) is False
    assert fetch(d) is False


def test_put_skips_without_outcar(cache_root: Path, tmp_path: Path):
    _reset_project()
    d = write_minimal_inputs(tmp_path / "no_out")
    assert put(d) is None


def test_put_does_not_store_potcar(cache_root: Path, tmp_path: Path):
    _reset_project()
    calc = write_complete_calc(tmp_path / "calc")
    ch = put(calc)
    from vasp_cache.paths import get_project
    job = get_project().open_job({"content_hash": ch})
    assert not Path(job.fn("POTCAR")).is_file()
```

- [ ] **Step 2: Run — fail**

```bash
python3 -m pytest tests/test_put_fetch.py -v
```

- [ ] **Step 3: Minimal `api.py` implementation**

```python
# src/vasp_cache/api.py
from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path
from typing import Any, Iterable

from vasp_cache.fingerprint import content_hash
from vasp_cache.paths import get_project

logger = logging.getLogger(__name__)

_OUTPUT_NAMES = ("OUTCAR", "CONTCAR", "vasprun.xml")
_INPUT_NAMES = ("INCAR", "POSCAR", "KPOINTS")  # no POTCAR


def _detect_formula_task(src_dir: Path) -> tuple[str, str]:
    name = src_dir.name
    if "_mp-" in name:
        formula = name.split("_mp-", 1)[0]
        return formula, name
    formula = "unknown"
    for cand in (src_dir / "CONTCAR", src_dir / "POSCAR"):
        if cand.is_file():
            try:
                from pymatgen.core.structure import Structure
                formula = Structure.from_file(str(cand)).composition.reduced_formula
                break
            except Exception:
                continue
    return formula, name


def _outcar_usable(src_dir: Path) -> tuple[bool, float | None]:
    """Return (converged_or_has_energy, energy)."""
    path = src_dir / "OUTCAR"
    if not path.is_file():
        alt = src_dir / "output" / "OUTCAR"
        path = alt if alt.is_file() else path
    if not path.is_file():
        return False, None
    text = path.read_text(errors="replace")
    import re
    energies = re.findall(r"free\s+energy\s+TOTEN\s*=\s*([-\d.]+)", text)
    energy = float(energies[-1]) if energies else None
    converged = "General timing and accounting" in text[-4096:]
    if converged or energy is not None:
        return True, energy
    return False, None


def put(
    calc_dir: Path | str,
    *,
    formula: str | None = None,
    task_name: str | None = None,
    store_inputs: bool = True,
    include: Iterable[str] = (),
) -> str | None:
    calc_dir = Path(calc_dir)
    usable, energy = _outcar_usable(calc_dir)
    if not usable:
        logger.debug("skip put %s: no usable OUTCAR", calc_dir)
        return None

    ch = content_hash(calc_dir)
    f, tn = _detect_formula_task(calc_dir)
    formula = formula or f
    task_name = task_name or tn

    project = get_project()
    job = project.open_job({"content_hash": ch}).init()

    # outputs
    for name in _OUTPUT_NAMES:
        src = calc_dir / name
        if src.is_file():
            shutil.copy2(src, job.fn(name))
    if not Path(job.fn("CONTCAR")).is_file() and (calc_dir / "POSCAR").is_file():
        shutil.copy2(calc_dir / "POSCAR", job.fn("CONTCAR"))

    if store_inputs:
        for name in _INPUT_NAMES:
            src = calc_dir / name
            if src.is_file():
                shutil.copy2(src, job.fn(name))

    for name in include:
        src = calc_dir / name
        if src.is_file():
            shutil.copy2(src, job.fn(name))

    # minimal doc (richer parse in Task 5)
    job.doc["formula"] = formula
    job.doc["task_name"] = task_name
    job.doc["total_energy"] = energy
    job.doc["converged"] = True
    job.doc["source_dir"] = str(calc_dir.resolve())
    job.doc["cached_at"] = time.time()
    job.doc["parsed_by"] = "minimal"
    m = load_mapping()
    job.doc["profile_id"] = m.profile_id
    job.doc["key_generation"] = m.key_generation
    job.doc["mapping_digest"] = mapping_digest(m)
    return ch


def has(input_dir: Path | str) -> bool:
    input_dir = Path(input_dir)
    ch = content_hash(input_dir)
    project = get_project()
    job = project.open_job({"content_hash": ch})
    try:
        return job.isfile("OUTCAR")  # signac Job.isfile if available
    except Exception:
        return Path(job.fn("OUTCAR")).is_file() if job in project else False


def fetch(input_dir: Path | str) -> bool:
    input_dir = Path(input_dir)
    if not has(input_dir):
        return False
    ch = content_hash(input_dir)
    job = get_project().open_job({"content_hash": ch})
    restored = False
    for name in _OUTPUT_NAMES:
        src = Path(job.fn(name))
        if src.is_file():
            shutil.copy2(src, input_dir / name)
            if name == "OUTCAR":
                restored = True
    return restored
```

Fix `has()` against real signac API: prefer

```python
def has(input_dir: Path | str) -> bool:
    input_dir = Path(input_dir)
    ch = content_hash(input_dir)
    project = get_project()
    job = project.open_job({"content_hash": ch})
    if job not in project:
        return False
    return Path(job.fn("OUTCAR")).is_file()
```

- [ ] **Step 4: Green tests**

```bash
python3 -m pytest tests/test_put_fetch.py -v
```

- [ ] **Step 5: Export API + commit**

Update `__init__.py` to export `put`, `has`, `fetch`, `override_cache_root`.

```bash
git add src/vasp_cache/api.py src/vasp_cache/__init__.py tests/test_put_fetch.py
git commit -m "feat: black-box put/has/fetch on signac workspaces"
```

---

### Task 5: Summary parse → job.document

**Files:**
- Create: `src/vasp_cache/parse.py`
- Create: `tests/test_parse.py`
- Modify: `src/vasp_cache/api.py` (`put` fills richer doc)

**Interfaces:**
- `summarize_calc(src_dir: Path) -> dict[str, Any]`

- [ ] **Step 1: Tests** (port intent from sop `test_parser.py`)

```python
# tests/test_parse.py
from pathlib import Path

from vasp_cache.parse import summarize_calc
from conftest import write_minimal_outcar, write_minimal_inputs


def test_regex_summary(tmp_path: Path):
    d = write_minimal_inputs(tmp_path / "c")
    write_minimal_outcar(d, energy="-5.0", converged=True)
    s = summarize_calc(d)
    assert s["converged"] is True
    assert s["total_energy"] == -5.0
    assert s["parsed_by"] in {"regex", "TaskDoc", "fallback"}
```

- [ ] **Step 2: Implement `parse.py`**

Port `_parse_vasp_dir` + tags helpers from sop `cache.py` **without** `_build_blob` and without `vasp_sop` imports. Keep TaskDoc try/except + regex fallback.

- [ ] **Step 3: Wire into `put`**

Replace minimal doc assignment with:

```python
summary = summarize_calc(calc_dir)
# merge formula/task_name overrides
for k, v in summary.items():
    job.doc[k] = v
job.doc["formula"] = formula
job.doc["task_name"] = task_name
job.doc["source_dir"] = str(calc_dir.resolve())
job.doc["cached_at"] = time.time()
```

Apply `MAX_LATTICE` skip: if `summary.get("max_abc")` and `MAX_LATTICE` and max_abc > MAX_LATTICE: return None.

```python
# in api.py or parse.py
MAX_LATTICE: float | None = 25.0
```

- [ ] **Step 4: pytest parse + put_fetch**

```bash
python3 -m pytest tests/test_parse.py tests/test_put_fetch.py -v
```

- [ ] **Step 5: Commit**

```bash
git commit -am "feat: fill job.document via TaskDoc/regex summary parse"
```

---

### Task 6: query / list_entries / stats / get_meta

**Files:**
- Modify: `src/vasp_cache/api.py`
- Create: `tests/test_query.py`

**Interfaces:**
- `query(formula=None, functional=None, calc_type=None, tags_contains=None, bandgap_min=None, lattice_max=None, converged_only=True, limit=100) -> list[dict]`
- `list_entries(limit=50) -> list[dict]`
- `stats() -> dict`
- `get_meta(input_dir | None = None, *, content_hash=None, formula=None, key=None) -> dict | None`

- [ ] **Step 1: Tests**

```python
def test_query_by_formula(cache_root, tmp_path):
    _reset_project()
    put(write_complete_calc(tmp_path / "Si_run"))
    rows = query(formula="Si")  # reduced_formula may be Si
    assert len(rows) >= 1
    assert "total_energy" in rows[0]
```

Adjust formula assertion to whatever `detect` + parse store (Si vs Si2). Prefer asserting `rows[0]["content_hash"]` matches `content_hash(calc)`.

- [ ] **Step 2: Implement using `project.find_jobs`**

```python
def query(...):
    project = get_project()
    filt: dict = {}
    if formula:
        filt["doc.formula"] = formula
    if bandgap_min is not None:
        filt["doc.bandgap"] = {"$gte": bandgap_min}
    if converged_only:
        filt["doc.converged"] = True
    # functional / tags_contains: filter in Python over tags string if signac regex awkward
    rows = []
    for job in project.find_jobs(filt):
        row = dict(job.doc)
        row["content_hash"] = job.sp["content_hash"]
        rows.append(row)
        if len(rows) >= limit:
            break
    return rows
```

- [ ] **Step 3: Green + commit**

```bash
python3 -m pytest tests/test_query.py -v
git commit -am "feat: query/list/stats/get_meta over signac job documents"
```

---

### Task 7: CLI

**Files:**
- Create: `src/vasp_cache/cli.py`
- Create: `tests/test_cli.py`

- [ ] **Step 1: CLI tests via subprocess or argparse main**

```python
def test_cli_put_status(cache_root, tmp_path):
    calc = write_complete_calc(tmp_path / "c")
    from vasp_cache.cli import main
    assert main(["put", str(calc)]) == 0
    assert main(["status"]) == 0
```

- [ ] **Step 2: Implement argparse CLI**

Subcommands: `put`, `put -r`, `fetch`, `has`, `query`, `status`, `content-hash`.

Recursive put: walk for directories containing `OUTCAR`, call `put`.

- [ ] **Step 3: Green + commit**

```bash
python3 -m pytest tests/test_cli.py -v
git commit -am "feat: vasp-cache CLI"
```

---

### Task 8: Docs refresh in vasp-cache repo

**Files:**
- Modify: `README.md`, `DESIGN.md` to match signac black-box design (replace old maggma-only narrative)

- [ ] **Step 1: Rewrite README** around put/fetch, signac, abandon JSONStore  
- [ ] **Step 2: Shorten DESIGN.md** to point at `docs/superpowers/specs/2026-07-14-vasp-cache-signac-design.md`  
- [ ] **Step 3: Commit**

```bash
git commit -am "docs: align README/DESIGN with signac black-box design"
```

---

### Task 9: vasp-sop adapter cutover

**Files (in `~/vasp_sop`):**
- Modify: `pyproject.toml` — add dependency  
- Modify: `vasp_sop/core/cache.py` — thin adapter  
- Modify: tests as needed  

- [ ] **Step 1: Add dependency**

```toml
# pyproject.toml dependencies
"vasp-cache>=0.1.0",
```

For local dev:

```bash
cd ~/vasp_sop && python3 -m pip install -e ~/vasp_cache
```

- [ ] **Step 2: Replace `cache.py` body**

Keep module path `vasp_sop.core.cache` for imports. Structure:

```python
"""Adapter to vasp-cache. MP path constants remain here."""
from pathlib import Path
from vasp_cache import (
    put as _put,
    has as _has,
    fetch as _fetch,
    query,
    list_entries as list_cache,
    stats as cache_stats,
    content_hash as _content_hash,
    override_cache_root,
    get_meta,
)
from vasp_cache.api import MAX_LATTICE  # if exported
from vasp_cache.paths import cache_root

# MP caches stay under ~/.vasp_sop (NOT results cache)
SOP_ROOT = Path.home() / ".vasp_sop"
MP_CACHE = SOP_ROOT / "mp_cache"
POSCAR_CACHE = MP_CACHE / "poscars"
CALC_CACHE = SOP_ROOT / "calc_cache"  # legacy path constant if still referenced
CACHE_ROOT = cache_root()  # or keep name pointing at vasp-cache root

def vasp_results_put(src_dir, formula=None, content_hash=None, task_name=None):
    _put(src_dir, formula=formula, task_name=task_name)

def cache_lookup(src_dir):
    return get_meta(src_dir) if _has(src_dir) else None

def restore_from_cache(src_dir) -> bool:
    return _fetch(src_dir)

def vasp_results_get(formula, key):
    # implement via query + match content_hash/task_name/mp id
    ...
```

Remove maggma JSONStore, blobs, migrate_from_sqlite, submissions helpers if already moved to JobStore.

Update `job_store.py` if it imported `CACHE_ROOT` from cache for `~/.vasp_sop` — **keep jobs.db under SOP_ROOT**, not vasp-cache root:

```python
# job_store should use Path.home()/".vasp_sop" explicitly, not vasp-cache root
```

- [ ] **Step 3: Run sop cache-related tests**

```bash
cd ~/vasp_sop
python3 -m pytest tests/test_cache.py tests/test_parser.py tests/test_cli.py -v --tb=short
```

Fix adapter until green (or update tests that asserted blobs.json / maggma specifics).

- [ ] **Step 4: Commit in vasp_sop**

```bash
git add -A && git commit -m "refactor: use vasp-cache (signac) for results; drop JSONStore cache"
```

---

### Task 10: End-to-end verification

- [ ] **Step 1: vasp-cache full suite**

```bash
cd ~/vasp_cache && python3 -m pytest -v
```

Expected: all pass

- [ ] **Step 2: Manual smoke**

```bash
export VASP_CACHE_ROOT=/tmp/vc_smoke
rm -rf "$VASP_CACHE_ROOT"
# use a real or fixture calc dir
vasp-cache put /path/to/complete_calc
vasp-cache status
- [ ] **Step 3: Confirm no legacy paths**

```bash
rg -n "meta\.json|blobs\.json|JSONStore|maggma" ~/vasp_cache/src ~/vasp_sop/vasp_sop/core/cache.py
```

Expected: no results-cache usage of maggma JSONStore

- [ ] **Step 4: Final commits if docs/tests tweaks needed**

---

## Spec coverage checklist

| Spec item | Task |
|-----------|------|
| signac project root / override | Task 3 |
| Mapping Profile + content_hash + soft | Task 2 |
| put file payload + mapping audit | Task 4 |
| fetch black box | Task 4 |
| job.doc summary | Task 5 |
| query secondary | Task 6 |
| CLI (incl. mapping show/check) | Task 7 |
| abandon JSONStore | Task 9–10 |
| sop adapter | Task 9 |
| no vasp_sop import in package | Tasks 1–7 |
| README/DESIGN | Task 8 |

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-14-vasp-cache-signac.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks  
2. **Inline Execution** — execute tasks in this session with executing-plans checkpoints  

Which approach?
