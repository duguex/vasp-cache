"""SQLite metadata index for content_hash → CAS object map + query fields.

Database path: ``cache_root/meta.sqlite`` (WAL mode).
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

_DB_NAME = "meta.sqlite"
_lock = threading.Lock()
_conns: dict[str, sqlite3.Connection] = {}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
    content_hash   TEXT PRIMARY KEY,
    formula        TEXT,
    task_name      TEXT,
    total_energy   REAL,
    converged      INTEGER,
    bandgap        REAL,
    nsites         INTEGER,
    max_abc        REAL,
    tags           TEXT,
    source_dir     TEXT,
    profile_id     TEXT,
    key_generation INTEGER,
    mapping_digest TEXT,
    cached_at      REAL NOT NULL,
    objects_json   TEXT NOT NULL,
    extra_json     TEXT
);
CREATE INDEX IF NOT EXISTS idx_entries_formula ON entries(formula);
CREATE INDEX IF NOT EXISTS idx_entries_cached_at ON entries(cached_at);
CREATE INDEX IF NOT EXISTS idx_entries_energy ON entries(total_energy);
"""


def db_path(cache_root: Path) -> Path:
    return Path(cache_root) / _DB_NAME


def connect(cache_root: Path) -> sqlite3.Connection:
    """Return a process-local connection for *cache_root* (WAL, row factory)."""
    root = str(Path(cache_root).resolve())
    with _lock:
        conn = _conns.get(root)
        if conn is not None:
            return conn
        Path(root).mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path(Path(root))), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.executescript(_SCHEMA)
        conn.commit()
        _conns[root] = conn
        return conn


def close_all() -> None:
    """Close all cached connections (tests)."""
    with _lock:
        for c in _conns.values():
            try:
                c.close()
            except Exception:
                pass
        _conns.clear()


def upsert_entry(
    cache_root: Path,
    *,
    content_hash: str,
    objects: dict[str, str],
    formula: str | None = None,
    task_name: str | None = None,
    total_energy: float | None = None,
    converged: bool | None = None,
    bandgap: float | None = None,
    nsites: int | None = None,
    max_abc: float | None = None,
    tags: str | None = None,
    source_dir: str | None = None,
    profile_id: str | None = None,
    key_generation: int | None = None,
    mapping_digest: str | None = None,
    cached_at: float | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    conn = connect(cache_root)
    now = cached_at if cached_at is not None else time.time()
    conv = None if converged is None else (1 if converged else 0)
    extra_json = json.dumps(extra) if extra else None
    conn.execute(
        """
        INSERT INTO entries (
            content_hash, formula, task_name, total_energy, converged, bandgap,
            nsites, max_abc, tags, source_dir, profile_id, key_generation,
            mapping_digest, cached_at, objects_json, extra_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(content_hash) DO UPDATE SET
            formula=excluded.formula,
            task_name=excluded.task_name,
            total_energy=excluded.total_energy,
            converged=excluded.converged,
            bandgap=excluded.bandgap,
            nsites=excluded.nsites,
            max_abc=excluded.max_abc,
            tags=excluded.tags,
            source_dir=excluded.source_dir,
            profile_id=excluded.profile_id,
            key_generation=excluded.key_generation,
            mapping_digest=excluded.mapping_digest,
            cached_at=excluded.cached_at,
            objects_json=excluded.objects_json,
            extra_json=excluded.extra_json
        """,
        (
            content_hash,
            formula,
            task_name,
            total_energy,
            conv,
            bandgap,
            nsites,
            max_abc,
            tags,
            source_dir,
            profile_id,
            key_generation,
            mapping_digest,
            now,
            json.dumps(objects, sort_keys=True),
            extra_json,
        ),
    )
    conn.commit()


def get_entry(cache_root: Path, content_hash: str) -> dict[str, Any] | None:
    conn = connect(cache_root)
    row = conn.execute(
        "SELECT * FROM entries WHERE content_hash = ?", (content_hash,)
    ).fetchone()
    if row is None:
        return None
    return _row_to_dict(row)


def has_entry(cache_root: Path, content_hash: str) -> bool:
    conn = connect(cache_root)
    r = conn.execute(
        "SELECT 1 FROM entries WHERE content_hash = ? LIMIT 1", (content_hash,)
    ).fetchone()
    return r is not None


def query_entries(
    cache_root: Path,
    *,
    formula: str | None = None,
    functional: str | None = None,
    tags: str | None = None,
    calc_type: str | None = None,
    bandgap_min: float | None = None,
    lattice_max: float | None = None,
    min_energy: float | None = None,
    max_energy: float | None = None,
    converged_only: bool = False,
    limit: int = 100,
) -> list[dict[str, Any]]:
    conn = connect(cache_root)
    clauses: list[str] = []
    params: list[Any] = []
    if formula:
        clauses.append("formula = ?")
        params.append(formula)
    if functional:
        clauses.append("(tags LIKE ? OR extra_json LIKE ?)")
        params.extend([f"%{functional}%", f"%{functional}%"])
    if tags:
        clauses.append("tags LIKE ?")
        params.append(f"%{tags}%")
    if calc_type:
        clauses.append("extra_json LIKE ?")
        params.append(f"%{calc_type}%")
    if bandgap_min is not None:
        clauses.append("bandgap >= ?")
        params.append(bandgap_min)
    if lattice_max is not None:
        clauses.append("max_abc <= ?")
        params.append(lattice_max)
    if min_energy is not None:
        clauses.append("total_energy >= ?")
        params.append(min_energy)
    if max_energy is not None:
        clauses.append("total_energy <= ?")
        params.append(max_energy)
    if converged_only:
        clauses.append("converged = 1")
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = f"SELECT * FROM entries{where} ORDER BY cached_at DESC LIMIT ?"
    params.append(int(limit))
    rows = conn.execute(sql, params).fetchall()
    return [_row_to_dict(r) for r in rows]


def list_recent(cache_root: Path, limit: int = 50) -> list[dict[str, Any]]:
    return query_entries(cache_root, limit=limit)


def stats(cache_root: Path) -> dict[str, Any]:
    conn = connect(cache_root)
    n = conn.execute("SELECT COUNT(*) AS c FROM entries").fetchone()["c"]
    formulas = conn.execute(
        "SELECT COUNT(DISTINCT formula) AS c FROM entries"
    ).fetchone()["c"]
    converged = conn.execute(
        "SELECT COUNT(*) AS c FROM entries WHERE converged = 1"
    ).fetchone()["c"]
    with_energy = conn.execute(
        "SELECT COUNT(*) AS c FROM entries WHERE total_energy IS NOT NULL"
    ).fetchone()["c"]
    return {
        "entries": n,
        "formulas": formulas,
        "converged": converged,
        "with_energy": with_energy,
        "backend": "cas+sqlite",
    }


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    objects = json.loads(d.pop("objects_json") or "{}")
    d["objects"] = objects
    extra = d.pop("extra_json", None)
    if extra:
        try:
            d.update(json.loads(extra))
        except json.JSONDecodeError:
            d["extra_json"] = extra
    if d.get("converged") is not None:
        d["converged"] = bool(d["converged"])
    return d
