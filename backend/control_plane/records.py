"""Control-plane record shapes — the *logical* Control-DB schema (IC-001/IC-002).

References only; no credentials/secrets/payloads (D-14). Physical PostgreSQL
persistence is provided behind the ControlStore port (Phase 2 default = in-memory;
concrete PostgreSQL provider deferred).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional

from shared.secrets import SecretRef


class TenantLifecycleState(Enum):
    REGISTERED = "Registered"
    PROVISIONING = "Provisioning"
    VERIFYING = "Verifying"  # set only in Build Phase 4 (needs tenant-DB)
    READY = "Ready"  # set only in Build Phase 4 (needs verification)
    SUSPENDED = "Suspended"
    FAILED = "Failed"  # set only in Build Phase 4 (set by verify)
    # IC-002 Recovery & Compensation (PRD 07D-2b.2a): isolation-class safety hold. Evidence-
    # preserving, non-routable, never resumes toward Verifying/Ready; sole egress Decommissioned.
    QUARANTINED = "Quarantined"
    DECOMMISSIONED = "Decommissioned"


@dataclass(frozen=True)
class TenantRecord:
    """IC-002 Tenant Descriptor (reference model). Credentials are NEVER stored."""

    tenant_id: str
    organization_ref: str
    lifecycle_state: TenantLifecycleState
    expected_schema_version: str
    database_association_ref: SecretRef  # reference {store_ref, version}; resolved in Phase 4
    federation_config_ref: str
    created_at: str
    updated_at: str


class Role(Enum):
    CONTROL = "CONTROL"
    MASTER_AGENT = "MASTER_AGENT"
    TENANT_ADMIN = "TENANT_ADMIN"
    TENANT_AGENT = "TENANT_AGENT"
    STARTUP_USER = "STARTUP_USER"
    INVESTOR_USER = "INVESTOR_USER"


@dataclass(frozen=True)
class MembershipRecord:
    """Storage only (D-04 1:N, D-32 roles). Eligibility, not active selection."""

    principal_ref: str
    tenant_id: str
    role: Role


@dataclass(frozen=True)
class FederationConfig:
    """Per-tenant OIDC config (IC-002 Tenant<->Org Mapping). Storage only; jwks by reference."""

    tenant_id: str
    oidc_issuer: str
    oidc_audience: str
    jwks_ref: str
    claim_to_tenant_rule: str


class DirectoryKind(Enum):
    STARTUP = "GlobalStartupDirectory"
    INVESTOR = "GlobalInvestorDirectory"


@dataclass
class DirectoryRecord:
    """Global Discovery Platform record (D-31). Control-DB only; Global Record != Tenant Record.

    `record_id` is a stable identifier for future IC-003 import / IC-004 lineage `source_ref`.
    """

    directory: DirectoryKind
    record_id: str
    display_name: str
    attributes: Dict[str, str] = field(default_factory=dict)  # non-sensitive global reference data


class SchemaCompatState(Enum):
    PASS = "Pass"
    FAIL = "Fail"
    VERSION_MISMATCH = "Version Mismatch"
    MIGRATION_REQUIRED = "Migration Required"


@dataclass(frozen=True)
class ControlAuditRecord:
    """Operational/control-plane audit (IC-002). References only; no secrets/lineage."""

    actor: str
    tenant_id: Optional[str]
    action: str
    from_state: Optional[str]
    to_state: Optional[str]
    timestamp: str
    correlation_id: str
