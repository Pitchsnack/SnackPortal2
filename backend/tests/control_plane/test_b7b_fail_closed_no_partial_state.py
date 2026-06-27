"""PRD 06 B-7B — fail-closed required audit write + NO partial state (B7B-D5) + ref fail-closed.

A failed REQUIRED durable audit write must reject the lifecycle transition with NO committed
partial state. B-7B implements this via call-site ordering (audit-before-irreversible-commit)
in ``registry.py`` and ``provisioning.py``: the required audit write precedes ``put_tenant``,
so if the audit write fails the state change is never committed. These tests are mutation-form
— under the pre-B-7B ordering (put_tenant then audit) the state WOULD be committed before the
failure and every "state unchanged" assertion would fail.

Also covers durable-store reference fail-closed: ``PermissionError`` (ref not allow-listed) and
``LookupError`` (unresolved ref) both propagate on first use, with secret-free messages.

Pure stdlib; no live DB. pytest- or standalone-run:
  python tests/control_plane/test_b7b_fail_closed_no_partial_state.py
"""

from __future__ import annotations

import pathlib
import sys
from typing import List, Optional

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _d15_doubles  # noqa: E402
import _h  # noqa: E402

from control_plane import events  # noqa: E402
from control_plane.adapters.providers.in_memory_store import InMemoryControlStore  # noqa: E402
from control_plane.adapters.providers.postgres_store import PostgresControlStore  # noqa: E402
from control_plane.audit import ControlPlaneAudit  # noqa: E402
from control_plane.records import ControlAuditRecord, TenantLifecycleState  # noqa: E402
from control_plane.registry import TenantRegistry  # noqa: E402
from shared.adapters.providers.env_reference_secret_store import DEFAULT_ALLOWED, EnvReferenceSecretStore  # noqa: E402
from shared.secrets import SecretRef  # noqa: E402


class _AuditFailingStore(InMemoryControlStore):
    """In-memory store whose append_audit fails (selectively) — proves fail-closed ordering."""

    def __init__(self, *, fail_on_action: Optional[str] = None, fail_all: bool = False) -> None:
        super().__init__()
        self._fail_on_action = fail_on_action
        self._fail_all = fail_all
        self.attempted: List[ControlAuditRecord] = []

    def append_audit(self, record: ControlAuditRecord) -> None:
        self.attempted.append(record)
        if self._fail_all or (self._fail_on_action is not None and record.action == self._fail_on_action):
            raise RuntimeError("durable audit write failed (simulated)")
        super().append_audit(record)


def _register(reg: TenantRegistry, tid: str = "t1") -> None:
    reg.register_tenant(
        tenant_id=tid,
        organization_ref="org",
        expected_schema_version="1",
        database_association_ref=SecretRef(f"tenant/{tid}/db", "1"),
        federation_config_ref="fed",
        actor="op",
        correlation_id="corr-reg",
    )


def test_register_fails_closed_with_no_partial_tenant() -> None:
    store = _AuditFailingStore(fail_all=True)
    reg = TenantRegistry(store, ControlPlaneAudit(store))
    raised = False
    try:
        _register(reg)
    except RuntimeError:
        raised = True
    assert raised, "a failed required durable audit write must reject the registration"
    # NO partial state: the tenant was never committed (audit precedes put_tenant)
    assert store.get_tenant("t1") is None
    # correlation id was carried through to the (failed) required audit write
    assert store.attempted and store.attempted[0].correlation_id == "corr-reg"


def test_registry_transition_fails_closed_state_unchanged() -> None:
    store = _AuditFailingStore(fail_on_action="MarkProvisioning")
    reg = TenantRegistry(store, ControlPlaneAudit(store))
    _register(reg)  # RegisterTenant is not the failing action -> committed Registered
    assert store.get_tenant("t1").lifecycle_state is TenantLifecycleState.REGISTERED
    raised = False
    try:
        reg.mark_provisioning("t1", actor="op", correlation_id="corr-mp")
    except RuntimeError:
        raised = True
    assert raised
    # state unchanged: the VERIFYING-equivalent commit never happened (audit failed first)
    assert store.get_tenant("t1").lifecycle_state is TenantLifecycleState.REGISTERED


def test_provisioning_gate_transition_fails_closed_state_unchanged() -> None:
    store = _AuditFailingStore(fail_on_action=events.DISTINCTNESS_VERIFICATION_STARTED)
    _d15_doubles.register_tenant(store, "t1", store_ref="tenant/t1/db")  # committed PROVISIONING (direct put)
    svc = _d15_doubles.build_service(store, _d15_doubles.FakeEvidenceProvider({}))
    raised = False
    try:
        svc.verify("t1", actor="op", correlation_id="corr-v")
    except RuntimeError:
        raised = True
    assert raised, "the gate's first transition audit failing must reject verify()"
    # state unchanged: still PROVISIONING (VERIFYING commit gated on its audit)
    assert store.get_tenant("t1").lifecycle_state is TenantLifecycleState.PROVISIONING


def test_durable_store_permission_error_fails_closed_secret_free() -> None:
    # default trust-anchor-only secret store: a control-store ref is NOT allow-listed.
    secrets = EnvReferenceSecretStore()
    store = PostgresControlStore(secrets=secrets, ref=SecretRef("control/control-store-dsn", "1"))
    assert store._conn_cache is None  # lazy: nothing happened at construction
    raised = False
    try:
        store.list_audit()  # first op -> resolve -> _guard -> PermissionError (never connects)
    except PermissionError as exc:
        raised = True
        assert "postgres" not in str(exc).lower() and "://" not in str(exc)
    assert raised, "a non-allow-listed control-store ref must fail closed (PermissionError)"
    assert store._conn_cache is None  # still no connection opened


def test_durable_store_lookup_error_fails_closed_secret_free() -> None:
    ref = SecretRef("control/control-store-dsn-unset-b7b", "1")  # allow-listed but unset env -> unresolved
    secrets = EnvReferenceSecretStore(allowed=frozenset({*DEFAULT_ALLOWED, ref.store_ref}))
    store = PostgresControlStore(secrets=secrets, ref=ref)
    raised = False
    try:
        store.list_audit()
    except LookupError as exc:
        raised = True
        assert "postgres" not in str(exc).lower() and "://" not in str(exc)
    assert raised, "an unresolved control-store ref must fail closed (LookupError)"


if __name__ == "__main__":
    _h.run(
        [
            test_register_fails_closed_with_no_partial_tenant,
            test_registry_transition_fails_closed_state_unchanged,
            test_provisioning_gate_transition_fails_closed_state_unchanged,
            test_durable_store_permission_error_fails_closed_secret_free,
            test_durable_store_lookup_error_fails_closed_secret_free,
        ]
    )
