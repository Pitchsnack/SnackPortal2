"""Concrete auth_router providers (containment zone).

Production verifier (PyJWT) + control-plane HTTP read client live here. This package
performs NO eager imports, so importing auth_router does not require PyJWT to be
installed (the stdlib test suite uses test doubles instead).
"""

from __future__ import annotations
