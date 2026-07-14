"""vasp-cache: input-fingerprint → VASP output files (signac backend)."""

from __future__ import annotations


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
    "load_mapping",
    "mapping_digest",
    "soft_distance",
    "soft_vector",
]
