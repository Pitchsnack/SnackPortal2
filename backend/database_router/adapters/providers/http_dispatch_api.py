"""Internal Gateway->Database-Router dispatch transport server (stdlib http.server) — D-15-T1b.

The router side of the D-15-T1a dispatch wire contract
(docs/d15/D15-DISPATCH-SPEC-01). Exposes ONE internal-only surface,
``POST /internal/dispatch/route``, which MUST remain internal-only and MUST NEVER be
portal-reachable or registered as a public/frontend ingress (IC-010 §R Internal-Surface
Protection; §M Service Contract). It binds ``127.0.0.1`` by default and runs on a plain
single-threaded ``HTTPServer`` (no threading/asyncio/concurrency machinery here; a
threaded server is 07E-concurrency scope, AT-D15T1-10).

Wire contract. The request envelope is exactly ``{v, context, category}`` where
``context`` is exactly the five ``RequestContext`` fields; ``v`` MUST be ``1``.
``category`` is ADVISORY metadata only and is NEVER a database selector — the router
binds SOLELY from the signed ``RequestContext`` claim (IC-010 §X/§H), so ``category`` is
never handed to ``route()``. ``DispatchDecision`` is never on the wire. A successful
dispatch resolves routing and, for a tenant route, binds and IMMEDIATELY RELEASES exactly
one tenant connection before responding; the live connection stays router-side and is
never serialized. The response envelope is exactly ``{status, public_code, dispatched}`` —
references only: no connection, database name, credential, DSN value, topology, route
reference, body, or business payload crosses the wire.

Fail closed (IC-010 §L — no error path may downgrade to a less-isolated outcome or expose
internal detail): a malformed / wrong-shape / unknown-version / unknown-category request,
and any unhandled server exception, produce a fixed ``503`` with an EMPTY body; a non-POST
method is refused ``405`` empty; a wrong path is refused ``404`` empty; no stdlib
``send_error`` HTML body is ever emitted. This is a routing transport adapter only — it
performs NO business work.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional, Tuple, cast

from database_router.models import RoutingDenied
from database_router.router import DatabaseRouter
from shared.context import RequestContext

_DISPATCH_PATH = "/internal/dispatch/route"

# The four DispatchCategory value strings, copied verbatim from api_gateway/models.py
# (IC-010 §Q). Held as a LOCAL frozenset because database_router must not import
# api_gateway (DAG independence); the static guard asserts this set equals the live enum.
_DISPATCH_CATEGORIES = frozenset({"TENANT_OPERATION", "GLOBAL_DIRECTORY_READ", "MEMBERSHIPS_FOR_PRINCIPAL", "IMPORT_INITIATION"})

_CONTEXT_KEYS = frozenset({"correlation_id", "request_id", "active_tenant_id", "principal_ref", "role"})


class _EnvelopeError(Exception):
    """A malformed/invalid request envelope — mapped fail-closed to a 503 empty body."""


def _optional_str(value: object) -> Optional[str]:
    if value is not None and not isinstance(value, str):
        raise _EnvelopeError("context field must be a string or null")
    return value


def _reconstruct_context(context: object) -> RequestContext:
    if not isinstance(context, dict) or set(context.keys()) != set(_CONTEXT_KEYS):
        raise _EnvelopeError("context keys must be exactly the five RequestContext fields")
    correlation_id = context["correlation_id"]
    if not isinstance(correlation_id, str):  # only correlation_id is always present (non-null)
        raise _EnvelopeError("correlation_id must be a non-null string")
    return RequestContext(
        correlation_id=correlation_id,
        request_id=_optional_str(context["request_id"]),
        active_tenant_id=_optional_str(context["active_tenant_id"]),
        principal_ref=_optional_str(context["principal_ref"]),
        role=_optional_str(context["role"]),
    )


def _decide(router: DatabaseRouter, raw: bytes) -> Tuple[int, str, bool]:
    """Validate the T1a envelope, route from the signed claim, and return the references-only
    ``(status, public_code, dispatched)`` triple. Raises ``_EnvelopeError`` on any invalid
    envelope (mapped to a 503 empty body by the caller). A ``RoutingDenied`` is mapped to its
    canonical ``(http_status, public_code, False)``; a successful route binds and releases any
    tenant connection before returning."""
    try:
        envelope = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise _EnvelopeError("body is not valid JSON") from exc
    if not isinstance(envelope, dict) or set(envelope.keys()) != {"v", "context", "category"}:
        raise _EnvelopeError("request keys must be exactly {v, context, category}")
    if envelope["v"] != 1:
        raise _EnvelopeError("unknown envelope version")
    category = envelope["category"]
    if not isinstance(category, str) or category not in _DISPATCH_CATEGORIES:
        raise _EnvelopeError("unknown dispatch category")
    ctx = _reconstruct_context(envelope["context"])

    # AUTHORITY PIN: the router binds solely from ctx; `category` is advisory only and is
    # never passed to route() (IC-010 §X — category is never a database selector).
    try:
        result = router.route(ctx)
    except RoutingDenied as denied:
        return (denied.http_status, denied.public_code, False)
    # References-only success: release any bound tenant connection before responding; the
    # live connection never leaves the router (CONTROL routes carry no connection).
    router.release(result)
    return (200, "ok", True)


def _make_handler(router: DatabaseRouter) -> "type[BaseHTTPRequestHandler]":
    class _DispatchHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 (http.server API)
            if self.path != _DISPATCH_PATH:
                self._respond_empty(404)  # wrong path: refused, no route call
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length > 0 else b""
                status, public_code, dispatched = _decide(router, raw)
            except Exception:
                # Invalid envelope OR any unhandled server exception -> fixed 503 empty body
                # (no stack trace, topology, database detail, or credential disclosure).
                self._respond_empty(503)
                return
            self._respond_json(status, public_code, dispatched)

        def _method_not_allowed(self) -> None:
            # POST-only edge: every non-POST method is refused 405 with an EMPTY body.
            self._respond_empty(405)

        # Refuse (not serve) other methods without ever reaching the stdlib HTML error path.
        do_GET = do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = _method_not_allowed

        def _respond_empty(self, status: int) -> None:
            self.send_response(status)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def _respond_json(self, status: int, public_code: str, dispatched: bool) -> None:
            payload = json.dumps({"status": status, "public_code": public_code, "dispatched": dispatched}).encode("utf-8")
            self.send_response(status)  # mirror envelope.status on the HTTP status line
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args: object) -> None:  # silence default stderr logging
            return

    return _DispatchHandler


def build_dispatch_server(router: DatabaseRouter, host: str = "127.0.0.1", port: int = 0) -> Tuple[HTTPServer, str]:
    """Build the internal dispatch HTTP server bound to a composed ``DatabaseRouter``.

    ``port=0`` binds an ephemeral port. This factory constructs the server only — it does
    NOT start serving (no runnable ops entrypoint in this slice; the caller/test hosts the
    single-threaded server). Returns ``(server, base_url)``.
    """
    server = HTTPServer((host, port), _make_handler(router))
    bound_host, bound_port = cast(str, server.server_address[0]), server.server_address[1]
    return server, f"http://{bound_host}:{bound_port}"
