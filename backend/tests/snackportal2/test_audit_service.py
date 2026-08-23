"""Day 1.7 — Audit Service.

The properties that matter here are the ones that make an audit trail worth having: the
emitter cannot name itself, the reader cannot read past its scope, delegation is per-target
rather than blanket, and no record can carry a payload.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from snackportal2.services.audit import main as audit_main
from snackportal2.services.audit.identity import CredentialDirectory, build_credential_directory
from snackportal2.services.audit.models import DENIAL_ANOMALY_ACTIONS, SHARING_ACTIONS, AuditAction, AuditEventSubmission
from snackportal2.services.audit.sink import AUDIT_TABLE, InMemoryAuditSink

from ._openapi_rules import assert_document

_CREDENTIALS = json.dumps(
    {
        "bff-key": {"emitter_ref": "bff", "scopes": ["audit:write"]},
        "reader-key": {"emitter_ref": "bff", "scopes": ["audit:read"]},
        "auditor-key": {"emitter_ref": "auditor", "scopes": ["audit:read:all"]},
        "delegate-key": {
            "emitter_ref": "support",
            "scopes": ["audit:read", "audit:delegate"],
            "delegable_targets": ["p-agent"],
        },
    }
)


def _client() -> TestClient:
    audit_main._credentials = CredentialDirectory.from_json(_CREDENTIALS)  # type: ignore[attr-defined]
    audit_main._sink = InMemoryAuditSink()  # type: ignore[attr-defined]
    return TestClient(audit_main.app, raise_server_exceptions=False)


def _submission(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "action": "RouteDenied",
        "outcome": "denied",
        "correlation_id": "c-1",
        "actor_ref": "p-agent",
        "tenant_ref": "acme",
    }
    payload.update(overrides)
    return payload


# --- The audit vocabulary (IC-013 §10) ----------------------------------------------------

def test_the_four_denial_and_anomaly_classes_are_exactly_the_historic_set() -> None:
    """None added, none removed, none renamed. Only the emitter moved."""
    assert {action.value for action in DENIAL_ANOMALY_ACTIONS} == {
        "CarrierMismatch",
        "CarrierOnControlAnomaly",
        "RouteDenied",
        "IsolationAnomaly",
    }


def test_the_sharing_subclass_is_authored_but_inert() -> None:
    """IC-013 §18: present in the vocabulary, emitted by nothing until IC-007 is Final."""
    assert len(SHARING_ACTIONS) == 9
    assert AuditAction.FORWARD_ATTEMPT_DENIED in SHARING_ACTIONS


def test_an_audit_submission_cannot_carry_a_payload_field() -> None:
    """References only: there is no field through which business content could arrive."""
    assert set(AuditEventSubmission.model_fields) == {
        "action",
        "outcome",
        "correlation_id",
        "actor_ref",
        "subject_ref",
        "tenant_ref",
        "record_ref",
        "carrier_ref",
    }


# --- Server-derived identity (3-day plan §10) ------------------------------------------------

def test_the_emitter_cannot_name_itself() -> None:
    """``source_service`` comes from the credential, and there is no field to override it."""
    assert "source_service" not in AuditEventSubmission.model_fields
    assert "event_id" not in AuditEventSubmission.model_fields
    assert "occurred_at" not in AuditEventSubmission.model_fields

    client = _client()
    written = client.post("/audit/events", headers={"Authorization": "Bearer bff-key"}, json=_submission())
    assert written.status_code == 201

    read = client.get("/audit/events", headers={"Authorization": "Bearer auditor-key"})
    event = read.json()["events"][0]
    assert event["source_service"] == "bff"
    assert event["event_id"]
    assert event["occurred_at"].endswith("+00:00")


def test_an_attempt_to_submit_server_derived_fields_is_ignored_not_honoured() -> None:
    client = _client()
    client.post(
        "/audit/events",
        headers={"Authorization": "Bearer bff-key"},
        json=_submission(source_service="control_plane", event_id="forged", occurred_at="1999-01-01T00:00:00+00:00"),
    )
    event = client.get("/audit/events", headers={"Authorization": "Bearer auditor-key"}).json()["events"][0]
    assert event["source_service"] == "bff"
    assert event["event_id"] != "forged"
    assert not event["occurred_at"].startswith("1999")


def test_an_unconfigured_service_accepts_nothing() -> None:
    directory = build_credential_directory(env={})
    assert directory.resolve("any-key") is None


def test_an_unknown_credential_is_a_canonical_401() -> None:
    response = _client().post("/audit/events", headers={"Authorization": "Bearer nope"}, json=_submission())
    assert response.status_code == 401
    assert response.json() == {"status": 401, "code": "unauthenticated"}


def test_a_read_only_credential_cannot_write() -> None:
    response = _client().post("/audit/events", headers={"Authorization": "Bearer reader-key"}, json=_submission())
    assert response.status_code == 403
    assert response.json() == {"status": 403, "code": "access_denied"}


def test_a_write_only_credential_cannot_read() -> None:
    response = _client().get("/audit/events", headers={"Authorization": "Bearer bff-key"})
    assert response.status_code == 403


def test_an_unknown_scope_fails_at_configuration_time() -> None:
    """A silently-ignored scope looks exactly like a granted one that does nothing."""
    try:
        CredentialDirectory.from_json(json.dumps({"k": {"emitter_ref": "x", "scopes": ["audit:everything"]}}))
    except ValueError:
        return
    raise AssertionError("an unknown audit scope was accepted")


# --- Read scoping and scoped delegation --------------------------------------------------------

def test_read_all_sees_every_event_and_plain_read_sees_only_its_own() -> None:
    client = _client()
    client.post("/audit/events", headers={"Authorization": "Bearer bff-key"}, json=_submission(actor_ref="p-agent"))
    client.post("/audit/events", headers={"Authorization": "Bearer bff-key"}, json=_submission(actor_ref="p-other"))

    everything = client.get("/audit/events", headers={"Authorization": "Bearer auditor-key"}).json()
    assert everything["scope"] == "audit:read:all"
    assert len(everything["events"]) == 2

    scoped = client.get("/audit/events", headers={"Authorization": "Bearer reader-key"}).json()
    assert scoped["scope"] == "audit:read"
    assert [event["actor_ref"] for event in scoped["events"]] == []


def test_delegation_is_per_target_not_blanket() -> None:
    """A broad delegation scope is never authority to impersonate every principal."""
    client = _client()
    client.post("/audit/events", headers={"Authorization": "Bearer bff-key"}, json=_submission(actor_ref="p-agent"))
    client.post("/audit/events", headers={"Authorization": "Bearer bff-key"}, json=_submission(actor_ref="p-stranger"))

    permitted = client.get("/audit/events?on_behalf_of=p-agent", headers={"Authorization": "Bearer delegate-key"})
    assert permitted.status_code == 200
    assert permitted.json()["scope"] == "delegated:p-agent"
    assert [event["actor_ref"] for event in permitted.json()["events"]] == ["p-agent"]

    refused = client.get("/audit/events?on_behalf_of=p-stranger", headers={"Authorization": "Bearer delegate-key"})
    assert refused.status_code == 403


def test_delegation_requires_the_scope_as_well_as_the_target() -> None:
    client = _client()
    response = client.get("/audit/events?on_behalf_of=p-agent", headers={"Authorization": "Bearer auditor-key"})
    assert response.status_code == 403, "read:all was treated as delegation authority"


# --- Sink -------------------------------------------------------------------------------------

def test_the_durable_sink_targets_the_new_table_not_the_retired_gateway_one() -> None:
    """DDL 012 pins CHECK (source_service = 'api_gateway'), which rejects a BFF row outright."""
    assert AUDIT_TABLE == "control_ingress_audit"
    assert AUDIT_TABLE != "control_gateway_audit"


def test_migration_m1_exists_and_excludes_the_retired_emitter() -> None:
    import pathlib

    migration = pathlib.Path(__file__).resolve().parents[2] / "migrations" / "control" / "016_bff_ingress_audit.sql"
    assert migration.exists(), "migration M-1 is missing; BFF audit emission is blocked without it"
    sql = migration.read_text(encoding="utf-8")
    assert "control_ingress_audit" in sql
    assert "source_service <> 'api_gateway'" in sql, "M-1 does not exclude the retired emitter"

    append_only = migration.parent / "017_bff_ingress_audit_append_only.sql"
    assert append_only.exists(), "M-1 has no append-only migration; an editable audit trail is not one"


def test_the_in_memory_sink_preserves_insertion_order() -> None:
    sink = InMemoryAuditSink()
    from snackportal2.services.audit.models import AuditEvent

    for index in range(3):
        sink.append(
            AuditEvent(
                event_id=str(index),
                occurred_at="2026-01-01T00:00:00+00:00",
                source_service="bff",
                action=AuditAction.ROUTE_DENIED,
                outcome="denied",
                correlation_id="c",
                actor_ref="p",
            )
        )
    assert [event.event_id for event in sink.read(None, None, 10)] == ["0", "1", "2"]


# --- OpenAPI gate --------------------------------------------------------------------------------

def test_audit_openapi_meets_the_standing_rules() -> None:
    assert_document(
        audit_main.app.openapi(),
        service="audit",
        expected_paths=["/health", "/readiness", "/audit/events"],
        expected_schemas=["AuditEvent", "AuditEventSubmission", "AuditAction", "AuditReadResponse"],
        required_security_schemes=["InternalServiceBearer"],
    )


def test_audit_health_is_public_and_the_event_routes_are_not() -> None:
    schema = audit_main.app.openapi()
    assert "security" not in schema["paths"]["/health"]["get"]
    assert schema["paths"]["/audit/events"]["post"]["security"] == [{"InternalServiceBearer": []}]
    assert schema["paths"]["/audit/events"]["get"]["security"] == [{"InternalServiceBearer": []}]
