"""Tenant Credential Secret Resolution Standard (PRD-P4-R2 D; D-14)."""
from __future__ import annotations

import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _h  # noqa: E402

from shared.context import RequestContext  # noqa: E402
from shared.secrets import SecretRef, SecretValue  # noqa: E402

from database_router.adapters.providers.env_tenant_secret_store import EnvTenantSecretStore  # noqa: E402
from database_router.models import RoutingDenied  # noqa: E402
from doubles import (  # noqa: E402
    FakeAudit,
    FakeConnectionFactory,
    FakeRoutingRead,
    FakeSecretStore,
    make_router,
)


def _ctx(tenant_id="t1"):
    return RequestContext(correlation_id="c", active_tenant_id=tenant_id, principal_ref="p", role="TENANT_ADMIN")


def _wire():
    read = FakeRoutingRead()
    read.set_view("t1")
    secrets = FakeSecretStore()
    factory = FakeConnectionFactory()
    audit = FakeAudit()
    router, _, _, _ = make_router(read=read, secret_store=secrets, factory=factory, audit=audit)
    return router, secrets, factory, audit


def test_credential_resolved_at_connect_time() -> None:
    router, secrets, factory, _ = _wire()
    router.route(_ctx())
    assert len(secrets.resolved) == 1
    assert secrets.resolved[0] == SecretRef("tenant/t1/db", "1")
    assert factory.descriptors == ["descriptor::tenant/t1/db@1"]


def test_credential_not_re_resolved_on_pooled_reuse() -> None:
    router, secrets, _, _ = _wire()
    r = router.route(_ctx())
    router.release(r)
    router.route(_ctx())                          # reuses the pooled connection
    assert len(secrets.resolved) == 1             # resolved only when a connection is created


def test_credential_never_in_result_or_audit() -> None:
    router, _, _, audit = _wire()
    result = router.route(_ctx())
    leak = "descriptor::"
    assert leak not in repr(result)
    for ev in audit.events:
        assert leak not in (ev.outcome + ev.action + (ev.target_ref or "") + ev.actor_ref)


def test_secret_value_repr_is_redacted() -> None:
    assert "topsecret" not in repr(SecretValue(material="topsecret"))


def test_missing_secret_denies_without_leak() -> None:
    read = FakeRoutingRead()
    read.set_view("t1")
    secrets = FakeSecretStore()
    secrets.set_missing("tenant/t1/db")
    audit = FakeAudit()
    router, _, _, _ = make_router(
        read=read, secret_store=secrets, factory=FakeConnectionFactory(), audit=audit
    )
    try:
        router.route(_ctx())
        assert False, "missing secret must deny"
    except RoutingDenied as d:
        assert d.http_status == 503 and d.public_code == "connection_unavailable"
    assert any(o.startswith("denied:connection_unavailable") for o in audit.outcomes())


def test_tenant_secret_store_is_allow_listed_to_tenant_refs() -> None:
    store = EnvTenantSecretStore()
    key = "SNACKPORTAL_TENANT_SECRET_TENANT_T1_DB_V1"
    os.environ[key] = "host=localhost dbname=t1"
    try:
        val = store.resolve(SecretRef("tenant/t1/db", "1"))
        assert val.material == "host=localhost dbname=t1"
        try:
            store.resolve(SecretRef("bootstrap/trust-anchor", "1"))
            assert False, "tenant SecretStore must refuse non-tenant references"
        except PermissionError:
            pass
    finally:
        os.environ.pop(key, None)


if __name__ == "__main__":
    _h.run([
        test_credential_resolved_at_connect_time,
        test_credential_not_re_resolved_on_pooled_reuse,
        test_credential_never_in_result_or_audit,
        test_secret_value_repr_is_redacted,
        test_missing_secret_denies_without_leak,
        test_tenant_secret_store_is_allow_listed_to_tenant_refs,
    ])
