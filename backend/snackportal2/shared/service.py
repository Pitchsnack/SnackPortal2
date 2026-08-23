"""The FastAPI application builder every SnackPortal2 service is constructed from.

One builder, so the OpenAPI standing rules (3-day plan §1.2) hold structurally rather than
by fourteen separate acts of discipline: explicit ``title`` / ``version`` / ``docs_url`` /
``redoc_url`` / ``openapi_url``, the canonical error handlers, correlation propagation, and
the minimally-disclosing liveness and readiness routes IC-013 §17 requires of every service.

This is **not** a mandated application factory and **not** a shared uvicorn runtime — both
are explicitly not imposed by IC-013 §21. Each service still defines its own ``app =
FastAPI(...)`` in its own ``main.py`` and starts independently; this builder is a
convenience those modules call, not a runtime they route through.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from fastapi import FastAPI
from pydantic import BaseModel, Field

from .config import ServiceSettings, load_settings
from .correlation import CorrelationMiddleware
from .errors import install_error_handlers


class HealthState(str, Enum):
    """Liveness outcome. Minimally disclosing — the process is up, or it is not."""

    OK = "ok"


class ReadinessState(str, Enum):
    """Readiness outcome (IC-013 §17, D-16).

    ``degraded`` is observability and alerting only: it MUST NOT deny routing to healthy
    tenants. No state name discloses which dependency is unhappy, or how many.
    """

    READY = "ready"
    DEGRADED = "degraded"
    NOT_READY = "not_ready"


class HealthResponse(BaseModel):
    """Liveness disclosure. Three fields, none of them sensitive.

    Prohibited here and in every readiness or version response (IC-013 §17): database
    names, tenant-database details, tenant counts or identities, infrastructure topology,
    secret state, and internal failure reasons.
    """

    status: HealthState = Field(description="Liveness state of this service process.")
    service: str = Field(description="Stable service key, e.g. 'bff'. Not a hostname and not a database name.")
    version: str = Field(description="Backend release version this service was built from.")


class ReadinessResponse(BaseModel):
    """Readiness disclosure — operational status only, never a failure reason."""

    status: ReadinessState = Field(description="Readiness state. Operational status only; never a dependency name or reason.")
    service: str = Field(description="Stable service key, e.g. 'bff'.")
    version: str = Field(description="Backend release version this service was built from.")


def _operation_prefix(service_key: str) -> str:
    """``access_control`` -> ``AccessControl``, for building unique explicit operation ids."""
    return "".join(part.capitalize() for part in service_key.split("_"))


def build_app(
    service_key: str,
    *,
    description: str,
    settings: Optional[ServiceSettings] = None,
) -> FastAPI:
    """Build a service's FastAPI application with the standing OpenAPI rules already met.

    Adds ``GET /health`` and ``GET /readiness``. Both are deliberately **public**: a
    liveness probe that requires a credential cannot serve an orchestrator, and neither
    response discloses anything (IC-013 §17). Every other route on every service declares
    its own security explicitly — there is no blanket "GET is public" rule (§1.2).
    """
    resolved = settings if settings is not None else load_settings(service_key)
    app = FastAPI(
        title=resolved.title,
        version=resolved.version,
        description=description,
        docs_url=resolved.docs_url,
        redoc_url=resolved.redoc_url,
        openapi_url=resolved.openapi_url,
    )
    app.add_middleware(CorrelationMiddleware)
    install_error_handlers(app)

    prefix = _operation_prefix(service_key)
    key = resolved.key
    version = resolved.version

    @app.get(
        "/health",
        response_model=HealthResponse,
        summary="Get service liveness",
        description="Report that this service process is alive. Discloses no dependency, topology, or tenant information.",
        tags=["Health"],
        operation_id="get" + prefix + "Health",
        response_description="The service process is alive.",
    )
    async def health() -> HealthResponse:
        return HealthResponse(status=HealthState.OK, service=key, version=version)

    @app.get(
        "/readiness",
        response_model=ReadinessResponse,
        summary="Get service readiness",
        description="Report whether this service is ready to accept work. Operational status only, never a failure reason.",
        tags=["Health"],
        operation_id="get" + prefix + "Readiness",
        response_description="The service readiness state.",
    )
    async def readiness() -> ReadinessResponse:
        return ReadinessResponse(status=ReadinessState.READY, service=key, version=version)

    return app


__all__ = [
    "HealthResponse",
    "HealthState",
    "ReadinessResponse",
    "ReadinessState",
    "build_app",
]
