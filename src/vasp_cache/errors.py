"""Public exceptions raised by vasp-cache."""

from __future__ import annotations


class ProvenanceConflictError(ValueError):
    """The same content hash has incompatible provenance roles."""


class IdentityInputError(ValueError):
    """Required input files are missing or invalid for identity hashing."""


class CacheConflictError(ValueError):
    """The same input identity produced a different output payload."""
