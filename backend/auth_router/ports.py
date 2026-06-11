"""auth_router ports (interfaces). Concrete adapters live under adapters/providers.

- SignatureVerifier: crypto signature check only (production = PyJWT/cryptography;
  test = stdlib HMAC). The validation *policy* stays vendor-neutral in jwt_validation.
- ControlPlaneReadPort: transport read of Phase-2 control-plane data (no in-process
  import of control_plane). Fail-closed semantics are enforced by callers.
- JtiDenylistPort: DEFERRED — interface only; Phase 3 implements no storage.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from .models import FederationView, Role, TenantStateView


class SignatureVerifier(ABC):
    @abstractmethod
    def verify_signature(self, signing_input: bytes, signature: bytes, key: object, alg: str) -> bool: ...


class ControlPlaneReadPort(ABC):
    """Read-only control-plane access over transport. Raises on unavailability
    (callers fail closed — never assume membership/state/role)."""

    @abstractmethod
    def get_federation_for_issuer(self, issuer: str) -> Optional[FederationView]: ...

    @abstractmethod
    def get_tenant_state(self, tenant_id: str) -> Optional[TenantStateView]: ...

    @abstractmethod
    def is_member(self, principal_ref: str, tenant_id: str) -> bool: ...

    @abstractmethod
    def get_role(self, principal_ref: str, tenant_id: str) -> Optional[Role]: ...


class JtiDenylistPort(ABC):
    """DEFERRED (L-4). Bounded, short-lived, control-plane-scoped, never per-tenant,
    not a session store. Phase 3 defines the seam but implements no storage."""

    @abstractmethod
    def is_revoked(self, jti: str) -> bool: ...
