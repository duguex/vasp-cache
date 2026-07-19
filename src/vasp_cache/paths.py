"""Cache root resolution (no signac)."""

from __future__ import annotations

import os
import threading
from pathlib import Path

_cache_root: Path | None = None
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
    global _cache_root
    with _lock:
        _cache_root = Path(p).resolve() if p is not None else None


def _reset_project() -> None:
    """Drop cache-root override (test teardown).

    Name kept for test compatibility (was signac project reset).
    """
    global _cache_root
    with _lock:
        _cache_root = None


def cache_root() -> Path:
    """Return the current effective cache root without creating it."""
    return _resolved_root()
