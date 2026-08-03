"""Internal Control-Plane Import operational-audit ingest edge (FastAPI/uvicorn) — W1a durable Import Audit.

Exposes ONE internal-only surface, ``POST /internal/import-audit/events``, which MUST remain internal-only
and MUST NEVER be portal-reachable or registered as a public / frontend ingress. It binds ``127.0.0.1`` by
default and serves through the shared uvicorn runtime (``shared.adapters.providers.asgi_runtime``); the
FastAPI app declares exactly the one route and the OpenAPI/docs surface is disabled, so the closed
single-surface posture is unchanged.

Wire contract (W1a). The request envelope is exactly ``{version, event}`` with ``version`` exactly ``1`` and
``event`` exactly the nine approved references-only Import-event keys (``source_service`` / ``id`` /
``recorded_at`` are NEVER wire keys — ``source_service`` is the store-side producer constant
``import_service``, and ``id`` / ``recorded_at`` are DB-assigned). Validation is STRICT and fail closed:
wrong path 404 empty; non-POST 405 empty; anything malformed, mis-keyed, mis-typed, out-of-vocabulary,
over-length, secret/token/DSN-shaped, or carrying a forbidden field name answers
``400 {"version": 1, "result": "INVALID"}``. W1a persists the whole Import-operational-audit class — the five
actions the Import Service emits — with the exact action/outcome combination pinned per action (the
routing-edge combination-rule precedent):

    ImportRequested | ImportStarted | ImportResumed -> outcome == "success"
    ImportCompleted                                 -> outcome in {"success", "replayed"}
    ImportFailed                                    -> outcome == "error:<bounded-suffix>"

Accepted events answer ``200 INSERTED`` / ``200 DUPLICATE_MATCH`` (both success — idempotent replay); a
same-ID/different-payload replay answers ``409 CONFLICT``; any internal store failure collapses to
``503 UNAVAILABLE``. A query-bearing request target is refused ``404`` empty (the pre-migration edge compared
the raw request target, so a stray ``?query`` never matched the path — restored explicitly here). Responses
are the fixed two-key envelope only: no SQL, table detail, Control-DB identity, hostname, topology, exception
text, stack trace, credential state, or stored event content ever crosses this edge, and no framework error
body is ever emitted.

Uncomposed until env-selected: ``build_import_audit_server`` CONSTRUCTS the server bound to an
``ImportAuditStorePort`` and returns it with its base URL — it does not start the request loop, and this
module deliberately has no blocking runnable entrypoint (the composition seam lives in ``control_plane/
main.py``). Tests host it on a loopback port.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Tuple

from fastapi import FastAPI, Request, Response

from control_plane.import_audit import (
    IMPORT_AUDIT_SOURCE_SERVICE,
    ImportAuditConflictError,
    ImportAuditInvalidError,
    ImportAuditRecord,
    ImportAuditStorePort,
)
from shared.adapters.providers.asgi_runtime import AsgiEdgeServer, build_asgi_server
from shared.adapters.providers.fastapi_edge import empty_response, has_query_string, json_response, new_edge_app

_INGEST_PATH = "/internal/import-audit/events"
_ENVELOPE_VERSION = 1
_EVENT_VERSION = 1  # W1a accepts exactly event_version 1 (additive evolution by contract amendment)

_TOP_LEVEL_KEYS = frozenset({"version", "event"})

# Exactly the nine approved references-only Import-event wire keys (all always present on import events).
_EVENT_KEYS = frozenset(
    {
        "audit_id",
        "event_version",
        "occurred_at",
        "correlation_id",
        "action",
        "outcome",
        "actor_ref",
        "target_ref",
        "source_ref",
    }
)

# Defense-in-depth beyond the exact-key-set check: these names are rejected BY NAME so a future allowlist
# edit can never silently admit a store-assigned, producer-constant, or forbidden-data field.
# ``source_service`` is a store-side constant and must never arrive on the wire.
_FORBIDDEN_EVENT_KEYS = frozenset(
    {
        "id",
        "recorded_at",
        "source_service",
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
        "records",
        "record",
        "rows",
        "fields",
        "database",
        "db_name",
        "hostname",
        "topology",
        "connection",
    }
)

# The exact five Import-operational-audit actions, and the pinned action/outcome combination (per action).
_ACTIONS_SUCCESS_ONLY = frozenset({"ImportRequested", "ImportStarted", "ImportResumed"})
_ACTION_COMPLETED = "ImportCompleted"
_COMPLETED_OUTCOMES = frozenset({"success", "replayed"})
_ACTION_FAILED = "ImportFailed"
_ERROR_PREFIX = "error:"
_SUCCESS_OUTCOME = "success"
_ALL_ACTIONS = _ACTIONS_SUCCESS_ONLY | {_ACTION_COMPLETED, _ACTION_FAILED}

# Secret/token/DSN-shaped value markers: any string value containing one is rejected.
_SECRET_SHAPES = ("eyJ", "-----BEGIN", "AKIA", "ghp_", "xox", "://")
_MAX_REF_LENGTH = 512  # uniform reference-field cap


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


def _parse_record(raw: bytes) -> ImportAuditRecord:
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
        raise _IngestValidationError("event keys must be exactly the nine approved fields")

    event_version = event["event_version"]
    if isinstance(event_version, bool) or not isinstance(event_version, int) or event_version != _EVENT_VERSION:
        raise _IngestValidationError("unsupported event_version")

    action = _required_string(event, "action")
    if action not in _ALL_ACTIONS:
        raise _IngestValidationError("unsupported action (not an Import-operational-audit action)")
    outcome = _required_string(event, "outcome")
    _check_action_outcome(action, outcome)

    return ImportAuditRecord(
        audit_id=_required_string(event, "audit_id"),
        event_version=event_version,
        occurred_at=_required_string(event, "occurred_at"),
        correlation_id=_required_string(event, "correlation_id"),
        action=action,
        outcome=outcome,
        source_service=IMPORT_AUDIT_SOURCE_SERVICE,  # store-side producer constant — never from the wire
        actor_ref=_required_string(event, "actor_ref"),
        target_ref=_required_string(event, "target_ref"),
        source_ref=_required_string(event, "source_ref"),
    )


def _check_action_outcome(action: str, outcome: str) -> None:
    """Pin the exact per-action outcome vocabulary (fail closed on any other combination)."""
    if action in _ACTIONS_SUCCESS_ONLY:
        if outcome != _SUCCESS_OUTCOME:
            raise _IngestValidationError("invalid action/outcome combination")
        return
    if action == _ACTION_COMPLETED:
        if outcome not in _COMPLETED_OUTCOMES:
            raise _IngestValidationError("invalid action/outcome combination")
        return
    # _ACTION_FAILED: outcome must be exactly "error:<bounded-suffix>" (suffix non-empty, no whitespace).
    if not outcome.startswith(_ERROR_PREFIX):
        raise _IngestValidationError("invalid action/outcome combination")
    suffix = outcome[len(_ERROR_PREFIX) :]
    if not suffix or any(c.isspace() for c in suffix):
        raise _IngestValidationError("invalid action/outcome combination")


def _result_response(status: int, result: str) -> Response:
    """The fixed two-key result envelope — the ONLY response shape this edge ever emits."""
    return json_response(status, {"version": _ENVELOPE_VERSION, "result": result})


def _make_app(store: ImportAuditStorePort) -> FastAPI:
    """Build the FastAPI app exposing EXACTLY the one internal Import-audit ingest surface.

    The app declares one route and one method; every other path is ``404`` and every other method
    ``405``, both with an EMPTY body, decided by the app's fail-closed handlers before the store is ever
    reached (``new_edge_app``). Docs/OpenAPI are disabled.
    """
    app = new_edge_app(invalid_status=400, unavailable_status=503)

    @app.post(_INGEST_PATH)
    async def ingest(request: Request) -> Response:
        if has_query_string(request):
            return empty_response(404)  # query-bearing target: refused, no store call
        try:
            raw = await request.body()
            record = _parse_record(raw)
        except Exception:
            # Malformed/invalid envelope -> fixed 400 INVALID (no detail, no echo).
            return _result_response(400, "INVALID")
        try:
            result = store.append_import_audit(record)
        except ImportAuditConflictError:
            return _result_response(409, "CONFLICT")
        except ImportAuditInvalidError:
            return _result_response(400, "INVALID")
        except Exception:
            # Internal store failure collapses to a bounded response: no exception text, SQL,
            # topology, or credential state may leak through this edge.
            return _result_response(503, "UNAVAILABLE")
        return _result_response(200, result.value)

    return app


def create_app_from_env() -> FastAPI:
    """The CANONICAL native ASGI application factory for the Import-audit ingest edge.

    Run directly by the operator through the ASGI runtime's own command line::

        uvicorn control_plane.adapters.providers.http_import_audit_api:create_app_from_env --factory ...

    This is what gives the edge a standalone operator startup path for the first time: previously
    it could only be composed as an object by the environment seam, never started on its own.

    Takes NO arguments: the listening host and port belong to the runtime process, not to the
    application, so this factory binds no socket and owns no address. It returns the composed
    ``FastAPI`` app and nothing else.

    ONE composition path (no second composition root): the durable store is built by
    ``control_plane.main.build_import_audit_store_from_env`` — the SAME single
    env-parsing/secret-binding function the compatibility ``build_import_audit_server_from_env``
    seam uses — and the app is built by the SAME ``_make_app``.

    Audit semantics are UNCHANGED by this factory. Residency (the Control Plane remains the sole
    Control-DB writer), the payload rules, the ingest contract, the durability semantics, and the
    fail-closed posture are exactly those of the store and ``_make_app`` it composes; this adds an
    operator startup path only.

    Fail closed (IC-010 §L): a blank effective ``SP2_CP_CONTROL_STORE_DSN_REF`` → ``ValueError``
    at composition. There is deliberately NO fallback to an in-memory sink — a durable audit edge
    must never silently become non-durable. The store is lazy-connect, so an unresolvable
    reference fails closed at first store use, not at import.
    """
    # Function-local absolute import (the established composition-root idiom): the adapter module
    # stays import-light and cycle-free, and importing it performs no composition.
    from control_plane.main import build_import_audit_store_from_env

    return _make_app(build_import_audit_store_from_env())


def build_import_audit_server(store: ImportAuditStorePort, host: str = "127.0.0.1", port: int = 0) -> Tuple[AsgiEdgeServer, str]:
    """Construct the internal Import operational-audit ingest server bound to an ``ImportAuditStorePort``.

    ``port=0`` binds an ephemeral port. This factory CONSTRUCTS the server only — starting and stopping
    the request loop is the caller's responsibility (tests host it on loopback; production composition
    is the ``control_plane/main.py`` seam). Returns ``(server, base_url)``.
    """
    return build_asgi_server(_make_app(store), host, port)
