"""Durable Distinctness Ledger — PRD 06 B-2 (controlled non-production; no live PostgreSQL).

Covers the durable `DistinctnessLedger` adapter (structure + construction-no-I/O + SQL/row
reconstruction via a fake connection + fail-closed reads), the preserved in-memory default
(env-unset composition + inventory semantics), the deferred-selection guard, and the B-2
baselines (no new IC-002 state / audit vocabulary; the `ControlStore` port and the
`DistinctnessLedger` ABC are frozen; the DDL is reference-only / additive / created-not-applied).

The live record/read of the durable adapter against a real Control DB is B-4 (see
`requires_pg/test_pg_distinctness_ledger.py`); this suite opens NO live connection. Per the
Driver Containment Standard the test never imports `psycopg` directly — it reaches the driver
only through the adapter module's attribute, so the architecture driver-containment scan stays
clean. Pure stdlib; standalone-runnable:
`python tests/control_plane/test_distinctness_ledger_b2.py`.
"""

from __future__ import annotations

import dataclasses
import os
import pathlib
import sys
from datetime import datetime, timedelta

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))  # backend on path

from control_plane import events  # noqa: E402
from control_plane import main as cp_main  # noqa: E402
from control_plane.adapters.providers import postgres_distinctness_ledger as ledger_mod  # noqa: E402
from control_plane.distinctness import (  # noqa: E402
    DistinctnessEvidence,
    DistinctnessLedger,
    InMemoryDistinctnessLedger,
)
from control_plane.ports import ControlStore  # noqa: E402
from control_plane.records import TenantLifecycleState  # noqa: E402
from shared.secrets import SecretRef, SecretStore, SecretValue  # noqa: E402

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
_DDL = _REPO_ROOT / "infrastructure" / "db" / "control" / "001_distinctness_ledger.sql"
_ADAPTER_SRC = _REPO_ROOT / "backend" / "control_plane" / "adapters" / "providers" / "postgres_distinctness_ledger.py"

# Baselines mirrored from the B-1 onboarding orchestration guards — B-2 adds NO lifecycle state
# and NO audit event. A future legitimate addition updates both guards (defense in depth).
EXPECTED_STATES = {"Registered", "Provisioning", "Verifying", "Ready", "Suspended", "Failed", "Decommissioned"}
EXPECTED_EVENT_ACTIONS = {
    "TenantRegistered",
    "DatabaseProvisionRequested",
    "DatabaseProvisionSucceeded",
    "DatabaseProvisionFailed",
    "DatabaseAssociated",
    "SecretReferenceRegistered",
    "DistinctnessVerificationStarted",
    "DistinctnessVerificationPassed",
    "DistinctnessVerificationFailed",
    "VerificationIncomplete",
    "IsolationAnomaly",
    "RoutingEnabled",
    "RoutingDisabled",
    "RouterCacheInvalidated",
    "RegistryMappingChanged",
    "TenantSuspended",
    "TenantReactivated",
    "TenantDecommissionStarted",
    "TenantDecommissionCompleted",
}
_CONTROL_STORE_METHODS = frozenset(
    {
        "is_reachable",
        "schema_version",
        "put_tenant",
        "get_tenant",
        "list_tenant_ids",
        "put_membership",
        "list_memberships",
        "put_federation",
        "get_federation",
        "put_directory_record",
        "get_directory_record",
        "list_directory",
        "append_audit",
        "list_audit",
    }
)


# --- test doubles (pure stdlib; no driver, no I/O) ----------------------------------------------
class _FakeSecretStore(SecretStore):
    """Resolves the Control-DB reference to an in-memory descriptor (test-only)."""

    def __init__(self, material: str = "ref-only-descriptor") -> None:
        self._material = material

    def resolve(self, ref: SecretRef) -> SecretValue:
        return SecretValue(self._material)

    def current_version(self, store_ref: str) -> str:
        return "1"


class _SpySecretStore(_FakeSecretStore):
    """A SecretStore that counts resolve() calls (to prove no resolution at construction)."""

    def __init__(self, material: str = "ref-only-descriptor") -> None:
        super().__init__(material)
        self.resolve_calls = 0

    def resolve(self, ref: SecretRef) -> SecretValue:
        self.resolve_calls += 1
        return super().resolve(ref)


