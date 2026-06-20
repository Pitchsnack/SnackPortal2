"""Minimally-disclosing liveness / readiness / version (IC-010 §S; D-10 / IC-001).

Health, readiness, and version expose operational status ONLY — never database names,
tenant-database details, tenant counts/identities, or infrastructure topology. Degraded
is observability-only and never denies routing to healthy tenants (D-16). No tenant or
DB identifier appears in any field.
"""

from __future__ import annotations

from typing import Dict

from shared.health import GlobalReadiness

SERVICE = "api_gateway"
BUILD_PHASE = "7"


def liveness() -> Dict[str, str]:
    return {"service": SERVICE, "status": "alive", "build_phase": BUILD_PHASE}


def readiness(state: GlobalReadiness = GlobalReadiness.READY) -> Dict[str, str]:
    # Operational status only; no tenant/DB identifier or topology (§S).
    return {"service": SERVICE, "state": state.value}


def version() -> Dict[str, str]:
    # Coarse, non-disclosing build identifier — not infrastructure/topology detail.
    return {"service": SERVICE, "build_phase": BUILD_PHASE}
