"""Federation configuration store (IC-002 Tenant<->Org Mapping / D-03) — storage only.

Stores per-tenant OIDC config (issuer, audience, jwks reference, claim->tenant rule)
that Build Phase 3 (IC-005) consumes. No runtime validation, no JWT processing, no
OIDC processing here. jwks is stored by reference (public keys; no secret inline).
"""

from __future__ import annotations

from typing import Optional

from .ports import ControlStore
from .records import FederationConfig


class FederationStore:
    def __init__(self, store: ControlStore) -> None:
        self._store = store

    def put(self, config: FederationConfig) -> None:
        self._store.put_federation(config)

    def get(self, tenant_id: str) -> Optional[FederationConfig]:
        return self._store.get_federation(tenant_id)
