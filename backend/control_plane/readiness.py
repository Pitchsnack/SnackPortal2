"""Readiness framework — three-state global readiness (D-10 / IC-001).

`degraded` is observability-only and never denies healthy tenants (D-16). Reports
are disclosure-safe (Phase-1 Disclosure Standard): no tenant ids/counts, no database
identifiers/topology, no secrets.
"""
from __future__ import annotations

from shared.health import GlobalReadiness, ReadinessReport


class ReadinessFramework:
    def evaluate(
        self,
        *,
        phase1_active: bool,
        control_store_reachable: bool,
        schema_pass: bool,
        degraded: bool = False,
    ) -> ReadinessReport:
        if not phase1_active or not control_store_reachable or not schema_pass:
            # Global not-ready is reserved for shared-dependency / Phase-0 failure (D-10).
            return ReadinessReport(state=GlobalReadiness.NOT_READY, detail="control plane not ready")
        if degraded:
            return ReadinessReport(state=GlobalReadiness.DEGRADED, detail="serving; non-critical degradation")
        return ReadinessReport(state=GlobalReadiness.READY, detail="")
