"""ControlStore port — the Control Database persistence boundary (interface only).

The control plane depends on this port; the concrete backend is selected at the
composition root. Phase 2 default is an in-memory adapter (pure stdlib); a portable
PostgreSQL provider is a deferred persistence-binding step. No tenant-DB access.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from .records import (
    ControlAuditRecord,
    DirectoryKind,
    DirectoryRecord,
    FederationConfig,
    MembershipRecord,
    TenantRecord,
)


class ControlStoreConcurrencyError(Exception):
    """A tenant lifecycle CAS write lost to a concurrent writer (PRD 07D-2e; R-2c-LWW).

    Raised by ``ControlStore.compare_and_swap_tenant`` when the stored
    ``TenantRecord.version`` no longer equals the caller's ``expected_version`` — a newer
    lifecycle write (e.g. a concurrent SuspendTenant) committed between the caller's read
    and its write, and MUST NOT be silently overwritten. A store/port-layer Python
    exception only: distinct from every service error type and NOT audit/event
    vocabulary (nothing records it; callers map it to their own fail-closed policy).
    """


class ControlStore(ABC):
    # --- control metadata ---
    @abstractmethod
    def is_reachable(self) -> bool: ...
    @abstractmethod
    def schema_version(self) -> int: ...

    # --- tenant registry ---
    @abstractmethod
    def put_tenant(self, record: TenantRecord) -> None: ...

    @abstractmethod
    def compare_and_swap_tenant(self, updated: TenantRecord, *, expected_version: int) -> TenantRecord:
        """Optimistic-concurrency lifecycle write (PRD 07D-2e; D-2e-2).

        Persists ``updated`` ONLY if the stored record's ``version`` still equals
        ``expected_version``; returns the persisted record with ``version`` incremented by
        exactly one. On mismatch (or a concurrently vanished record) raises
        ``ControlStoreConcurrencyError`` and persists nothing — a newer write is never
        silently overwritten. ``put_tenant`` remains the create/seed path only.

        Durable-adapter transaction contract (D-2e-4): the CAS UPDATE executes inside the
        connection's open transaction and does NOT commit by itself — the lifecycle
        transition's subsequent ``append_audit`` commits BOTH atomically, so a conflict
        rolls back with no orphan audit and a failed audit write rolls back the state
        change. The in-memory adapter applies immediately (its writes never fail).
        """

    @abstractmethod
    def get_tenant(self, tenant_id: str) -> Optional[TenantRecord]: ...
    @abstractmethod
    def list_tenant_ids(self) -> List[str]: ...

    # --- membership ---
    @abstractmethod
    def put_membership(self, record: MembershipRecord) -> None: ...
    @abstractmethod
    def list_memberships(self, principal_ref: Optional[str] = None, tenant_id: Optional[str] = None) -> List[MembershipRecord]: ...

    # --- federation config ---
    @abstractmethod
    def put_federation(self, config: FederationConfig) -> None: ...
    @abstractmethod
    def get_federation(self, tenant_id: str) -> Optional[FederationConfig]: ...

    # --- global discovery platform ---
    @abstractmethod
    def put_directory_record(self, record: DirectoryRecord) -> None: ...
    @abstractmethod
    def get_directory_record(self, directory: DirectoryKind, record_id: str) -> Optional[DirectoryRecord]: ...
    @abstractmethod
    def list_directory(self, directory: DirectoryKind) -> List[DirectoryRecord]: ...

    # --- operational audit (append-only) ---
    @abstractmethod
    def append_audit(self, record: ControlAuditRecord) -> None: ...
    @abstractmethod
    def list_audit(self) -> List[ControlAuditRecord]: ...
