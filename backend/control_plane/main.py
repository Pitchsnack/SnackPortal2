"""Control Plane composition root (Build Phase 2).

Wires the control-plane frameworks against the ControlStore port (default in-memory
adapter) and the vendor-neutral env/file SecretStore provider for Bootstrap Phase 0.
No tenant-database access, no routing, no runtime authentication.
"""

from __future__ import annotations

import os
from typing import Dict, Tuple

from shared.adapters.providers.env_reference_secret_store import DEFAULT_ALLOWED, EnvReferenceSecretStore
from shared.secrets import SecretRef

from .adapters.providers.in_memory_distinctness import (
    InMemoryDistinctnessEvidenceProvider,
    nonprod_control_db_evidence,
)
from .adapters.providers.in_memory_probe import InMemoryTenantDatabaseProbe
from .adapters.providers.in_memory_store import InMemoryControlStore
from .adapters.providers.in_memory_tenant_schema_applicator import InMemoryTenantSchemaApplicator
from .audit import ControlPlaneAudit
from .bootstrap import BootstrapController
from .directory import GlobalDirectory
from .distinctness import DistinctnessLedger, InMemoryDistinctnessLedger
from .federation import FederationStore
from .membership import MembershipRegistry
from .onboarding import OnboardingOrchestrator
from .ports import ControlStore
from .provisioning import (
    InMemoryProvisioningOperator,
    ProvisioningOperator,
    ProvisioningVerificationService,
    TenantSchemaApplicator,
)
from .readiness import ReadinessFramework
from .registry import TenantRegistry
from .schema_compat import SchemaCompatibilityChecker

SERVICE = "control_plane"
SUPPORTED_SCHEMA_MIN = 1
SUPPORTED_SCHEMA_MAX = 1

# D-15 orchestration adapter selection (OB-1). Unset/empty -> in-memory (controlled
# non-production default); any other value selects the controlled-non-prod real-cluster
# adapters, which are delivered in B-4 (live-PostgreSQL exercise) — not B-1.
PROVISIONING_ADAPTER_ENV = "SP2_CP_PROVISIONING_ADAPTER"

# D-15 distinctness-ledger selection (PRD 06 B-2). Unset/empty -> in-memory (controlled
# non-production default; the per-instance distinctness-evidence inventory). Any other value
# selects the durable Control-DB-backed ledger, whose live record/read exercise against a real
# Control DB is delivered in B-4 (live PostgreSQL) — not B-2; selecting it here defers with
# NotImplementedError rather than silently falling back. Construction performs no I/O.
DISTINCTNESS_LEDGER_ENV = "SP2_CP_DISTINCTNESS_LEDGER"

# Control-Store selection (PRD 06 B-7B; controlled non-production runtime audit-sink wiring).
# Unset/empty -> in-memory (the default persistence — construction performs no I/O). The value
# 'postgres' selects the durable Control-DB-backed ControlStore (the operational audit sink is
# ONE consumer of this store — B-7B selects a durable ControlStore, not a separate audit sink);
# it is lazy-connect (no I/O at construction; connects and fails closed on first store
# operation). Any other value raises (fail closed), mirroring the SP2_CP_PROVISIONING_ADAPTER /
# SP2_CP_DISTINCTNESS_LEDGER deferral-lock — except 'postgres' is IMPLEMENTED here (non-prod),
# not deferred. No production activation, no runtime DDL.
CONTROL_STORE_ENV = "SP2_CP_CONTROL_STORE"

# Name of the secret-store REFERENCE (SecretRef.store_ref) for the durable Control-Store DSN
# (D-14). The composition root resolves the DSN through the SecretStore by this reference and
# holds NO DSN literal; SNACKPORTAL_TEST_DSN is never reused as runtime config.
CONTROL_STORE_DSN_REF_ENV = "SP2_CP_CONTROL_STORE_DSN_REF"
DEFAULT_CONTROL_STORE_DSN_REF = "control/control-store-dsn"

