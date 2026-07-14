from __future__ import annotations

import os
import threading
from pathlib import Path

import signac

_cache_root: Path | None = None
_project: signac.Project | None = None
_lock = threading.Lock()


def _default_root() -> Path:
    """Default on shared storage (not under $HOME)."""
    return Path("/mnt/shared/vasp_cache")


def _resolved_root() -> Path:
    """Resolve the effective cache root directory.

    Priority:
    1. In-memory override set by ``override_cache_root()``.
    2. ``VASP_CACHE_ROOT`` environment variable.
    3. ``/mnt/shared/vasp_cache`` (shared default).
    """
    if _cache_root is not None:
        return _cache_root
    env = os.environ.get("VASP_CACHE_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    return _default_root()


def override_cache_root(p: Path | None) -> None:
    """Override the cache root directory (primarily for tests).

    Pass ``None`` to clear the override and fall back to env / default.
    """
    global _cache_root, _project
    with _lock:
        _cache_root = Path(p).resolve() if p is not None else None
        _project = None


def _reset_project() -> None:
    """Drop cached project singleton and cache-root override (tests)."""
    global _cache_root, _project
    with _lock:
        _cache_root = None
        _project = None


def get_project() -> signac.Project:
    """Return (or create) a signac Project at the active cache root.

    The project is cached as a module-level singleton so subsequent calls
    do not re-read the filesystem.
    """
    global _project
    with _lock:
        if _project is not None:
            return _project
        root = _resolved_root()
        root.mkdir(parents=True, exist_ok=True)
        try:
            _project = signac.get_project(path=str(root))
        except LookupError:
            _project = signac.init_project(path=str(root))
        return _project


def cache_root() -> Path:
    """Return the current effective cache root without creating a project."""
    return _resolved_root()
