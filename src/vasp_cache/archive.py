"""Whole-cache archive export / import.

Archive format (``.tar.gz`` or ``.tgz``)::

    manifest.json          # stats + identity metadata
    data/                  # contents of VASP_CACHE_ROOT
      .signac/
      workspace/
      mapping.yaml         # optional lab overlay
      ...
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

from vasp_cache.paths import cache_root, get_project, override_cache_root, _reset_project

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
    """Pack the cache root into *dest* (``.tar.gz``).

    Parameters
    ----------
    dest:
        Output archive path.
    root:
        Cache root to export. Default: active resolved root.
    """
    dest = Path(dest)
    if dest.suffix == ".gz" and dest.with_suffix("").suffix == ".tar":
        pass
    elif dest.suffix == ".tgz":
        pass
    elif not str(dest).endswith(".tar.gz"):
        dest = dest.with_suffix(dest.suffix + ".tar.gz") if dest.suffix else Path(str(dest) + ".tar.gz")

    if root is not None:
        _reset_project()
        override_cache_root(Path(root))
    try:
        src = cache_root()
        if not src.is_dir():
            raise FileNotFoundError(f"cache root does not exist: {src}")

        # ensure project is open/flushable
        try:
            get_project()
        except Exception:
            pass

        manifest = {
            "format": "vasp-cache-archive-v1",
            "created_at": time.time(),
            "source_root": str(src.resolve()),
            "stats": _collect_stats_safe(),
        }
        try:
            from vasp_cache.mapping import load_mapping

            m = load_mapping()
            manifest["key_generation"] = m.get("key_generation")
            manifest["mapping_hard_structure"] = (m.get("hard") or {}).get("structure")
        except Exception as exc:
            manifest["mapping_error"] = str(exc)

        dest.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(dest, "w:gz") as tar:
            # write manifest via temp file
            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
                json.dump(manifest, tf, indent=2)
                tf_path = Path(tf.name)
            try:
                tar.add(tf_path, arcname=_MANIFEST_NAME)
            finally:
                tf_path.unlink(missing_ok=True)

            for child in sorted(src.iterdir()):
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
    """Restore an archive created by :func:`export_archive`.

    Parameters
    ----------
    archive:
        Path to ``.tar.gz`` archive.
    root:
        Destination cache root. Default: active resolved root
        (``/mnt/shared/vasp_cache`` unless overridden).
    overwrite:
        If False and destination already has ``workspace/`` or ``.signac/``,
        raise ``FileExistsError``. If True, remove destination first.

    Returns
    -------
    manifest dict from the archive.
    """
    archive = Path(archive)
    if not archive.is_file():
        raise FileNotFoundError(archive)

    if root is not None:
        dest = Path(root)
    else:
        dest = cache_root()

    dest = dest.resolve()
    if dest.exists() and any(
        (dest / name).exists() for name in (".signac", "workspace")
    ):
        if not overwrite:
            raise FileExistsError(
                f"destination not empty: {dest} (pass overwrite=True to replace)"
            )
        # remove only cache contents, not parent mount
        for child in list(dest.iterdir()):
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()

    dest.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, Any] = {}
    with tarfile.open(archive, "r:gz") as tar:
        # validate members: only manifest + data/
        for m in tar.getmembers():
            name = m.name
            if name in (_MANIFEST_NAME, f"./{_MANIFEST_NAME}"):
                continue
            if name.startswith(f"{_DATA_PREFIX}/") or name.startswith(f"./{_DATA_PREFIX}/"):
                continue
            if name in (_DATA_PREFIX, f"./{_DATA_PREFIX}"):
                continue
            raise ValueError(f"unexpected archive member: {name}")

        # extract manifest
        try:
            f = tar.extractfile(_MANIFEST_NAME)
        except KeyError:
            f = tar.extractfile(f"./{_MANIFEST_NAME}")
        if f is None:
            raise ValueError("archive missing manifest.json")
        manifest = json.loads(f.read().decode("utf-8"))

        # extract data/* into dest
        for m in tar.getmembers():
            name = m.name.lstrip("./")
            if not name.startswith(f"{_DATA_PREFIX}/"):
                continue
            rel = name[len(_DATA_PREFIX) + 1 :]
            if not rel or rel.endswith("/"):
                # directory entries
                if rel:
                    (dest / rel).mkdir(parents=True, exist_ok=True)
                continue
            # prevent path escape
            target = (dest / rel).resolve()
            if not str(target).startswith(str(dest.resolve())):
                raise ValueError(f"path escapes destination: {m.name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            src = tar.extractfile(m)
            if src is None:
                continue
            with open(target, "wb") as out:
                shutil.copyfileobj(src, out)
            # best-effort mode
            try:
                if m.mode:
                    target.chmod(m.mode & 0o777)
            except OSError:
                pass

    # reset project handle to new location
    _reset_project()
    if root is not None:
        override_cache_root(dest)
    else:
        # if dest is default path, just reset singleton
        override_cache_root(None)
        if dest != cache_root():
            override_cache_root(dest)

    logger.info("imported archive %s -> %s", archive, dest)
    return manifest