class _FakeCursor:
    def __init__(self, rows=None, raise_on_execute=False):
        self.rows = rows or []
        self.executed = []  # list[(sql, params)]
        self._raise = raise_on_execute

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        if self._raise:
            raise RuntimeError("simulated control-DB error")

    def fetchall(self):
        return self.rows

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor
        self.committed = 0
        self.closed = 0

    def cursor(self):
        return self._cursor

    def commit(self):
        self.committed += 1

    def close(self):
        self.closed += 1


_CONTROL_REF = SecretRef(store_ref="sp2_control", version="1")


def _ev(tenant_id="t1", **over):
    base = dict(
        system_identifier="sysA",
        database_identity=f"{tenant_id}:1",
        observed_target=f"sp2_tenant_{tenant_id}",
        secret_ref_key=f"sp2_tenant_{tenant_id}",
        sentinel_namespace=f"dv_sentinel_{tenant_id}",
        sentinel_token=f"tok_{tenant_id}",
        sentinel_written=True,
    )
    base.update(over)
    return DistinctnessEvidence(**base)


def _patch_connect(conn_or_factory):
    """Swap the adapter module's psycopg.connect (the shared driver module attribute). Returns a
    restore() callable. No static `import psycopg` here — the scanner stays clean."""
    orig = ledger_mod.psycopg.connect
    if callable(conn_or_factory):
        ledger_mod.psycopg.connect = conn_or_factory
    else:
        ledger_mod.psycopg.connect = lambda *a, **k: conn_or_factory

    def restore():
        ledger_mod.psycopg.connect = orig

    return restore


def _adapter():
    return ledger_mod.PostgresDistinctnessLedger(_FakeSecretStore(), _CONTROL_REF)


# --- preserved in-memory default + inventory semantics ------------------------------------------
def test_inmemory_inventory_semantics() -> None:
    led = InMemoryDistinctnessLedger()
    led.record_evidence("t1", _ev("t1"))
    led.record_evidence("t2", _ev("t2"))
    assert set(led.evidence_excluding("t1").keys()) == {"t2"}
    assert set(led.evidence_excluding("t2").keys()) == {"t1"}
    # upsert-latest (one row per tenant)
    led.record_evidence("t1", _ev("t1", database_identity="t1:99"))
    assert led.evidence_excluding("t2")["t1"].database_identity == "t1:99"
    led.remove("t1")
    assert set(led.evidence_excluding("t2").keys()) == set()


def test_default_ledger_is_in_memory() -> None:
    # DB2-4 / AC-5: env unset -> the gate's ledger is the in-memory ledger.
    saved = os.environ.pop(cp_main.DISTINCTNESS_LEDGER_ENV, None)
    try:
        cp = cp_main.ControlPlane()
        assert isinstance(cp.provisioning._ledger, InMemoryDistinctnessLedger)
    finally:
        if saved is not None:
            os.environ[cp_main.DISTINCTNESS_LEDGER_ENV] = saved


def test_unsupported_ledger_selection_defers_to_b4() -> None:
    # AC-5: a non-default selection defers to B-4 with NotImplementedError (no silent fallback).
    saved = os.environ.get(cp_main.DISTINCTNESS_LEDGER_ENV)
    os.environ[cp_main.DISTINCTNESS_LEDGER_ENV] = "postgres"
    try:
        raised = False
        try:
            cp_main.ControlPlane()
        except NotImplementedError:
            raised = True
        assert raised, "durable ledger selection must defer to B-4"
    finally:
        if saved is None:
            os.environ.pop(cp_main.DISTINCTNESS_LEDGER_ENV, None)
        else:
            os.environ[cp_main.DISTINCTNESS_LEDGER_ENV] = saved


# --- durable adapter: structure + construction-no-I/O -------------------------------------------
def test_durable_adapter_conforms_to_abc() -> None:
    assert issubclass(ledger_mod.PostgresDistinctnessLedger, DistinctnessLedger)
    adapter = _adapter()
    assert isinstance(adapter, DistinctnessLedger)
    for m in ("record_evidence", "evidence_excluding", "remove"):
        assert callable(getattr(adapter, m))


