"""Request correlation — ``X-Correlation-ID`` propagation and nothing else.

The correlation id ties one logical request together across the BFF and every service it
calls. It is **purely technical** (3-day plan §Day 1.1): it MUST NOT decide tenant,
permission, database, or ownership, and it is never an identity, an authorization input,
or a routing authority. A client may supply one; supplying one grants nothing.
"""

from __future__ import annotations

import re
import uuid
from contextvars import ContextVar
from typing import Optional

from starlette.types import ASGIApp, Message, Receive, Scope, Send

CORRELATION_HEADER = "X-Correlation-ID"

# A client-supplied correlation id is echoed into logs and forwarded to downstream
# services, so it is bounded and character-restricted before it is ever accepted. An
# unbounded or newline-bearing value would be a log-injection channel.
_SAFE_CORRELATION = re.compile(r"\A[A-Za-z0-9._:-]{1,128}\Z")

_correlation_id: ContextVar[str] = ContextVar("sp2_correlation_id", default="")


def new_correlation_id() -> str:
    """Mint a fresh correlation id."""
    return str(uuid.uuid4())


def sanitize_correlation_id(raw: Optional[str]) -> str:
    """Accept a well-formed client-supplied id, otherwise mint a new one.

    Rejection is silent by design: a malformed correlation id is not a client error worth
    denying a request over, and it must never be reflected back unvalidated.
    """
    if raw is not None and _SAFE_CORRELATION.match(raw):
        return raw
    return new_correlation_id()


def current_correlation_id() -> str:
    """The correlation id bound to the request currently being served."""
    return _correlation_id.get()


class CorrelationMiddleware:
    """Pure-ASGI middleware binding a correlation id and echoing it on the response.

    Written against the raw ASGI interface rather than ``BaseHTTPMiddleware`` so that the
    context variable is set on the same task that runs the endpoint — ``BaseHTTPMiddleware``
    runs the downstream app in a separate task, where a ``ContextVar`` set by the middleware
    is not visible.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming: Optional[str] = None
        wanted = CORRELATION_HEADER.lower().encode("latin-1")
        for key, value in scope.get("headers", []):
            if key.lower() == wanted:
                incoming = value.decode("latin-1", errors="replace")
                break

        correlation_id = sanitize_correlation_id(incoming)
        token = _correlation_id.set(correlation_id)
        header = (CORRELATION_HEADER.encode("latin-1"), correlation_id.encode("latin-1"))

        async def send_with_correlation(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append(header)
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_correlation)
        finally:
            _correlation_id.reset(token)


__all__ = [
    "CORRELATION_HEADER",
    "CorrelationMiddleware",
    "current_correlation_id",
    "new_correlation_id",
    "sanitize_correlation_id",
]
