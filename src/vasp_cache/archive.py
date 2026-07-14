"""Whole-cache archive export / import (CAS + SQLite layout).

Archive format (``.tar.gz``)::

    manifest.json
    data/meta.sqlite
    data/cas/...
    data/mapping.yaml   # optional
"""

from __future__ import annotations

import json
import logging
import shutil
import tarfile
import tempfile
import time
from pathlib import Path
from typing import Any

from vasp_cache.paths import cache_root, override_cache_root, _reset_project

logger = logging.getLogger(__name__)

_MANIFEST_NAME = "manifest.json"
_DATA_PREFIX = "data"


def _collect_stats_safe() -> dict[str, Any]:
    try:
        from vasp_cache.api import stats

        return dict(stats())
    except Exception as exc:
        return {"error": str(exc)}


def export_archive(
    dest: Path | str,
    *,
    root: Path | str | None = None,
) -> Path:
    """Pack the cache root into *dest* (``.tar.gz``)."""
    dest = Path(dest)
    if dest.suffix == ".tgz":
        pass
    elif not str(dest).endswith(".tar.gz"):
        dest = Path(str(dest) + ".tar.gz") if dest.suffix != ".gz" else dest

    if root is not None:
        _reset_project()
        override_cache_root(Path(root))
    try:
        src = cache_root()
        if not src.is_dir():
            raise FileNotFoundError(f"cache root does not exist: {src}")

        manifest = {
            "format": "vasp-cache-archive-v2",
            "backend": "cas+sqlite",
            "created_at": time.time(),
            "source_root": str(src.resolve()),
            "stats": _collect_stats_safe(),
        }
        try:
            from vasp_cache.mapping import load_mapping

            m = load_mapping()
            manifest["key_generation"] = m.get("key_generation")
        except Exception as exc:
            manifest["mapping_error"] = str(exc)

        dest.parent.mkdir(parents=True, exist_ok=True)
        # close DB so meta.sqlite is consistent on disk
        from vasp_cache.meta import close_all

        close_all()

        with tarfile.open(dest, "w:gz") as tar:
            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
                json.dump(manifest, tf, indent=2)
                tf_path = Path(tf.name)
            try:
                tar.add(tf_path, arcname=_MANIFEST_NAME)
            finally:
                tf_path.unlink(missing_ok=True)

            for child in sorted(src.iterdir()):
                # skip signac leftovers if any
                if child.name in (".signac", "workspace", "jobs.db"):
                    continue
                tar.add(child, arcname=f"{_DATA_PREFIX}/{child.name}")

        logger.info("exported cache %s -> %s", src, dest)
        return dest.resolve()
    finally:
        if root is not None:
            _reset_project()
            override_cache_root(None)


def import_archive(
    archive: Path | str,
    *,
    root: Path | str | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Restore an archive created by :func:`export_archive`."""
    archive = Path(archive)
    if not archive.is_file():
        raise FileNotFoundError(archive)

    dest = Path(root).resolve() if root is not None else cache_root()
    dest = dest.resolve()

    markers = ("meta.sqlite", "cas", ".signac", "workspace")
    if dest.exists() and any((dest / name).exists() for name in markers):
        if not overwrite:
            raise FileExistsError(
                f"destination not empty: {dest} (pass overwrite=True to replace)"
            )
        from vasp_cache.meta import close_all

        close_all()
        for child in list(dest.iterdir()):
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()

    dest.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, Any] = {}
    with tarfile.open(archive, "r:gz") as tar:
        for m in tar.getmembers():
            name = m.name.lstrip("./")
            if name in (_MANIFEST_NAME,):
                continue
            if name == _DATA_PREFIX or name.startswith(f"{_DATA_PREFIX}/"):
                continue
            raise ValueError(f"unexpected archive member: {name}")

        try:
            f = tar.extractfile(_MANIFEST_NAME)
        except KeyError:
            f = tar.extractfile(f"./{_MANIFEST_NAME}")
        if f is None:
            raise ValueError("archive missing manifest.json")
        manifest = json.loads(f.read().decode("utf-8"))

        for m in tar.getmembers():
            name = m.name.lstrip("./")
            if not name.startswith(f"{_DATA_PREFIX}/"):
                continue
            rel = name[len(_DATA_PREFIX) + 1 :]
            if not rel:
                continue
            target = (dest / rel).resolve()
            if not str(target).startswith(str(dest.resolve())):
                raise ValueError(f"path escapes destination: {m.name}")
            if m.isdir() or rel.endswith("/"):
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            src = tar.extractfile(m)
            if src is None:
                continue
            with open(target, "wb") as out:
                shutil.copyfileobj(src, out)

    _reset_project()
    if root is not None:
        override_cache_root(dest)
    else:
        override_cache_root(None)

    logger.info("imported archive %s -> %s", archive, dest)
    return manifest
