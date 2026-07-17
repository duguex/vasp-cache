"""SQLite metadata index for content_hash → CAS object map + query fields.

Database path: ``cache_root/meta.sqlite`` (WAL mode).
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Literal

from vasp_cache.errors import ProvenanceConflictError

_DB_NAME = "meta.sqlite"
_lock = threading.Lock()
_conns: dict[str, sqlite3.Connection] = {}

ProvenanceFilter = Literal["canonical", "sampled", "unknown", "all"]
_PROVENANCE_VALUES = {"canonical", "sampled", "unknown"}
_PROVENANCE_SOURCES = {"explicit", "inferred", "legacy"}
_SOURCE_RANK = {"legacy": 0, "inferred": 1, "explicit": 2}


_SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
    content_hash          TEXT PRIMARY KEY,
    formula               TEXT,
    task_name             TEXT,
    total_energy          REAL,
    converged             INTEGER,
    bandgap               REAL,
    nsites                INTEGER,
    max_abc               REAL,
    tags                  TEXT,
    source_dir            TEXT,
    profile_id            TEXT,
    key_generation        INTEGER,
    mapping_digest        TEXT,
    cached_at             REAL NOT NULL,
    objects_json          TEXT NOT NULL,
    extra_json            TEXT,
    provenance            TEXT NOT NULL DEFAULT 'unknown',
    provenance_source     TEXT NOT NULL DEFAULT 'legacy',
    outcar_complete       INTEGER,
    electronic_converged  INTEGER,
    ionic_converged       INTEGER,
    nsw                   INTEGER,
    ibrion                INTEGER,
    isif                  INTEGER
);
CREATE INDEX IF NOT EXISTS idx_entries_formula ON entries(formula);
CREATE INDEX IF NOT EXISTS idx_entries_cached_at ON entries(cached_at);
CREATE INDEX IF NOT EXISTS idx_entries_energy ON entries(total_energy);
"""


_MIGRATION_COLUMNS = {
    "provenance": "TEXT NOT NULL DEFAULT 'unknown'",
    "provenance_source": "TEXT NOT NULL DEFAULT 'legacy'",
    "outcar_complete": "INTEGER",
    "electronic_converged": "INTEGER",
    "ionic_converged": "INTEGER",
    "nsw": "INTEGER",
    "ibrion": "INTEGER",
    "isif": "INTEGER",
}


def _ensure_schema(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(entries)")}
    for name, definition in _MIGRATION_COLUMNS.items():
        if name not in columns:
            conn.execute(f"ALTER TABLE entries ADD COLUMN {name} {definition}")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_entries_provenance "
        "ON entries(provenance)"
    )
    conn.commit()


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
        _ensure_schema(conn)
        conn.commit()
        _conns[root] = conn
        return conn


class _ReadonlyConnection(sqlite3.Connection):
    _cleanup = None

    def close(self) -> None:
        try:
            super().close()
        finally:
            cleanup = self._cleanup
            self._cleanup = None
            if cleanup is not None:
                cleanup()


