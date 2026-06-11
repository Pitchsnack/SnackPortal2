"""Tenant-database verification probe (Build Phase 4; Standard PRD-P4-R2 G; IC-002/D-17).

Verification is a CONTROL-PLANE-owned capability. The probe opens a short-lived,
single-shot connection to a tenant database (via a provider under
control_plane/adapters/providers/**) to check connectivity + observed schema version,
then closes. It is NOT the serving connection path and does NOT call or import
database_router — so the dependency graph stays acyclic (no control_plane →
database_router edge). The association is passed by reference; credentials are
resolved in-memory by the provider and never returned here (D-14).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from shared.secrets import SecretRef


@dataclass(frozen=True)
class ProbeResult:
    reachable: bool
    observed_schema_version: Optional[str]  # None when unreachable / undeterminable


class TenantDatabaseProbe(ABC):
    @abstractmethod
    def probe(self, association_ref: SecretRef) -> ProbeResult: ...
