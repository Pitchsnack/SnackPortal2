"""Shared primitive types and enumerations (references only).

Every enumeration exposed through an API is a Python ``Enum`` subclass, as the OpenAPI
standing rules require (3-day plan §1.2). Every reference here is an opaque string: a
``*_ref`` never carries a name, an email, PII, a payload, a token, a DSN, or a physical
database identifier (IC-013 §7/§10, IC-014 §4).
"""

from __future__ import annotations

from enum import Enum

# --- Roles -------------------------------------------------------------------------


class PlatformRole(str, Enum):
    """The six MVP platform/token roles (IC-005 / D-32; IC-014 §5.1).

    These are platform roles carried by the signed token. They are **not** per-record
    permissions and **not** tenant organizational roles (which remain references-only
    under IC-007 and are never token roles, D-38).
    """

    CONTROL = "CONTROL"
    MASTER_AGENT = "MASTER_AGENT"
    TENANT_ADMIN = "TENANT_ADMIN"
    TENANT_AGENT = "TENANT_AGENT"
    STARTUP_USER = "STARTUP_USER"
    INVESTOR_USER = "INVESTOR_USER"


# The Control-AI role is RESERVED and UNBOUND under this revision (Canonical Overview
# Part 4B; IC-014 §5.1). It is deliberately absent from ``PlatformRole`` so that no token
# can carry it and no rule can bind it before IC-006 is authored to Draft-complete.
RESERVED_CONTROL_AI_ROLE = "CONTROL_AI"


class WorkspaceType(str, Enum):
    """Presentation-layer workspace label, derived FROM the tenant context (IC-013 §6).

    Never a routing input, never a database selector, never an authority of its own. The
    tenant context is never derived from the workspace.
    """

    TENANT_WORKSPACE = "TENANT_WORKSPACE"
    CONTROL_WORKSPACE = "CONTROL_WORKSPACE"


# --- Isolation / dispatch ------------------------------------------------------------


class DatabaseDomain(str, Enum):
    """The single resolution domain a request targets (IC-013 §11, IC-014 §5.4).

    One request resolves to the Control DB **or** exactly one tenant DB — never both,
    never several. There is no Control-DB fallback.
    """

    CONTROL = "CONTROL"
    TENANT = "TENANT"


class OperationCategory(str, Enum):
    """The enumerated BFF operation taxonomy (IC-013 §16).

    Each request resolves to exactly one category, and each category to exactly one
    database domain. ``GOVERNED_SHARING`` is authored-but-inert until IC-007 is Final
    (IC-013 §18).
    """

    TENANT_OPERATION = "TENANT_OPERATION"
    GLOBAL_DIRECTORY_READ = "GLOBAL_DIRECTORY_READ"
    MEMBERSHIPS_FOR_PRINCIPAL = "MEMBERSHIPS_FOR_PRINCIPAL"
    IMPORT_INITIATION = "IMPORT_INITIATION"
    GOVERNED_SHARING = "GOVERNED_SHARING"


# The IC-013 §16 category -> domain map. Exhaustive and closed: an operation whose
# category is absent here cannot be dispatched, and no category may straddle domains.
CATEGORY_DOMAIN: dict[OperationCategory, DatabaseDomain] = {
    OperationCategory.TENANT_OPERATION: DatabaseDomain.TENANT,
    OperationCategory.GLOBAL_DIRECTORY_READ: DatabaseDomain.CONTROL,
    OperationCategory.MEMBERSHIPS_FOR_PRINCIPAL: DatabaseDomain.CONTROL,
    OperationCategory.IMPORT_INITIATION: DatabaseDomain.TENANT,
    OperationCategory.GOVERNED_SHARING: DatabaseDomain.CONTROL,
}


class RecordResidency(str, Enum):
    """Where a record physically lives (D-37 §10 provenance; IC-009 §D).

    ``Global Record != Tenant Record``: an imported record is tenant-resident even though
    its lineage references a global record (IC-003 point-in-time copy).
    """

    GLOBAL = "global"
    TENANT = "tenant"


class TenantLifecycleState(str, Enum):
    """Tenant lifecycle as the Control Plane registry records it (IC-002).

    Readiness gating is a *registry* property. Consistent denial (IC-013 §12) means a
    caller can never tell an unknown tenant from one they may not reach.
    """

    PROVISIONING = "PROVISIONING"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    DISABLED = "DISABLED"


__all__ = [
    "CATEGORY_DOMAIN",
    "RESERVED_CONTROL_AI_ROLE",
    "DatabaseDomain",
    "OperationCategory",
    "PlatformRole",
    "RecordResidency",
    "TenantLifecycleState",
    "WorkspaceType",
]
