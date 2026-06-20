"""In-memory physical-distinctness evidence — controlled non-production composition.

A deterministic, no-I/O ``DistinctnessEvidenceProvider`` for the default ``ControlPlane``
composition (OB-1/OB-2; EXEC-B1 R1). The live tree has only the postgres provider (which
opens a connection) and a test-only fake, so the default composition has no production
in-memory evidence source — this supplies one. It derives a unique physical fingerprint
and the observed provisioning target from the association reference: in controlled
non-production the secret-store reference *is* the provisioned target name
(``tenant_database_name``), so the evidence the gate sees matches the registry's intended
target. It never opens a connection and never handles a credential value (D-14). The
real-cluster evidence path is the postgres provider in this package, exercised live only
in B-4.

This adds no new distinctness model: it returns the existing ``DistinctnessEvidence``
shape under the existing IC-010 §P verifier (unchanged).
"""

from __future__ import annotations

from typing import Optional

from control_plane.distinctness import DistinctnessEvidence, DistinctnessEvidenceProvider
from shared.secrets import SecretRef

# Controlled-non-prod cluster identifiers. The Control DB and tenant databases are modelled
# as distinct physical databases (distinct fingerprints), preserving the §P tenant-vs-
# Control-DB and tenant-vs-tenant distinctness guarantees in the in-memory composition.
NONPROD_CONTROL_SYSTEM_IDENTIFIER = "sp2_nonprod_control_cluster"
NONPROD_TENANT_SYSTEM_IDENTIFIER = "sp2_nonprod_tenant_cluster"
NONPROD_CONTROL_TARGET = "sp2_control"
NONPROD_CONTROL_SECRET_REF = "sp2_control"
NONPROD_CONTROL_SENTINEL_NAMESPACE = "dv_sentinel_control"


def nonprod_control_db_evidence() -> DistinctnessEvidence:
    """Controlled-non-production Control-DB distinctness evidence (reference-only).

    Distinct cluster/db identity, target, secret reference, and sentinel namespace from any
    provisioned tenant database, so the gate's tenant-vs-Control-DB check is meaningful.
    """
    return DistinctnessEvidence(
        system_identifier=NONPROD_CONTROL_SYSTEM_IDENTIFIER,
        database_identity=f"{NONPROD_CONTROL_TARGET}:control",
        observed_target=NONPROD_CONTROL_TARGET,
        secret_ref_key=NONPROD_CONTROL_SECRET_REF,
        sentinel_namespace=NONPROD_CONTROL_SENTINEL_NAMESPACE,
        sentinel_token=None,
        sentinel_written=True,
    )


class InMemoryDistinctnessEvidenceProvider(DistinctnessEvidenceProvider):
    """Deterministic, no-I/O evidence: derives a unique physical fingerprint and the
    observed provisioning target from the association store reference."""

    def __init__(self, *, system_identifier: str = NONPROD_TENANT_SYSTEM_IDENTIFIER) -> None:
        self._system_identifier = system_identifier

    def gather(
        self,
        association_ref: SecretRef,
        *,
        sentinel_token: str,
        sentinel_namespace: str,
    ) -> Optional[DistinctnessEvidence]:
        target = association_ref.store_ref
        return DistinctnessEvidence(
            system_identifier=self._system_identifier,
            database_identity=f"{target}:db",
            observed_target=target,
            secret_ref_key=association_ref.store_ref,
            sentinel_namespace=sentinel_namespace,
            sentinel_token=sentinel_token,
            sentinel_written=True,
        )
