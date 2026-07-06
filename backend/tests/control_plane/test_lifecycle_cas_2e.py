"""PRD 07D-2e — lifecycle CAS unit suite (in-memory parity + fake-connection transactional proofs).

Covers the R-2c-LWW closure at the unit level: `TenantRecord.version` defaults, the
`ControlStore.compare_and_swap_tenant` port (in-memory success / stale-version refusal /
vanished-record refusal), the typed `ControlStoreConcurrencyError` (distinct from every
service error; NOT audit/event vocabulary), registry/provisioning/lifecycle CAS routing,
the `verify()` conflict-yield policy (yield to a legitimate SUSPENDED/QUARANTINED/
DECOMMISSIONED/FAILED winner with the EXISTING `VERIFICATION_INCOMPLETE` result; one bounded
retry while mid-flight; fail closed otherwise), the A1 same-target no-op's version/write
invariance, and — against a FAKE driver connection — the D-2e-4 transactional contract of the
durable store: the CAS UPDATE carries the `version = expected` predicate and does NOT commit;
the transition's audit append commits BOTH; a conflict or a failed audit write rolls back with
no orphan state (the live-PG harness proves the same against real PostgreSQL).

Pure stdlib; no driver connection; no live PostgreSQL. Standalone-runnable:
`python tests/control_plane/test_lifecycle_cas_2e.py`.
"""

from __future__ import annotations

import pathlib
import sys
from dataclasses import replace
from typing import Optional

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))  # backend on path

from control_plane import events  # noqa: E402
from control_plane import main as cp_main  # noqa: E402
from control_plane.adapters.providers.in_memory_distinctness import nonprod_control_db_evidence  # noqa: E402
from control_plane.adapters.providers.in_memory_probe import InMemoryTenantDatabaseProbe  # noqa: E402
from control_plane.adapters.providers.in_memory_store import InMemoryControlStore  # noqa: E402
from control_plane.adapters.providers.postgres_store import PostgresControlStore  # noqa: E402
from control_plane.audit import ControlPlaneAudit  # noqa: E402
from control_plane.distinctness import DistinctnessCollisionError, DistinctnessResult  # noqa: E402
from control_plane.lifecycle import LifecycleError, TenantLifecycleService  # noqa: E402
from control_plane.ports import ControlStoreConcurrencyError  # noqa: E402
from control_plane.provisioning import (  # noqa: E402
    REASON_CONCURRENT_LIFECYCLE_WINNER,
    ProvisioningError,
    ProvisioningVerificationService,
)
from control_plane.records import ControlAuditRecord, TenantLifecycleState, TenantRecord  # noqa: E402
from control_plane.recovery import RecoveryError  # noqa: E402
from control_plane.registry import RegistryError, TenantRegistry  # noqa: E402
from control_plane.verification import ProbeResult, TenantDatabaseProbe  # noqa: E402
from shared.secrets import SecretRef  # noqa: E402


def _record(tid: str = "t1", state: TenantLifecycleState = TenantLifecycleState.PROVISIONING, version: int = 0) -> TenantRecord:
    return TenantRecord(
        tenant_id=tid,
        organization_ref="org",
        lifecycle_state=state,
        expected_schema_version="1",
        database_association_ref=SecretRef(f"tenant/{tid}/dsn", "1"),
        federation_config_ref="fed",
        created_at="t0",
        updated_at="t0",
        version=version,
    )


def _seed(store: InMemoryControlStore, tid: str = "t1", state: TenantLifecycleState = TenantLifecycleState.PROVISIONING) -> TenantRecord:
    rec = _record(tid, state)
    store.put_tenant(rec)
    return rec


