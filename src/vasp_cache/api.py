"""Public API for the fresh formula–INCAR calculation index."""

from __future__ import annotations

from pathlib import Path
import json
from typing import Any, Iterable

from vasp_cache import index


def put(directory: Path | str, *, root: Path | None = None) -> str | None:
    return index.put(directory, root=root)


def rebuild(
    source_root: Path | str,
    *,
    root: Path | None = None,
    exclude: Iterable[str] | None = None,
) -> dict[str, int]:
    return index.rebuild(source_root, root=root, exclude=exclude)


def has(directory: Path | str, *, root: Path | None = None) -> bool:
    return index.has(directory, root=root)


def fetch(identity_key: str, target_dir: Path | str,
          *, root: Path | None = None) -> bool:
    return index.fetch(identity_key, target_dir, root=root)


def query(
    formula: str | None = None,
    *,
    root: Path | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    return index.query(formula=formula, root=root, limit=limit)


def get_meta(
    input_dir: Path | str | None = None,
    *,
    content_hash: str | None = None,
    formula: str | None = None,
    key: str | None = None,
    root: Path | None = None,
) -> dict[str, Any] | None:
    if input_dir is not None:
        try:
            identity = index.identity_for_directory(input_dir)
        except ValueError:
            return None
        rows = index.query(root=root, limit=1000)
        return next(
            (row for row in rows if row["identity_key"] == identity.key), None
        )
    rows = index.query(formula=formula, root=root, limit=1000)
    if content_hash is not None:
        return next(
            (row for row in rows if row["identity_key"] == content_hash), None)
    if key is not None:
        return next(
            (row for row in rows
             if key == row["identity_key"]
             or key == row.get("source_path", "")),
            None,
        )
    return rows[0] if rows else None


def list_entries(*, root: Path | None = None, limit: int = 50) -> list[dict[str, Any]]:
    return index.query(root=root, limit=limit)


def stats(*, root: Path | None = None) -> dict[str, int | str]:
    conn = index.connect(root)
    try:
        entries, formulas, backend = conn.execute(
            "SELECT COUNT(*), COUNT(DISTINCT formula), "
            "'sqlite-index' FROM entries"
        ).fetchone()
        total_size = conn.execute(
            "SELECT COALESCE(SUM("
            "LENGTH(outcar_blob) "
            "+ LENGTH(COALESCE(vasprun_blob, '')) "
            "+ LENGTH(COALESCE(contcar_blob, ''))"
            "), 0) FROM entries"
        ).fetchone()[0]
    finally:
        conn.close()
    return {
        "entries": int(entries),
        "total_blob_bytes": total_size,
        "formulas": int(formulas),
        "backend": str(backend),
    }
