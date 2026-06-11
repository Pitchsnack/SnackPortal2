"""Configuration loader contract (interface only).

Resolves non-secret configuration and secret *references*. It MUST NOT return
secret values — those are resolved via the SecretStore port at use time (D-14).
Per-service config schemas live in their service; only the loader mechanism is
cross-cutting. No concrete loading is implemented in Build Phase 1.
"""

from __future__ import annotations

from typing import Optional, Protocol

from .secrets import SecretRef


class ConfigLoader(Protocol):
    def get(self, key: str) -> Optional[str]: ...
    def get_secret_ref(self, key: str) -> Optional[SecretRef]: ...
