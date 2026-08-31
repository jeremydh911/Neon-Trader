"""Env-gated plug-in adapters for the private Ahana stack.

These stubs never vendor sister-product source. If the optional package is
not installed, or the matching env var is unset, each adapter logs and
no-ops. Sister repos (AhanaFlow, AhanaZip, Chatwire / Cloud Wire, aarmOS)
stay private and must not be copied into this public tree.
"""

from . import ahanaflow, chatwire, ahanazip

__all__ = ["ahanaflow", "chatwire", "ahanazip"]
