"""Canonical error vocabulary and the one wire error shape.

Two rules govern this module.

**Consistent denial (IC-013 §12, IC-014 §8.3).** Unknown tenant and unauthorized tenant
MUST be indistinguishable to the caller. Denials carry canonical codes only — never tenant
counts, tenant identities, database identifiers, topology, secret state, rule text, or
internal failure reasons.

**Runtime shape == declared shape (3-day plan §9).** Every error a service can return —
including FastAPI's own request-validation failure, which natively returns a *list*-valued
``detail`` — is normalized to :class:`ErrorResponse` by the handlers installed here, so the
declared OpenAPI response schema is never a lie about the runtime body.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Union

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException


class ErrorCode(str, Enum):
    """The closed canonical public denial vocabulary.

    Reuses the existing canonical set (IC-005 401/403; IC-002 not-found / not-ready /
    disabled / unavailable). **No new public denial code is introduced** (IC-014 §8.3).
    ``TENANT_NOT_FOUND`` is deliberately the single answer for *both* "no such tenant" and
    "you may not reach that tenant" — see :func:`consistent_tenant_denial`.
    """

    UNAUTHENTICATED = "unauthenticated"
    CARRIER_MISMATCH = "carrier_mismatch"
    ACCESS_DENIED = "access_denied"
    TENANT_NOT_FOUND = "tenant_not_found"
    TENANT_NOT_READY = "tenant_not_ready"
    TENANT_UNAVAILABLE = "tenant_unavailable"
    ISOLATION_VIOLATION = "isolation_violation"
    INVALID_REQUEST = "invalid_request"
    NOT_FOUND = "not_found"
    INTERNAL_ERROR = "internal_error"


class ErrorResponse(BaseModel):
    """The single error body every SnackPortal2 service returns.

    Deliberately two fields. Anything richer becomes a disclosure channel: a message that
    varies with the cause tells a prober which of "unknown" and "forbidden" happened.
    """

    status: int = Field(description="The HTTP status code carried by this denial.")
    code: ErrorCode = Field(description="The canonical public denial code. Never a reason, rule, or internal detail.")


class AppError(Exception):
    """A fail-closed application denial carrying exactly a status and a canonical code."""

    def __init__(self, status: int, code: ErrorCode) -> None:
        super().__init__(code.value)
        self.status = status
        self.code = code

    def as_response(self) -> JSONResponse:
        """Render this denial as the one approved wire shape."""
        return JSONResponse(status_code=self.status, content={"status": self.status, "code": self.code.value})


def unauthenticated() -> AppError:
    """401 — no principal was established (IC-013 §12)."""
    return AppError(401, ErrorCode.UNAUTHENTICATED)


def carrier_mismatch() -> AppError:
    """403 — a recognized tenant carrier disagreed with the signed claim (IC-013 §5)."""
    return AppError(403, ErrorCode.CARRIER_MISMATCH)


def access_denied() -> AppError:
    """403 — the Access Control Service returned Denied (IC-014 §8.1)."""
    return AppError(403, ErrorCode.ACCESS_DENIED)


def isolation_violation() -> AppError:
    """403 — the request would straddle databases or span tenants (IC-013 §11)."""
    return AppError(403, ErrorCode.ISOLATION_VIOLATION)


def consistent_tenant_denial() -> AppError:
    """404 — the mandated indistinguishable answer for unknown *and* unauthorized tenants.

    IC-013 §12 and IC-014 §8.3 both require that a caller cannot learn whether a tenant
    exists. Every call site that could otherwise answer "no such tenant" or "not your
    tenant" routes through this one function so the two can never drift apart.
    """
    return AppError(404, ErrorCode.TENANT_NOT_FOUND)


def tenant_not_ready() -> AppError:
    """409 — the tenant is reachable by this principal but is not ACTIVE (IC-002)."""
    return AppError(409, ErrorCode.TENANT_NOT_READY)


def tenant_unavailable() -> AppError:
    """503 — the tenant database is unreachable. Never a Control-DB fallback (IC-013 §11)."""
    return AppError(503, ErrorCode.TENANT_UNAVAILABLE)


def invalid_request() -> AppError:
    """422 — the request body or parameters failed contract validation."""
    return AppError(422, ErrorCode.INVALID_REQUEST)


def not_found() -> AppError:
    """404 — the addressed record does not exist within the single resolved domain."""
    return AppError(404, ErrorCode.NOT_FOUND)


_DESCRIBED: Dict[int, str] = {
    400: "The request was malformed.",
    401: "No authenticated principal was established.",
    403: "The principal is not permitted to perform this operation.",
    404: "The addressed record or tenant is not available to this principal.",
    409: "The tenant is not in a state that permits this operation.",
    422: "The request failed contract validation.",
    500: "The service failed to complete the operation.",
    503: "A required downstream resource is unavailable. No fallback is performed.",
}


def error_responses(*statuses: int) -> Dict[Union[int, str], Dict[str, Any]]:
    """Build the ``responses=`` map declaring :class:`ErrorResponse` for each status.

    Every declared application error gets a status code, a description, and a response
    schema (3-day plan §1.2). Routes pass the statuses they can actually produce.
    """
    out: Dict[Union[int, str], Dict[str, Any]] = {}
    for status in statuses:
        out[status] = {"model": ErrorResponse, "description": _DESCRIBED.get(status, "The request was denied.")}
    return out


# Status -> canonical code for framework-raised HTTP errors (404 route miss, 405, ...).
_STATUS_CODES: Dict[int, ErrorCode] = {
    400: ErrorCode.INVALID_REQUEST,
    401: ErrorCode.UNAUTHENTICATED,
    403: ErrorCode.ACCESS_DENIED,
    404: ErrorCode.NOT_FOUND,
    405: ErrorCode.INVALID_REQUEST,
    409: ErrorCode.TENANT_NOT_READY,
    422: ErrorCode.INVALID_REQUEST,
    503: ErrorCode.TENANT_UNAVAILABLE,
}


def install_error_handlers(app: FastAPI) -> None:
    """Normalize every error path to :class:`ErrorResponse`.

    The ``Exception`` handler is what makes "fail closed" true rather than aspirational:
    an unanticipated failure becomes a bare 500 ``internal_error`` with no traceback, no
    exception text, and no partial result — never a 200 with a degraded body.
    """

    @app.exception_handler(AppError)
    async def _app_error(_request: Request, exc: AppError) -> JSONResponse:
        return exc.as_response()

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_request: Request, _exc: RequestValidationError) -> JSONResponse:
        # FastAPI's native body is a list of per-field dicts echoing the submitted input.
        # That both contradicts the declared schema and echoes client input back, so it is
        # replaced wholesale by the canonical shape.
        return invalid_request().as_response()

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _STATUS_CODES.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
        return JSONResponse(status_code=exc.status_code, content={"status": exc.status_code, "code": code.value})

    @app.exception_handler(Exception)
    async def _unhandled(_request: Request, _exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=500, content={"status": 500, "code": ErrorCode.INTERNAL_ERROR.value})


__all__ = [
    "AppError",
    "ErrorCode",
    "ErrorResponse",
    "access_denied",
    "carrier_mismatch",
    "consistent_tenant_denial",
    "error_responses",
    "install_error_handlers",
    "invalid_request",
    "isolation_violation",
    "not_found",
    "tenant_not_ready",
    "tenant_unavailable",
    "unauthenticated",
]
