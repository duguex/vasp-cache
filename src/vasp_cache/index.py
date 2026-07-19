"""SQLite index for VASP calculation directories — BLOB + structured extracts."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import math
import os
import re
import sqlite3
import tempfile
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator

from vasp_cache.errors import IdentityInputError
from vasp_cache.paths import cache_root

_DB_NAME = "index.sqlite"

_SCHEMA = """
CREATE TABLE entries (
    identity_key   TEXT PRIMARY KEY,
    formula        TEXT NOT NULL,
    incar_json     TEXT NOT NULL,
    structure_json TEXT NOT NULL,
    kpoints_json   TEXT NOT NULL,
    potcar_json    TEXT NOT NULL,
    lattice_json   TEXT NOT NULL,
    -- structured extracts
    final_energy            REAL,
    total_mag               REAL,
    electrostatic_potentials TEXT,
    final_structure_json    TEXT,
    n_ionic_steps           INTEGER,
    converged_ionic         INTEGER,
    converged_electronic    INTEGER,
    -- BLOBs
    outcar_blob   BLOB NOT NULL,
    vasprun_blob  BLOB,
    contcar_blob  BLOB,
    -- metadata
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    source_path TEXT
);

CREATE TABLE discarded_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    identity_key TEXT NOT NULL,
    source_path  TEXT NOT NULL,
    reason       TEXT NOT NULL,
    final_energy REAL,
    converged_ionic    INTEGER,
    converged_electronic INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (identity_key) REFERENCES entries(identity_key)
);

