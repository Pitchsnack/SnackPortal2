"""Router cache-invalidation signal port (D15-ARCH-SPEC-01 §10.3, §11.2, §22; WP-11).

When a database association, secret reference, provisioning target, or routing
eligibility changes, any cached routing decision must be invalidated so a stale router
cache can never point a tenant at an old or wrong database after re-association.

The control plane does NOT import the Database Router (services are mutually independent —
import-linter). It signals invalidation through this port; a concrete transport provider
(e.g. an HTTP client to the router's internal invalidation endpoint) lives under
`control_plane/adapters/providers/**`. This is only the invalidation *signal* — it does
NOT re-implement the Database Router's request-time resolution (which remains the sole
database selector, IC-005/D-07).

The signal carries a tenant *reference* and a correlation id only — no credentials,
descriptors, or topology (D-14; IC-001 Global Audit Representation Rule).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Tuple


class RouterInvalidationPort(ABC):
    @abstractmethod
    def invalidate_tenant(self, tenant_id: str, *, correlation_id: str) -> None:
        """Request that the Database Router drop any cached routing view for `tenant_id`."""
        ...


class NoOpRouterInvalidation(RouterInvalidationPort):
    """Default signal sink — safe when no router transport is wired (the router's own
    TTL still bounds staleness). Records nothing; performs no I/O."""

    def invalidate_tenant(self, tenant_id: str, *, correlation_id: str) -> None:
        return None


class RecordingRouterInvalidation(RouterInvalidationPort):
    """In-memory signal recorder for controlled non-production verification and tests.

    Captures (tenant_id, correlation_id) pairs so the provisioning flow's invalidation
    behavior is observable without binding a real router transport."""

    def __init__(self) -> None:
        self.signals: List[Tuple[str, str]] = []

    def invalidate_tenant(self, tenant_id: str, *, correlation_id: str) -> None:
        self.signals.append((tenant_id, correlation_id))
