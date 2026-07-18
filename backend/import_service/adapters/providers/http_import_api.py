"""Internal Gateway->Import-Service initiate transport server (stdlib http.server) — W1a composed-core.

The Import-Service side of the W1a composed-core import wire. Exposes ONE internal-only surface,
``POST /internal/import/initiate``, which MUST remain internal-only and MUST NEVER be portal-reachable or
registered as a public/frontend ingress (the northbound served ``/import`` is W1b scope, not this slice). It
binds ``127.0.0.1`` by default and runs on a plain single-threaded ``HTTPServer`` (no threading / asyncio /
concurrency machinery here — AT-D15T1-10).

Wire contract. The request envelope is exactly the five references-only initiation keys
``{source_ref, target_tenant_ref, operation_key, correlation_id, actor_ref}`` — references only: no source
payload, credential, token, DSN, or business content ever crosses this edge. The edge builds the exact W1a
``ImportRequest`` (DIRECTORY source by reference; ``directory_kind="startup"``; SYNC; the composed-core
call-site configuration ``natural_key_field="global_startup_id"``, ``target_table="startups"``) and calls
``ImportService.start_import`` — which executes the real, atomic tenant copy + lineage + durable Import Audit.
The response envelope on success is exactly ``{"version": 1, "outcome": {state, replayed, applied_count,
noop_count, import_id}}`` — references only: no tenant row, no source content, no credential, DSN, hostname, or
topology crosses this edge.

Fail closed (IC-010 §L): a wrong path is refused ``404`` empty; a non-POST method is refused ``405`` empty; a
malformed / wrong-shape / over-length / secret-shaped request answers ``400 {"version": 1, "result":
"INVALID"}``; and ANY engine/audit exception (including a terminal durable-audit failure — audit-before-hand-
back) collapses to ``503 {"version": 1, "result": "UNAVAILABLE"}`` with no leakage. No stdlib ``send_error``
HTML body is ever emitted.

Uncomposed until env-selected: ``build_import_server`` CONSTRUCTS the server bound to a composed
``ImportService`` and returns it with its base URL; ``serve_import_api`` is the sole blocking runnable
entrypoint (it composes via ``build_import_server_from_env`` in ``import_service/main.py`` and serves on the
calling thread). Carries no database descriptor (the phase-5 containment posture — this edge holds no driver).
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, Tuple, cast

from import_service.models import ImportMode, ImportRequest, ImportStatus, SourceDescriptor, SourceKind
from import_service.service import ImportService

_INITIATE_PATH = "/internal/import/initiate"
_ENVELOPE_VERSION = 1

_REQUEST_KEYS = frozenset({"source_ref", "target_tenant_ref", "operation_key", "correlation_id", "actor_ref"})

_SECRET_SHAPES = ("eyJ", "-----BEGIN", "AKIA", "ghp_", "xox", "://")
_MAX_REF_LENGTH = 512


class _RequestError(Exception):
    """A malformed/invalid initiation request — mapped fail-closed to 400 INVALID."""


def _required_ref(request: Dict[str, Any], key: str) -> str:
    value = request[key]
    if not isinstance(value, str):
        raise _RequestError("initiation field must be a string")
    if not value or len(value) > _MAX_REF_LENGTH:
        raise _RequestError("initiation field must be a bounded non-empty reference")
    for marker in _SECRET_SHAPES:
        if marker in value:
            raise _RequestError("initiation field carries a secret/token/DSN-shaped value")
    return value


def _build_request(raw: bytes) -> ImportRequest:
    """Strictly validate the references-only initiation envelope and build the exact W1a ImportRequest."""
    try:
        envelope = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise _RequestError("body is not valid JSON") from exc
    if not isinstance(envelope, dict) or set(envelope.keys()) != set(_REQUEST_KEYS):
        raise _RequestError("request keys must be exactly the five initiation fields")
    source_ref = _required_ref(envelope, "source_ref")
    return ImportRequest(
        tenant_id=_required_ref(envelope, "target_tenant_ref"),
        source=SourceDescriptor(kind=SourceKind.DIRECTORY, ref=source_ref, directory_kind="startup"),
        mode=ImportMode.SYNC,
        operation_key=_required_ref(envelope, "operation_key"),
        correlation_id=_required_ref(envelope, "correlation_id"),
        actor_ref=_required_ref(envelope, "actor_ref"),
        natural_key_field="global_startup_id",
        target_table="startups",
    )


def _outcome_json(status: ImportStatus) -> Dict[str, object]:
    """References-only completion projection of an ImportStatus (never the tenant row or source content)."""
    return {
        "state": status.state,
        "replayed": status.replayed,
        "applied_count": status.applied_count,
        "noop_count": status.noop_count,
        "import_id": status.import_id,
    }


def _make_handler(service: ImportService) -> "type[BaseHTTPRequestHandler]":
    class _InitiateHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 (http.server API)
            if self.path != _INITIATE_PATH:
                self._respond_empty(404)  # wrong path: refused, no import call
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length > 0 else b""
                request = _build_request(raw)
            except Exception:
                # Malformed/invalid request -> fixed 400 INVALID (no detail, no echo).
                self._respond_result(400, "INVALID")
                return
            try:
                status = service.start_import(request)
            except Exception:
                # ANY engine/audit failure (incl. terminal durable-audit failure — audit-before-hand-back)
                # collapses to the bounded UNAVAILABLE envelope: no exception text, SQL, source content,
                # topology, or credential state may leak.
                self._respond_result(503, "UNAVAILABLE")
                return
            self._respond_outcome(status)

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

        def _respond_outcome(self, status: ImportStatus) -> None:
            self._write(200, {"version": _ENVELOPE_VERSION, "outcome": _outcome_json(status)})

        def _write(self, status: int, body: Dict[str, object]) -> None:
            payload = json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args: object) -> None:  # silence default stderr logging
            return

    return _InitiateHandler


def build_import_server(service: ImportService, host: str = "127.0.0.1", port: int = 0) -> Tuple[HTTPServer, str]:
    """Construct the internal Import initiate HTTP server bound to a composed ``ImportService``.

    ``port=0`` binds an ephemeral port. This factory constructs the plain single-threaded server only — it
    does NOT start serving (the blocking runnable entrypoint is ``serve_import_api``; tests may host the
    single-threaded server directly). Returns ``(server, base_url)``.
    """
    server = HTTPServer((host, port), _make_handler(service))
    bound_host, bound_port = cast(str, server.server_address[0]), server.server_address[1]
    return server, f"http://{bound_host}:{bound_port}"


def serve_import_api() -> None:
    """Blocking runnable entrypoint for the internal Import initiate edge (W1a).

    Composes the server via the env seam ``build_import_server_from_env`` (``import_service/main.py``) and
    serves it on the CALLING thread:

    * inactive composition (``SP2_IMPORT_HOST`` unset/empty) → deterministic ``RuntimeError`` — fail closed;
      no socket was bound and nothing is served;
    * malformed composition config → ``ValueError`` from the seam (inherited, fail closed);
    * active → ``server.serve_forever()`` exactly once on a single-threaded plain ``HTTPServer`` (AT-D15T1-10:
      one server per operating-system process; no thread, daemon, subprocess, supervisor, or retry loop
      here), and ``server.server_close()`` ALWAYS runs in ``finally`` — ``KeyboardInterrupt`` and any
      serve-time exception propagate to the caller unswallowed.

    No overclaim: this makes the edge RUNNABLE — it does not deploy or supervise it, prove a served-request
    live topology, provision a physical database, activate production, or close any B5 blocker.
    """
    # Function-local absolute import (the serve_dispatch_api precedent; the adapter stays import-light).
    from import_service.main import build_import_server_from_env

    composed = build_import_server_from_env()
    if composed is None:
        raise RuntimeError(
            "serve_import_api: import-server composition is INACTIVE — "
            "SP2_IMPORT_HOST is unset/empty (fail closed: no socket bound, nothing served)"
        )
    server_obj, _base_url = composed
    server = cast(HTTPServer, server_obj)
    try:
        server.serve_forever()
    finally:
        server.server_close()
