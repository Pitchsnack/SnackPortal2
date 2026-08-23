"""Day 1.1 — the shared technical foundation.

These tests police the properties the rest of the rebuild leans on: that the exposure
model is secure by omission (IC-013 §21.1), that the canonical error shape is what the
runtime actually returns (3-day plan §9), that logging cannot carry a payload, and — the
load-bearing one — that ``RequestContext`` can only be built from an ``AuthContext``
(IC-013 §7).
"""

from __future__ import annotations

import inspect
import logging

from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from snackportal2.shared import config, correlation, errors, security, service
from snackportal2.shared.types import PlatformRole, WorkspaceType

# --- Exposure model (IC-013 §21.1) ----------------------------------------------------

def test_every_service_binds_loopback_by_omission() -> None:
    """E-2: ``0.0.0.0`` is never what happens when nobody configures a host."""
    for key in config.SERVICE_REGISTRY:
        settings = config.load_settings(key, env={})
        assert settings.host == config.LOOPBACK, key + " does not default to loopback"


def test_reload_and_serving_knobs_are_secure_by_omission() -> None:
    """E-4 and E-5: reload off, access log off, server header off, proxy headers untrusted."""
    for key in config.SERVICE_REGISTRY:
        settings = config.load_settings(key, env={})
        assert settings.reload is False, key + " defaults reload on"
        assert settings.access_log is False, key + " defaults access logging on"
        assert settings.server_header is False, key + " defaults the server header on"
        assert settings.proxy_headers is False, key + " trusts proxy headers by default"


def test_serving_knobs_remain_environment_configurable() -> None:
    """E-5: these are deployment settings, not architecture invariants — they must be settable.

    A build that hard-coded "access logging is always off" would violate the contract just
    as surely as one that defaulted it on: some regulated environments require access logs.
    """
    settings = config.load_settings(
        "bff",
        env={"SP2_BFF_HOST": "0.0.0.0", "SP2_BFF_PORT": "9100", "SP2_BFF_ACCESS_LOG": "true", "SP2_BFF_PROXY_HEADERS": "1"},
    )
    assert settings.host == "0.0.0.0"
    assert settings.port == 9100
    assert settings.access_log is True
    assert settings.proxy_headers is True


def test_exactly_one_service_is_the_public_ingress_and_it_is_the_bff() -> None:
    """E-1. The registry is the source the deployment-manifest check reads."""
    public = [key for key, svc in config.SERVICE_REGISTRY.items() if svc.public_ingress]
    assert public == ["bff"], "expected exactly the BFF to be a public ingress, found " + repr(public)
    assert config.PUBLIC_INGRESS_SERVICE == "bff"


def test_service_ports_are_unique_and_avoid_the_retired_gateway_range() -> None:
    ports = config.default_ports()
    assert len(set(ports.values())) == len(ports), "duplicate default ports: " + repr(ports)
    for key, port in ports.items():
        assert not 8080 <= port <= 8088, key + " reuses a port from the retired edge range"


# --- RequestContext construction (IC-013 §7) -------------------------------------------

def test_request_context_constructor_accepts_only_an_auth_context() -> None:
    """The signature IS the enforcement: no parameter can carry client-supplied tenancy."""
    signature = inspect.signature(security.RequestContext.from_auth_context)
    parameters = list(signature.parameters)
    assert parameters == ["auth"], "unexpected constructor parameters: " + repr(parameters)
    annotation = signature.parameters["auth"].annotation
    assert "AuthContext" in str(annotation), "constructor does not take an AuthContext: " + str(annotation)


def test_workspace_type_is_derived_from_the_signed_claim() -> None:
    """IC-013 §6: workspace is derived FROM tenant context, never the other way round."""
    tenant = security.RequestContext.from_auth_context(
        security.AuthContext(correlation_id="c", principal_ref="p", role=PlatformRole.TENANT_AGENT, active_tenant_ref="acme")
    )
    assert tenant.tenant_context == "acme"
    assert tenant.workspace_type is WorkspaceType.TENANT_WORKSPACE

    control = security.RequestContext.from_auth_context(
        security.AuthContext(correlation_id="c", principal_ref="p", role=PlatformRole.CONTROL, active_tenant_ref=None)
    )
    assert control.tenant_context is None
    assert control.workspace_type is WorkspaceType.CONTROL_WORKSPACE


def test_request_context_has_exactly_the_canonical_fields() -> None:
    """IC-013 §7 names five fields. A sixth would be a new, ungoverned channel."""
    assert set(security.RequestContext.model_fields) == {
        "correlation_id",
        "principal_ref",
        "role",
        "tenant_context",
        "workspace_type",
    }