# Tenant schema-applicator selection (PRD 07B; D15-ARCH-SPEC-01 §8 Step 2b). Unset/empty ->
# in-memory (controlled non-production default; construction performs no I/O). The real applicator
# (which applies the existing provisioning + lineage DDL to a freshly provisioned tenant database in
# a single atomic, fail-closed transaction) is exercised live by the PRD 07B requires_pg harness,
# which composes it DIRECTLY with a tenant-DSN secret store; composition-level live selection
# requires the same controlled-non-prod wiring as SP2_CP_PROVISIONING_ADAPTER and is delivered in a
# later phase — any non-default value defers here (fail closed) rather than half-wire it.
TENANT_SCHEMA_APPLICATOR_ENV = "SP2_CP_TENANT_SCHEMA_APPLICATOR"


class ControlPlane:
    """Assembled control plane. Construction performs no I/O and no bootstrap."""

    def __init__(self, store: ControlStore | None = None) -> None:
        # An explicit store wins (tests / the B-7A harness). Otherwise the Control-Store is
        # selected by env (B-7B); the default is in-memory and construction performs no I/O.
        self.store = store if store is not None else self._build_store()
        self.audit = ControlPlaneAudit(self.store)
        self.registry = TenantRegistry(self.store, self.audit)
        self.membership = MembershipRegistry(self.store)
        self.federation = FederationStore(self.store)
        self.directory = GlobalDirectory(self.store)
        self.readiness = ReadinessFramework()
        self.schema = SchemaCompatibilityChecker(SUPPORTED_SCHEMA_MIN, SUPPORTED_SCHEMA_MAX)
        self.secret_store = EnvReferenceSecretStore()
        self.bootstrap = BootstrapController(self.secret_store)
        # D-15 orchestration wiring (B-1, controlled non-production). Adapter selected by
        # env (OB-1); default is in-memory. Construction performs no I/O.
        self.operator, self.provisioning = self._build_provisioning()
        self.schema_applicator = self._build_schema_applicator()
        self.onboarding = OnboardingOrchestrator(self.registry, self.operator, self.provisioning, self.audit, self.schema_applicator)

    def _build_store(self) -> ControlStore:
        """Select the Control-Store backend (controlled non-production; PRD 06 B-7B).

        Default (env unset/empty) is the in-memory adapter — construction performs no I/O.
        ``postgres`` selects the durable Control-DB-backed store (lazy-connect; the audit sink
        is one consumer). Any other value raises (fail closed), mirroring the deferral-lock
        pattern of ``_build_provisioning`` / ``_build_ledger``.
        """
        kind = (os.environ.get(CONTROL_STORE_ENV) or "in_memory").strip().lower()
        if kind in ("", "in_memory"):
            return InMemoryControlStore(schema_version=1)
        if kind == "postgres":
            return self._build_durable_control_store()
        raise ValueError(f"unsupported {CONTROL_STORE_ENV}={kind!r}; expected 'in_memory' or 'postgres'")

    def _build_durable_control_store(self) -> ControlStore:
        """Build the durable PostgreSQL ControlStore (lazy-connect; references only — D-14).

        The Control-DB descriptor is a SECRET REFERENCE: the composition root holds
        ``{store_ref, version}``, never a DSN literal, and never reuses ``SNACKPORTAL_TEST_DSN``.
        Resolution uses a SEPARATE ``EnvReferenceSecretStore`` whose allow-list is widened to
        include the control-store ref ONLY — the default trust-anchor-only secret store
        (``self.secret_store``, used by Bootstrap) is preserved unchanged. The provider import is
        function-local so the composition root binds no database driver at module load (Driver
        Containment Standard). Construction opens no connection (lazy); a missing/unresolvable ref
        or an unreachable Control DB fails closed on the first store operation.
        """
        from .adapters.providers.postgres_store import PostgresControlStore  # function-local (driver containment)

        store_ref = (os.environ.get(CONTROL_STORE_DSN_REF_ENV) or DEFAULT_CONTROL_STORE_DSN_REF).strip()
        ref = SecretRef(store_ref=store_ref, version="1")
        # Widen the allow-list for the control-store ref ONLY (default trust-anchor-only preserved
        # everywhere else). Without this, EnvReferenceSecretStore.resolve() raises PermissionError.
        control_store_secrets = EnvReferenceSecretStore(allowed=frozenset({*DEFAULT_ALLOWED, store_ref}))
        return PostgresControlStore(secrets=control_store_secrets, ref=ref)

    def _build_provisioning(self) -> Tuple[ProvisioningOperator, ProvisioningVerificationService]:
        """Build the D-15 provisioning operator + verification gate (controlled non-prod).

        Default (env unset/empty) is the fully in-memory composition — no I/O on
        construction. Any other adapter value selects controlled-non-prod real-cluster
        adapters, which are delivered in B-4 (live-PostgreSQL exercise), not B-1.
        """
        adapter = (os.environ.get(PROVISIONING_ADAPTER_ENV) or "in_memory").strip().lower()
        if adapter not in ("", "in_memory"):
            raise NotImplementedError(f"provisioning adapter {adapter!r} is delivered in B-4; B-1 supports 'in_memory' only")
        operator: ProvisioningOperator = InMemoryProvisioningOperator()
        supported = [str(v) for v in range(SUPPORTED_SCHEMA_MIN, SUPPORTED_SCHEMA_MAX + 1)]
        provisioning = ProvisioningVerificationService(
            self.store,
            self.audit,
            InMemoryTenantDatabaseProbe(schema_version=str(SUPPORTED_SCHEMA_MAX)),
            InMemoryDistinctnessEvidenceProvider(),
            nonprod_control_db_evidence(),
            ledger=self._build_ledger(),
            supported_schema_versions=supported,
        )
        return operator, provisioning

    def _build_schema_applicator(self) -> TenantSchemaApplicator:
        """Select the tenant schema applicator (controlled non-prod; PRD 07B; D15 Step 2b).

        Default (env unset/empty) is the in-memory applicator — construction performs no I/O and
        applies no DDL. Any other value defers (fail closed): the real PostgreSQL applicator is
        built and live-proven by the PRD 07B requires_pg harness (which composes it directly with a
        tenant-DSN secret store), but composition-level live selection needs the same
        controlled-non-prod wiring as ``_build_provisioning`` (SP2_CP_PROVISIONING_ADAPTER) — that
        is a later phase, so this does not half-wire it against the trust-anchor-only secret store.
        """
        kind = (os.environ.get(TENANT_SCHEMA_APPLICATOR_ENV) or "in_memory").strip().lower()
        if kind in ("", "in_memory"):
            return InMemoryTenantSchemaApplicator()
        raise NotImplementedError(
            f"{TENANT_SCHEMA_APPLICATOR_ENV}={kind!r} (live applicator) is composed directly by the "
            "PRD 07B requires_pg harness; composition-level live wiring is delivered in a later phase"
        )

    def _build_ledger(self) -> DistinctnessLedger:
        """Select the distinctness-evidence ledger (controlled non-prod; PRD 06 B-2).

        Default (env unset/empty) is the in-memory ledger — construction performs no I/O. Any
        other value selects the durable Control-DB-backed ledger, whose live record/read against
        a real Control DB is delivered in B-4 (live-PostgreSQL exercise), not B-2; it defers here
        with NotImplementedError rather than silently falling back. The durable adapter itself is
        lazy-connect (no I/O at construction) and is exercised live only in B-4.
        """
        kind = (os.environ.get(DISTINCTNESS_LEDGER_ENV) or "in_memory").strip().lower()
        if kind not in ("", "in_memory"):
            raise NotImplementedError(f"distinctness ledger {kind!r} is exercised in B-4 (live Control DB); B-2 supports 'in_memory' only")
        return InMemoryDistinctnessLedger()


def liveness() -> Dict[str, str]:
    # Static, non-disclosing liveness (no tenant/database detail).
    return {"service": SERVICE, "status": "alive", "build_phase": "2"}


def create_app() -> ControlPlane:
    return ControlPlane()
