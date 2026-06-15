"""Physical Distinctness Verification (D15-ARCH-SPEC-01 §6, §9; D-15/D-30/D-31).

Control-plane-owned. Before a tenant may become routable, the Provisioning Verifier
proves the tenant database is a physically distinct PostgreSQL database — distinct from
every *other tenant* database AND from the *Control Database* — using multiple evidence
layers (D15-ARCH-SPEC-01 §6.2):

    PostgreSQL system_identifier
    + database-level identity
    + provisioning-target validation
    + write-sentinel verification or equivalent

`system_identifier` ALONE is insufficient (§6.3 / DV-AC9): it identifies the cluster, not
the database. Two tenants in the same cluster but different databases are distinct; two
references that resolve to the same (system_identifier, database_identity) are NOT.

This module is pure domain logic (no database driver). Evidence is gathered by a
`DistinctnessEvidenceProvider` whose concrete implementation lives under
`control_plane/adapters/providers/**` (Driver Containment Standard). The verifier
consumes evidence and returns one of the four §9.4 result states; only VERIFIED is
routing-eligible. Any failure or uncertainty fails closed.

References only: evidence/ledger carry cluster/database identifiers, a non-sensitive
provisioning-target reference, a secret *reference* key (never the secret value), and a
sentinel namespace/token. No credentials, no PII, no business payloads (D-14, IC-001
Global Audit Representation Rule).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Mapping, Optional

from shared.secrets import SecretRef


class DistinctnessResult(Enum):
    """The four architectural outcomes of Physical Distinctness Verification (§9.4)."""

    VERIFIED = "Verified"  # Result A — physically distinct; routing-eligible (if lifecycle allows)
    VERIFICATION_FAILED = "VerificationFailed"  # Result B — completed, detected a failure
    VERIFICATION_INCOMPLETE = "VerificationIncomplete"  # Result C — could not complete
    ISOLATION_ANOMALY = "IsolationAnomaly"  # Result D — co-location / same-db / misroute / Control-DB collision


# Non-sensitive failure/category reasons (safe for audit; never identifiers/PII).
REASON_VERIFIED = "verified"
REASON_INCOMPLETE_EVIDENCE = "incomplete_evidence"
REASON_SENTINEL_FAILURE = "sentinel_failure"
REASON_SYSTEM_ID_ONLY = "system_identifier_insufficient"
REASON_MISROUTED_TARGET = "misrouted_target"
REASON_CONTROL_DB_COLLISION = "control_db_collision"
REASON_TENANT_COLLISION = "tenant_collision"


@dataclass(frozen=True)
class DistinctnessEvidence:
    """Reference-only evidence for one database environment (§9.2).

    Carries identity/comparison keys only — never a credential, name, email, or payload.
    """

    system_identifier: str  # DV-C1 — PostgreSQL cluster system identifier
    database_identity: str  # DV-C2 — database-level identity, e.g. "datname:oid"
    observed_target: str  # the provisioning target the connection actually reached (DV-C3/DV-C7)
    secret_ref_key: str  # non-sensitive secret-store reference key (store_ref); never the value
    sentinel_namespace: str  # control-owned namespace the sentinel was written under (DV-C4)
    sentinel_token: Optional[str]  # the unique sentinel written+read back; None if not proven
    sentinel_written: bool  # True iff the sentinel was written to and read back from the intended DB

    @property
    def fingerprint(self) -> str:
        """The physical-database fingerprint = (system_identifier, database_identity).

        The Unit of Physical Isolation (§6.1) is one physically distinct database identity;
        two distinct tenants MUST NOT share this fingerprint. system_identifier alone is
        insufficient (§6.3) — the database_identity is always part of the fingerprint.
        """
        return f"{self.system_identifier}::{self.database_identity}"


@dataclass(frozen=True)
class DistinctnessOutcome:
    """Result of running Physical Distinctness Verification for one tenant."""

    result: DistinctnessResult
    reason: str  # non-sensitive category (one of the REASON_* constants)

    @property
    def routable(self) -> bool:
        """Routing may be enabled ONLY on VERIFIED (fail-closed, §9.3 DV-C9 / DV-AC16)."""
        return self.result is DistinctnessResult.VERIFIED

    @property
    def is_anomaly(self) -> bool:
        return self.result is DistinctnessResult.ISOLATION_ANOMALY


def secret_ref_key(ref: SecretRef) -> str:
    """Non-sensitive comparison key for a secret reference (the store location only).

    Two associations that resolve through the same secret-store location reach the same
    database; comparing this key catches a tenant pointed at the Control DB's secret
    reference (DV-C7A) before any connection is attempted. The secret *value* is never
    used or stored here (D-14)."""
    return ref.store_ref


class PhysicalDistinctnessVerifier:
    """Pure decision logic implementing DV-C1..DV-C9 + DV-C7A (§9.3).

    Inputs are gathered evidence; there is no I/O here. The verifier fails closed: any
    missing evidence, sentinel failure, misroute, or collision yields a non-VERIFIED
    result and therefore leaves routing disabled.
    """

    def verify(
        self,
        tenant_id: str,
        candidate: Optional[DistinctnessEvidence],
        *,
        intended_target: str,
        control_db: DistinctnessEvidence,
        inventory: Mapping[str, DistinctnessEvidence],
    ) -> DistinctnessOutcome:
        # Result C — could not complete (no evidence at all).
        if candidate is None:
            return DistinctnessOutcome(DistinctnessResult.VERIFICATION_INCOMPLETE, REASON_INCOMPLETE_EVIDENCE)

        # DV-C1 + DV-C2 present? system_identifier ALONE is insufficient (DV-AC9): the
        # database-level identity must also be present or distinctness cannot be proven.
        if not candidate.system_identifier or not candidate.database_identity:
            reason = REASON_SYSTEM_ID_ONLY if candidate.system_identifier else REASON_INCOMPLETE_EVIDENCE
            return DistinctnessOutcome(DistinctnessResult.VERIFICATION_INCOMPLETE, reason)

        # DV-C4 — write-sentinel verification (or equivalent) must have proven write+readback.
        if not candidate.sentinel_written or not candidate.sentinel_token:
            return DistinctnessOutcome(DistinctnessResult.VERIFICATION_INCOMPLETE, REASON_SENTINEL_FAILURE)

        # DV-C3 / DV-C7 — provisioning-target validation: the database the connection reached
        # must match the intended target recorded in the registry (else it is misrouted —
        # including, but not limited to, pointing at the Control Database).
        if candidate.observed_target != intended_target:
            return DistinctnessOutcome(DistinctnessResult.ISOLATION_ANOMALY, REASON_MISROUTED_TARGET)

        # DV-C7A — tenant-vs-Control-DB distinctness. Compare on system_identifier +
        # database-level identity + provisioning target + secret reference + sentinel
        # namespace. Any match means the tenant resolves to / collides with the Control DB.
        if (
            candidate.fingerprint == control_db.fingerprint
            or candidate.observed_target == control_db.observed_target
            or candidate.secret_ref_key == control_db.secret_ref_key
            or candidate.sentinel_namespace == control_db.sentinel_namespace
            or (control_db.sentinel_token is not None and candidate.sentinel_token == control_db.sentinel_token)
        ):
            return DistinctnessOutcome(DistinctnessResult.ISOLATION_ANOMALY, REASON_CONTROL_DB_COLLISION)

        # DV-C5 / DV-C6 — tenant-vs-tenant collision: no other tenant may share the physical
        # fingerprint, the provisioning target, the secret reference, or the sentinel.
        for other_id, other in inventory.items():
            if other_id == tenant_id:
                continue
            if (
                candidate.fingerprint == other.fingerprint
                or candidate.observed_target == other.observed_target
                or candidate.secret_ref_key == other.secret_ref_key
                or (other.sentinel_token is not None and candidate.sentinel_token == other.sentinel_token)
            ):
                return DistinctnessOutcome(DistinctnessResult.ISOLATION_ANOMALY, REASON_TENANT_COLLISION)

        # Result A — physically distinct (tenant-vs-tenant AND tenant-vs-Control-DB).
        return DistinctnessOutcome(DistinctnessResult.VERIFIED, REASON_VERIFIED)


class DistinctnessEvidenceProvider(ABC):
    """Gathers physical-distinctness evidence for a tenant database (§9.2).

    The concrete provider opens a short-lived connection (driver confined to
    control_plane/adapters/providers/**), reads the cluster system_identifier and the
    database-level identity, validates the provisioning target, and writes+reads a unique
    write-sentinel in a control-owned namespace. It returns None (→ INCOMPLETE) on any
    failure and never surfaces a credential, descriptor, or topology (fail-closed, D-14).
    """

    @abstractmethod
    def gather(
        self,
        association_ref: SecretRef,
        *,
        sentinel_token: str,
        sentinel_namespace: str,
    ) -> Optional[DistinctnessEvidence]: ...


class DistinctnessLedger(ABC):
    """Reference-only inventory of per-tenant distinctness evidence (§9.2 input 8).

    Kept separate from the frozen ControlStore port so the existing Control-DB persistence
    interface is unchanged. Holds comparison keys only (no credentials/PII); the default is
    in-memory. Used to detect tenant-vs-tenant collisions during verification.
    """

    @abstractmethod
    def record_evidence(self, tenant_id: str, evidence: DistinctnessEvidence) -> None: ...
    @abstractmethod
    def evidence_excluding(self, tenant_id: str) -> Mapping[str, DistinctnessEvidence]: ...
    @abstractmethod
    def remove(self, tenant_id: str) -> None: ...


class InMemoryDistinctnessLedger(DistinctnessLedger):
    """Pure-stdlib default ledger (controlled non-production verification)."""

    def __init__(self) -> None:
        self._by_tenant: Dict[str, DistinctnessEvidence] = {}

    def record_evidence(self, tenant_id: str, evidence: DistinctnessEvidence) -> None:
        self._by_tenant[tenant_id] = evidence

    def evidence_excluding(self, tenant_id: str) -> Mapping[str, DistinctnessEvidence]:
        return {tid: ev for tid, ev in self._by_tenant.items() if tid != tenant_id}

    def remove(self, tenant_id: str) -> None:
        self._by_tenant.pop(tenant_id, None)
