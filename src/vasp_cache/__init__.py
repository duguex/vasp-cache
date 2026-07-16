"""vasp-cache: input-fingerprint → VASP output files (signac backend)."""

from __future__ import annotations

from vasp_cache.api import (
    ProvenanceConflictError,
    fetch,
    get_meta,
    has,
    list_entries,
    put,
    query,
    stats,
)
from vasp_cache.archive import export_archive, import_archive
from vasp_cache.mapping import (
    content_hash,
    load_mapping,
    mapping_digest,
    soft_distance,
    soft_vector,
)
from vasp_cache.paths import override_cache_root

__version__ = "0.2.0"

__all__ = [
    "ProvenanceConflictError",
    "__version__",
    "content_hash",
    "export_archive",
    "fetch",
    "get_meta",
    "has",
    "import_archive",
    "list_entries",
    "load_mapping",
    "mapping_digest",
    "override_cache_root",
    "put",
    "query",
    "soft_distance",
    "soft_vector",
    "stats",
]