class _ConflictingStore(InMemoryControlStore):
    """CAS double simulating a LOST race: the first N compare_and_swap_tenant calls raise the
    typed conflict; optionally the simulated winner's state lands first (version bumped), so a
    re-read observes the legitimate concurrent write."""

    def __init__(self, *, conflicts: int = 1, winner_state: Optional[TenantLifecycleState] = None) -> None:
        super().__init__()
        self._conflicts_left = conflicts
        self._winner_state = winner_state
        self.cas_calls = 0

    def compare_and_swap_tenant(self, updated: TenantRecord, *, expected_version: int) -> TenantRecord:
        self.cas_calls += 1
        if self._conflicts_left > 0:
            self._conflicts_left -= 1
            if self._winner_state is not None:
                current = self._tenants[updated.tenant_id]
                self._tenants[updated.tenant_id] = replace(current, lifecycle_state=self._winner_state, version=current.version + 1)
            raise ControlStoreConcurrencyError("simulated concurrent lifecycle winner")
        return super().compare_and_swap_tenant(updated, expected_version=expected_version)


class _CasCountingStore(InMemoryControlStore):
    """Counts CAS invocations (proves the A1 no-op never reaches the write path)."""

    def __init__(self) -> None:
        super().__init__()
        self.cas_calls = 0

    def compare_and_swap_tenant(self, updated: TenantRecord, *, expected_version: int) -> TenantRecord:
        self.cas_calls += 1
        return super().compare_and_swap_tenant(updated, expected_version=expected_version)


def _gate(store: InMemoryControlStore) -> ProvisioningVerificationService:
    return ProvisioningVerificationService(
        store,
        ControlPlaneAudit(store),
        InMemoryTenantDatabaseProbe(schema_version="1"),
        cp_main.CanonicalTenantRefInMemoryEvidence(),
        nonprod_control_db_evidence(),
        supported_schema_versions=["1"],
    )


# --- TenantRecord.version + typed error --------------------------------------------------------
def test_tenant_record_version_defaults_to_zero() -> None:
    rec = TenantRecord(
        tenant_id="t1",
        organization_ref="org",
        lifecycle_state=TenantLifecycleState.REGISTERED,
        expected_schema_version="1",
        database_association_ref=SecretRef("tenant/t1/dsn", "1"),
        federation_config_ref="fed",
        created_at="t0",
        updated_at="t0",
    )
    assert rec.version == 0, "existing keyword construction (no version) must default to 0"


def test_concurrency_error_is_a_distinct_typed_error() -> None:
    # D-2e-3: a store/port-layer Python exception only — distinct from every service error and
    # NOT audit/event vocabulary (nothing in events.py names it; the frozen guards are untouched).
    err = ControlStoreConcurrencyError("x")
    for other in (RegistryError, ProvisioningError, LifecycleError, DistinctnessCollisionError, RecoveryError):
        assert not isinstance(err, other), f"must be distinct from {other.__name__}"
        assert not issubclass(ControlStoreConcurrencyError, other)
    actions = {v for k, v in vars(events).items() if k.isupper() and isinstance(v, str)}
    assert "ControlStoreConcurrencyError" not in actions, "must not enter the event vocabulary"


# --- in-memory CAS parity -----------------------------------------------------------------------
def test_inmemory_cas_success_increments_version() -> None:
    store = InMemoryControlStore()
    rec = _seed(store)
    out = store.compare_and_swap_tenant(replace(rec, lifecycle_state=TenantLifecycleState.SUSPENDED, updated_at="t1"), expected_version=0)
    assert out.version == 1, "successful CAS must return version + 1"
    stored = store.get_tenant("t1")
    assert stored is not None and stored.version == 1 and stored.lifecycle_state is TenantLifecycleState.SUSPENDED


def test_inmemory_cas_stale_version_fails_closed() -> None:
    store = InMemoryControlStore()
    rec = _seed(store)
    store.compare_and_swap_tenant(replace(rec, updated_at="t1"), expected_version=0)  # -> version 1
    before = store.get_tenant("t1")
    raised = False
    try:
        store.compare_and_swap_tenant(replace(rec, updated_at="t2"), expected_version=0)  # stale
    except ControlStoreConcurrencyError:
        raised = True
    assert raised, "a stale expected_version must raise the typed conflict"
    assert store.get_tenant("t1") == before, "a refused CAS must change nothing"


def test_inmemory_cas_unknown_tenant_fails_closed() -> None:
    store = InMemoryControlStore()
    raised = False
    try:
        store.compare_and_swap_tenant(_record("ghost"), expected_version=0)
    except ControlStoreConcurrencyError:
        raised = True
    assert raised, "CAS against a vanished record must raise the typed conflict (never insert)"
    assert store.get_tenant("ghost") is None


