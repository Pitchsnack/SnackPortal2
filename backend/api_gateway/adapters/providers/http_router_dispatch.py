"""Production ``RouterDispatchPort`` over internal HTTP (stdlib urllib) — D-15-T1b.

The gateway side of the D-15-T1a dispatch wire contract
(docs/d15/D15-DISPATCH-SPEC-01). A transport CLIENT to the Database Router's internal
dispatch endpoint — reached over transport ONLY, never an in-process import of
``database_router`` (IC-010 §H/§M; DAG independence). The gateway never resolves or opens
a database (IC-010 §X).

Serializes exactly the T1a request envelope ``{v, context, category}`` — the five
``RequestContext`` fields plus the ADVISORY category value taken from
``DispatchDecision.category``. Nothing else from ``DispatchDecision`` is serialized: the
gateway-computed ``target_tenant_id``/``domain`` never crosses the wire (the router binds
solely from the signed claim), and ``DispatchDecision`` itself is never serialized.

Validates the response is EXACTLY ``{status, public_code, dispatched}`` with ``public_code``
in the closed 12-code allowlist and the correct primitive types. Because the server mirrors
the envelope status on the HTTP status line, a 4xx/5xx mapped router outcome arrives as an
``HTTPError`` whose body is read and shape-validated before mapping (otherwise a denial such
as ``not_found``/``administratively_disabled`` would be unreachable end-to-end). Every
malformed / wrong-shape / wrong-type / unknown-code / timeout / transport-failure outcome
collapses fail-closed to ``RouteOutcome(503, "unavailable", False)`` (IC-010 §L — no error
path downgrades to a less-isolated outcome or surfaces internal detail). Single attempt,
bounded timeout, no retry loop. References only — no DB handle, DB name, DSN, credential,
topology, body, or payload crosses this boundary.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from api_gateway.models import DispatchDecision, RouteOutcome
from api_gateway.ports import RouterDispatchPort
from shared.context import RequestContext

_DISPATCH_PATH = "/internal/dispatch/route"

# The closed router-denial public_code set (D15-DISPATCH-SPEC-01 §9). A response code
# outside this set collapses fail-closed. The static guard asserts this equals the spec set.
_ALLOWED_PUBLIC_CODES = frozenset(
    {
        "ok",
        "not_found",
        "no_active_tenant",
        "forbidden",
        "administratively_disabled",
        "not_ready",
        "schema_out_of_range",
        "unavailable",
        "tenant_routing_unavailable",
        "control_plane_unavailable",
        "connection_unavailable",
        "routing_isolation_fault",
    }
)

# The single fail-closed outcome for every untrusted/unavailable case (IC-010 §L).
_FAIL_CLOSED = RouteOutcome(status=503, public_code="unavailable", dispatched=False)


class HttpRouterDispatch(RouterDispatchPort):
    def __init__(self, base_url: str, timeout: float = 2.0) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout

    def dispatch(self, context: RequestContext, decision: DispatchDecision) -> RouteOutcome:
        body = json.dumps(
            {
                "v": 1,
                "context": {
                    "correlation_id": context.correlation_id,
                    "request_id": context.request_id,
                    "active_tenant_id": context.active_tenant_id,
                    "principal_ref": context.principal_ref,
                    "role": context.role,
                },
                "category": decision.category.value,  # advisory only; the router never selects on it
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            self._base + _DISPATCH_PATH,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:  # internal router URL
                return self._map(response.read())
        except urllib.error.HTTPError as exc:
            # Mapped router outcome on a mirrored 4xx/5xx status line: read + shape-validate the
            # error body before mapping; a missing/unreadable body collapses fail-closed.
            try:
                raw = exc.read()
            except Exception:
                return _FAIL_CLOSED
            return self._map(raw)
        except Exception:
            # Timeout / connection refused / any transport failure -> fail closed (single attempt).
            return _FAIL_CLOSED

    def _map(self, raw: bytes) -> RouteOutcome:
        try:
            data = json.loads(raw.decode("utf-8"))
        except Exception:
            return _FAIL_CLOSED
        if not isinstance(data, dict) or set(data.keys()) != {"status", "public_code", "dispatched"}:
            return _FAIL_CLOSED
        status = data["status"]
        public_code = data["public_code"]
        dispatched = data["dispatched"]
        if not isinstance(status, int) or isinstance(status, bool):
            return _FAIL_CLOSED
        if not isinstance(public_code, str) or public_code not in _ALLOWED_PUBLIC_CODES:
            return _FAIL_CLOSED
        if not isinstance(dispatched, bool):
            return _FAIL_CLOSED
        return RouteOutcome(status=status, public_code=public_code, dispatched=dispatched)
