"""In-memory doubles for D15 provisioning-verification tests (stdlib; no driver).

Fakes for the tenant-DB probe and the distinctness evidence provider, plus builders for a
registered tenant and a wired ProvisioningVerificationService. No psycopg, no I/O.
"""

from __future__ import annotations

import itertools
import pathlib
import sys
from dataclasses import replace
from typing import Dict, Optional

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))  # backend on path

from control_plane.adapters.providers.in_memory_store import InMemoryControlStore  # noqa: E402
from control_plane.audit import ControlPlaneAudit  # noqa: E402
from control_plane.distinctness import (  # noqa: E402
    DistinctnessEvidence,
    DistinctnessEvidenceProvider,
    InMemoryDistinctnessLedger,
)
from control_plane.provisioning import ProvisioningVerificationService, tenant_database_name  # noqa: E402
from control_plane.records import TenantLifecycleState, TenantRecord  # noqa: E402
from control_plane.router_signal import RecordingRouterInvalidation  # noqa: E402
from control_plane.verification import ProbeResult, TenantDatabaseProbe  # noqa: E402
from shared.secrets import SecretRef  # noqa: E402

# A stable Control-DB evidence fixture: distinct cluster-db identity, target, secret ref,
# and sentinel namespace from any tenant the tests create.
CONTROL_EVIDENCE = DistinctnessEvidence(
    system_identifier="cluster-A",
    database_identity="sp2_control:1",
    observed_target="sp2_control",
    secret_ref_key="control_secret",
    sentinel_namespace="dv_sentinel_control",
    sentinel_token=None,
    sentinel_written=True,
)


class FakeProbe(TenantDatabaseProbe):
    def __init__(self, *, reachable: bool = True, observed_schema_version: Optional[str] = "1") -> None:
        self._reachable = reachable
        self._ver = observed_schema_version

    def probe(self, association_ref: SecretRef) -> ProbeResult:
        return ProbeResult(reachable=self._reachable, observed_schema_version=self._ver)


class FakeEvidenceProvider(DistinctnessEvidenceProvider):
    """Returns evidence pre-seeded per association store_ref. Echoes the service-chosen
    sentinel token/namespace and binds secret_ref_key to the association (as a real
    provider would). Returns None to simulate an unreachable/incomplete gather."""

    def __init__(self, by_store_ref: Dict[str, DistinctnessEvidence], *, available: bool = True) -> None:
        self._by = by_store_ref
        self._available = available

    def gather(self, association_ref: SecretRef, *, sentinel_token: str, sentinel_namespace: str) -> Optional[DistinctnessEvidence]:
        if not self._available:
            return None
        base = self._by.get(association_ref.store_ref)
        if base is None:
            return None
        return replace(
            base,
            secret_ref_key=association_ref.store_ref,
            sentinel_token=sentinel_token,
            sentinel_namespace=sentinel_namespace,
            sentinel_written=True,
        )


def tenant_evidence(
    tenant_id: str, *, system_identifier: str = "cluster-A", database_identity: Optional[str] = None, observed_target: Optional[str] = None
) -> DistinctnessEvidence:
    """Build a 'verified-shape' tenant evidence base (sentinel fields filled by the provider)."""
    return DistinctnessEvidence(
        system_identifier=system_identifier,
        database_identity=database_identity or f"{tenant_database_name(tenant_id)}:{abs(hash(tenant_id)) % 100000}",
        observed_target=observed_target or tenant_database_name(tenant_id),
        secret_ref_key="(provider-bound)",
        sentinel_namespace="(provider-bound)",
        sentinel_token=None,
        sentinel_written=False,
    )


def register_tenant(
    store: InMemoryControlStore,
    tenant_id: str,
    *,
    store_ref: str,
    schema: str = "1",
    state: TenantLifecycleState = TenantLifecycleState.PROVISIONING,
) -> TenantRecord:
    rec = TenantRecord(
        tenant_id=tenant_id,
        organization_ref=f"org_ref_{tenant_id}",
        lifecycle_state=state,
        expected_schema_version=schema,
        database_association_ref=SecretRef(store_ref=store_ref, version="1"),
        federation_config_ref=f"fed_ref_{tenant_id}",
        created_at="2026-06-14T00:00:00+00:00",
        updated_at="2026-06-14T00:00:00+00:00",
    )
    store.put_tenant(rec)
    return rec


def build_service(
    store: InMemoryControlStore,
    evidence_provider: DistinctnessEvidenceProvider,
    *,
    probe: Optional[TenantDatabaseProbe] = None,
    router: Optional[RecordingRouterInvalidation] = None,
    ledger: Optional[InMemoryDistinctnessLedger] = None,
) -> ProvisioningVerificationService:
    counter = itertools.count()
    return ProvisioningVerificationService(
        store,
        ControlPlaneAudit(store),
        probe or FakeProbe(),
        evidence_provider,
        CONTROL_EVIDENCE,
        supported_schema_versions=["1"],
        ledger=ledger or InMemoryDistinctnessLedger(),
        router_invalidation=router or RecordingRouterInvalidation(),
        token_factory=lambda: f"sentok-{next(counter)}",
    )