# --- registry CAS routing -----------------------------------------------------------------------
def test_registry_transition_cas_success_increments_version_once() -> None:
    store = InMemoryControlStore()
    reg = TenantRegistry(store, ControlPlaneAudit(store))
    _seed(store, state=TenantLifecycleState.REGISTERED)
    out = reg.mark_provisioning("t1", actor="op", correlation_id="c1")
    assert out.version == 1, "one successful transition must increment version exactly once"
    assert store.get_tenant("t1") == out
    marks = [r for r in store.list_audit() if r.action == "MarkProvisioning"]
    assert len(marks) == 1, "exactly one matching audit record per successful transition"


def test_registry_transition_cas_conflict_no_state_change_no_orphan_audit() -> None:
    store = _ConflictingStore(conflicts=1)
    reg = TenantRegistry(store, ControlPlaneAudit(store))
    _seed(store, state=TenantLifecycleState.REGISTERED)
    before = store.get_tenant("t1")
    raised = False
    try:
        reg.mark_provisioning("t1", actor="op", correlation_id="c1")
    except ControlStoreConcurrencyError:
        raised = True
    assert raised, "the typed conflict must propagate from registry._transition"
    assert store.get_tenant("t1") == before, "no state change on a lost race"
    assert store.list_audit() == [], "NO audit record on a lost race (no orphan; CAS precedes the append)"


def test_a1_noop_does_not_increment_version_or_reach_cas() -> None:
    # MC-2e-6 kill site: the 07D-2d same-target no-op stays fully non-mutating under CAS —
    # it returns before the write path, so version, updated_at, audit, and CAS-count all hold.
    store = _CasCountingStore()
    reg = TenantRegistry(store, ControlPlaneAudit(store))
    _seed(store, state=TenantLifecycleState.REGISTERED)
    reg.mark_provisioning("t1", actor="op", correlation_id="c1")  # -> PROVISIONING, version 1
    before_rec = store.get_tenant("t1")
    before_audit = store.list_audit()
    before_cas = store.cas_calls
    again = reg.mark_provisioning("t1", actor="op", correlation_id="c2")  # same-target no-op
    assert again == before_rec, "the no-op must return the existing record unmutated"
    assert again.version == 1, "the no-op must not increment version"
    assert store.get_tenant("t1") == before_rec
    assert store.list_audit() == before_audit
    assert store.cas_calls == before_cas, "the no-op must never reach compare_and_swap_tenant"


# --- provisioning verify() conflict policy (D-2e-5) ---------------------------------------------
def test_verify_conflict_yields_to_suspended_winner() -> None:
    # MC-2e-4/-5 kill sites: a suspend that commits between verify()'s read and its VERIFYING
    # write must WIN — verify yields with the EXISTING non-routable VERIFICATION_INCOMPLETE
    # result, zero side effects, no auto-quarantine, and never READY/RoutingEnabled.
    store = _ConflictingStore(conflicts=1, winner_state=TenantLifecycleState.SUSPENDED)
    svc = _gate(store)
    _seed(store, state=TenantLifecycleState.READY)
    audit_before = store.list_audit()
    out = svc.verify("t1", actor="op", correlation_id="c-yield")
    assert out.result is DistinctnessResult.VERIFICATION_INCOMPLETE, out
    assert out.reason == REASON_CONCURRENT_LIFECYCLE_WINNER
    rec = store.get_tenant("t1")
    assert rec is not None and rec.lifecycle_state is TenantLifecycleState.SUSPENDED, "the winner's state is preserved"
    assert store.list_audit() == audit_before, "the yield must have ZERO side effects (started event never committed)"
    acts = [r.action for r in store.list_audit()]
    assert events.ROUTING_ENABLED not in acts and events.TENANT_QUARANTINED not in acts


