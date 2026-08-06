"""Internal Gateway->Import-Service initiate transport server (FastAPI/uvicorn) — W1a composed-core.

The Import-Service side of the W1a composed-core import wire. Exposes ONE internal-only surface,
``POST /internal/import/initiate``, which MUST remain internal-only and MUST NEVER be portal-reachable or
registered as a public/frontend ingress (the northbound served ``/import`` is W1b scope, not this slice). It
binds ``127.0.0.1`` by default and serves through the shared uvicorn runtime
(``shared.adapters.providers.asgi_runtime``); the FastAPI app declares exactly the one route and the
OpenAPI/docs surface is disabled, so the closed single-surface posture is unchanged.

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
query-bearing request target is refused ``404`` empty (the pre-migration edge compared the raw request target,
so a stray ``?query`` never matched the path — restored explicitly here); a malformed / wrong-shape /
over-length / secret-shaped request answers ``400 {"version": 1, "result": "INVALID"}``; and ANY engine/audit
exception (including a terminal durable-audit failure — audit-before-hand-back) collapses to
``503 {"version": 1, "result": "UNAVAILABLE"}`` with no leakage. No framework error body is ever emitted.

Uncomposed until env-selected: ``build_import_server`` CONSTRUCTS the server bound to a composed
``ImportService`` and returns it with its base URL; ``serve_import_api`` is the sole blocking runnable
entrypoint (it composes via ``build_import_server_from_env`` in ``import_service/main.py`` and serves on the
calling thread). Carries no database descriptor (the phase-5 containment posture — this edge holds no driver).
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional, Tuple, cast

from fastapi import FastAPI, Request, Response

from import_service.models import ImportMode, ImportRequest, ImportStatus, SourceDescriptor, SourceKind
from import_service.ports import DirectoryReadPort
from import_service.service import ImportService
from shared.adapters.providers.asgi_runtime import AsgiEdgeServer, build_asgi_server
from shared.adapters.providers.fastapi_edge import empty_response, has_query_string, json_response, new_edge_app
from shared.lineage import LineageEmitPort
from shared.session import RoutedSessionProvider

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


def _make_app(service: ImportService) -> FastAPI:
    """Build the FastAPI app exposing EXACTLY the one internal import-initiate surface.

    The app declares one route and one method; every other path is ``404`` and every other method
    ``405``, both with an EMPTY body, decided by the app's fail-closed handlers before the import
    engine is ever reached (``new_edge_app``). Docs/OpenAPI are disabled.
    """
    app = new_edge_app(invalid_status=400, unavailable_status=503)

    @app.post(_INITIATE_PATH)
    async def initiate(http_request: Request) -> Response:
        if has_query_string(http_request):
            return empty_response(404)  # query-bearing target: refused, no import call
        try:
            raw = await http_request.body()
            request = _build_request(raw)
        except Exception:
            # Malformed/invalid request -> fixed 400 INVALID (no detail, no echo).
            return json_response(400, {"version": _ENVELOPE_VERSION, "result": "INVALID"})
        try:
            status = service.start_import(request)
        except Exception:
            # ANY engine/audit failure (incl. terminal durable-audit failure — audit-before-hand-back)
            # collapses to the bounded UNAVAILABLE envelope: no exception text, SQL, source content,
            # topology, or credential state may leak.
            return json_response(503, {"version": _ENVELOPE_VERSION, "result": "UNAVAILABLE"})
        return json_response(200, {"version": _ENVELOPE_VERSION, "outcome": _outcome_json(status)})

    return app


def create_app(service: ImportService) -> FastAPI:
    """The PUBLIC application seam: build the Import edge app over a composed ``ImportService``.

    A thin public alias of ``_make_app`` so a deployment composition root can obtain the composed
    application WITHOUT binding a socket and without reaching into a private name. Both the native
    ASGI application factory and ``build_import_server`` go through this one seam, so the route set,
    the fail-closed handlers, and the disabled docs/OpenAPI surface have a single definition.
    """
    return _make_app(service)


def build_import_server(service: ImportService, host: str = "127.0.0.1", port: int = 0) -> Tuple[AsgiEdgeServer, str]:
    """Construct the internal Import initiate HTTP server bound to a composed ``ImportService``.

    ``port=0`` binds an ephemeral port. This factory constructs the server only — it does NOT start
    serving (the blocking runnable entrypoint is ``serve_import_api``; tests may host the server
    directly via ``serve_forever``/``shutdown``/``server_close``). Returns ``(server, base_url)``.
    """
    return build_asgi_server(create_app(service), host, port)


def serve_import_api(
    *,
    session_provider: Optional[RoutedSessionProvider] = None,
    lineage: Optional[LineageEmitPort] = None,
    directory_read: Optional[DirectoryReadPort] = None,
) -> None:
    """Blocking runnable compatibility entrypoint for the internal Import initiate edge (W1a).

    STARTUP DEFECT CORRECTED (composition only — no Import business, contract, lineage, schema, or
    route change). This function previously called ``build_import_server_from_env()`` with NO
    arguments while that seam REQUIRES the three cross-package collaborator ports whenever it is
    active. The result was a structurally unreachable serving path: ``SP2_IMPORT_HOST`` unset gave
    ``RuntimeError`` (inactive), and ``SP2_IMPORT_HOST`` set gave ``ValueError`` (ports missing) —
    there was no environment in which the serve loop could be reached. The correction is to accept
    the injected ports and FORWARD them to the seam, so the caller that owns those ports (a
    deployment composition root, which alone may import database_router / lineage_service) can
    actually reach the loop.

    ``directory_read`` may be omitted when ``SP2_IMPORT_DIRECTORY_READ_BASE_URL`` selects the
    in-package ``HttpDirectoryRead`` client; the two cross-package ports must always be injected.

    Behaviour once composed is unchanged:

    * inactive composition (``SP2_IMPORT_HOST`` unset/empty) → deterministic ``RuntimeError`` — fail
      closed; no socket was bound and nothing is served;
    * malformed composition config, or a missing required port → ``ValueError`` from the seam
      (inherited, fail closed);
    * active → ``server.serve_forever()`` exactly once on the calling thread (AT-D15T1-10: one server
      per operating-system process; no daemon, subprocess, supervisor, or retry loop is created HERE —
      request concurrency is the ASGI runtime's own event loop), and ``server.server_close()`` ALWAYS
      runs in ``finally`` — ``KeyboardInterrupt`` and any serve-time exception propagate to the caller
      unswallowed.

    The CANONICAL operator startup path is now the native ASGI application factory owned by the
    deployment composition root, which composes the same ports and needs no injected socket.

    No overclaim: this makes the edge RUNNABLE — it does not deploy or supervise it, prove a
    served-request live topology, provision a physical database, activate production, or close any B5
    blocker.
    """
    # Function-local absolute import (the serve_dispatch_api precedent; the adapter stays import-light).
    from import_service.main import build_import_server_from_env

    composed = build_import_server_from_env(
        session_provider=session_provider,
        lineage=lineage,
        directory_read=directory_read,
    )
    if composed is None:
        raise RuntimeError(
            "serve_import_api: import-server composition is INACTIVE — "
            "SP2_IMPORT_HOST is unset/empty (fail closed: no socket bound, nothing served)"
        )
    server_obj, _base_url = composed
    server = cast(AsgiEdgeServer, server_obj)
    try:
        server.serve_forever()
    finally:
        server.server_close()
