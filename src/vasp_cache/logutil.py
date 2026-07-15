"""Passive diagnostic log — always written to a file, no caller setup required.

Default file
------------
``$VASP_CACHE_ROOT/logs/vasp_cache.log``
(override with env ``VASP_CACHE_LOG_FILE``)

Levels
------
- **File:** INFO and above (put skip/ok, has/fetch miss, errors)
- **stderr:** WARNING by default; CLI ``-v`` → INFO, ``-vv`` → DEBUG

Nothing to "turn on" for the file trail — first API/CLI use configures it.
"""

from __future__ import annotations

import logging
import os
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

_lock = threading.Lock()
_configured = False
_file_path: Path | None = None

_LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
_DATE_FMT = "%Y-%m-%d %H:%M:%S"


def log_path() -> Path:
    """Resolved log file path (may not exist yet)."""
    env = os.environ.get("VASP_CACHE_LOG_FILE")
    if env:
        return Path(env).expanduser().resolve()
    try:
        from vasp_cache.paths import cache_root

        return (cache_root() / "logs" / "vasp_cache.log").resolve()
    except Exception:
        return Path.home() / ".vasp_cache" / "logs" / "vasp_cache.log"


def ensure_logging(*, stderr_level: str | int | None = None) -> Path:
    """Idempotent: attach rotating file handler + optional stderr.

    Safe to call often. Returns the file path in use.
    """
    global _configured, _file_path
    with _lock:
        path = log_path()
        path.parent.mkdir(parents=True, exist_ok=True)

        root = logging.getLogger("vasp_cache")
        root.setLevel(logging.DEBUG)  # handlers filter

        if not _configured:
            fh = RotatingFileHandler(
                path,
                maxBytes=20 * 1024 * 1024,
                backupCount=5,
                encoding="utf-8",
            )
            fh.setLevel(logging.INFO)
            fh.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FMT))
            root.addHandler(fh)

            sh = logging.StreamHandler()
            # quiet terminal unless user raises level later
            sh.setLevel(logging.WARNING)
            sh.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
            sh.set_name("vasp_cache_stderr")  # type: ignore[attr-defined]
            root.addHandler(sh)

            root.propagate = False
            _configured = True
            _file_path = path
            root.info("logging to %s", path)

        if stderr_level is not None:
            if isinstance(stderr_level, str):
                stderr_level = getattr(logging, stderr_level.upper(), logging.WARNING)
            for h in root.handlers:
                if isinstance(h, logging.StreamHandler) and not isinstance(
                    h, RotatingFileHandler
                ):
                    h.setLevel(stderr_level)

        # if cache root changed and path differs, add another file handler once
        if _file_path is not None and path != _file_path:
            # keep writing to original; env/root change mid-process is rare
            pass

        return _file_path or path


def setup_logging(level: str | int | None = None) -> Path:
    """CLI/API helper: ensure file log + set stderr verbosity."""
    if level is None:
        level = os.environ.get("VASP_CACHE_LOG_LEVEL", "WARNING")
    return ensure_logging(stderr_level=level)


def reset_for_tests() -> None:
    global _configured, _file_path
    with _lock:
        root = logging.getLogger("vasp_cache")
        for h in list(root.handlers):
            root.removeHandler(h)
            try:
                h.close()
            except Exception:
                pass
        _configured = False
        _file_path = None
