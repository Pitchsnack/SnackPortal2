"""Production ``AuthenticatorPort`` over internal HTTP (stdlib urllib) — 07E-3b.

The gateway side of the 07E-3a auth wire contract
(docs/auth/AUTH-TRANSPORT-SPEC-01). A transport CLIENT to the Auth Router's internal
authentication endpoint — reached over transport ONLY, never an in-process import of
``auth_router`` (IC-010 §H/§M; IC-005; DAG independence). The gateway performs NO
JWT/signature/OIDC validation (IC-010 §D; ports.py:20-23), mints no token, resolves no
database, and imports no ``database_router``.

Serializes exactly the spec request envelope ``{v, authorization, recognized_carriers,
correlation_id}`` (Section C) — the bearer credential is sent ONLY here, gateway→router,
for validation; it is never logged and never returned. Nothing else crosses: no
``DispatchDecision``, no routing decision, no DB material.

Validates a 200 body is EXACTLY the references-only ``{correlation_id, principal_ref,
active_tenant_id, role}`` shape (Section D) with the correct primitive types, then returns
an ``AuthResult``. CONTROL is derived by the runtime from ``active_tenant_id is None`` — it
is never a field. A mapped denial arrives on a mirrored 4xx/5xx status line as an
``HTTPError``; the status drives the fail-closed ``RequestRejected`` (Section E):
401→``unauthenticated``, 403 ``carrier_mismatch``→``carrier_mismatch``, 403 other→
``forbidden``, 503→``unavailable``. Every transport error / timeout / malformed / oversized
/ wrong-shape / missing-field / extra-forbidden-key outcome collapses fail-closed to
``unavailable`` (IC-010 §L — no error path downgrades to a less-isolated outcome, defaults a
tenant, or surfaces internal detail). Single attempt, bounded timeout, bounded response
size. No new ``public_code`` beyond ``api_gateway/models.py``.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Optional, Sequence

from api_gateway.models import (
    AuthResult,
    RequestRejected,
    carrier_mismatch,
    forbidden,
    unauthenticated,
    unavailable,
)
from api_gateway.ports import AuthenticatorPort

_AUTH_PATH = "/internal/auth/authenticate"

# The exact references-only success shape (AUTH-TRANSPORT-SPEC-01 §D). A 200 body whose key
# set differs (missing/extra field) collapses fail-closed. The static guard asserts this set.
_SUCCESS_KEYS = frozenset({"correlation_id", "principal_ref", "active_tenant_id", "role"})


def _is_optional_str(value: object) -> bool:
    return value is None or isinstance(value, str)


class HttpAuthenticator(AuthenticatorPort):
    def __init__(self, base_url: str, timeout: float = 2.0, max_response_bytes: int = 64 * 1024) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout
        self._max_bytes = max_response_bytes

    def authenticate(self, authorization: Optional[str], recognized_carriers: Sequence[str], correlation_id: str) -> AuthResult:
        payload = json.dumps(
            {
                "v": 1,
                "authorization": authorization,  # bearer credential, gateway->router only; never logged/returned
                "recognized_carriers": list(recognized_carriers),
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
            # A mapped denial on a mirrored 4xx/5xx status line: the status drives the mapping.
            raise self._map_error(exc) from None
        except RequestRejected:
            raise
        except Exception:
            # Timeout / connection refused / any transport failure -> fail closed (single attempt).
            raise unavailable() from None

    def _map_success(self, raw: bytes) -> AuthResult:
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
        return AuthResult(
            correlation_id=correlation_id,
            principal_ref=principal_ref,
            active_tenant_id=active_tenant_id,
            role=role,
        )

    def _map_error(self, exc: urllib.error.HTTPError) -> RequestRejected:
        status = exc.code
        if status == 401:
            return unauthenticated()
        if status == 403:
            # Only the carrier-mismatch 403 needs the body to disambiguate; every other 403
            # is the consistent forbidden() (no tenant-existence leak, IC-010 §E/§L).
            if self._read_public_code(exc) == "carrier_mismatch":
                return carrier_mismatch()
            return forbidden()
        # 503 and any other/unexpected status -> fail closed (IC-010 §L).
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
