"""Membership registry (D-04 / D-32 / IC-002) — storage only.

One principal -> many tenants (1:N). Roles stored, never evaluated. MASTER_AGENT may
hold many tenant assignments. No active-tenant selection, no authorization, no
permission evaluation, no JWT — those are Build Phase 3 (IC-005).
"""

from __future__ import annotations

from typing import List

from .ports import ControlStore
from .records import MembershipRecord, Role


class MembershipRegistry:
    def __init__(self, store: ControlStore) -> None:
        self._store = store

    def add_membership(self, *, principal_ref: str, tenant_id: str, role: Role) -> MembershipRecord:
        record = MembershipRecord(principal_ref=principal_ref, tenant_id=tenant_id, role=role)
        self._store.put_membership(record)
        return record

    def tenants_for(self, principal_ref: str) -> List[MembershipRecord]:
        return self._store.list_memberships(principal_ref=principal_ref)

    def members_of(self, tenant_id: str) -> List[MembershipRecord]:
        return self._store.list_memberships(tenant_id=tenant_id)