def test_verify_conflict_bounded_retry_succeeds_when_still_mid_flight() -> None:
    # A spurious/sibling conflict while the record is still PROVISIONING: exactly one bounded
    # retry at the fresh version, then the gate proceeds normally to READY.
    store = _ConflictingStore(conflicts=1, winner_state=None)
    svc = _gate(store)
    _seed(store, state=TenantLifecycleState.PROVISIONING)
    out = svc.verify("t1", actor="op", correlation_id="c-retry")
    assert out.result is DistinctnessResult.VERIFIED, out
    rec = store.get_tenant("t1")
    assert rec is not None and rec.lifecycle_state is TenantLifecycleState.READY
    starts = [r for r in store.list_audit() if r.action == events.DISTINCTNESS_VERIFICATION_STARTED]
    assert len(starts) == 1, "the failed first attempt must not leave a started record (only the retry's)"


def test_verify_conflict_twice_fails_closed() -> None:
    store = _ConflictingStore(conflicts=2, winner_state=None)
    svc = _gate(store)
    _seed(store, state=TenantLifecycleState.PROVISIONING)
    raised = False
    try:
        svc.verify("t1", actor="op", correlation_id="c-2x")
    except ProvisioningError:
        raised = True
    assert raised, "a second consecutive conflict must fail closed (ONE bounded retry only)"


def test_verify_conflict_ready_winner_fails_closed() -> None:
    # A READY winner (another verifier finished first) is not a yield target: fail closed.
    store = _ConflictingStore(conflicts=1, winner_state=TenantLifecycleState.READY)
    svc = _gate(store)
    _seed(store, state=TenantLifecycleState.PROVISIONING)
    raised = False
    try:
        svc.verify("t1", actor="op", correlation_id="c-rw")
    except ProvisioningError:
        raised = True
    assert raised, "a READY winner must fail closed, never be overwritten or yielded to as incomplete"


# --- lifecycle service CAS routing --------------------------------------------------------------
class _FakeLifecycleProbe(TenantDatabaseProbe):
    def probe(self, association_ref: SecretRef) -> ProbeResult:
        return ProbeResult(reachable=True, observed_schema_version="1")


def test_lifecycle_service_cas_success_and_conflict() -> None:
    store = InMemoryControlStore()
    audit = ControlPlaneAudit(store)
    svc = TenantLifecycleService(store, audit, _FakeLifecycleProbe(), supported_schema_versions=("1",))
    _seed(store, state=TenantLifecycleState.REGISTERED)
    rec = svc.verify_tenant("t1", actor="op", correlation_id="c-l1")
    assert rec.lifecycle_state is TenantLifecycleState.READY
    assert rec.version == 2, "two CAS transitions (Verifying, Ready) must increment version twice"
    conflicted = _ConflictingStore(conflicts=1)
    svc2 = TenantLifecycleService(conflicted, ControlPlaneAudit(conflicted), _FakeLifecycleProbe(), supported_schema_versions=("1",))
    _seed(conflicted, "t2", state=TenantLifecycleState.REGISTERED)
    before = conflicted.get_tenant("t2")
    raised = False
    try:
        svc2.verify_tenant("t2", actor="op", correlation_id="c-l2")
    except LifecycleError:
        raised = True
    assert raised, "a lifecycle-service CAS conflict must fail closed with the service error"
    assert conflicted.get_tenant("t2") == before and conflicted.list_audit() == [], "no lost write, no orphan audit"


# --- durable-store transactional contract (fake driver connection; D-2e-4) ----------------------
class _FakeCursor2e:
    def __init__(self, conn: "_FakeConn2e") -> None:
        self._conn = conn
        self.rowcount = -1

    def __enter__(self) -> "_FakeCursor2e":
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def execute(self, sql: str, params: object = None) -> None:
        self._conn.executed.append((sql, params))
        if self._conn.fail_on is not None and self._conn.fail_on in sql:
            raise RuntimeError("simulated durable failure")
        self.rowcount = 0 if (self._conn.cas_matches_zero and "UPDATE control_tenants" in sql) else 1


class _FakeConn2e:
    def __init__(self) -> None:
        self.executed: list = []
        self.committed = 0
        self.rolled_back = 0
        self.fail_on: Optional[str] = None
        self.cas_matches_zero = False

    def cursor(self) -> _FakeCursor2e:
        return _FakeCursor2e(self)

    def commit(self) -> None:
        self.committed += 1

    def rollback(self) -> None:
        self.rolled_back += 1


