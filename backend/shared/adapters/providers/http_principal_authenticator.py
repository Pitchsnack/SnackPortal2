"""``PrincipalAuthenticatorPort`` over the internal IC-005 authenticate transport (stdlib urllib).

A transport CLIENT to the Auth Router's internal authentication endpoint, speaking exactly
the existing AUTH-TRANSPORT-SPEC-01 wire (``docs/auth/AUTH-TRANSPORT-SPEC-01``) — the same
envelope, the same success shape, and the same status-driven denial mapping the API Gateway's
client used. Nothing about the wire changes when the Gateway is removed; only who calls it.

It lives in ``shared`` because more than one route-owning service now needs to consume
authentication, and duplicating a security-critical client per service is how the two copies
drift. Placement here is lawful and load-bearing: ``shared`` is a dependency leaf under the
import-linter contract, so this module *cannot* import ``auth_router`` (or any other service)
even by accident — it knows only a base URL and a wire envelope, exactly as an HTTP client
should. That is also what keeps it from being a gateway: it forwards no business request and
returns no downstream body, only the four references-only identity fields.

No JWT, JWKS, signature, issuer, OIDC, or crypto handling happens here or in any service that
links it — validation stays inside ``auth_router`` (the deliberate asymmetry the auth-transport
guards pin). The bearer credential is sent on exactly one hop, edge -> Auth Router, for
validation; it is never logged, never stored, and never returned.

Fail closed: every transport error, timeout, malformed / oversized / wrong-shape / missing-field
/ extra-key outcome collapses to 503 ``unavailable``. No error path downgrades to a less
isolated outcome, defaults a tenant, or surfaces internal detail. Single attempt, bounded
timeout, bounded response size.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Optional, Sequence

from shared.public_edge import (
    PrincipalAuthenticatorPort,
    PublicBoundaryDenied,
    TrustedPrincipal,
    carrier_mismatch,
    forbidden,
    unauthenticated,
    unavailable,
)

__all__ = ["HttpPrincipalAuthenticator"]

_AUTH_PATH = "/internal/auth/authenticate"

# The exact references-only success shape (AUTH-TRANSPORT-SPEC-01 §D). A 200 body whose key
# set differs (missing or extra field) collapses fail-closed rather than being read loosely.
_SUCCESS_KEYS = frozenset({"correlation_id", "principal_ref", "active_tenant_id", "role"})


def _is_optional_str(value: object) -> bool:
    return value is None or isinstance(value, str)


class HttpPrincipalAuthenticator(PrincipalAuthenticatorPort):
    """The IC-005 authenticate client. Construction performs no network I/O (lazy)."""

    def __init__(self, base_url: str, timeout: float = 2.0, max_response_bytes: int = 64 * 1024) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout
        self._max_bytes = max_response_bytes

    def authenticate(self, authorization: Optional[str], carriers: Sequence[str], correlation_id: str) -> TrustedPrincipal:
        payload = json.dumps(
            {
                "v": 1,
                "authorization": authorization,  # bearer credential, edge->auth-router only; never logged/returned
                "recognized_carriers": list(carriers),
                "correlation_id": correlation_id,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            self._base + _AUTH_PATH,
            data=payload,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:  # internal auth-router URL
                raw = response.read(self._max_bytes + 1)
                if len(raw) > self._max_bytes:
                    raise unavailable()  # oversized response -> fail closed
                return self._map_success(raw)
        except urllib.error.HTTPError as exc:
            raise self._map_error(exc) from None
        except PublicBoundaryDenied:
            raise
        except Exception:
            # Timeout / connection refused / any transport failure -> fail closed (single attempt).
            raise unavailable() from None

    def _map_success(self, raw: bytes) -> TrustedPrincipal:
        try:
            data = json.loads(raw.decode("utf-8"))
        except Exception:
            raise unavailable() from None
        if not isinstance(data, dict) or set(data.keys()) != _SUCCESS_KEYS:
            raise unavailable()  # missing / extra / wrong-shape success body -> fail closed
        correlation_id = data["correlation_id"]
        principal_ref = data["principal_ref"]
        active_tenant_id = data["active_tenant_id"]
        role = data["role"]
        if not isinstance(correlation_id, str) or not isinstance(principal_ref, str):
            raise unavailable()
        if not _is_optional_str(active_tenant_id) or not _is_optional_str(role):
            raise unavailable()
        # References only — active_tenant_id is None for a tenantless CONTROL principal (derived).
        return TrustedPrincipal(
            correlation_id=correlation_id,
            principal_ref=principal_ref,
            active_tenant_id=active_tenant_id,
            role=role,
        )

    def _map_error(self, exc: urllib.error.HTTPError) -> PublicBoundaryDenied:
        status = exc.code
        if status == 401:
            return unauthenticated()
        if status == 403:
            # Only the carrier-mismatch 403 needs the body to disambiguate; every other 403 is
            # the consistent forbidden() — an unknown tenant and a non-member stay identical.
            if self._read_public_code(exc) == "carrier_mismatch":
                return carrier_mismatch()
            return forbidden()
        # 503 and any other/unexpected status -> fail closed.
        return unavailable()

    def _read_public_code(self, exc: urllib.error.HTTPError) -> Optional[str]:
        try:
            raw = exc.read(self._max_bytes + 1)
        except Exception:
            return None
        if len(raw) > self._max_bytes:
            return None
        try:
            data = json.loads(raw.decode("utf-8"))
        except Exception:
            return None
        if isinstance(data, dict):
            code = data.get("public_code")
            if isinstance(code, str):
                return code
        return None
