"""In-memory tenant schema applicator — controlled non-production composition (no I/O).

The default `ControlPlane` composition needs a `TenantSchemaApplicator` that "applies" a tenant
database's schema *without* opening a connection. The controlled-non-production real-cluster path
is the postgres applicator in this package, exercised live only by the PRD 07B requires_pg harness.
Records intent (the (tenant_id, target) pairs it was asked to apply); applies nothing; never fails.
Pure stdlib; no driver; references only (D-14). Adds no new behavior model — it satisfies the
existing `TenantSchemaApplicator` port consumed by the onboarding orchestrator's Step 2b.
"""

from __future__ import annotations

from typing import List, Tuple

from control_plane.provisioning import TenantSchemaApplicator
from shared.secrets import SecretRef


class InMemoryTenantSchemaApplicator(TenantSchemaApplicator):
    """Deterministic, no-I/O applicator: records (tenant_id, target); applies no DDL."""

    def __init__(self) -> None:
        self.applied: List[Tuple[str, str]] = []

    def apply_schema(self, tenant_id: str, *, target: str, association_ref: SecretRef) -> None:
        self.applied.append((tenant_id, target))
