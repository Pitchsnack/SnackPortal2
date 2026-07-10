"""Internal Gateway->Auth-Router authentication transport server (stdlib http.server) — 07E-3b.

The auth-router side of the 07E-3a auth wire contract
(docs/auth/AUTH-TRANSPORT-SPEC-01). Exposes ONE internal-only surface,
``POST /internal/auth/authenticate``, which MUST remain internal-only and MUST NEVER be
portal-reachable, public, or frontend/Lovable-facing (IC-010 §R Internal-Surface
Protection; §M Service Contract; Section B). It binds ``127.0.0.1`` by default and runs on
a plain single-threaded ``HTTPServer`` (no threading/asyncio/concurrency machinery here;
concurrency hardening is 07E-3c scope). It imports NO ``api_gateway`` and emits NO Database
Router ``RequestContext`` — the gateway builds ``RequestContext`` exclusively from this
response (Section F).

Wire contract. The request envelope is exactly ``{v, authorization, recognized_carriers,
correlation_id}`` where ``v`` MUST be ``1`` (Section C). It bridges the envelope to the
existing in-process ``Authenticator.authenticate(token, *, correlation_id, carrier_tenant,
previous_tenant)`` (auth_router owns validation, Stage 1 + Stage 2, Section F):

* ``authorization`` -> ``token``: accept only ``Bearer <cred>`` (scheme case-insensitive,
  exactly one space); strip the scheme to the raw credential. Missing/empty/non-Bearer/
  malformed -> 401 ``unauthenticated`` WITHOUT calling the authenticator; the credential is
  never logged.
* ``recognized_carriers`` (list) -> ``carrier_tenant`` (single): reduce to the distinct set
  — ``{}`` -> ``None``; one distinct value -> that value; >=2 distinct -> 403
  ``carrier_mismatch`` WITHOUT calling the authenticator (identical duplicates collapse).
* ``previous_tenant`` -> always ``None`` (the tenant-switch path is out of scope here).

The success response is exactly the references-only ``{correlation_id, principal_ref,
active_tenant_id, role}`` shape (Section D) — no token, credential, PII, DB material,
permission matrix, ``DispatchDecision``, or ``RouteOutcome`` ever crosses. CONTROL is
``active_tenant_id is None`` (derived, never a field). An ``AuthDenied`` maps to the
existing public wire semantics by its status (no new ``public_code``): 401 ->
``unauthenticated``; 403 ``carrier_mismatch`` -> ``carrier_mismatch``; 403 other ->
``forbidden``; 503 -> ``unavailable``.

Fail closed (IC-010 §L): a malformed / wrong-shape / unknown-version request envelope and any
unhandled server exception produce a fixed ``503`` with an EMPTY body; a non-POST method is
refused ``405`` empty; a wrong path is refused ``404`` empty; no stdlib ``send_error`` HTML
body is ever emitted; the raw credential never appears in a log, error, or response. This is an
authentication transport adapter only — it opens no database and contacts no Database Router.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict, List, Optional, Tuple, cast

from auth_router.authenticator import Authenticator
from auth_router.models import AuthContext, AuthDenied

_AUTH_PATH = "/internal/auth/authenticate"

_REQUEST_KEYS = frozenset({"v", "authorization", "recognized_carriers", "correlation_id"})


class _EnvelopeError(Exception):
    """A malformed/invalid request envelope — mapped fail-closed to a 503 empty body."""


class _Reject(Exception):
    """A mapped auth denial serialized as ``{status, public_code}`` (references only)."""

    def __init__(self, status: int, public_code: str) -> None:
        super().__init__(public_code)
        self.status = status
        self.public_code = public_code


def _bearer_token(authorization: object) -> Optional[str]:
    """``"Bearer <cred>"`` -> raw credential, else ``None`` (never logs the credential).

    Scheme is case-insensitive and separated by exactly one space; missing/empty/non-Bearer/
    malformed authorization yields ``None`` (the caller maps that to 401 without validating).
    """
    if not isinstance(authorization, str):
        return None
    scheme, sep, rest = authorization.partition(" ")
    if sep != " " or scheme.lower() != "bearer":
        return None
    if not rest or rest.startswith(" "):  # exactly one separating space; non-empty credential
        return None
    return rest


def _reduce_carriers(recognized_carriers: object) -> Optional[str]:
    """Reduce the carrier-asserted tenant values to a single ``carrier_tenant`` (IC-005).

    ``{}`` -> ``None``; one distinct value -> that value; >=2 distinct -> 403 ``carrier_mismatch``
    (raised as ``_Reject`` WITHOUT calling the authenticator — disagreeing carriers cannot all
    match one signed claim). Identical duplicates collapse to one distinct value.
    """
    if not isinstance(recognized_carriers, list):
        raise _EnvelopeError("recognized_carriers must be a list")
    distinct: List[str] = []
    for carrier in recognized_carriers:
        if not isinstance(carrier, str):
            raise _EnvelopeError("recognized_carriers must contain only strings")
        if carrier not in distinct:
            distinct.append(carrier)
    if not distinct:
        return None
    if len(distinct) == 1:
        return distinct[0]
    raise _Reject(403, "carrier_mismatch")


def _map_denied(denied: AuthDenied) -> _Reject:
    """Map an ``AuthDenied`` to the public wire semantics by status (no new public_code).

    401 -> ``unauthenticated``; 403 ``carrier_mismatch`` -> ``carrier_mismatch``; 403 other ->
    ``forbidden``; 503 (and any other) -> ``unavailable``. Granular reasons (unknown_issuer,
    invalid signature, tenant_access_denied, not_ready, ...) never leak past the status bucket.
    """
    status = denied.http_status
    if status == 401:
        return _Reject(401, "unauthenticated")
    if status == 403:
        return _Reject(403, "carrier_mismatch" if denied.public_code == "carrier_mismatch" else "forbidden")
    return _Reject(503, "unavailable")


def _authenticate(authenticator: Authenticator, raw: bytes) -> Tuple[int, Dict[str, object]]:
    """Validate the envelope, bridge it to ``Authenticator.authenticate``, and return the
    references-only ``(200, {4-field success})``. Raises ``_Reject`` for a mapped denial and
    ``_EnvelopeError`` for any invalid envelope (mapped to a 503 empty body by the caller)."""
    try:
        envelope = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise _EnvelopeError("body is not valid JSON") from exc
    if not isinstance(envelope, dict) or set(envelope.keys()) != set(_REQUEST_KEYS):
        raise _EnvelopeError("request keys must be exactly {v, authorization, recognized_carriers, correlation_id}")
    if envelope["v"] != 1:
        raise _EnvelopeError("unknown envelope version")
    correlation_id = envelope["correlation_id"]
    if not isinstance(correlation_id, str) or not correlation_id:
        raise _EnvelopeError("correlation_id must be a non-empty string")

    token = _bearer_token(envelope["authorization"])
    if token is None:
        # Missing/empty/non-Bearer/malformed authorization -> 401 WITHOUT validating.
        raise _Reject(401, "unauthenticated")
    carrier_tenant = _reduce_carriers(envelope["recognized_carriers"])  # may _Reject(403, carrier_mismatch)

    try:
        ctx: AuthContext = authenticator.authenticate(
            token,
            correlation_id=correlation_id,
            carrier_tenant=carrier_tenant,
            previous_tenant=None,  # tenant-switch path is out of scope for this transport
        )
    except AuthDenied as denied:
        raise _map_denied(denied) from None
    # References-only success — CONTROL is derived from active_tenant_id is None (never a field).
    return (
        200,
        {
            "correlation_id": ctx.correlation_id,
            "principal_ref": ctx.principal_ref,
            "active_tenant_id": ctx.active_tenant_id,
            "role": ctx.role,
        },
    )


def _make_handler(authenticator: Authenticator) -> "type[BaseHTTPRequestHandler]":
    class _AuthHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 (http.server API)
            if self.path != _AUTH_PATH:
                self._respond_empty(404)  # wrong path: refused, no validation
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length > 0 else b""
                status, body = _authenticate(authenticator, raw)
            except _Reject as reject:
                # Mapped denial: {status, public_code} on a mirrored status line (references only).
                self._respond_json(reject.status, {"status": reject.status, "public_code": reject.public_code})
                return
            except Exception:
                # Invalid envelope OR any unhandled server exception -> fixed 503 EMPTY body
                # (no stack trace, credential, token, or internal detail disclosure).
                self._respond_empty(503)
                return
            self._respond_json(status, body)

        def _method_not_allowed(self) -> None:
            # POST-only edge: every non-POST method is refused 405 with an EMPTY body.
            self._respond_empty(405)

        # Refuse (not serve) other methods without ever reaching the stdlib HTML error path.
        do_GET = do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = _method_not_allowed

        def _respond_empty(self, status: int) -> None:
            self.send_response(status)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def _respond_json(self, status: int, body: Dict[str, object]) -> None:
            payload = json.dumps(body).encode("utf-8")
            self.send_response(status)  # mirror the mapped status on the HTTP status line
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args: object) -> None:  # silence default stderr logging (no credential leak)
            return

    return _AuthHandler


def build_authenticate_server(authenticator: Authenticator, host: str = "127.0.0.1", port: int = 0) -> Tuple[HTTPServer, str]:
    """Build the internal authenticate HTTP server bound to a composed ``Authenticator``.

    ``port=0`` binds an ephemeral port. This factory constructs the server only — it does NOT
    start serving (the blocking runnable entrypoint is ``serve_authenticate_api``; tests may
    also host the single-threaded server directly). Returns ``(server, base_url)``.
    """
    server = HTTPServer((host, port), _make_handler(authenticator))
    bound_host, bound_port = cast(str, server.server_address[0]), server.server_address[1]
    return server, f"http://{bound_host}:{bound_port}"


def serve_authenticate_api() -> None:
    """Blocking runnable entrypoint for the internal authenticate edge (B5-2).

    Composes the server via the merged env seam ``build_authenticate_server_from_env``
    (``auth_router/main.py``) and serves it on the CALLING thread:

    * inactive composition (``SP2_AR_CONTROL_PLANE_READ_BASE_URL`` unset/empty) → deterministic
      ``RuntimeError`` — fail closed; no socket was bound and nothing is served;
    * malformed composition config → ``ValueError`` from the seam (inherited, fail closed);
    * active → ``server.serve_forever()`` exactly once on a single-threaded plain ``HTTPServer``
      (AT-D15T1-10: one server per operating-system process; no thread, daemon, subprocess,
      supervisor, or retry loop here), and ``server.server_close()`` ALWAYS runs in ``finally`` —
      ``KeyboardInterrupt`` and any serve-time exception propagate to the caller unswallowed.

    Ops: docs/runbooks/b5_service_startup_order.md (the control-plane read edge starts first; its
    URL feeds ``SP2_AR_CONTROL_PLANE_READ_BASE_URL``; this service's URL then feeds
    ``SP2_GW_AUTH_ROUTER_BASE_URL``). No overclaim: this makes the service RUNNABLE — it does not
    deploy or supervise it, prove a served-request live topology, provision a physical database,
    or complete Smoke C / the Physical Multi-Database MVP (B5-BLK-4 stays OPEN).
    """
    # Function-local absolute import mirrors the 07E-1 serve_read_api precedent (composition root
    # imported lazily at call time; the adapter module stays import-light and cycle-free).
    from auth_router.main import build_authenticate_server_from_env

    composed = build_authenticate_server_from_env()
    if composed is None:
        raise RuntimeError(
            "serve_authenticate_api: authenticate-server composition is INACTIVE — "
            "SP2_AR_CONTROL_PLANE_READ_BASE_URL is unset/empty (fail closed: no socket bound, nothing served)"
        )
    server_obj, _base_url = composed
    server = cast(HTTPServer, server_obj)
    try:
        server.serve_forever()
    finally:
        server.server_close()