def _fake_durable() -> "tuple[PostgresControlStore, _FakeConn2e]":
    store = PostgresControlStore("postgresql://fake/fake")
    conn = _FakeConn2e()
    store._conn_cache = conn  # inject: no psycopg.connect is ever reached
    return store, conn


def _audit_record() -> ControlAuditRecord:
    return ControlAuditRecord(
        actor="op",
        tenant_id="t1",
        action="MarkProvisioning",
        from_state="Registered",
        to_state="Provisioning",
        timestamp="t1",
        correlation_id="c",
    )


def test_durable_cas_predicates_on_version_and_defers_commit() -> None:
    # MC-2e-1/-2 kill sites (unit legs): the UPDATE carries the version predicate and the CAS
    # does NOT commit by itself — the following audit append commits both in ONE transaction.
    store, conn = _fake_durable()
    out = store.compare_and_swap_tenant(_record(), expected_version=0)
    assert out.version == 1
    sql, params = conn.executed[-1]
    assert "UPDATE control_tenants" in sql and "AND version = %s" in sql, "the CAS UPDATE must predicate on version"
    assert isinstance(params, tuple) and params[-1] == 0, "expected_version must bind as the final predicate parameter"
    assert "version = version + 1" in sql, "a successful CAS must increment version in place"
    assert conn.committed == 0, "CAS must NOT commit (the transition's audit append commits the transaction)"
    store.append_audit(_audit_record())
    assert conn.committed == 1, "the audit append must commit the composite exactly once (one transaction)"
    assert conn.rolled_back == 0


def test_durable_cas_conflict_rolls_back_and_raises() -> None:
    # MC-2e-3 kill site (unit leg): a conflict (0 rows) rolls back the open transaction —
    # discarding any composite work — and raises the typed error; nothing commits.
    store, conn = _fake_durable()
    conn.cas_matches_zero = True
    raised = False
    try:
        store.compare_and_swap_tenant(_record(), expected_version=0)
    except ControlStoreConcurrencyError:
        raised = True
    assert raised
    assert conn.rolled_back == 1, "a lost CAS must roll the transaction back (no orphan composite work)"
    assert conn.committed == 0


def test_durable_audit_failure_rolls_back_uncommitted_cas() -> None:
    # The transactional form of B7B-D5: CAS executed (uncommitted), then the required audit
    # append fails -> append_audit rolls back and re-raises; the state change never commits.
    store, conn = _fake_durable()
    store.compare_and_swap_tenant(_record(), expected_version=0)
    assert conn.committed == 0
    conn.fail_on = "INSERT INTO control_audit"
    raised = False
    try:
        store.append_audit(_audit_record())
    except RuntimeError:
        raised = True
    assert raised, "the audit failure must propagate (fail closed)"
    assert conn.rolled_back == 1, "the failed audit append must roll back the open transaction (CAS discarded)"
    assert conn.committed == 0, "no partial state may commit"


_TESTS = [
    test_tenant_record_version_defaults_to_zero,
    test_concurrency_error_is_a_distinct_typed_error,
    test_inmemory_cas_success_increments_version,
    test_inmemory_cas_stale_version_fails_closed,
    test_inmemory_cas_unknown_tenant_fails_closed,
    test_registry_transition_cas_success_increments_version_once,
    test_registry_transition_cas_conflict_no_state_change_no_orphan_audit,
    test_a1_noop_does_not_increment_version_or_reach_cas,
    test_verify_conflict_yields_to_suspended_winner,
    test_verify_conflict_bounded_retry_succeeds_when_still_mid_flight,
    test_verify_conflict_twice_fails_closed,
    test_verify_conflict_ready_winner_fails_closed,
    test_lifecycle_service_cas_success_and_conflict,
    test_durable_cas_predicates_on_version_and_defers_commit,
    test_durable_cas_conflict_rolls_back_and_raises,
    test_durable_audit_failure_rolls_back_uncommitted_cas,
]

if __name__ == "__main__":
    for _t in _TESTS:
        _t()
        print("PASS:", _t.__name__)
    print("ALL PASSED")