def connect_readonly(cache_root: Path) -> sqlite3.Connection | None:
    """Open an existing metadata database without any write-capable setup.

    Inspection must not create a cache root, run schema DDL, change journal
    mode, or commit.  SQLite's ``mode=ro`` URI enforces that contract while
    still allowing reads from an existing WAL database.
    """
    path = db_path(cache_root)
    if not path.is_file():
        return None
    wal_path = path.with_name(path.name + "-wal")
    shm_path = path.with_name(path.name + "-shm")
    cleanup = None
    if wal_path.exists() or shm_path.exists():
        snapshot = tempfile.TemporaryDirectory(prefix="vasp-cache-meta-")
        snapshot_db = Path(snapshot.name) / path.name
        shutil.copy2(path, snapshot_db)
        for sidecar in (wal_path, shm_path):
            if sidecar.is_file():
                shutil.copy2(sidecar, snapshot_db.with_name(sidecar.name))
        path = snapshot_db
        cleanup = snapshot.cleanup
    uri = f"{path.resolve().as_uri()}?mode=ro&immutable=1" if cleanup is None else (
        f"{path.resolve().as_uri()}?mode=ro"
    )
    try:
        conn = sqlite3.connect(
            uri, uri=True, check_same_thread=False, factory=_ReadonlyConnection
        )
    except Exception:
        if cleanup is not None:
            cleanup()
        raise
    conn.row_factory = sqlite3.Row
    conn._cleanup = cleanup
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
    provenance: str = "unknown",
    provenance_source: str = "legacy",
    outcar_complete: bool | None = None,
    electronic_converged: bool | None = None,
    ionic_converged: bool | None = None,
    nsw: int | None = None,
    ibrion: int | None = None,
    isif: int | None = None,
) -> None:
    conn = connect(cache_root)
    if provenance not in _PROVENANCE_VALUES:
        raise ValueError(f"invalid provenance: {provenance}")
    if provenance_source not in _PROVENANCE_SOURCES:
        raise ValueError(f"invalid provenance source: {provenance_source}")
    now = cached_at if cached_at is not None else time.time()
    values = {
        "content_hash": content_hash,
        "formula": formula,
        "task_name": task_name,
        "total_energy": total_energy,
        "converged": None if converged is None else int(bool(converged)),
        "bandgap": bandgap,
        "nsites": nsites,
        "max_abc": max_abc,
        "tags": tags,
        "source_dir": source_dir,
        "profile_id": profile_id,
        "key_generation": key_generation,
        "mapping_digest": mapping_digest,
        "cached_at": now,
        "objects_json": json.dumps(objects, sort_keys=True),
        "extra_json": json.dumps(extra, sort_keys=True) if extra else None,
        "provenance": provenance,
        "provenance_source": provenance_source,
        "outcar_complete": (
            None if outcar_complete is None else int(bool(outcar_complete))
        ),
        "electronic_converged": (
            None
            if electronic_converged is None
            else int(bool(electronic_converged))
        ),
        "ionic_converged": (
            None if ionic_converged is None else int(bool(ionic_converged))
        ),
        "nsw": nsw,
        "ibrion": ibrion,
        "isif": isif,
    }
    conn.execute(
        """
        INSERT INTO entries (
            content_hash, formula, task_name, total_energy, converged, bandgap,
            nsites, max_abc, tags, source_dir, profile_id, key_generation,
            mapping_digest, cached_at, objects_json, extra_json, provenance,
            provenance_source, outcar_complete, electronic_converged,
            ionic_converged, nsw, ibrion, isif
        ) VALUES (
            :content_hash, :formula, :task_name, :total_energy, :converged,
            :bandgap, :nsites, :max_abc, :tags, :source_dir, :profile_id,
            :key_generation, :mapping_digest, :cached_at, :objects_json,
            :extra_json, :provenance, :provenance_source, :outcar_complete,
            :electronic_converged, :ionic_converged, :nsw, :ibrion, :isif
        )
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
            extra_json=excluded.extra_json,
            provenance=excluded.provenance,
            provenance_source=excluded.provenance_source,
            outcar_complete=excluded.outcar_complete,
            electronic_converged=excluded.electronic_converged,
            ionic_converged=excluded.ionic_converged,
            nsw=excluded.nsw,
            ibrion=excluded.ibrion,
            isif=excluded.isif
        """,
        values,
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


def preflight_provenance(
    cache_root: Path,
    content_hash: str,
    incoming: str,
    incoming_source: str,
) -> tuple[str, str]:
    """Resolve a duplicate role before any CAS object is written."""
    if incoming not in _PROVENANCE_VALUES:
        raise ValueError(f"invalid provenance: {incoming}")
    if incoming_source not in _PROVENANCE_SOURCES:
        raise ValueError(f"invalid provenance source: {incoming_source}")

    existing = get_entry(cache_root, content_hash)
    if existing is None:
        return incoming, incoming_source

    current = existing.get("provenance") or "unknown"
    current_source = existing.get("provenance_source") or "legacy"
    if current not in _PROVENANCE_VALUES:
        current = "unknown"
    if current_source not in _PROVENANCE_SOURCES:
        current_source = "legacy"

    if current_source == "explicit":
        if (
            incoming_source == "explicit"
            and current != incoming
            and current != "unknown"
            and incoming != "unknown"
        ):
            raise ProvenanceConflictError(
                f"content hash {content_hash} has explicit provenance "
                f"{current!r}, cannot replace with {incoming!r}"
            )
        return current, current_source

    if incoming_source == "explicit":
        return incoming, incoming_source
    if current != "unknown" and incoming == "unknown":
        return current, current_source
    if (
        current_source == "inferred"
        and incoming_source == "inferred"
        and current != incoming
        and current != "unknown"
        and incoming != "unknown"
    ):
        raise ProvenanceConflictError(
            f"content hash {content_hash} has inferred provenance "
            f"{current!r}, cannot replace with {incoming!r}"
        )
    if _SOURCE_RANK[incoming_source] >= _SOURCE_RANK[current_source]:
        return incoming, incoming_source
    return current, current_source


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
    provenance: ProvenanceFilter = "canonical",
    limit: int = 100,
) -> list[dict[str, Any]]:
    if provenance not in {"canonical", "sampled", "unknown", "all"}:
        raise ValueError(f"invalid provenance filter: {provenance}")
    conn = connect(cache_root)
    clauses: list[str] = []
    params: list[Any] = []
    if provenance != "all":
        clauses.append("provenance = ?")
        params.append(provenance)
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
    sql = f"SELECT * FROM entries{where} ORDER BY cached_at DESC, content_hash ASC LIMIT ?"
    params.append(int(limit))
    rows = conn.execute(sql, params).fetchall()
    return [_row_to_dict(r) for r in rows]


