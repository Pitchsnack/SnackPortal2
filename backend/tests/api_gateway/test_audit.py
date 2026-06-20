"""Audit (IC-010 §J / AD-1): named emit-set, references-only, single emission, no sink."""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _gateway_doubles as D  # noqa: E402
import _h  # noqa: E402

from api_gateway.adapters.providers.in_memory_audit_emitter import InMemoryAuditEmitter  # noqa: E402
from api_gateway.models import AuditAction  # noqa: E402

_SECRET = "tok-t1"


def _events_for(path: str, *, host: str = "", headers=None, authorization=_SECRET):
    gateway, _authn, _router, audit = D.tenant_setup()
    gateway.handle(D.req(path=path, host=host, headers=headers or {}, authorization=authorization, correlation_id="cid-1"))
    return audit.events


def test_emit_set_named_events() -> None:
    assert [e.action for e in _events_for("/tenant/x", headers={"X-Tenant-Id": "t2"})] == [AuditAction.CARRIER_MISMATCH]
    assert [e.action for e in _events_for("/nope", headers={"X-Tenant-Id": "t1"})] == [AuditAction.ROUTE_DENIED]
    assert [e.action for e in _events_for("/tenant/x", host="t2.s.example", headers={"X-Tenant-Id": "t1"})] == [
        AuditAction.ISOLATION_ANOMALY
    ]


def test_carrier_on_control_anomaly_is_emitted() -> None:
    authn = D.StubAuthenticator()
    authn.add_token("tok-ctl", principal="ops", tenant=None, role="CONTROL")
    audit = D.RecordingAuditEmitter()
    gateway = D.build_gateway(authenticator=authn, router=D.StubRouterDispatch(), audit=audit)
    gateway.handle(D.req(path="/directory/x", headers={"X-Tenant-Id": "t9"}, authorization="tok-ctl"))
    assert [e.action for e in audit.events] == [AuditAction.CARRIER_ON_CONTROL_ANOMALY]


def test_records_are_references_only_no_token_or_pii() -> None:
    events = _events_for("/tenant/x", host="t2.s.example", headers={"X-Tenant-Id": "t1"})  # IsolationAnomaly
    for e in events:
        for value in (e.correlation_id, e.outcome, e.actor_ref, e.tenant_ref, e.carrier_ref):
            assert value != _SECRET  # no bearer token leaks into an audit record
        if e.carrier_ref is not None:
            assert e.carrier_ref.startswith("carrier:") and len(e.carrier_ref) <= 64  # opaque + bounded (IC-005:116)


def test_single_emission_per_anomaly() -> None:
    events = _events_for("/tenant/x", headers={"X-Tenant-Id": "t2"})  # one carrier_mismatch
    keys = [(e.action, e.correlation_id) for e in events]
    assert len(keys) == len(set(keys)) == 1  # exactly one record for the anomaly


def test_default_emitter_is_in_memory_no_sink() -> None:
    emitter = InMemoryAuditEmitter()
    assert emitter.events() == []  # in-process list; no DB/file/external persistence


if __name__ == "__main__":
    _h.run(
        [
            test_emit_set_named_events,
            test_carrier_on_control_anomaly_is_emitted,
            test_records_are_references_only_no_token_or_pii,
            test_single_emission_per_anomaly,
            test_default_emitter_is_in_memory_no_sink,
        ]
    )
