"""In-memory tenant-database probe — controlled non-production composition (no I/O).

The default `ControlPlane` composition needs a `TenantDatabaseProbe` that reports a
reachable tenant database at the supported schema version *without* opening a connection.
The controlled-non-production real-cluster path is the postgres probe in this package,
exercised live only in B-4. Pure stdlib; no driver; references only (D-14).

This adds no new verification model: it returns the existing `ProbeResult` shape consumed
by the existing `ProvisioningVerificationService`.
"""

from __future__ import annotations

from control_plane.verification import ProbeResult, TenantDatabaseProbe
from shared.secrets import SecretRef


class InMemoryTenantDatabaseProbe(TenantDatabaseProbe):
    """Deterministic, no-I/O probe: reports reachable at a fixed schema version."""

    def __init__(self, *, schema_version: str = "1", reachable: bool = True) -> None:
        self._schema_version = schema_version
        self._reachable = reachable

    def probe(self, association_ref: SecretRef) -> ProbeResult:
        if not self._reachable:
            return ProbeResult(reachable=False, observed_schema_version=None)
        return ProbeResult(reachable=True, observed_schema_version=self._schema_version)
