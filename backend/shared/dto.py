"""Cross-cutting DTO shapes (shared, vendor-neutral) — shapes only.

Only shapes consumed by >=2 services and owned by no single contract live here
(Shared Package Admission Policy, governance E). Reference-only; never secrets or
tokens (D-14, IC-005). Contract-owned DTOs (e.g. Tenant Descriptor, Lineage
Record, Import Request) live in their owning service, not here.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class IdentitySource(Enum):
    INTERNAL = "internal"    # internal platform identity (D-03)
    FEDERATED = "federated"  # OIDC-federated external-org principal (D-03)


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    subject_ref: str         # identity reference, never a token/credential
    source: IdentitySource


@dataclass(frozen=True)
class TenantContext:
    active_tenant_id: str    # the single active tenant per request (D-04/D-06)


@dataclass(frozen=True)
class AuthError:
    code: str                # non-sensitive code only
