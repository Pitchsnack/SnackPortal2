"""Control Plane composition root (Build Phase 2).

Wires the control-plane frameworks against the ControlStore port (default in-memory
adapter) and the vendor-neutral env/file SecretStore provider for Bootstrap Phase 0.
No tenant-database access, no routing, no runtime authentication.
"""

from __future__ import annotations

from typing import Dict

from shared.adapters.providers.env_reference_secret_store import EnvReferenceSecretStore

from .adapters.providers.in_memory_store import InMemoryControlStore
from .audit import ControlPlaneAudit
from .bootstrap import BootstrapController
from .directory import GlobalDirectory
from .federation import FederationStore
from .membership import MembershipRegistry
from .readiness import ReadinessFramework
from .registry import TenantRegistry
from .schema_compat import SchemaCompatibilityChecker

SERVICE = "control_plane"
SUPPORTED_SCHEMA_MIN = 1
SUPPORTED_SCHEMA_MAX = 1


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


def liveness() -> Dict[str, str]:
    # Static, non-disclosing liveness (no tenant/database detail).
    return {"service": SERVICE, "status": "alive", "build_phase": "2"}


def create_app() -> ControlPlane:
    return ControlPlane()
