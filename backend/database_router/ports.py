"""database_router ports (interfaces). Concrete adapters live under adapters/providers.

- ControlPlaneRoutingReadPort: transport read of the control-plane routing view
  (no in-process import of control_plane). Raises on unavailability so callers fail
  closed (PRD-P4-R2 B; D-07).
- TenantConnection / ConnectionFactory: the per-tenant database connection seam. A
  connection is bound to exactly one tenant for its lifetime and never reused across
  tenants (PRD-P4-R2 E; D-13/D-30). The factory is the ONLY place a real database
  driver is touched (driver lives under database_router/adapters/providers/**).

Caller-controlled transactions (begin/commit/rollback) are supported so a future
import + lineage write can commit atomically on the single resolved connection
(PRD-P4-R2 J; IC-003/IC-004). No credentials are held in these shapes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from .models import TenantRoutingView


class ControlPlaneRoutingReadPort(ABC):
    """Read-only, transport access to the control-plane routing view.

    Returns None for an unknown/unauthorized tenant (consistent denial). Raises on
    control-plane unavailability — callers MUST fail closed (never assume routability).
    """

    @abstractmethod
    def get_routing_view(self, tenant_id: str) -> Optional[TenantRoutingView]: ...


class TenantConnection(ABC):
    """A connection bound to exactly one tenant + association version for its lifetime."""

    @property
    @abstractmethod
    def tenant_id(self) -> str: ...

    @property
    @abstractmethod
    def association_version(self) -> str: ...

    @abstractmethod
    def is_alive(self) -> bool: ...

    @abstractmethod
    def begin(self) -> None: ...

    @abstractmethod
    def commit(self) -> None: ...

    @abstractmethod
    def rollback(self) -> None: ...

    @abstractmethod
    def reset(self) -> None:
        """Clear session state before the connection returns to its pool."""

    @abstractmethod
    def close(self) -> None: ...

    @abstractmethod
    def execute(self, statement: str, params: tuple = ()) -> None:
        """Run a parameterized write statement on the bound connection (Build Phase 5)."""

    @abstractmethod
    def query(self, statement: str, params: tuple = ()) -> list:
        """Run a parameterized read and return rows as dicts (Build Phase 5)."""


class ConnectionFactory(ABC):
    """Opens a new tenant connection from a resolved, in-memory connection descriptor.

    `descriptor` is the secret material resolved at connect time (D-14). It is used
    only to open the connection and is never stored, logged, or returned.
    """

    @abstractmethod
    def open(self, tenant_id: str, association_version: str, descriptor: str) -> TenantConnection: ...