def test_durable_adapter_construction_opens_no_connection() -> None:
    # TESTABILITY-2 / DB2-4: lazy-connect — __init__ opens no connection.
    calls = []
    restore = _patch_connect(lambda *a, **k: calls.append((a, k)))
    try:
        adapter = _adapter()
        assert calls == [], "construction must open no connection (lazy-connect)"
        assert isinstance(adapter, DistinctnessLedger)
    finally:
        restore()


def test_controlplane_construction_opens_no_connection() -> None:
    # AC / §9: patch the driver connect and assert ControlPlane() construction performs no I/O.
    saved_l = os.environ.pop(cp_main.DISTINCTNESS_LEDGER_ENV, None)
    saved_p = os.environ.pop(cp_main.PROVISIONING_ADAPTER_ENV, None)
    calls = []
    restore = _patch_connect(lambda *a, **k: calls.append((a, k)))
    try:
        cp_main.ControlPlane()
        assert calls == [], "ControlPlane construction must perform no live DB connection"
    finally:
        restore()
        if saved_l is not None:
            os.environ[cp_main.DISTINCTNESS_LEDGER_ENV] = saved_l
        if saved_p is not None:
            os.environ[cp_main.PROVISIONING_ADAPTER_ENV] = saved_p


def test_durable_adapter_holds_no_secret_value() -> None:
    # D-14: the adapter retains only references (the SecretStore + the SecretRef), never the
    # resolved descriptor/secret value — and it resolves NOTHING at construction (lazy).
    secret_material = "postgresql://u:pw@h:5432/control"
    spy = _SpySecretStore(secret_material)
    adapter = ledger_mod.PostgresDistinctnessLedger(spy, _CONTROL_REF)
    assert spy.resolve_calls == 0, "construction must not resolve the secret (no descriptor materialized)"
    for value in vars(adapter).values():
        assert secret_material not in repr(value), "adapter must not retain the resolved secret/DSN value"
    assert adapter._control_db_ref == _CONTROL_REF


# --- durable adapter: SQL + row reconstruction via a fake connection (no live PG) ---------------
def test_durable_record_evidence_upserts_reference_only() -> None:
    cur = _FakeCursor()
    conn = _FakeConn(cur)
    restore = _patch_connect(conn)
    try:
        _adapter().record_evidence("t1", _ev("t1", sentinel_token="tok1"))
        assert len(cur.executed) == 1
        sql, params = cur.executed[0]
        assert "insert into control_distinctness_ledger" in sql.lower()
        assert "on conflict (tenant_id) do update" in sql.lower()
        assert params[0] == "t1"
        assert params[1:8] == ("sysA", "t1:1", "sp2_tenant_t1", "sp2_tenant_t1", "dv_sentinel_t1", "tok1", True)
        # recorded_at must be a real timezone-aware UTC ISO-8601 timestamp (not merely "contains T")
        assert isinstance(params[8], str)
        recorded = datetime.fromisoformat(params[8])
        assert recorded.tzinfo is not None and recorded.utcoffset() == timedelta(0), "recorded_at must be UTC"
        assert conn.committed == 1 and conn.closed == 1
        # reference-only: the resolved descriptor never enters the persisted row
        assert all("ref-only-descriptor" not in str(p) for p in params)
    finally:
        restore()


def test_durable_record_evidence_handles_null_sentinel_token() -> None:
    cur = _FakeCursor()
    restore = _patch_connect(_FakeConn(cur))
    try:
        _adapter().record_evidence("t1", _ev("t1", sentinel_token=None, sentinel_written=False))
        _, params = cur.executed[0]
        assert params[6] is None and params[7] is False
    finally:
        restore()


