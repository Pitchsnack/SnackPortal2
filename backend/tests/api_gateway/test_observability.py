"""Observability (IC-010 §S / WP-11): request+latency metrics present (OBS-1), non-disclosing (OBS-2)."""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _gateway_doubles as D  # noqa: E402
import _h  # noqa: E402

from api_gateway.adapters.providers.in_memory_metrics import InMemoryMetrics  # noqa: E402


def _gateway_with_metrics():
    authn = D.StubAuthenticator()
    authn.add_token("tok-t1", principal="p1", tenant="t1", role="TENANT_AGENT")
    authn.add_token("tok-t2", principal="p2", tenant="t2", role="TENANT_AGENT")
    metrics = InMemoryMetrics()
    gateway = D.build_gateway(authenticator=authn, router=D.StubRouterDispatch(), audit=D.RecordingAuditEmitter(), metrics=metrics)
    return gateway, metrics


def test_request_and_latency_metrics_present() -> None:  # OBS-1
    gateway, metrics = _gateway_with_metrics()
    gateway.handle(D.req(path="/tenant/x", headers={"X-Tenant-Id": "t1"}, authorization="tok-t1"))  # success
    gateway.handle(D.req(path="/nope", authorization="tok-t1"))  # rejection
    recs = metrics.records()
    assert len(recs) == 2  # one request metric per request (success + rejection)
    for r in recs:
        assert isinstance(r.duration_ms, float) and r.duration_ms >= 0.0  # latency present
        assert isinstance(r.status, int)
    assert recs[0].outcome == "ok" and recs[0].category == "TENANT_OPERATION"
    assert recs[1].outcome == "unknown_route" and recs[1].status == 403


def test_metrics_disclose_no_tenant() -> None:  # OBS-2
    gateway, metrics = _gateway_with_metrics()
    gateway.handle(D.req(path="/tenant/x", headers={"X-Tenant-Id": "t1"}, authorization="tok-t1"))
    gateway.handle(D.req(path="/tenant/y", headers={"X-Tenant-Id": "t2"}, authorization="tok-t2"))
    recs = metrics.records()
    # Structural: a metric carries operational labels only — no tenant/DB field exists.
    for r in recs:
        assert set(vars(r).keys()) == {"category", "outcome", "status", "duration_ms"}
    # Behavioral: no label value discloses a tenant id / DB name / connection / topology.
    forbidden = ("t1", "t2", "tenant_id", "tenant=", "postgres", "database", "dsn", "://", "topology")
    for r in recs:
        blob = f"{r.category}|{r.outcome}".lower()
        for bad in forbidden:
            assert bad not in blob, f"metric label discloses {bad!r}: {r}"


if __name__ == "__main__":
    _h.run([test_request_and_latency_metrics_present, test_metrics_disclose_no_tenant])
