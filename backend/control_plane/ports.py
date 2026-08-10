"""ControlStore port — the Control Database persistence boundary (interface only).

The control plane depends on this port; the concrete backend is selected at the
composition root. Phase 2 default is an in-memory adapter (pure stdlib); a portable
PostgreSQL provider is a deferred persistence-binding step. No tenant-DB access.

This module also declares ``WorkspaceMembershipReadPort`` — a deliberately separate,
single-method READ port. ``ControlStore`` is the full persistence boundary (it can write
tenants, memberships, federation config, directory records and audit rows); the public
workspace edge needs exactly one read out of it and must not be handed the rest.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

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


class WorkspaceMembershipReadPort(ABC):
    """The ENTIRE Control-Plane capability the public workspace edge is permitted to hold.

    One method, read-only, self-scoped by its single argument. This port exists because the
    public workspace edge is an internet-facing process: whatever it is handed is what an
    attacker who compromises it inherits. Handing it a ``ControlPlane`` (provisioning
    operator, schema applicator, recovery/compensation, orphan scan, onboarding orchestrator,
    distinctness ledger, tenant registry, the provisioning-admin secret binding) or even a raw
    ``ControlStore`` (``put_tenant``, ``compare_and_swap_tenant``, ``put_membership``,
    ``put_federation``, ``put_directory_record``, ``append_audit``) grants capability that the
    one public read route has no use for.

    Narrow by TYPE, not by discipline: there is no powerful object behind an unused method
    here, because the port declares no such method to begin with. An edge holding only this
    port cannot create a tenant database, drop one, provision, apply schema, run recovery or
    compensation, or write any Control-DB row — those operations are not expressible through
    it. That is the property the architecture guard checks structurally.

    Credential posture: implementations resolve whatever Control-DB credential the composition
    root already binds. Nothing here widens database authority, and nothing here presumes the
    credential is read-write — a narrower, genuinely read-only Control-DB role can be supplied
    later purely as configuration, with no change to this port or to the edge that consumes it.
    """

    @abstractmethod
    def memberships_for_principal(self, principal_ref: str) -> Dict[str, Any]:
        """Enumerate ONE principal's tenant memberships (IC-002:207 MembershipsForPrincipal).

        Returns the transport-neutral enumeration ``{"memberships": [{"tenant_id", "role"}]}``
        — references only, never a credential, a database identity, or any PII. An unknown,
        empty, or malformed ``principal_ref`` yields an EMPTY list, never an error and never an
        existence leak. The caller composes the public DTO and re-validates the shape, so an
        unexpected structure fails closed rather than reaching a client.
        """
