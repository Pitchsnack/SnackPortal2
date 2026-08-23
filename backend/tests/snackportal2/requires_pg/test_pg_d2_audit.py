"""Stage 4D §6.6 — the Audit Service against the real Control database.

Mandatory, because M-1 is the migration the whole stage exists to close. Everything here runs
against ``control_ingress_audit`` as migration 016/017 created it, through the real Audit
Service composed from the environment.

Four properties get particular attention, because each is a thing an in-memory sink cannot
disprove: the emitter identity is derived from the credential and survives the round trip; the
timestamp is UTC-aware after passing through a ``text`` column; the outcome and action enums
come back as enums rather than as free strings; and the row cannot be altered afterwards.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterator

import httpx
import pytest

from snackportal2.services.audit.identity import (
    ENV_CREDENTIALS,
    SCOPE_DELEGATE,
    SCOPE_READ,
    SCOPE_READ_ALL,
    SCOPE_WRITE,
    build_credential_directory,
)
from snackportal2.services.audit.models import AuditAction, AuditOutcome
from snackportal2.services.audit.sink import (
    AUDIT_TABLE,
    ENV_AUDIT_DSN,
    InMemoryAuditSink,
    PostgresAuditSink,
    build_sink,
)

from . import _stage4_pg as pg
from . import _stage4_servers as srv

pytestmark = pytest.mark.skipif(not pg.configured(), reason=pg.SKIP_REASON)

BFF_EMITTER = "audit-emitter-bff"
ROUTER_EMITTER = "audit-emitter-router"
AUDITOR_EMITTER = "audit-emitter-auditor"
DELEGATE_EMITTER = "audit-emitter-delegate"

#: A credential the Audit Service is deliberately never told about.
UNRECOGNIZED_EMITTER = "audit-emitter-not-configured"

CREDENTIALS = {
    BFF_EMITTER: {"emitter_ref": "bff", "scopes": [SCOPE_WRITE, SCOPE_READ]},
    ROUTER_EMITTER: {"emitter_ref": "database_router", "scopes": [SCOPE_WRITE]},
    AUDITOR_EMITTER: {"emitter_ref": "auditor", "scopes": [SCOPE_READ_ALL]},
    DELEGATE_EMITTER: {"emitter_ref": "operator", "scopes": [SCOPE_READ, SCOPE_DELEGATE], "delegable_targets": ["bff"]},
}


@pytest.fixture(scope="module")
def audit(tmp_path_factory: pytest.TempPathFactory) -> Iterator[srv.ServiceFleet]:
    pg.provision()
    log_dir: Path = tmp_path_factory.mktemp("stage4d2-logs")
    running = srv.ServiceFleet(log_dir)
    try:
        running.start(
            "audit",
            {"SP2_AUDIT_DSN": pg.dsn("control"), "SP2_AUDIT_CREDENTIALS": json.dumps(CREDENTIALS)},
        )
        yield running
    finally:
        running.stop()


def _emit(fleet: srv.ServiceFleet, credential: str, **event: Any) -> httpx.Response:
    payload: Dict[str, Any] = {
        "action": AuditAction.ROUTE_DENIED.value,
        "outcome": AuditOutcome.DENIED.value,
        "correlation_id": "c-audit",
        "actor_ref": "p-agent",
    }
    payload.update(event)
    return httpx.post(
        fleet.url("audit") + "/audit/events",
        headers={"Authorization": "Bearer " + credential},
        json=payload,
        timeout=15.0,
    )


def _read(fleet: srv.ServiceFleet, credential: str, **params: Any) -> httpx.Response:
    return httpx.get(
        fleet.url("audit") + "/audit/events",
        headers={"Authorization": "Bearer " + credential},
        params=params,
        timeout=15.0,
    )


# --- the sink selector --------------------------------------------------------------------


def test_a_configured_control_dsn_selects_the_durable_sink() -> None:
    assert isinstance(build_sink(env={}), InMemoryAuditSink)
    assert isinstance(build_sink(env={ENV_AUDIT_DSN: "  "}), InMemoryAuditSink)
    assert isinstance(build_sink(env={ENV_AUDIT_DSN: pg.dsn("control")}), PostgresAuditSink)


def test_the_audit_table_the_sink_targets_is_the_one_m1_created() -> None:
    assert AUDIT_TABLE == "control_ingress_audit"
    assert AUDIT_TABLE in pg.table_names(pg.dsn("control"))


def test_an_unconfigured_audit_service_accepts_nothing_rather_than_everything() -> None:
    directory = build_credential_directory(env={})
    assert directory.resolve(BFF_EMITTER) is None
    assert build_credential_directory(env={ENV_CREDENTIALS: json.dumps(CREDENTIALS)}).resolve(BFF_EMITTER) is not None


# --- persistence --------------------------------------------------------------------------


def test_an_audit_event_persists_to_the_real_control_database(audit: srv.ServiceFleet) -> None:
    response = _emit(
        audit,
        BFF_EMITTER,
        action=AuditAction.TENANT_STARTUP_READ.value,
        outcome=AuditOutcome.ALLOWED.value,
        correlation_id="c-persist",
        actor_ref="p-agent",
        tenant_ref="acme",
        record_ref="ref:acme:startups:1",
    )
    assert response.status_code == 201, response.text
    event_id = response.json()["event_id"]
    assert response.json()["recorded"] is True

    stored = pg.rows(
        pg.dsn("control"),
        "SELECT source_service, action, outcome, correlation_id, actor_ref, tenant_ref, record_ref "
        "FROM " + AUDIT_TABLE + " WHERE event_id = %s",
        (event_id,),
    )
    assert stored == [("bff", "tenant_startup_read", "allowed", "c-persist", "p-agent", "acme", "ref:acme:startups:1")]


def test_the_emitting_service_is_derived_from_the_credential_and_survives_the_round_trip(
    audit: srv.ServiceFleet,
) -> None:
    """An emitter that could name itself could name someone else (3-day plan §10).

    The submission carries no ``source_service`` field at all; a caller that supplies one is
    rejected outright rather than having it quietly ignored, so the attribution stored is a
    fact about which key was used.
    """
    bff_event = _emit(audit, BFF_EMITTER, correlation_id="c-identity-bff").json()["event_id"]
    router_event = _emit(audit, ROUTER_EMITTER, correlation_id="c-identity-router").json()["event_id"]

    assert pg.scalar(pg.dsn("control"), "SELECT source_service FROM " + AUDIT_TABLE + " WHERE event_id = %s", (bff_event,)) == "bff"
    assert (
        pg.scalar(pg.dsn("control"), "SELECT source_service FROM " + AUDIT_TABLE + " WHERE event_id = %s", (router_event,))
        == "database_router"
    )

    # A submitted ``source_service`` is not rejected — the submission model ignores unknown
    # fields — but it is not *honoured* either, which is the property that matters. Had it
    # been honoured, this row would additionally have hit M-1's ``source_service <>
    # 'api_gateway'`` constraint, so two independent controls would have to fail together for
    # a spoofed attribution to land.
    spoofed = _emit(audit, BFF_EMITTER, correlation_id="c-spoof", source_service="api_gateway")
    assert spoofed.status_code == 201, spoofed.text
    assert pg.scalar(pg.dsn("control"), "SELECT source_service FROM " + AUDIT_TABLE + " WHERE correlation_id = 'c-spoof'") == "bff", (
        "a submitted source_service overrode the credential-derived one"
    )


def test_the_event_id_is_server_minted_and_unique_per_emission(audit: srv.ServiceFleet) -> None:
    first = _emit(audit, BFF_EMITTER, correlation_id="c-ids").json()["event_id"]
    second = _emit(audit, BFF_EMITTER, correlation_id="c-ids").json()["event_id"]
    assert first != second

    from uuid import UUID

    assert UUID(first).version == 4

    supplied = _emit(audit, BFF_EMITTER, correlation_id="c-ids", event_id="chosen-by-the-emitter")
    assert supplied.status_code == 201, supplied.text
    assert supplied.json()["event_id"] != "chosen-by-the-emitter", "the emitter chose its own event id"
    assert pg.scalar(pg.dsn("control"), "SELECT count(*) FROM " + AUDIT_TABLE + " WHERE event_id = 'chosen-by-the-emitter'") == 0


def test_the_timestamp_survives_the_text_column_as_a_utc_aware_value(audit: srv.ServiceFleet) -> None:
    """M-1 stores ``occurred_at`` as ``text``, so "still UTC-aware" is a real question.

    ``recorded_at`` is the DB-assigned ``timestamptz`` beside it, and comparing the two is what
    proves the stored string is the same instant and not a naive local rendering.
    """
    before = datetime.now(timezone.utc)
    event_id = _emit(audit, BFF_EMITTER, correlation_id="c-clock").json()["event_id"]
    after = datetime.now(timezone.utc)

    occurred_raw, recorded_at = pg.rows(
        pg.dsn("control"), "SELECT occurred_at, recorded_at FROM " + AUDIT_TABLE + " WHERE event_id = %s", (event_id,)
    )[0]

    occurred = datetime.fromisoformat(str(occurred_raw))
    assert occurred.tzinfo is not None, "the stored timestamp lost its timezone: " + repr(occurred_raw)
    assert occurred.utcoffset() == timedelta(0), "the stored timestamp is not UTC: " + repr(occurred_raw)
    assert before <= occurred <= after, "the stored timestamp is not the emission instant"

    assert recorded_at.tzinfo is not None
    assert abs((recorded_at - occurred).total_seconds()) < 60, "server clock and DB clock disagree by more than a minute"


def test_the_outcome_and_action_enums_round_trip_as_enums(audit: srv.ServiceFleet) -> None:
    for action, outcome in (
        (AuditAction.CARRIER_MISMATCH, AuditOutcome.DENIED),
        (AuditAction.CARRIER_ON_CONTROL_ANOMALY, AuditOutcome.ANOMALY),
        (AuditAction.ISOLATION_ANOMALY, AuditOutcome.ANOMALY),
        (AuditAction.WORKSPACE_MEMBERSHIPS_READ, AuditOutcome.ALLOWED),
        (AuditAction.TENANT_STARTUP_UPDATE, AuditOutcome.ALLOWED),
    ):
        response = _emit(
            audit,
            BFF_EMITTER,
            action=action.value,
            outcome=outcome.value,
            correlation_id="c-enum-" + action.value,
            actor_ref="p-enum",
        )
        assert response.status_code == 201, response.text

    read = _read(audit, AUDITOR_EMITTER, limit=500)
    assert read.status_code == 200, read.text
    by_correlation = {event["correlation_id"]: event for event in read.json()["events"]}
    for action, outcome in (
        (AuditAction.CARRIER_MISMATCH, AuditOutcome.DENIED),
        (AuditAction.ISOLATION_ANOMALY, AuditOutcome.ANOMALY),
    ):
        event = by_correlation["c-enum-" + action.value]
        assert AuditAction(event["action"]) is action
        assert AuditOutcome(event["outcome"]) is outcome


def test_an_action_outside_the_closed_vocabulary_is_refused_at_both_layers(audit: srv.ServiceFleet) -> None:
    """The service rejects it, and if it ever stopped, the M-1 CHECK constraint still would."""
    response = _emit(audit, BFF_EMITTER, action="InventedAction", correlation_id="c-vocab")
    assert response.status_code == 422
    assert pg.scalar(pg.dsn("control"), "SELECT count(*) FROM " + AUDIT_TABLE + " WHERE correlation_id = 'c-vocab'") == 0

    with pytest.raises(pg.database_error()):
        pg.execute(
            pg.dsn("control"),
            "INSERT INTO " + AUDIT_TABLE + " (event_id, occurred_at, source_service, action, outcome, "
            "correlation_id, actor_ref) VALUES ('vocab-probe', '2026-08-23T00:00:00+00:00', 'bff', "
            "'InventedAction', 'denied', 'c-vocab-sql', 'p')",
        )


def test_an_outcome_outside_the_closed_vocabulary_is_refused_at_both_layers(audit: srv.ServiceFleet) -> None:
    assert _emit(audit, BFF_EMITTER, outcome="maybe", correlation_id="c-outcome").status_code == 422
    with pytest.raises(pg.database_error()):
        pg.execute(
            pg.dsn("control"),
            "INSERT INTO " + AUDIT_TABLE + " (event_id, occurred_at, source_service, action, outcome, "
            "correlation_id, actor_ref) VALUES ('outcome-probe', '2026-08-23T00:00:00+00:00', 'bff', "
            "'RouteDenied', 'maybe', 'c-outcome-sql', 'p')",
        )


def test_a_persisted_audit_row_cannot_be_altered_afterwards(audit: srv.ServiceFleet) -> None:
    event_id = _emit(audit, BFF_EMITTER, correlation_id="c-immutable").json()["event_id"]
    for statement in (
        "UPDATE " + AUDIT_TABLE + " SET outcome = 'allowed' WHERE event_id = %s",
        "DELETE FROM " + AUDIT_TABLE + " WHERE event_id = %s",
    ):
        with pytest.raises(pg.database_error()):
            pg.execute(pg.dsn("control"), statement, (event_id,))
    assert pg.scalar(pg.dsn("control"), "SELECT outcome FROM " + AUDIT_TABLE + " WHERE event_id = %s", (event_id,)) == "denied"


# --- read scope ---------------------------------------------------------------------------


def test_a_read_all_scope_sees_events_from_every_emitter(audit: srv.ServiceFleet) -> None:
    _emit(audit, BFF_EMITTER, correlation_id="c-scope-bff", actor_ref="bff")
    _emit(audit, ROUTER_EMITTER, correlation_id="c-scope-router", actor_ref="database_router")
    response = _read(audit, AUDITOR_EMITTER, limit=500)
    assert response.status_code == 200
    assert response.json()["scope"] == "audit:read:all"
    services = {event["source_service"] for event in response.json()["events"]}
    assert {"bff", "database_router"} <= services


def test_a_self_scoped_read_sees_only_what_the_caller_was_the_actor_of(audit: srv.ServiceFleet) -> None:
    _emit(audit, BFF_EMITTER, correlation_id="c-self", actor_ref="bff")
    _emit(audit, ROUTER_EMITTER, correlation_id="c-self-other", actor_ref="database_router")
    response = _read(audit, BFF_EMITTER, limit=500)
    assert response.status_code == 200
    assert response.json()["scope"] == "audit:read"
    assert {event["actor_ref"] for event in response.json()["events"]} == {"bff"}


def test_a_tenant_filter_narrows_the_read_to_one_tenant(audit: srv.ServiceFleet) -> None:
    _emit(audit, BFF_EMITTER, correlation_id="c-tenant-acme", actor_ref="bff", tenant_ref="acme")
    _emit(audit, BFF_EMITTER, correlation_id="c-tenant-zeta", actor_ref="bff", tenant_ref="zeta")
    response = _read(audit, AUDITOR_EMITTER, tenant_ref="zeta", limit=500)
    assert response.status_code == 200
    assert {event["tenant_ref"] for event in response.json()["events"]} == {"zeta"}


def test_delegated_reads_need_the_scope_and_the_named_target(audit: srv.ServiceFleet) -> None:
    """A broad delegation scope is never authority to impersonate everyone."""
    permitted = _read(audit, DELEGATE_EMITTER, on_behalf_of="bff", limit=10)
    assert permitted.status_code == 200
    assert permitted.json()["scope"] == "delegated:bff"

    refused = _read(audit, DELEGATE_EMITTER, on_behalf_of="database_router", limit=10)
    assert refused.status_code == 403
    assert refused.json() == {"status": 403, "code": "access_denied"}


def test_a_write_only_credential_cannot_read_and_an_unknown_one_does_neither(audit: srv.ServiceFleet) -> None:
    assert _read(audit, ROUTER_EMITTER, limit=10).status_code == 403
    assert _emit(audit, AUDITOR_EMITTER, correlation_id="c-no-write").status_code == 403
    assert _emit(audit, UNRECOGNIZED_EMITTER, correlation_id="c-unknown").status_code == 401
    assert _read(audit, UNRECOGNIZED_EMITTER, limit=10).status_code == 401
    assert httpx.get(audit.url("audit") + "/audit/events", timeout=10.0).status_code == 401


def test_events_read_back_in_deterministic_order(audit: srv.ServiceFleet) -> None:
    first = _read(audit, AUDITOR_EMITTER, limit=500).json()["events"]
    second = _read(audit, AUDITOR_EMITTER, limit=500).json()["events"]
    assert first == second


# --- references only ------------------------------------------------------------------------


def test_no_audit_response_or_log_discloses_a_connection_string(audit: srv.ServiceFleet) -> None:
    fragments = srv.dsn_secret_fragments()
    bodies = [
        _read(audit, AUDITOR_EMITTER, limit=500).text,
        httpx.get(audit.url("audit") + "/readiness", timeout=10.0).text,
        httpx.get(audit.url("audit") + "/openapi.json", timeout=10.0).text,
    ]
    for body in bodies:
        for fragment in fragments:
            assert fragment not in body
    for key, text in audit.all_logs().items():
        for fragment in fragments:
            assert fragment not in text, key + " logged a DSN fragment"


def test_the_audit_table_has_no_column_for_business_payload() -> None:
    """IC-001's Global Audit Representation Rule, as a schema property rather than a promise."""
    columns = set(pg.column_names(pg.dsn("control"), AUDIT_TABLE))
    for forbidden in ("name", "email", "payload", "body", "dsn", "secret", "token", "detail", "message", "stack"):
        offending = [column for column in columns if forbidden in column]
        assert not offending, "M-1 carries a payload-shaped column: " + repr(offending)


def test_the_sharing_audit_classes_are_present_in_the_vocabulary_and_emitted_by_nothing(
    audit: srv.ServiceFleet,
) -> None:
    """Authored-but-inert until IC-007 is Final (IC-013 §18): defined, and unused.

    Nine classes, not the ten the M-1 header's prose implies — there are eight ``share_*``
    actions plus ``forward_attempt_denied``, and the migration's CHECK constraint enumerates
    exactly those nine. The enum and the constraint agree; only the comment miscounts.
    """
    from snackportal2.services.audit.models import SHARING_ACTIONS

    assert len(SHARING_ACTIONS) == 9
    assert len([action for action in SHARING_ACTIONS if action.value.startswith("share_")]) == 8
    emitted = pg.rows(pg.dsn("control"), "SELECT DISTINCT action FROM " + AUDIT_TABLE)
    used = {str(row[0]) for row in emitted}
    assert not used & {action.value for action in SHARING_ACTIONS}, "an inert sharing class was emitted: " + repr(used)
