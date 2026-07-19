"""Black-box VASP calculation cache — 5-layer identity, SQLite BLOB storage."""

from __future__ import annotations

from vasp_cache.api import (
    fetch,
    get_meta,
    has,
    list_entries,
    put,
    query,
    rebuild,
    stats,
)
from vasp_cache.errors import IdentityInputError
from vasp_cache.index import Identity, identity_for_directory
from vasp_cache.paths import override_cache_root

__version__ = "0.3.0"

__all__ = [
    "Identity",
    "IdentityInputError",
    "__version__",
    "fetch",
    "get_meta",
    "has",
    "identity_for_directory",
    "list_entries",
    "override_cache_root",
    "put",
    "query",
    "rebuild",
    "stats",
]
