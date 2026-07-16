"""Public exceptions raised by vasp-cache."""

from __future__ import annotations


class ProvenanceConflictError(ValueError):
    """The same content hash has incompatible provenance roles."""
