"""Public exceptions raised by vasp-cache."""

from __future__ import annotations


class IdentityInputError(ValueError):
    """Required input files are missing or invalid for identity hashing."""