CREATE INDEX entries_formula ON entries(formula);
CREATE INDEX entries_energy ON entries(final_energy);
CREATE INDEX discarded_identity ON discarded_candidates(identity_key);
"""

_REQUIRED_FILES = ("POSCAR", "INCAR", "KPOINTS", "POTCAR",
                   "OUTCAR", "CONTCAR", "vasprun.xml")


# --- helpers -----------------------------------------------------------

def _compress(data: bytes) -> bytes:
    return zlib.compress(data, level=6)


def _decompress(data: bytes) -> bytes:
    return zlib.decompress(data)


# --- identity ----------------------------------------------------------

@dataclass(frozen=True)
class Identity:
    key: str
    formula: str
    incar: dict[str, str]
    structure_json: str


def db_path(root: Path | None = None) -> Path:
    return (Path(root) if root is not None else cache_root()) / _DB_NAME


def normalize_incar(path: Path | str) -> dict[str, str]:
    """Return sorted canonical INCAR dict, preserving value text."""
    path = Path(path)
    if not path.is_file():
        raise IdentityInputError(f"identity requires INCAR: {path}")
    text = path.read_text("utf-8")
    values: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "!", "//")):
            continue
        delim = "=" if "=" in stripped else ";"
        if delim not in stripped:
            continue
        key, _, val = stripped.partition(delim)
        key = key.strip().upper()
        val = val.strip()
        for cm in (" #", "\t#", " !", "\t!"):
            if cm in val:
                val = val[:val.index(cm)].strip()
                break
        val = " ".join(val.split())
        if key and val:
            values[key] = val
    if not values:
        raise IdentityInputError(f"INCAR contains no parameters: {path}")
    return dict(sorted(values.items()))


def normalize_kpoints(path: Path | str) -> dict[str, Any]:
    """Canonical KPOINTS dict for identity and reconstruction."""
    path = Path(path)
    if not path.is_file():
        raise IdentityInputError(f"identity requires KPOINTS: {path}")
    try:
        from pymatgen.io.vasp.inputs import Kpoints
        k = Kpoints.from_file(str(path))
        return dict(k.as_dict())
    except Exception as exc:
        raise IdentityInputError(f"invalid KPOINTS: {path}") from exc


def normalize_potcar(path: Path | str) -> dict[str, Any]:
    """Extract POTCAR identity tokens."""
    path = Path(path)
    if not path.is_file():
        raise IdentityInputError(f"identity requires POTCAR: {path}")
    data = path.read_bytes()
    entries: list[dict[str, str]] = []
    for m in re.finditer(
        rb"TITEL\s*=\s*PAW(?:_PKJ)?_(\S+)\s+(\S+)\s*(?:(\d{2}\w{3}\d{4}))?",
        data,
    ):
        xc = m.group(1).decode("ascii")
        elem = m.group(2).decode("ascii")
        version = m.group(3).decode("ascii") if m.group(3) else ""
        entries.append({"element": elem, "xc": xc, "version": version})
    if not entries:
        raise IdentityInputError(f"POTCAR: no TITEL found: {path}")
    return {
        "entries": entries,
        "species": [e["element"] for e in entries],
        "xc": entries[0]["xc"],
    }


def normalize_lattice(structure_dict: dict[str, Any]) -> dict[str, Any]:
    """Canonical lattice parameters from a Structure dict."""
    lat = structure_dict.get("lattice", {})
    mat = lat.get("matrix", [[1, 0, 0], [0, 1, 0], [0, 0, 1]])

    def _len(v):
        return math.sqrt(sum(x * x for x in v))

    def _angle(v1, v2):
        n1, n2 = _len(v1), _len(v2)
        dot = sum(x * y for x, y in zip(v1, v2))
        return math.degrees(math.acos(
            max(-1.0, min(1.0, dot / (n1 * n2)))
        ))

    return {
        "a": round(_len(mat[0]), 3),
        "b": round(_len(mat[1]), 3),
        "c": round(_len(mat[2]), 3),
        "alpha": round(_angle(mat[1], mat[2]), 1),
        "beta":  round(_angle(mat[0], mat[2]), 1),
        "gamma": round(_angle(mat[0], mat[1]), 1),
    }


def _structure_from_poscar(path: Path | str) -> tuple[str, str]:
    path = Path(path)
    if not path.is_file():
        raise IdentityInputError(f"identity requires POSCAR: {path}")
    try:
        from pymatgen.core.structure import Structure
        structure = Structure.from_file(str(path))
    except Exception as exc:
        raise IdentityInputError(f"invalid POSCAR: {path}") from exc
    formula = structure.composition.reduced_formula
    if not formula:
        raise IdentityInputError(f"POSCAR has no chemical formula: {path}")
    structure.sort()
    structure_json = json.dumps(
        structure.as_dict(), sort_keys=True, default=str,
    )
    return formula, structure_json


def identity_for_directory(directory: Path | str) -> Identity:
    directory = Path(directory)
    formula, structure_json = _structure_from_poscar(directory / "POSCAR")
    incar = normalize_incar(directory / "INCAR")
    kpoints = normalize_kpoints(directory / "KPOINTS")
    potcar = normalize_potcar(directory / "POTCAR")
    lattice = normalize_lattice(json.loads(structure_json))
    payload = json.dumps(
        {"formula": formula, "incar": incar, "structure": structure_json,
         "kpoints": kpoints, "potcar": potcar, "lattice": lattice},
        ensure_ascii=True, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return Identity(
        hashlib.sha256(payload).hexdigest(), formula, incar, structure_json,
    )


# --- structured extracts -----------------------------------------------

def _extract_outcar(path: Path) -> dict[str, Any]:
    """Extract fields from original OUTCAR via pymatgen.Outcar."""
    result: dict[str, Any] = {
        "final_energy": None, "total_mag": None,
        "electrostatic_potentials": None,
    }
    try:
        from pymatgen.io.vasp.outputs import Outcar
        o = Outcar(str(path))
        if o.final_energy is not None:
            result["final_energy"] = float(o.final_energy)
        if o.total_mag is not None:
            result["total_mag"] = float(o.total_mag)
        eps = o.electrostatic_potential
        if eps is not None:
            result["electrostatic_potentials"] = [float(p) for p in eps]
    except Exception:
        pass
    return result


def _extract_vasprun(path: Path) -> dict[str, Any]:
    """Extract fields from vasprun.xml via pymatgen.Vasprun."""
    result: dict[str, Any] = {
        "n_ionic_steps": None,
        "converged_ionic": None,
        "converged_electronic": None,
        "final_structure_json": None,
        "final_energy": None,
    }
    try:
        from pymatgen.io.vasp.outputs import Vasprun
        v = Vasprun(str(path), parse_dos=False, parse_eigen=False)
        result["n_ionic_steps"] = len(v.ionic_steps)
        result["converged_ionic"] = int(v.converged_ionic)
        result["converged_electronic"] = int(v.converged_electronic)
        final_s = v.final_structure
        result["final_structure_json"] = (
            final_s.as_dict() if final_s is not None else None
        )
        result["final_energy"] = (
            float(v.final_energy) if v.final_energy is not None else None
        )
    except Exception:
        pass
    return result


# --- schema ------------------------------------------------------------

def _create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)
    conn.commit()


def connect(root: Path | None = None) -> sqlite3.Connection:
    root = Path(root) if root is not None else cache_root()
    root.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path(root)))
    conn.row_factory = sqlite3.Row
    _create_schema_if_needed(conn)
    return conn


def _create_schema_if_needed(conn: sqlite3.Connection) -> None:
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master "
        "WHERE type='table' AND name='entries'"
    ).fetchone()
    if exists is None:
        _create_schema(conn)


def close_all() -> None:
    pass


# --- put ---------------------------------------------------------------

_INSERT_SQL = """INSERT OR REPLACE INTO entries (
     identity_key, formula, incar_json, structure_json,
     kpoints_json, potcar_json, lattice_json,
     final_energy, total_mag, electrostatic_potentials,
     final_structure_json,
     n_ionic_steps, converged_ionic, converged_electronic,
     outcar_blob, vasprun_blob, contcar_blob, source_path
   ) VALUES (?, ?, ?, ?, ?, ?, ?,
             ?, ?, ?, ?, ?, ?, ?,
             ?, ?, ?, ?)"""


def _should_replace(
    conn: sqlite3.Connection,
    identity_key: str,
    conv_ionic: bool | int | None,
) -> tuple[bool, str]:
    """Candidate replaces only if it improves convergence.

    Converged beats unconverged. If both same level, existing stays.
    """
    row = conn.execute(
        "SELECT converged_ionic FROM entries WHERE identity_key = ?",
        (identity_key,),
    ).fetchone()
    if row is None:
        return True, "new"
    existing_conv = bool(row["converged_ionic"])
    candidate_conv = bool(conv_ionic)
    if candidate_conv and not existing_conv:
        return True, "candidate_converged"
    return False, "existing_kept"


def _record_discard(
    conn: sqlite3.Connection,
    identity_key: str,
    source_path: str,
    reason: str,
    converged_ionic: bool | int | None,
    converged_electronic: bool | int | None,
    final_energy: float | None,
) -> None:
    conn.execute(
        """INSERT INTO discarded_candidates
           (identity_key, source_path, reason, final_energy,
            converged_ionic, converged_electronic)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (identity_key, source_path, reason,
         final_energy, converged_ionic, converged_electronic),
    )


