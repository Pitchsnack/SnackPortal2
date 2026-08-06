"""Internal Gateway->Database-Router tenant Startup operations transport server (FastAPI/uvicorn) — D-42 CLM Stage B.

The Database-Router side of the CLM tenant Startup wire (IC-010 CLM section). Exposes TWO
internal-only surfaces, ``POST /internal/tenant/startups/read`` and ``POST
/internal/tenant/startups/update``, which MUST remain internal-only and MUST NEVER be
portal-reachable or registered as a public/frontend ingress (the northbound served
``GET/PATCH /tenant/startups/<startup_ref>`` lives at the API Gateway edge). It binds
``127.0.0.1`` by default and serves through the shared uvicorn runtime
(``shared.adapters.providers.asgi_runtime``); the FastAPI app declares exactly the two routes
and the OpenAPI/docs surface is disabled, so the closed two-surface posture is unchanged.

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
``405`` empty; a query-bearing request target is refused ``404`` empty (the pre-migration edge
compared the raw request target, so a stray ``?query`` never matched a path — restored
explicitly here); a malformed / wrong-shape / over-length / secret-shaped envelope answers
``400 {"version": 1, "result": "INVALID"}``; an unknown ``startup_ref`` within the bound
tenant database answers ``404 {"version": 1, "result": "NOT_FOUND"}`` (the consistent IC-002
not-found semantic; nothing was written); and ANY executor/routing/session exception collapses
to ``503 {"version": 1, "result": "UNAVAILABLE"}`` with no leakage — no partial write can
survive (the executor rolls back). No framework error body is ever emitted.

Uncomposed until env-selected: ``build_tenant_startup_server`` CONSTRUCTS the server bound to
a composed ``TenantStartupOperations`` and returns it with its base URL;
``serve_tenant_startup_api`` is the sole blocking runnable entrypoint (it composes via
``build_tenant_startup_server_from_env`` in ``database_router/main.py`` and serves on the
calling thread). Carries no database descriptor — tenant data is reached only through the
executor's injected routed-session port.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional, Tuple, cast

from fastapi import FastAPI, Request, Response

from database_router.tenant_startup_ops import TenantStartupOperations, TenantStartupRecord
from shared.adapters.providers.asgi_runtime import AsgiEdgeServer, build_asgi_server
from shared.adapters.providers.fastapi_edge import empty_response, has_query_string, json_response, new_edge_app

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


def _result_response(status: int, result: str) -> Response:
    """The fixed two-key result envelope (the only shape for every non-record answer)."""
    return json_response(status, {"version": _ENVELOPE_VERSION, "result": result})


async def _handle(ops: TenantStartupOperations, request: Request, *, is_update: bool) -> Response:
    """The shared read/update body: validate the bounded envelope, then execute exactly one
    routed tenant operation. Both surfaces share this one executor call site."""
    if has_query_string(request):
        return empty_response(404)  # query-bearing target: refused, no executor call
    short_description: Optional[str] = None
    try:
        raw = await request.body()
        if len(raw) > _MAX_BODY_BYTES:
            raise _RequestError("body exceeds the bounded envelope size")
        if is_update:
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
        return _result_response(400, "INVALID")
    try:
        if is_update:
            record = ops.update(short_description=short_description, **arguments)
        else:
            record = ops.read(**arguments)
    except Exception:
        # ANY routing/session/executor failure collapses to the bounded UNAVAILABLE
        # envelope: no exception text, SQL, row content, topology, or credential state
        # may leak; the executor rolled back, so no partial write survives.
        return _result_response(503, "UNAVAILABLE")
    if record is None:
        # Unknown startup_ref within the bound tenant database (IC-002 not-found).
        return _result_response(404, "NOT_FOUND")
    return json_response(200, {"version": _ENVELOPE_VERSION, "record": _record_json(record)})


def _make_app(ops: TenantStartupOperations) -> FastAPI:
    """Build the FastAPI app exposing EXACTLY the two internal tenant Startup surfaces.

    The app declares two routes and one method each; every other path is ``404`` and every
    other method ``405``, both with an EMPTY body, decided by the app's fail-closed handlers
    before the executor is ever reached (``new_edge_app``). Docs/OpenAPI are disabled.
    """
    app = new_edge_app(invalid_status=400, unavailable_status=503)

    @app.post(_READ_PATH)
    async def read(request: Request) -> Response:
        return await _handle(ops, request, is_update=False)

    @app.post(_UPDATE_PATH)
    async def update(request: Request) -> Response:
        return await _handle(ops, request, is_update=True)

    return app


def create_app_from_env() -> FastAPI:
    """The CANONICAL native ASGI application factory for the tenant Startup operations edge.

    Run directly by the operator through the ASGI runtime's own command line::

        uvicorn database_router.adapters.providers.http_tenant_startup_api:create_app_from_env --factory ...

    Takes NO arguments: the listening host and port belong to the runtime process, not to the
    application, so this factory binds no socket and owns no address. It returns the composed
    ``FastAPI`` app and nothing else.

    ONE composition path (no second composition root): the executor is built by
    ``database_router.main.build_tenant_startup_ops_from_env`` — the SAME single
    env-parsing/adapter-wiring function the compatibility ``build_tenant_startup_server_from_env``
    seam uses — and the app is built by the SAME ``_make_app``. The router, the routed session
    provider, and the bounded operations executor therefore have exactly one source of truth.

    Fail closed (IC-010 §L): the operator invoked this process deliberately, so an INACTIVE
    composition is a misconfiguration, not a no-op. ``SP2_DBR_ROUTING_READ_BASE_URL`` unset/empty →
    ``RuntimeError``; a malformed value → ``ValueError`` (inherited). There is deliberately NO
    fallback to an in-memory double: one routed tenant session must always resolve to EXACTLY ONE
    physical tenant database (IC-010 §K/§O; D-07).

    Import-time inertness is preserved: nothing here runs at module import, and the driver-bearing
    provider modules are imported lazily inside the composition function, never at module load.
    """
    # Function-local absolute import (the established composition-root idiom): the adapter module
    # stays import-light and cycle-free, and importing it performs no composition.
    from database_router.main import build_tenant_startup_ops_from_env

    ops = build_tenant_startup_ops_from_env()
    if ops is None:
        raise RuntimeError(
            "create_app_from_env: tenant-startup composition is INACTIVE — "
            "SP2_DBR_ROUTING_READ_BASE_URL is unset/empty (fail closed: no application composed)"
        )
    return _make_app(ops)


def build_tenant_startup_server(ops: TenantStartupOperations, host: str = "127.0.0.1", port: int = 0) -> Tuple[AsgiEdgeServer, str]:
    """Construct the internal tenant Startup operations HTTP server bound to a composed
    ``TenantStartupOperations``.

    ``port=0`` binds an ephemeral port. This factory constructs the server only — it does NOT
    start serving (the blocking runnable entrypoint is ``serve_tenant_startup_api``; tests may
    host the server directly via ``serve_forever``/``shutdown``/``server_close``). Returns
    ``(server, base_url)``.
    """
    return build_asgi_server(_make_app(ops), host, port)


def serve_tenant_startup_api() -> None:
    """Blocking runnable entrypoint for the internal tenant Startup operations edge (D-42 CLM).

    Composes the server via the env seam ``build_tenant_startup_server_from_env``
    (``database_router/main.py``) and serves it on the CALLING thread:

    * inactive composition (the router selector unset/empty) → deterministic ``RuntimeError`` —
      fail closed; no socket was bound and nothing is served;
    * malformed composition config → ``ValueError`` from the seam (inherited, fail closed);
    * active → ``server.serve_forever()`` exactly once on the calling thread (AT-D15T1-10: one
      server per operating-system process; no thread, daemon, subprocess, supervisor, or retry
      loop is created HERE — request concurrency is the ASGI runtime's own event loop), and
      ``server.server_close()`` ALWAYS runs in ``finally`` — ``KeyboardInterrupt`` and any
      serve-time exception propagate to the caller unswallowed.

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
    server = cast(AsgiEdgeServer, server_obj)
    try:
        server.serve_forever()
    finally:
        server.server_close()
