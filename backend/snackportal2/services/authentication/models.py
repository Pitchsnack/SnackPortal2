"""Authentication Service wire models (IC-005).

Everything here is references-only. The one credential-bearing field is the credential
being *validated* — never an identity the caller asserts. Per the 3-day plan §10, a value
does not become trustworthy by appearing in a Pydantic request: ``tenant_carrier`` is
accepted, compared, and then discarded, and it is never an authority for anything.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from ...shared.types import PlatformRole


class CarrierCheck(str, Enum):
    """Outcome of the IC-005 carrier-match check (IC-013 §5).

    The check lives here; the *rejection* lives at the BFF, which is also the sole emitter
    of ingress-edge audit (IC-013 §10). Splitting them this way means the BFF cannot deny a
    carrier without a verdict, and this service cannot emit audit it has no business
    emitting.
    """

    ABSENT = "absent"
    MATCHED = "matched"
    MISMATCH = "mismatch"
    CONTROL_ANOMALY = "control_anomaly"


class AuthenticationRequest(BaseModel):
    """Ask the Authentication Service to validate one credential.

    ``tenant_carrier`` is the recognized carrier the BFF observed — the tenant subdomain or
    the ``X-Tenant-Id`` header, and nothing else (IC-013 §5). Cookies, query-string
    parameters, portal state and client local storage are prohibited carriers and never
    reach this field.
    """

    credential: str = Field(
        min_length=1,
        description="The bearer credential to validate. Consumed and never returned, logged, or audited.",
    )
    tenant_carrier: Optional[str] = Field(
        default=None,
        max_length=128,
        description="The recognized tenant carrier observed at the ingress, if any. Compared only; never an authority.",
    )


class AuthenticationResponse(BaseModel):
    """The trusted authenticated identity context (IC-005) — references only.

    Carries no token, secret, credential, name, email, or PII, and no database identifier.
    ``active_tenant_ref`` is the **signed** claim: it is the sole routing authority, and the
    Database Router binds a database from it without re-deriving anything.
    """

    principal_ref: str = Field(description="Opaque reference to the authenticated principal. Never a name or email.")
    role: PlatformRole = Field(description="The platform role carried by the validated credential.")
    active_tenant_ref: Optional[str] = Field(
        default=None,
        description="The signed active-tenant claim, or null for a tenantless CONTROL principal.",
    )
    carrier_check: CarrierCheck = Field(
        description="Verdict of the carrier-match check. The caller MUST reject 'mismatch' with 403 carrier_mismatch."
    )


__all__ = ["AuthenticationRequest", "AuthenticationResponse", "CarrierCheck"]