def _put_into_conn(
    conn: sqlite3.Connection, identity: Identity, directory: Path,
) -> None:
    source = str(directory.resolve())
    outcar_bytes = (directory / "OUTCAR").read_bytes()
    vasprun_bytes = (directory / "vasprun.xml").read_bytes()
    contcar_bytes = (directory / "CONTCAR").read_bytes()

    outcar_extract = _extract_outcar(directory / "OUTCAR")
    vasprun_extract = _extract_vasprun(directory / "vasprun.xml")
    kpoints = normalize_kpoints(directory / "KPOINTS")
    potcar = normalize_potcar(directory / "POTCAR")
    lattice = normalize_lattice(json.loads(identity.structure_json))

    final_energy = (vasprun_extract.get("final_energy")
                    or outcar_extract.get("final_energy"))
    conv_ionic = vasprun_extract.get("converged_ionic")
    conv_electronic = vasprun_extract.get("converged_electronic")

    replace, reason = _should_replace(conn, identity.key, conv_ionic)
    if not replace:
        _record_discard(
            conn, identity.key, source, reason,
            conv_ionic, conv_electronic, final_energy,
        )
        return

    # if replacing an existing entry, record the old one as discarded
    old = conn.execute(
        "SELECT source_path, converged_ionic, converged_electronic, "
        "final_energy FROM entries WHERE identity_key = ?",
        (identity.key,),
    ).fetchone()
    if old is not None:
        _record_discard(
            conn, identity.key, old["source_path"], "replaced",
            old["converged_ionic"], old["converged_electronic"],
            old["final_energy"],
        )

    ep = outcar_extract.get("electrostatic_potentials")
    conn.execute(_INSERT_SQL, (
        identity.key,
        identity.formula,
        json.dumps(identity.incar, sort_keys=True),
        identity.structure_json,
        json.dumps(kpoints, sort_keys=True),
        json.dumps(potcar, sort_keys=True),
        json.dumps(lattice, sort_keys=True),
        final_energy,
        outcar_extract.get("total_mag"),
        json.dumps(ep) if ep is not None else None,
        json.dumps(vasprun_extract.get("final_structure_json")),
        vasprun_extract.get("n_ionic_steps"),
        conv_ionic,
        conv_electronic,
        _compress(outcar_bytes),
        _compress(vasprun_bytes),
        _compress(contcar_bytes),
        source,
    ))


