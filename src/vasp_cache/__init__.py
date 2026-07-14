"""vasp-cache: input-fingerprint → VASP output files (signac backend)."""

from __future__ import annotations


from vasp_cache.api import fetch, has, put
from vasp_cache.paths import override_cache_root

from vasp_cache.mapping import (
    content_hash,
    load_mapping,
    mapping_digest,
    soft_distance,
    soft_vector,
)

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "content_hash",
    "fetch",
    "has",
    "load_mapping",
    "mapping_digest",
    "override_cache_root",
    "put",
    "soft_distance",
    "soft_vector",
]
