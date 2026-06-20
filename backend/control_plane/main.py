"""Control Plane composition root (Build Phase 2).

Wires the control-plane frameworks against the ControlStore port (default in-memory
adapter) and the vendor-neutral env/file SecretStore provider for Bootstrap Phase 0.
No tenant-database access, no routing, no runtime authentication.
"""

from __future__ import annotations

import os
from typing import Dict, Tuple

from shared.adapters.providers.env_reference_secret_store import EnvReferenceSecretStore

from .adapters.providers.in_memory_distinctness import (
    InMemoryDistinctnessEvidenceProvider,
    nonprod_control_db_evidence,
)
from .adapters.providers.in_memory_probe import InMemoryTenantDatabaseProbe
from .adapters.providers.in_memory_store import InMemoryControlStore
from .audit import ControlPlaneAudit
from .bootstrap import BootstrapController
from .directory import GlobalDirectory
from .federation import FederationStore
from .membership import MembershipRegistry
from .onboarding import OnboardingOrchestrator
from .provisioning import (
    InMemoryProvisioningOperator,
    ProvisioningOperator,
    ProvisioningVerificationService,
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


class ControlPlane:
    """Assembled control plane. Construction performs no I/O and no bootstrap."""

    def __init__(self, store: InMemoryControlStore | None = None) -> None:
        self.store = store or InMemoryControlStore(schema_version=1)
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
        self.onboarding = OnboardingOrchestrator(self.registry, self.operator, self.provisioning, self.audit)

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
            supported_schema_versions=supported,
        )
        return operator, provisioning


def liveness() -> Dict[str, str]:
    # Static, non-disclosing liveness (no tenant/database detail).
    return {"service": SERVICE, "status": "alive", "build_phase": "2"}


def create_app() -> ControlPlane:
    return ControlPlane()