def test_durable_evidence_excluding_reconstructs_inventory() -> None:
    rows = [
        ("t2", "sysB", "t2:2", "sp2_tenant_t2", "sp2_tenant_t2", "dv_sentinel_t2", "tok2", True),
        ("t3", "sysC", "t3:3", "sp2_tenant_t3", "sp2_tenant_t3", "dv_sentinel_t3", None, False),
    ]
    cur = _FakeCursor(rows=rows)
    conn = _FakeConn(cur)
    restore = _patch_connect(conn)
    try:
        inv = _adapter().evidence_excluding("t1")
        sql, params = cur.executed[0]
        assert "where tenant_id <> %s" in sql.lower()
        assert params == ("t1",)
        assert set(inv.keys()) == {"t2", "t3"}
        assert isinstance(inv["t2"], DistinctnessEvidence)
        assert inv["t2"].system_identifier == "sysB" and inv["t2"].sentinel_token == "tok2" and inv["t2"].sentinel_written is True
        assert inv["t3"].sentinel_token is None and inv["t3"].sentinel_written is False
        assert conn.closed == 1
    finally:
        restore()


def test_durable_evidence_excluding_fails_closed_on_error() -> None:
    # Load-bearing: a read error must PROPAGATE (gate fails closed), never return an empty
    # inventory (which would hide a tenant-vs-tenant collision = fail-open).
    cur = _FakeCursor(raise_on_execute=True)
    conn = _FakeConn(cur)
    restore = _patch_connect(conn)
    try:
        raised = False
        try:
            _adapter().evidence_excluding("t1")
        except RuntimeError:
            raised = True
        assert raised, "evidence_excluding must propagate read errors (fail-closed), never return {}"
        assert conn.closed == 1, "connection must still be closed on error"
    finally:
        restore()


def test_durable_remove_deletes_by_tenant() -> None:
    cur = _FakeCursor()
    conn = _FakeConn(cur)
    restore = _patch_connect(conn)
    try:
        _adapter().remove("t1")
        sql, params = cur.executed[0]
        assert "delete from control_distinctness_ledger" in sql.lower()
        assert params == ("t1",)
        assert conn.committed == 1 and conn.closed == 1
    finally:
        restore()


def test_durable_all_methods_fail_closed_on_connect_error() -> None:
    # Fail-closed across the whole adapter: if the connection cannot be opened, every operation
    # propagates the error (the gate aborts before Ready) — none silently succeeds.
    def _boom(*a, **k):
        raise RuntimeError("connect refused")

    restore = _patch_connect(_boom)
    try:
        adapter = _adapter()
        for op in (
            lambda: adapter.record_evidence("t1", _ev("t1")),
            lambda: adapter.evidence_excluding("t1"),
            lambda: adapter.remove("t1"),
        ):
            raised = False
            try:
                op()
            except RuntimeError:
                raised = True
            assert raised, "connect failure must propagate (fail-closed)"
    finally:
        restore()


def test_durable_mutations_no_partial_commit_on_execute_error() -> None:
    # A failing write must NOT commit and must still close the connection (no partial commit).
    for op_name in ("record_evidence", "remove"):
        cur = _FakeCursor(raise_on_execute=True)
        conn = _FakeConn(cur)
        restore = _patch_connect(conn)
        try:
            adapter = _adapter()
            raised = False
            try:
                if op_name == "record_evidence":
                    adapter.record_evidence("t1", _ev("t1"))
                else:
                    adapter.remove("t1")
            except RuntimeError:
                raised = True
            assert raised, f"{op_name} must propagate the write error (fail-closed)"
            assert conn.committed == 0, f"{op_name} must not commit on error (no partial commit)"
            assert conn.closed == 1, f"{op_name} must still close the connection on error"
        finally:
            restore()


def test_upsert_updates_each_column_from_excluded() -> None:
    # Guards against a transposed EXCLUDED.<col> in the upsert (a column-mapping regression the
    # fake-cursor SQL-text tests would otherwise miss). The fake cursor records SQL text only.
    sql = ledger_mod._UPSERT.lower()
    set_clause = sql.split("do update set", 1)[1]
    for col in (
        "system_identifier",
        "database_identity",
        "observed_target",
        "secret_ref_key",
        "sentinel_namespace",
        "sentinel_token",
        "sentinel_written",
        "recorded_at",
    ):
        assert f"{col} = excluded.{col}" in set_clause, f"upsert must set {col} from EXCLUDED.{col}"
    assert "tenant_id = excluded" not in set_clause, "the primary key (tenant_id) must not be reassigned"


# --- B-2 baselines: frozen port / frozen ABC / no new state / no new vocabulary -----------------
def test_no_new_lifecycle_states() -> None:
    assert {s.value for s in TenantLifecycleState} == EXPECTED_STATES


