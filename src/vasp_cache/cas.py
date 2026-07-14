"""Content-addressed blob store (CAS).

Layout under ``cache_root/cas/``::

    cas/ab/cd/<sha256 hex>

Objects are immutable. Writes are atomic (temp file + rename).
"""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

_CAS_DIRNAME = "cas"
_HASH_LEN = 64  # sha256 hex


def cas_root(cache_root: Path) -> Path:
    return Path(cache_root) / _CAS_DIRNAME


def object_path(cache_root: Path, digest: str) -> Path:
    d = digest.lower()
    if len(d) != _HASH_LEN or any(c not in "0123456789abcdef" for c in d):
        raise ValueError(f"invalid sha256 digest: {digest!r}")
    return cas_root(cache_root) / d[:2] / d[2:4] / d


def has_object(cache_root: Path, digest: str) -> bool:
    return object_path(cache_root, digest).is_file()


def put_bytes(cache_root: Path, data: bytes) -> str:
    """Store *data*; return sha256 hex digest."""
    digest = hashlib.sha256(data).hexdigest()
    dest = object_path(cache_root, digest)
    if dest.is_file():
        return digest
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(dest.parent), prefix=".tmp-")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, dest)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    return digest


def put_file(cache_root: Path, src: Path | str) -> str:
    """Hash and store file at *src*; return digest. Dedup if present."""
    src = Path(src)
    h = hashlib.sha256()
    with open(src, "rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    digest = h.hexdigest()
    dest = object_path(cache_root, digest)
    if dest.is_file():
        return digest
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(dest.parent), prefix=".tmp-")
    os.close(fd)
    try:
        shutil.copyfile(src, tmp_name)
        # fsync file
        with open(tmp_name, "rb") as f:
            os.fsync(f.fileno())
        os.replace(tmp_name, dest)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    return digest


def materialize(cache_root: Path, digest: str, dest: Path | str) -> None:
    """Copy object *digest* to *dest* (overwrite)."""
    src = object_path(cache_root, digest)
    if not src.is_file():
        raise FileNotFoundError(f"CAS object missing: {digest}")
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)


def read_bytes(cache_root: Path, digest: str) -> bytes:
    src = object_path(cache_root, digest)
    if not src.is_file():
        raise FileNotFoundError(f"CAS object missing: {digest}")
    return src.read_bytes()


def iter_objects(cache_root: Path):
    """Yield (digest, path) for all objects."""
    root = cas_root(cache_root)
    if not root.is_dir():
        return
    for p in root.rglob("*"):
        if p.is_file() and not p.name.startswith("."):
            # digest is last path component if length 64
            if len(p.name) == _HASH_LEN:
                yield p.name, p
