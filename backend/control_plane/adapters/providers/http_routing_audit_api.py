"""Internal Control-Plane routing-audit ingest edge (stdlib http.server) — DBR-AR-2B.

Exposes ONE internal-only surface, ``POST /internal/routing-audit/events``, which MUST
remain internal-only and MUST NEVER be portal-reachable or registered as a public /
frontend ingress. It binds ``127.0.0.1`` by default and runs on a plain single-threaded
stdlib HTTP server (no threading / asyncio / concurrency machinery here — AT-D15T1-10).

Wire contract (DBR-AR-2B MC9). The request envelope is exactly ``{version, event}`` with
``version`` exactly ``1`` and ``event`` exactly the seventeen approved references-only
keys (the router event's inherited ``target_ref`` travels as ``tenant_ref``; ``id`` /
``store_id`` / ``recorded_at`` / ``trace_ref`` are NEVER wire keys — ``recorded_at`` is
DB-assigned and ``trace_ref`` is a reserved column only). Validation is STRICT and fail
closed: wrong path 404 empty; non-POST 405 empty; anything malformed, mis-keyed,
mis-typed, out-of-vocabulary, over-length, secret/token/DSN-shaped, or carrying a
forbidden field name answers ``400 {"version": 1, "result": "INVALID"}``. Accepted
events answer ``200 INSERTED`` / ``200 DUPLICATE_MATCH`` (both success — idempotent
replay); a same-ID/different-payload replay answers ``409 CONFLICT``; any internal store
failure collapses to ``503 UNAVAILABLE``. Responses are the fixed two-key envelope only:
no SQL, table detail, Control-DB identity, hostname, topology, exception text, stack
trace, credential state, or stored event content ever crosses this edge, and no stdlib
HTML error body is ever emitted.

Uncomposed in DBR-AR-2B: ``build_routing_audit_server`` CONSTRUCTS the server bound to a
``RoutingAuditStorePort`` and returns it with its base URL — it does not start the
request loop, and this module deliberately has no blocking runnable entrypoint and no
environment seam (DBR-AR-2C owns composition, audit-before-hand-back, and failure
posture). Nothing constructs it in production in 2B; tests host it on a loopback port.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, Optional, Tuple, cast

from control_plane.routing_audit import (
    ROUTING_AUDIT_STORE_ACTIONS,
    RoutingAuditConflictError,
    RoutingAuditInvalidError,
    RoutingAuditRecord,
    RoutingAuditStorePort,
)

_INGEST_PATH = "/internal/routing-audit/events"
_ENVELOPE_VERSION = 1
_EVENT_VERSION = 1  # DBR-AR-2B accepts exactly event_version 1 (additive evolution by contract amendment)

_TOP_LEVEL_KEYS = frozenset({"version", "event"})

_REQUIRED_EVENT_KEYS = frozenset(
    {
        "event_id",
        "event_version",
        "occurred_at",
        "correlation_id",
        "actor_ref",
        "action",
        "outcome",
        "source_service",
        "source_version",
    }
)
_OPTIONAL_EVENT_KEYS = frozenset(
    {
        "request_ref",
        "tenant_ref",
        "resolved_tenant_ref",
        "public_code",
        "error_class",
        "association_store_ref",
        "association_version",
        "lane",
    }
)
# Exactly the seventeen approved wire keys (MC9).
_EVENT_KEYS = _REQUIRED_EVENT_KEYS | _OPTIONAL_EVENT_KEYS

# Defense-in-depth beyond the exact-key-set check: these names are rejected BY NAME so a
# future allowlist edit can never silently admit a store-assigned or forbidden-data field.
_FORBIDDEN_EVENT_KEYS = frozenset(
    {
        "id",
        "store_id",
        "recorded_at",
        "trace_ref",
        "dsn",
        "password",
        "passwd",
        "secret",
        "token",
        "jwt",
        "bearer_token",
        "authorization",
        "request_body",
        "response_body",
        "body",
        "payload",
        "hostname",
        "topology",
        "connection",
    }
)

_ACTIONS = frozenset(ROUTING_AUDIT_STORE_ACTIONS)
# Canonical router-edge public-code vocabulary (contract §3/§7; EC10 — a safe superset:
# no current RouteDenied path emits routing_isolation_fault, but the contract homes it).
_PUBLIC_CODES = frozenset(
    {
        "not_found",
        "no_active_tenant",
        "not_ready",
        "schema_out_of_range",
        "administratively_disabled",
        "unavailable",
        "control_plane_unavailable",
        "connection_unavailable",
        "tenant_routing_unavailable",
        "routing_isolation_fault",
    }
)
_ERROR_CLASSES = frozenset({"secret_resolution", "pool", "connect", "driver"})
_LANES = frozenset({"interactive", "bulk"})
_ANOMALY_OUTCOME = "anomaly:tenant_binding"
_SUCCESS_OUTCOME = "success"

# Secret/token/DSN-shaped value markers (MC9): any string value containing one is rejected.
_SECRET_SHAPES = ("eyJ", "-----BEGIN", "AKIA", "ghp_", "xox", "://")
_MAX_REF_LENGTH = 512  # uniform reference-field cap (MC9)


class _IngestValidationError(Exception):
    """A malformed/invalid ingest envelope — mapped fail-closed to 400 INVALID."""


def _checked_string(value: object) -> str:
    if not isinstance(value, str):
        raise _IngestValidationError("event field must be a string")
    if len(value) > _MAX_REF_LENGTH:
        raise _IngestValidationError("event field exceeds the reference length cap")
    for marker in _SECRET_SHAPES:
        if marker in value:
            raise _IngestValidationError("event field carries a secret/token/DSN-shaped value")
    return value


def _required_string(event: Dict[str, Any], key: str) -> str:
    value = _checked_string(event[key])
    if not value:
        raise _IngestValidationError("required event field must be non-empty")
    return value


def _optional_string(event: Dict[str, Any], key: str) -> Optional[str]:
    value = event[key]
    if value is None:
        return None
    return _checked_string(value)


def _parse_record(raw: bytes) -> RoutingAuditRecord:
    """Strictly validate one wire envelope and translate it to the Control-Plane-local record."""
    try:
        envelope = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise _IngestValidationError("body is not valid JSON") from exc
    if not isinstance(envelope, dict) or set(envelope.keys()) != set(_TOP_LEVEL_KEYS):
        raise _IngestValidationError("request keys must be exactly {version, event}")
    version = envelope["version"]
    if isinstance(version, bool) or version != _ENVELOPE_VERSION:
        raise _IngestValidationError("unsupported envelope version")
    event = envelope["event"]
    if not isinstance(event, dict):
        raise _IngestValidationError("event must be an object")
    present = set(event.keys())
    forbidden = present & _FORBIDDEN_EVENT_KEYS
    if forbidden:
        raise _IngestValidationError("event carries a forbidden field name")
    if present != set(_EVENT_KEYS):
        raise _IngestValidationError("event keys must be exactly the seventeen approved fields")

    event_version = event["event_version"]
    if isinstance(event_version, bool) or not isinstance(event_version, int) or event_version != _EVENT_VERSION:
        raise _IngestValidationError("unsupported event_version")

    action = _required_string(event, "action")
    if action not in _ACTIONS:
        raise _IngestValidationError("unknown action")
    outcome = _required_string(event, "outcome")
    public_code = _optional_string(event, "public_code")
    if action in ("Route", "RouteControl"):
        if outcome != _SUCCESS_OUTCOME or public_code is not None:
            raise _IngestValidationError("invalid action/outcome/public-code combination")
    elif action == "RouteDenied":
        if public_code not in _PUBLIC_CODES or outcome != "denied:" + public_code:
            raise _IngestValidationError("invalid action/outcome/public-code combination")
    else:  # IsolationAnomaly
        if outcome != _ANOMALY_OUTCOME or public_code is not None:
            raise _IngestValidationError("invalid action/outcome/public-code combination")

    error_class = _optional_string(event, "error_class")
    if error_class is not None and (error_class not in _ERROR_CLASSES or public_code != "connection_unavailable"):
        raise _IngestValidationError("invalid error_class")
    lane = _optional_string(event, "lane")
    if lane is not None and lane not in _LANES:
        raise _IngestValidationError("invalid lane")
    source_service = _required_string(event, "source_service")
    if source_service != "database_router":
        raise _IngestValidationError("unknown source_service")

    return RoutingAuditRecord(
        event_id=_required_string(event, "event_id"),
        event_version=event_version,
        occurred_at=_required_string(event, "occurred_at"),
        correlation_id=_required_string(event, "correlation_id"),
        actor_ref=_required_string(event, "actor_ref"),
        action=action,
        outcome=outcome,
        source_service=source_service,
        source_version=_required_string(event, "source_version"),
        request_ref=_optional_string(event, "request_ref"),
        tenant_ref=_optional_string(event, "tenant_ref"),
        resolved_tenant_ref=_optional_string(event, "resolved_tenant_ref"),
        public_code=public_code,
        error_class=error_class,
        association_store_ref=_optional_string(event, "association_store_ref"),
        association_version=_optional_string(event, "association_version"),
        lane=lane,
    )


def _make_handler(store: RoutingAuditStorePort) -> "type[BaseHTTPRequestHandler]":
    class _IngestHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 (http.server API)
            if self.path != _INGEST_PATH:
                self._respond_empty(404)  # wrong path: refused, no store call
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length > 0 else b""
                record = _parse_record(raw)
            except Exception:
                # Malformed/invalid envelope -> fixed 400 INVALID (no detail, no echo).
                self._respond_result(400, "INVALID")
                return
            try:
                result = store.append_routing_audit(record)
            except RoutingAuditConflictError:
                self._respond_result(409, "CONFLICT")
                return
            except RoutingAuditInvalidError:
                self._respond_result(400, "INVALID")
                return
            except Exception:
                # Internal store failure collapses to a bounded response: no exception
                # text, SQL, topology, or credential state may leak through this edge.
                self._respond_result(503, "UNAVAILABLE")
                return
            self._respond_result(200, result.value)

        def _method_not_allowed(self) -> None:
            # POST-only edge: every non-POST method is refused 405 with an EMPTY body.
            self._respond_empty(405)

        # Refuse (not handle) other methods without ever reaching the stdlib HTML error path.
        do_GET = do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = _method_not_allowed

        def _respond_empty(self, status: int) -> None:
            self.send_response(status)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def _respond_result(self, status: int, result: str) -> None:
            payload = json.dumps({"version": _ENVELOPE_VERSION, "result": result}).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args: object) -> None:  # silence default stderr logging
            return

    return _IngestHandler


def build_routing_audit_server(store: RoutingAuditStorePort, host: str = "127.0.0.1", port: int = 0) -> Tuple[HTTPServer, str]:
    """Construct the internal routing-audit ingest server bound to a `RoutingAuditStorePort`.

    ``port=0`` binds an ephemeral port. This factory CONSTRUCTS the plain single-threaded
    server only — starting and stopping the request loop is the caller's responsibility
    (tests host it on loopback; production composition is DBR-AR-2C scope and does not
    exist in 2B). Returns ``(server, base_url)``.
    """
    server = HTTPServer((host, port), _make_handler(store))
    bound_host, bound_port = cast(str, server.server_address[0]), server.server_address[1]
    return server, f"http://{bound_host}:{bound_port}"
