"""Shared FastAPI application shape for the SnackPortal2 service edges — vendor-containment zone.

The eight internal transport edges and the northbound gateway edge all share one serving
posture, and it differs from FastAPI's defaults in ways that are contractual rather than
cosmetic (IC-010 §L fail-closed): a refused route, a refused method, or a malformed request
must answer with a FIXED status and an EMPTY body — never FastAPI's default
``{"detail": "Not Found"}`` / ``{"detail": "Method Not Allowed"}`` / the 422 validation
report, each of which discloses routing shape or request structure back to the caller.

``new_edge_app`` returns a FastAPI application with:

* every route-level rejection (404 route-not-exposed, 405 method-not-allowed, and any other
  ``HTTPException``) rendered as a fixed status with an EMPTY body;
* request-validation failures collapsed to a caller-chosen fixed fail-closed status with an
  EMPTY body, so a malformed request never receives a structural error report;
* unhandled server exceptions collapsed to the caller-chosen fail-closed status with an
  EMPTY body — no stack trace, exception text, SQL, topology, credential, or token may
  cross an edge;
* the interactive docs and the OpenAPI schema DISABLED. These are internal, closed-surface,
  contract-governed edges (IC-010 §R Internal-Surface Protection); publishing a machine-
  readable route/shape catalogue at ``/openapi.json`` would widen every edge's exposed
  surface beyond its allowlist and is exactly what the closed route allowlists forbid.

``json_response`` is the single response helper. It serializes with ``json.dumps`` and hands
FastAPI the finished bytes rather than returning a dict, so the wire bytes stay byte-for-byte
what the pre-migration stdlib edges emitted (FastAPI's default ``JSONResponse`` re-encodes
with compact separators and would silently change every envelope on the wire).
"""

from __future__ import annotations

import json
from typing import Any, Dict, Mapping, Optional

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

__all__ = ["empty_response", "json_response", "new_edge_app"]


def empty_response(status: int, headers: Optional[Mapping[str, str]] = None) -> Response:
    """A fixed-status response with an EMPTY body — the only shape for every denial.

    Starlette emits ``content-length: 0`` for empty content, matching the explicit
    ``send_header("Content-Length", "0")`` the stdlib edges wrote on every rejection.
    """
    return Response(status_code=status, content=b"", headers=dict(headers) if headers else None)


def json_response(status: int, body: Dict[str, Any], headers: Optional[Mapping[str, str]] = None) -> Response:
    """A JSON response whose bytes are produced HERE, not by FastAPI's encoder.

    Serialization stays ``json.dumps(body)`` with stdlib defaults so the migrated edges put
    exactly the pre-migration bytes on the wire.
    """
    payload = json.dumps(body).encode("utf-8")
    return Response(status_code=status, content=payload, media_type="application/json", headers=dict(headers) if headers else None)


def new_edge_app(*, invalid_status: int = 400, unavailable_status: int = 503) -> FastAPI:
    """Build a fail-closed FastAPI app for a service edge.

    ``invalid_status`` is the fixed status a request-validation failure collapses to and
    ``unavailable_status`` the status an unhandled server exception collapses to — both with
    an EMPTY body. Docs/OpenAPI are disabled: these are closed, internal, contract-governed
    surfaces, not self-describing public APIs.
    """
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    # LOAD-BEARING: Starlette would otherwise answer an unexposed ``/route/`` (or ``/route``)
    # with a 307 redirect to the exposed spelling. The pre-migration edges compared the exact
    # request target and answered 404, and every route allowlist in this codebase is CLOSED —
    # a redirect would quietly widen each allowlist to a second spelling of every path.
    app.router.redirect_slashes = False

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception(_request: Request, exc: StarletteHTTPException) -> Response:
        # 404 route-not-exposed / 405 method-not-allowed / any other routing rejection:
        # the status is preserved, the detail body is discarded (never echo routing shape).
        return empty_response(exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_request: Request, _exc: RequestValidationError) -> Response:
        # Never return FastAPI's structural validation report — it discloses the expected
        # request shape. Collapse to the edge's own fixed fail-closed status, empty body.
        return empty_response(invalid_status)

    @app.exception_handler(Exception)
    async def _unhandled(_request: Request, _exc: Exception) -> Response:
        # Terminal fail-closed: no stack trace, exception text, SQL, topology, credential
        # state, or token may ever leave an edge.
        return empty_response(unavailable_status)

    return app


def has_query_string(request: Request) -> bool:
    """True when the request target carried a query string.

    The pre-migration edges compared the RAW request target (``self.path``, which includes
    any ``?query``) against their exact path allowlist, so a stray query string could never
    equal a listed route. FastAPI matches on the path alone, so the internal edges restore
    that property by refusing any query-bearing request explicitly.
    """
    return bool(request.url.query)