def list_recent(cache_root: Path, limit: int = 50) -> list[dict[str, Any]]:
    return query_entries(cache_root, provenance="all", limit=limit)


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
    for key in (
        "converged",
        "outcar_complete",
        "electronic_converged",
        "ionic_converged",
    ):
        if d.get(key) is not None:
            d[key] = bool(d[key])
    return d

def _readonly_columns(conn: sqlite3.Connection) -> set[str]:
    table = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'entries'"
    ).fetchone()
    if table is None:
        return set()
    return {row[1] for row in conn.execute("PRAGMA table_info(entries)")}


def iter_entries(cache_root: Path):
    """Yield decoded metadata entries without creating or migrating a database."""
    conn = connect_readonly(cache_root)
    if conn is None:
        return
    try:
        if not _readonly_columns(conn):
            return
        for row in conn.execute("SELECT * FROM entries"):
            yield _row_to_dict(row)
    finally:
        conn.close()


def get_entry_readonly(cache_root: Path, content_hash: str) -> dict[str, Any] | None:
    """Read one metadata row without schema setup or migration."""
    conn = connect_readonly(cache_root)
    if conn is None:
        return None
    try:
        if not _readonly_columns(conn):
            return None
        row = conn.execute(
            "SELECT * FROM entries WHERE content_hash = ?", (content_hash,)
        ).fetchone()
        return None if row is None else _row_to_dict(row)
    finally:
        conn.close()


def query_entries_readonly(
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
    provenance: ProvenanceFilter = "canonical",
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Query existing metadata using a strictly read-only SQLite connection."""
    if provenance not in {"canonical", "sampled", "unknown", "all"}:
        raise ValueError(f"invalid provenance filter: {provenance}")
    conn = connect_readonly(cache_root)
    if conn is None:
        return []
    try:
        columns = _readonly_columns(conn)
        if not columns:
            return []
        clauses: list[str] = []
        params: list[Any] = []
        if provenance != "all":
            if "provenance" not in columns:
                if provenance != "unknown":
                    return []
            else:
                clauses.append("provenance = ?")
                params.append(provenance)
        for column, clause, value in (
            ("formula", "formula = ?", formula),
            ("tags", "tags LIKE ?", f"%{tags}%" if tags else None),
            ("bandgap", "bandgap >= ?", bandgap_min),
            ("max_abc", "max_abc <= ?", lattice_max),
            ("total_energy", "total_energy >= ?", min_energy),
        ):
            if value is not None and column in columns:
                clauses.append(clause)
                params.append(value)
        if max_energy is not None and "total_energy" in columns:
            clauses.append("total_energy <= ?")
            params.append(max_energy)
        if converged_only and "converged" in columns:
            clauses.append("converged = 1")
        if functional:
            functional_clauses = []
            if "tags" in columns:
                functional_clauses.append("tags LIKE ?")
                params.append(f"%{functional}%")
            if "extra_json" in columns:
                functional_clauses.append("extra_json LIKE ?")
                params.append(f"%{functional}%")
            if functional_clauses:
                clauses.append("(" + " OR ".join(functional_clauses) + ")")
        if calc_type and "extra_json" in columns:
            clauses.append("extra_json LIKE ?")
            params.append(f"%{calc_type}%")
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = f"SELECT * FROM entries{where} ORDER BY cached_at DESC, content_hash ASC LIMIT ?"
        params.append(int(limit))
        return [_row_to_dict(row) for row in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()