def put(directory: Path | str, root: Path | None = None) -> str | None:
    directory = Path(directory)
    if any(not (directory / f).is_file() for f in _REQUIRED_FILES):
        return None
    try:
        identity = identity_for_directory(directory)
    except IdentityInputError:
        return None
    conn = connect(root)
    try:
        _put_into_conn(conn, identity, directory)
        conn.commit()
    finally:
        conn.close()
    return identity.key


# --- fetch -------------------------------------------------------------

_FETCH_SQL = """SELECT incar_json, structure_json, kpoints_json, potcar_json,
                      outcar_blob, vasprun_blob, contcar_blob
               FROM entries WHERE identity_key = ?"""


def fetch(
    identity_key: str, target_dir: Path | str, root: Path | None = None,
) -> bool:
    target_dir = Path(target_dir)
    conn = connect(root)
    try:
        row = conn.execute(_FETCH_SQL, (identity_key,)).fetchone()
        if row is None:
            return False
        incar_json = row["incar_json"]
        structure_json = row["structure_json"]
        kpoints_json = row["kpoints_json"]
        potcar_json = row["potcar_json"]
        outcar_data = _decompress(row["outcar_blob"])
        vasprun_data = _decompress(row["vasprun_blob"]) \
            if row["vasprun_blob"] else b""
        contcar_data = _decompress(row["contcar_blob"]) \
            if row["contcar_blob"] else b""
    finally:
        conn.close()

    target_dir.mkdir(parents=True, exist_ok=True)

    (target_dir / "OUTCAR").write_bytes(outcar_data)
    (target_dir / "vasprun.xml").write_bytes(vasprun_data)
    (target_dir / "CONTCAR").write_bytes(contcar_data)

    from pymatgen.core.structure import Structure
    structure = Structure.from_dict(json.loads(structure_json))
    structure.to(fmt="poscar", filename=str(target_dir / "POSCAR"))

    incar = json.loads(incar_json)
    with open(target_dir / "INCAR", "w") as f:
        for key, val in sorted(incar.items()):
            f.write(f"{key} = {val}\n")

    kpts = json.loads(kpoints_json)
    _write_kpoints(target_dir / "KPOINTS", kpts)

    _write_potcar_stub(target_dir / "POTCAR", json.loads(potcar_json))

    return True


def _write_kpoints(path: Path, kpts: dict[str, Any]) -> None:
    from pymatgen.io.vasp.inputs import Kpoints
    k = Kpoints.from_dict(kpts)
    k.write_file(str(path))


def _write_potcar_stub(path: Path, potcar: dict[str, Any]) -> None:
    """Write TITEL-only POTCAR stub for downstream consumers."""
    lines = []
    for entry in potcar.get("entries", []):
        elem = entry["element"]
        xc = entry["xc"]
        ver = entry.get("version", "")
        titel = f"PAW_{xc} {elem}"
        if ver:
            titel += f" {ver}"
        lines.append(f"  TITEL  = {titel}")
    path.write_text("\n".join(lines))


