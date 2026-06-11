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
