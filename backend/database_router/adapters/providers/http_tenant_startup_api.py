"""Internal Gateway->Database-Router tenant Startup operations transport server (stdlib http.server) — D-42 CLM Stage B.

The Database-Router side of the CLM tenant Startup wire (IC-010 CLM section). Exposes TWO
internal-only surfaces, ``POST /internal/tenant/startups/read`` and ``POST
/internal/tenant/startups/update``, which MUST remain internal-only and MUST NEVER be
portal-reachable or registered as a public/frontend ingress (the northbound served
``GET/PATCH /tenant/startups/<startup_ref>`` lives at the API Gateway edge). It binds
``127.0.0.1`` by default and runs on a plain single-threaded ``HTTPServer`` (no threading /
asyncio / concurrency machinery here — AT-D15T1-10).

Wire contract. The read envelope is exactly the five references-only keys ``{v, startup_ref,
target_tenant_ref, correlation_id, actor_ref}``; the update envelope adds EXACTLY the one
allowlisted content field ``short_description`` (a UTF-8 string of at most 500 characters,
or null to clear — the SOLE CLM-mutable field). The edge hands references to
``TenantStartupOperations`` (one routed session → EXACTLY ONE physical tenant database) and
answers ``{"version": 1, "record": {record_ref, display_name, short_description,
investment_stage, lineage_reference}}`` — references + the two bounded nullable content
fields only: no tenant row beyond that projection, no credential, DSN, hostname, or topology
ever crosses this edge.

Fail closed (IC-010 §L): a wrong path is refused ``404`` empty; a non-POST method is refused
``405`` empty; a malformed / wrong-shape / over-length / secret-shaped envelope answers
``400 {"version": 1, "result": "INVALID"}``; an unknown ``startup_ref`` within the bound
tenant database answers ``404 {"version": 1, "result": "NOT_FOUND"}`` (the consistent IC-002
not-found semantic; nothing was written); and ANY executor/routing/session exception collapses
to ``503 {"version": 1, "result": "UNAVAILABLE"}`` with no leakage — no partial write can
survive (the executor rolls back). No stdlib ``send_error`` HTML body is ever emitted.

Uncomposed until env-selected: ``build_tenant_startup_server`` CONSTRUCTS the server bound to
a composed ``TenantStartupOperations`` and returns it with its base URL;
``serve_tenant_startup_api`` is the sole blocking runnable entrypoint (it composes via
``build_tenant_startup_server_from_env`` in ``database_router/main.py`` and serves on the
calling thread). Carries no database descriptor — tenant data is reached only through the
executor's injected routed-session port.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, Optional, Tuple, cast

from database_router.tenant_startup_ops import TenantStartupOperations, TenantStartupRecord

_READ_PATH = "/internal/tenant/startups/read"
_UPDATE_PATH = "/internal/tenant/startups/update"
_ENVELOPE_VERSION = 1

_READ_KEYS = frozenset({"v", "startup_ref", "target_tenant_ref", "correlation_id", "actor_ref"})
_UPDATE_KEYS = _READ_KEYS | frozenset({"short_description"})

# Secret/token/DSN shapes are refused in every REFERENCE field. The bounded free-text
# short_description is deliberately scanned against the token/PEM shapes only ("://" is
# lawful inside business free text; a credential or key block never is).
_REF_SECRET_SHAPES = ("eyJ", "-----BEGIN", "AKIA", "ghp_", "xox", "://")
_TEXT_SECRET_SHAPES = ("eyJ", "-----BEGIN", "AKIA", "ghp_", "xox")
_MAX_REF_LENGTH = 512
_MAX_SHORT_DESCRIPTION_CHARS = 500
_MAX_BODY_BYTES = 32768  # bounded internal envelope read (>= the 16384-byte northbound body + envelope)


class _RequestError(Exception):
    """A malformed/invalid tenant Startup envelope — mapped fail-closed to 400 INVALID."""


def _required_ref(envelope: Dict[str, Any], key: str) -> str:
    value = envelope[key]
    if not isinstance(value, str):
        raise _RequestError("envelope field must be a string")
    if not value or len(value) > _MAX_REF_LENGTH:
        raise _RequestError("envelope field must be a bounded non-empty reference")
    for marker in _REF_SECRET_SHAPES:
        if marker in value:
            raise _RequestError("envelope field carries a secret/token/DSN-shaped value")
    return value


def _bounded_short_description(envelope: Dict[str, Any]) -> Optional[str]:
    value = envelope["short_description"]
    if value is None:
        return None
    if not isinstance(value, str):
        raise _RequestError("short_description must be a UTF-8 string or null")
    if len(value) > _MAX_SHORT_DESCRIPTION_CHARS:
        raise _RequestError("short_description exceeds the 500-character bound")
    for marker in _TEXT_SECRET_SHAPES:
        if marker in value:
            raise _RequestError("short_description carries a secret/token-shaped value")
    return value


def _parse_envelope(raw: bytes, keys: frozenset[str]) -> Dict[str, Any]:
    try:
        envelope = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise _RequestError("body is not valid JSON") from exc
    if not isinstance(envelope, dict) or set(envelope.keys()) != set(keys):
        raise _RequestError("envelope keys must be exactly the approved field set")
    version = envelope["v"]
    if isinstance(version, bool) or version != _ENVELOPE_VERSION:
        raise _RequestError("unsupported envelope version")
    return envelope


def _record_json(record: TenantStartupRecord) -> Dict[str, object]:
    """References + bounded-content projection only (never a raw row or extra column)."""
    return {
        "record_ref": record.record_ref,
        "display_name": record.display_name,
        "short_description": record.short_description,
        "investment_stage": record.investment_stage,
        "lineage_reference": record.lineage_reference,
    }


def _make_handler(ops: TenantStartupOperations) -> "type[BaseHTTPRequestHandler]":
    class _TenantStartupHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 (http.server API)
            if self.path not in (_READ_PATH, _UPDATE_PATH):
                self._respond_empty(404)  # wrong path: refused, no executor call
                return
            short_description: Optional[str] = None
            try:
                length = int(self.headers.get("Content-Length") or 0)
                if length < 0 or length > _MAX_BODY_BYTES:
                    raise _RequestError("body exceeds the bounded envelope size")
                raw = self.rfile.read(length) if length > 0 else b""
                if self.path == _UPDATE_PATH:
                    envelope = _parse_envelope(raw, _UPDATE_KEYS)
                    short_description = _bounded_short_description(envelope)
                else:
                    envelope = _parse_envelope(raw, _READ_KEYS)
                arguments = {
                    "tenant_ref": _required_ref(envelope, "target_tenant_ref"),
                    "startup_ref": _required_ref(envelope, "startup_ref"),
                    "correlation_id": _required_ref(envelope, "correlation_id"),
                    "actor_ref": _required_ref(envelope, "actor_ref"),
                }
            except Exception:
                # Malformed/invalid envelope -> fixed 400 INVALID (no detail, no echo).
                self._respond_result(400, "INVALID")
                return
            try:
                if self.path == _UPDATE_PATH:
                    record = ops.update(short_description=short_description, **arguments)
                else:
                    record = ops.read(**arguments)
            except Exception:
                # ANY routing/session/executor failure collapses to the bounded UNAVAILABLE
                # envelope: no exception text, SQL, row content, topology, or credential state
                # may leak; the executor rolled back, so no partial write survives.
                self._respond_result(503, "UNAVAILABLE")
                return
            if record is None:
                # Unknown startup_ref within the bound tenant database (IC-002 not-found).
                self._respond_result(404, "NOT_FOUND")
                return
            self._write(200, {"version": _ENVELOPE_VERSION, "record": _record_json(record)})

        def _method_not_allowed(self) -> None:
            # POST-only edge: every non-POST method is refused 405 with an EMPTY body.
            self._respond_empty(405)

        do_GET = do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = _method_not_allowed

        def _respond_empty(self, status: int) -> None:
            self.send_response(status)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def _respond_result(self, status: int, result: str) -> None:
            self._write(status, {"version": _ENVELOPE_VERSION, "result": result})

        def _write(self, status: int, body: Dict[str, object]) -> None:
            payload = json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args: object) -> None:  # silence default stderr logging
            return

    return _TenantStartupHandler


def build_tenant_startup_server(ops: TenantStartupOperations, host: str = "127.0.0.1", port: int = 0) -> Tuple[HTTPServer, str]:
    """Construct the internal tenant Startup operations HTTP server bound to a composed
    ``TenantStartupOperations``.

    ``port=0`` binds an ephemeral port. This factory constructs the plain single-threaded server
    only — it does NOT start serving (the blocking runnable entrypoint is
    ``serve_tenant_startup_api``; tests may host the single-threaded server directly). Returns
    ``(server, base_url)``.
    """
    server = HTTPServer((host, port), _make_handler(ops))
    bound_host, bound_port = cast(str, server.server_address[0]), server.server_address[1]
    return server, f"http://{bound_host}:{bound_port}"


def serve_tenant_startup_api() -> None:
    """Blocking runnable entrypoint for the internal tenant Startup operations edge (D-42 CLM).

    Composes the server via the env seam ``build_tenant_startup_server_from_env``
    (``database_router/main.py``) and serves it on the CALLING thread:

    * inactive composition (the router selector unset/empty) → deterministic ``RuntimeError`` —
      fail closed; no socket was bound and nothing is served;
    * malformed composition config → ``ValueError`` from the seam (inherited, fail closed);
    * active → ``server.serve_forever()`` exactly once on a single-threaded plain ``HTTPServer``
      (AT-D15T1-10: one server per operating-system process; no thread, daemon, subprocess,
      supervisor, or retry loop here), and ``server.server_close()`` ALWAYS runs in ``finally`` —
      ``KeyboardInterrupt`` and any serve-time exception propagate to the caller unswallowed.

    No overclaim: this makes the edge RUNNABLE — it does not deploy or supervise it, prove a
    served-request live topology, activate production, or close any B5 blocker.
    """
    # Function-local absolute import (the serve_dispatch_api precedent; the adapter stays import-light).
    from database_router.main import build_tenant_startup_server_from_env

    composed = build_tenant_startup_server_from_env()
    if composed is None:
        raise RuntimeError(
            "serve_tenant_startup_api: tenant-startup-server composition is INACTIVE — "
            "SP2_DBR_ROUTING_READ_BASE_URL is unset/empty (fail closed: no socket bound, nothing served)"
        )
    server_obj, _base_url = composed
    server = cast(HTTPServer, server_obj)
    try:
        server.serve_forever()
    finally:
        server.server_close()