# --- query / has -------------------------------------------------------

def _decode(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "identity_key":          row["identity_key"],
        "formula":               row["formula"],
        "incar":                 json.loads(row["incar_json"]),
        "structure":             json.loads(row["structure_json"]),
        "final_energy":          row["final_energy"],
        "total_mag":             row["total_mag"],
        "n_ionic_steps":         row["n_ionic_steps"],
        "converged_ionic":       row["converged_ionic"],
        "converged_electronic":  row["converged_electronic"],
        "source_path":           row["source_path"],
        "created_at":            row["created_at"],
    }


def query(
    formula: str | None = None,
    root: Path | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    conn = connect(root)
    try:
        if formula:
            rows = conn.execute(
                """SELECT * FROM entries
                   WHERE formula = ?
                   ORDER BY created_at DESC LIMIT ?""",
                (formula, int(limit)),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT * FROM entries
                   ORDER BY created_at DESC LIMIT ?""",
                (int(limit),),
            ).fetchall()
        return [_decode(row) for row in rows]
    finally:
        conn.close()


def has(directory: Path | str, root: Path | None = None) -> bool:
    try:
        key = identity_for_directory(directory).key
    except IdentityInputError:
        return False
    conn = connect(root)
    try:
        return conn.execute(
            "SELECT 1 FROM entries WHERE identity_key = ?", (key,),
        ).fetchone() is not None
    finally:
        conn.close()


# --- rebuild (bulk import) ---------------------------------------------

def _iter_candidates(
    root: Path, exclude: Iterable[str] | None = None,
) -> Iterator[Path]:
    exclude = exclude or ()
    seen: set[Path] = set()
    for poscar in root.rglob("POSCAR"):
        directory = poscar.parent.resolve()
        if directory in seen:
            continue
        seen.add(directory)
        if any(fnmatch.fnmatch(str(directory), p) for p in exclude):
            continue
        if (directory / "INCAR").is_file():
            yield directory


def rebuild(
    source_root: Path | str,
    root: Path | None = None,
    *,
    exclude: Iterable[str] | None = None,
) -> dict[str, int]:
    source_root = Path(source_root).resolve()
    target_root = Path(root) if root is not None else cache_root()
    target_root.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=".index-", suffix=".sqlite", dir=str(target_root),
    )
    os.close(fd)
    temp = Path(temp_name)
    conn = sqlite3.connect(str(temp))
    conn.row_factory = sqlite3.Row
    scanned = skipped = done = 0
    try:
        _create_schema(conn)
        candidates = list(_iter_candidates(source_root, exclude=exclude))
        # sort by relative path for deterministic processing order
        candidates.sort(key=lambda d: str(d.relative_to(source_root)))
        for directory in candidates:
            scanned += 1
            if any(not (directory / f).is_file()
                   for f in _REQUIRED_FILES):
                skipped += 1
                continue
            try:
                identity = identity_for_directory(directory)
            except IdentityInputError:
                skipped += 1
                continue
            _put_into_conn(conn, identity, directory)
            done += 1
        conn.commit()
        identities = conn.execute(
            "SELECT COUNT(*) FROM entries",
        ).fetchone()[0]
        discards = conn.execute(
            "SELECT COUNT(*) FROM discarded_candidates",
        ).fetchone()[0]
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(
                f"fresh index integrity check failed: {integrity}",
            )
    except Exception:
        conn.close()
        temp.unlink(missing_ok=True)
        raise
    else:
        conn.close()
    os.replace(temp, db_path(target_root))
    for name in ("meta.sqlite", "meta.sqlite-wal", "meta.sqlite-shm"):
        (target_root / name).unlink(missing_ok=True)
    return {
        "scanned": scanned,
        "skipped": skipped,
        "done": done,
        "identities": int(identities),
        "discarded": int(discards),
    }
