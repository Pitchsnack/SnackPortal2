"""Health & readiness shapes (interface/shapes only).

Three-state global readiness (D-10 / IC-001) and two-state tenant readiness
(IC-002). The Readiness & Disclosure Standard (governance I; IC-001/IC-002/IC-005)
binds any future implementation: readiness is access-controlled and minimally
disclosing and MUST NOT leak tenant or database existence/topology. No readiness
logic exists in Build Phase 1.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class GlobalReadiness(Enum):
    READY = "ready"
    DEGRADED = "degraded"  # observability-only; never denies healthy tenants (D-16)
    NOT_READY = "not_ready"


class TenantReadiness(Enum):
    READY = "ready"
    NOT_READY = "not_ready"


@dataclass(frozen=True)
class LivenessReport:
    alive: bool


@dataclass(frozen=True)
class ReadinessReport:
    state: GlobalReadiness
    detail: str = ""  # non-sensitive only; no tenant/DB identifiers
