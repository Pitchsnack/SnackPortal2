"""Shared PUBLIC-edge transport posture (FastAPI) — a library, not a component.

``shared/adapters/providers/fastapi_edge.py`` already gives every SnackPortal2 edge its
fail-closed *application* shape (empty-bodied 404/405, no OpenAPI, no slash redirects). That
posture is necessary but not sufficient for an edge a browser can reach. This module adds
exactly the browser-facing half — and nothing else:

* **correlation** — accept a bounded, charset-safe inbound ``x-correlation-id`` or mint a
  fresh opaque one; echo it on every response (anti-spoof, anti-log-injection);
* **raw-target decisions** — every allowlist/matcher decision is made against the undecoded
  request target plus the verbatim query string, so a percent-encoded traversal is judged as
  it arrived rather than after the framework decoded it into something acceptable;
* **query rejection** — no public target accepts a query string (a prohibited tenant carrier
  channel), refused ``404`` pre-handler;
* **request bounds** — request-target bytes, header count, total header bytes, chunked
  transfer refusal, and a per-route body budget the owning edge supplies;
* **exact-origin CORS** — an allowlist of literal origins, never a wildcard, never
  credentialed; a denied or absent ``Origin`` receives no CORS headers at all;
* **``Cache-Control: no-store``** on every response.

**Why this is not a gateway.** It performs no authentication, no authorization, no tenant
derivation, no route classification, no service selection, no response composition, and no
business logic. It cannot: ``shared`` is a dependency leaf, so it can neither import nor name
a service. It is the HTTP-hygiene layer each owning service links into its *own* edge — the
same relationship a web framework has to an application, not the relationship a gateway has
to a backend.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional, Tuple

from fastapi import FastAPI, Request, Response

from shared.adapters.providers.fastapi_edge import empty_response

__all__ = [
    "CORRELATION_HEADER",
    "PublicEdgePolicy",
    "install_public_transport",
    "raw_request_target",
    "write_preflight",
]

CORRELATION_HEADER = "x-correlation-id"

_MAX_CORRELATION_LEN = 128
_SAFE_CORRELATION = re.compile(r"[A-Za-z0-9._\-]+")

_MAX_REQUEST_TARGET_BYTES = 2048  # request-target (path + any query) byte cap
_MAX_HEADER_COUNT = 64  # header-count cap
_MAX_TOTAL_HEADER_BYTES = 16384  # 16 KiB total accepted header bytes


@dataclass(frozen=True)
class PublicEdgePolicy:
    """One public edge's browser-facing policy.

    ``allowed_origins`` is an EXACT-origin allowlist; an empty tuple denies every
    cross-origin request (fail closed — the browser blocks the response). ``body_budget``
    is supplied by the owning edge because only that edge knows which of its own routes
    may carry a body; it returns the maximum accepted ``Content-Length`` in bytes for a
    given ``(raw_target, method)``, and ``0`` for every body-less route.
    """

    allowed_origins: Tuple[str, ...]
    body_budget: Callable[[str, str], int]
    default_cors_methods: str = "GET, OPTIONS"
    default_cors_headers: str = "Authorization, x-correlation-id"


def raw_request_target(request: Request) -> str:
    """The RAW request-target: the undecoded path plus any verbatim ``?query``.

    Load-bearing: a stray ``?query`` must never equal a listed route, and a percent-encoded
    traversal (``%2e%2e``, ``%2F``) must be judged as it arrived.
    """
    raw_path = request.scope.get("raw_path")
    target = raw_path.decode("latin-1") if isinstance(raw_path, bytes) else request.url.path
    query = request.scope.get("query_string") or b""
    if query:
        target += "?" + query.decode("latin-1")
    return target


def _correlation_id(request: Request) -> str:
    """Accept a bounded, safe inbound correlation id; otherwise mint a fresh opaque one."""
    raw = request.headers.get(CORRELATION_HEADER)
    if raw is not None:
        value = raw.strip()
        if 1 <= len(value) <= _MAX_CORRELATION_LEN and _SAFE_CORRELATION.fullmatch(value):
            return value
    return uuid.uuid4().hex


def _bounds_violation(request: Request, target: str, body_budget: int) -> Optional[int]:
    """The pre-handler transport bounds: target, header count/bytes, transfer-encoding, body."""
    if len(target.encode("utf-8")) > _MAX_REQUEST_TARGET_BYTES:
        return 413
    raw_headers = request.scope.get("headers") or []
    if len(raw_headers) > _MAX_HEADER_COUNT:
        return 413
    # Total accepted header bytes, counted on the wire shape ("name: value\r\n" == 4 extra bytes).
    if sum(len(name) + len(value) + 4 for name, value in raw_headers) > _MAX_TOTAL_HEADER_BYTES:
        return 413
    if request.headers.get("Transfer-Encoding"):
        return 413  # chunked/streamed bodies are never accepted (bounded Content-Length only)
    raw_len = request.headers.get("Content-Length")
    if raw_len is not None:
        try:
            length = int(raw_len)
        except ValueError:
            return 400  # malformed transport request
        if length > body_budget:
            return 413  # a body beyond the per-route budget (0 for every body-less route)
    return None


def _write_cors_headers(
    response: Response,
    origin: Optional[str],
    allowed_origins: Tuple[str, ...],
    *,
    preflight: bool,
    cors_methods: str,
    cors_headers: str,
) -> None:
    """Exact-origin allowlist only. A denied or absent origin receives NO CORS headers
    (the browser blocks the response). NEVER a wildcard; NEVER credentialed CORS."""
    if origin is None or origin not in allowed_origins:
        return
    response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Access-Control-Allow-Credentials"] = "false"
    response.headers["Vary"] = "Origin"
    if preflight:
        response.headers["Access-Control-Allow-Methods"] = cors_methods
        response.headers["Access-Control-Allow-Headers"] = cors_headers


def write_preflight(request: Request, cors_methods: str, cors_headers: str) -> Response:
    """A CORS preflight answer: 204, EMPTY body, and no application code reached.

    The allowed methods/headers are stashed for the transport middleware, which emits them
    only when the ``Origin`` is on the exact-origin allowlist.
    """
    request.state.cors_methods = cors_methods
    request.state.cors_headers = cors_headers
    request.state.preflight = True
    return empty_response(204)


def install_public_transport(app: FastAPI, policy: PublicEdgePolicy) -> None:
    """Install the one pre-handler transport gate on a public edge application.

    Every response — including the empty-bodied 404/405 rejections the shared fail-closed
    handlers produce — passes back through this middleware, so correlation echo and the
    exact-origin CORS decision are uniform across the whole surface.
    """

    @app.middleware("http")
    async def _transport(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        correlation_id = _correlation_id(request)
        origin = request.headers.get("Origin")
        target = raw_request_target(request)
        request.state.correlation_id = correlation_id
        request.state.raw_target = target
        request.state.preflight = False
        request.state.cors_methods = policy.default_cors_methods
        request.state.cors_headers = policy.default_cors_headers
        bounds_status = _bounds_violation(request, target, policy.body_budget(target, request.method))
        if bounds_status is not None:
            # Rejected pre-handler; the unread request body is discarded by the ASGI server.
            response = empty_response(bounds_status)
        elif request.scope.get("query_string"):
            # No public target accepts a query string (a prohibited tenant-carrier channel).
            response = empty_response(404)
        else:
            response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers[CORRELATION_HEADER] = correlation_id
        _write_cors_headers(
            response,
            origin,
            policy.allowed_origins,
            preflight=bool(request.state.preflight),
            cors_methods=request.state.cors_methods,
            cors_headers=request.state.cors_headers,
        )
        return response
