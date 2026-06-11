"""In-memory ControlStore adapter (pure stdlib) — Build Phase 2 default persistence.

Stands in for the Control Database so the control-plane frameworks are functional and
testable without binding a database driver. The logical Control-DB schema is the record
models + the ControlStore port. No tenant-DB access; control-plane data only.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from control_plane.ports import ControlStore
from control_plane.records import (
    ControlAuditRecord,
    DirectoryKind,
    DirectoryRecord,
    FederationConfig,
    MembershipRecord,
    TenantRecord,
)


class InMemoryControlStore(ControlStore):
    def __init__(self, schema_version: int = 1, reachable: bool = True) -> None:
        self._schema_version = schema_version
        self._reachable = reachable
        self._tenants: Dict[str, TenantRecord] = {}
        self._memberships: List[MembershipRecord] = []
        self._federation: Dict[str, FederationConfig] = {}
        self._directory: Dict[Tuple[str, str], DirectoryRecord] = {}
        self._audit: List[ControlAuditRecord] = []

    # control metadata
    def is_reachable(self) -> bool:
        return self._reachable

    def schema_version(self) -> int:
        return self._schema_version

    # tenants
    def put_tenant(self, record: TenantRecord) -> None:
        self._tenants[record.tenant_id] = record

    def get_tenant(self, tenant_id: str) -> Optional[TenantRecord]:
        return self._tenants.get(tenant_id)

    def list_tenant_ids(self) -> List[str]:
        return list(self._tenants.keys())

    # memberships
    def put_membership(self, record: MembershipRecord) -> None:
        self._memberships.append(record)

    def list_memberships(self, principal_ref: Optional[str] = None, tenant_id: Optional[str] = None) -> List[MembershipRecord]:
        out = self._memberships
        if principal_ref is not None:
            out = [m for m in out if m.principal_ref == principal_ref]
        if tenant_id is not None:
            out = [m for m in out if m.tenant_id == tenant_id]
        return list(out)

    # federation
    def put_federation(self, config: FederationConfig) -> None:
        self._federation[config.tenant_id] = config

    def get_federation(self, tenant_id: str) -> Optional[FederationConfig]:
        return self._federation.get(tenant_id)

    # directory
    def put_directory_record(self, record: DirectoryRecord) -> None:
        self._directory[(record.directory.value, record.record_id)] = record

    def get_directory_record(self, directory: DirectoryKind, record_id: str) -> Optional[DirectoryRecord]:
        return self._directory.get((directory.value, record_id))

    def list_directory(self, directory: DirectoryKind) -> List[DirectoryRecord]:
        return [r for (d, _), r in self._directory.items() if d == directory.value]

    # audit (append-only)
    def append_audit(self, record: ControlAuditRecord) -> None:
        self._audit.append(record)

    def list_audit(self) -> List[ControlAuditRecord]:
        return list(self._audit)