# --- Errors: runtime shape == declared shape (§9) ---------------------------------------

class ProbeBody(BaseModel):
    """Module-level on purpose.

    ``from __future__ import annotations`` turns every annotation into a string, and
    FastAPI resolves those against the *module* globals. A model defined inside the
    factory below would be invisible there, and FastAPI would silently reinterpret the
    body parameter as a missing query parameter — a 422 that looks like a validation bug
    but is really a scoping one.
    """

    value: int = Field(description="An integer that must actually be an integer.")


def _probe_app() -> TestClient:
    app = service.build_app("audit", description="probe")

    @app.post(
        "/probe",
        response_model=ProbeBody,
        summary="Echo a value",
        description="Echo the submitted value back.",
        tags=["Probe"],
        operation_id="echoProbeValue",
        response_description="The echoed value.",
        responses=errors.error_responses(403, 422),
    )
    async def echo(body: ProbeBody) -> ProbeBody:
        if body.value == 13:
            raise errors.access_denied()
        if body.value == 99:
            raise RuntimeError("an unexpected internal failure")
        return body

    return TestClient(app, raise_server_exceptions=False)


def test_validation_error_returns_the_declared_shape_not_a_list() -> None:
    """FastAPI's native 422 body is a list of per-field dicts. Ours is the canonical shape."""
    response = _probe_app().post("/probe", json={"value": "not-an-integer"})
    assert response.status_code == 422
    assert response.json() == {"status": 422, "code": "invalid_request"}


def test_application_denial_returns_the_canonical_code() -> None:
    response = _probe_app().post("/probe", json={"value": 13})
    assert response.status_code == 403
    assert response.json() == {"status": 403, "code": "access_denied"}


def test_unhandled_exception_fails_closed_with_no_disclosure() -> None:
    """An unanticipated failure is a bare 500 — never a traceback, never a partial result."""
    response = _probe_app().post("/probe", json={"value": 99})
    assert response.status_code == 500
    assert response.json() == {"status": 500, "code": "internal_error"}
    assert "RuntimeError" not in response.text


def test_unknown_and_unauthorized_tenant_are_byte_identical() -> None:
    """IC-013 §12 / IC-014 §8.3 consistent denial, proven at the byte level."""
    unknown = errors.consistent_tenant_denial().as_response()
    unauthorized = errors.consistent_tenant_denial().as_response()
    assert unknown.body == unauthorized.body
    assert unknown.status_code == unauthorized.status_code == 404


# --- Correlation -------------------------------------------------------------------------

def test_correlation_id_is_echoed_and_client_supplied_values_are_bounded() -> None:
    client = _probe_app()
    supplied = client.post("/probe", json={"value": 1}, headers={"X-Correlation-ID": "abc-123"})
    assert supplied.headers["X-Correlation-ID"] == "abc-123"

    generated = client.post("/probe", json={"value": 1})
    assert generated.headers["X-Correlation-ID"]

    injected = client.post("/probe", json={"value": 1}, headers={"X-Correlation-ID": "a" * 500})
    assert injected.headers["X-Correlation-ID"] != "a" * 500


def test_malformed_correlation_ids_are_replaced_not_reflected() -> None:
    for hostile in ("", "with space", "line\nbreak", "a" * 129, "semi;colon"):
        assert correlation.sanitize_correlation_id(hostile) != hostile


# --- Logging redaction --------------------------------------------------------------------

def test_logging_drops_prohibited_fields_and_non_scalar_values() -> None:
    """Redaction is enforced in the logger, not trusted to call sites."""
    from snackportal2.shared.logging import redact

    redacted = redact(
        {
            "tenant_ref": "acme",
            "record_ref": "r-1",
            "outcome": "denied",
            "authorization": "Bearer xyz",
            "tenant_dsn": "postgresql://u:p@h/db",
            "email": "someone@example.com",
            "access_token": "xyz",
            "row": {"company_name": "Acme"},
        }
    )
    assert redacted == {"tenant_ref": "acme", "record_ref": "r-1", "outcome": "denied"}


def test_log_event_emits_only_permitted_fields() -> None:
    from snackportal2.shared.logging import configure_logging, log_event

    logger = configure_logging("probe")
    records: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = _Capture()
    logger.addHandler(handler)
    try:
        log_event(logger, "route_denied", "probe", tenant_ref="acme", access_token="secret")
    finally:
        logger.removeHandler(handler)

    assert len(records) == 1
    fields = records[0].sp2_fields  # type: ignore[attr-defined]
    assert fields == {"tenant_ref": "acme"}