def test_no_new_audit_vocabulary() -> None:
    actions = {v for k, v in vars(events).items() if k.isupper() and isinstance(v, str)}
    assert actions == EXPECTED_EVENT_ACTIONS


def test_control_store_port_frozen() -> None:
    # DB2-1: the durable ledger is a separate adapter; the ControlStore port is NOT extended.
    assert ControlStore.__abstractmethods__ == _CONTROL_STORE_METHODS


def test_distinctness_ledger_abc_unchanged() -> None:
    assert DistinctnessLedger.__abstractmethods__ == frozenset({"record_evidence", "evidence_excluding", "remove"})


# --- DDL: reference-only / additive / created-not-applied; grounded in the live evidence ---------
def _ddl_body(sql: str) -> str:
    """The executable DDL with -- comments stripped (so prohibition wording in comments does not
    trip the secret-token scan)."""
    out = []
    for line in sql.splitlines():
        code = line.split("--", 1)[0]
        if code.strip():
            out.append(code)
    return "\n".join(out).lower()


def test_ddl_is_reference_only_idempotent_additive() -> None:
    body = _ddl_body(_DDL.read_text(encoding="utf-8"))
    assert "create table if not exists control_distinctness_ledger" in body
    # additive + non-destructive
    for destructive in ("drop table", "drop column", "truncate", "alter table"):
        assert destructive not in body, f"DDL must be additive; found {destructive!r}"
    # reference-only: no credential/secret columns or literals in the executable DDL
    for forbidden in ("password", "passwd", "secret_value", "connection_string", "private key", "jwt", "api_key", " dsn"):
        assert forbidden not in body, f"DDL must be reference-only; found {forbidden!r}"


def test_ledger_row_matches_evidence_fields() -> None:
    body = _ddl_body(_DDL.read_text(encoding="utf-8"))
    ev_fields = {f.name for f in dataclasses.fields(DistinctnessEvidence)}
    for field in ev_fields:
        assert field in body, f"DDL must persist evidence field {field}"
    assert "tenant_id" in body and "recorded_at" in body
    # C-2 guard: no invented parallel-evidence schema
    for invented in ("evidence_digest", "algorithm_version", "comparison_scope", "provider_name", "control_db_reference_digest"):
        assert invented not in body, f"DDL must not invent a parallel schema; found {invented!r}"


def test_adapter_applies_no_ddl() -> None:
    # The durable adapter reads/writes rows only; it never creates/alters/drops schema (DDL is
    # created-not-applied; applying it is B-4).
    src = _ADAPTER_SRC.read_text(encoding="utf-8").lower()
    for ddl_kw in ("create table", "create schema", "alter table", "drop table", "drop schema", "create index"):
        assert ddl_kw not in src, f"adapter must not apply DDL; found {ddl_kw!r}"


_TESTS = [
    test_inmemory_inventory_semantics,
    test_default_ledger_is_in_memory,
    test_unsupported_ledger_selection_defers_to_b4,
    test_durable_adapter_conforms_to_abc,
    test_durable_adapter_construction_opens_no_connection,
    test_controlplane_construction_opens_no_connection,
    test_durable_adapter_holds_no_secret_value,
    test_durable_record_evidence_upserts_reference_only,
    test_durable_record_evidence_handles_null_sentinel_token,
    test_durable_evidence_excluding_reconstructs_inventory,
    test_durable_evidence_excluding_fails_closed_on_error,
    test_durable_remove_deletes_by_tenant,
    test_durable_all_methods_fail_closed_on_connect_error,
    test_durable_mutations_no_partial_commit_on_execute_error,
    test_upsert_updates_each_column_from_excluded,
    test_no_new_lifecycle_states,
    test_no_new_audit_vocabulary,
    test_control_store_port_frozen,
    test_distinctness_ledger_abc_unchanged,
    test_ddl_is_reference_only_idempotent_additive,
    test_ledger_row_matches_evidence_fields,
    test_adapter_applies_no_ddl,
]

if __name__ == "__main__":
    for _t in _TESTS:
        _t()
        print("PASS:", _t.__name__)
    print("ALL PASSED")
