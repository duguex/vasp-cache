"""Minimal diagnostic logging for vasp-cache.

Usage::

    from vasp_cache.logutil import setup_logging
    setup_logging("DEBUG")   # or INFO / WARNING

    # or env: VASP_CACHE_LOG_LEVEL=DEBUG
    # CLI: vasp-cache -v … / -vv …
"""

from __future__ import annotations

import logging
import os

_CONFIGURED = False


def setup_logging(level: str | int | None = None) -> None:
    """Configure ``vasp_cache`` loggers once (stderr)."""
    global _CONFIGURED
    if level is None:
        level = os.environ.get("VASP_CACHE_LOG_LEVEL", "WARNING")
    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.WARNING)

    root = logging.getLogger("vasp_cache")
    root.setLevel(level)
    if not _CONFIGURED:
        h = logging.StreamHandler()
        h.setFormatter(
            logging.Formatter("%(levelname)s %(name)s: %(message)s")
        )
        root.addHandler(h)
        root.propagate = False
        _CONFIGURED = True
    else:
        for h in root.handlers:
            h.setLevel(level)


def reset_for_tests() -> None:
    global _CONFIGURED
    root = logging.getLogger("vasp_cache")
    for h in list(root.handlers):
        root.removeHandler(h)
    _CONFIGURED = False
