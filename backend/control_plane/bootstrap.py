"""Bootstrap framework — two-phase startup (IC-001 / D-01).

Phase 0: verify the bootstrap system identity against a static trust anchor with
**no database access** and no runtime OIDC/JWT. Phase 1 begins only after the
Control Database is reachable, schema-compatible, and the registry is available;
Phase 0 is closed and break-glass disabled at transition (IC-001 §14).
"""
from __future__ import annotations

import hmac
from enum import Enum

from shared.secrets import SecretRef, SecretStore

from .ports import ControlStore

TRUST_ANCHOR_REF = SecretRef(store_ref="bootstrap/trust-anchor", version="1")


class BootstrapPhase(Enum):
    PHASE_0 = "BootstrapPhase0"
    PHASE_1 = "BootstrapPhase1"


class BootstrapError(Exception):
    """Non-sensitive bootstrap failure."""


class BootstrapController:
    def __init__(self, secret_store: SecretStore) -> None:
        self._secret_store = secret_store
        self._phase = BootstrapPhase.PHASE_0
        self._identity_verified = False
        self._phase0_closed = False
        self._break_glass_enabled = True

    @property
    def phase(self) -> BootstrapPhase:
        return self._phase

    @property
    def phase0_closed(self) -> bool:
        return self._phase0_closed

    @property
    def break_glass_enabled(self) -> bool:
        return self._break_glass_enabled

    def verify_system_identity(self, presented: str) -> bool:
        """Phase-0 STATIC trust-anchor verification.

        Resolves the trust anchor via the SecretStore port (no DB lookup) and
        constant-time compares the presented system identity. This is NOT runtime
        authentication (no OIDC/JWT) — that is Build Phase 3.
        """
        anchor = self._secret_store.resolve(TRUST_ANCHOR_REF)
        ok = hmac.compare_digest(presented, anchor.material)
        self._identity_verified = self._identity_verified or ok
        return ok

    def enter_phase1(self, control_store: ControlStore, *, schema_compatible: bool) -> None:
        """Transition Phase 0 -> Phase 1. Gated; closes Phase 0; disables break-glass."""
        if self._phase is BootstrapPhase.PHASE_1:
            return
        if not self._identity_verified:
            raise BootstrapError("system identity not verified")
        if not control_store.is_reachable():
            raise BootstrapError("Control Database not reachable")
        if not schema_compatible:
            raise BootstrapError("Control-DB schema incompatible")
        # Registry availability == control store reachable (registry resides in the Control DB).
        self._phase0_closed = True
        self._break_glass_enabled = False
        self._phase = BootstrapPhase.PHASE_1
