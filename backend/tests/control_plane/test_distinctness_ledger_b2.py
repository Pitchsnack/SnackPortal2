"""Durable Distinctness Ledger — PRD 06 B-2 (controlled non-production; no live PostgreSQL).

Covers the durable `DistinctnessLedger` adapter (structure + construction-no-I/O + SQL/row
reconstruction via a fake connection + fail-closed reads), the preserved in-memory default
(env-unset composition + inventory semantics), the 07D-1 selection contract ('postgres' composes
the durable ledger lazily; unknown values fail closed with ValueError), and the B-2
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
    DistinctnessCollisionError,
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
# PRD 07D-2b.2a (IC-002 recovery-core amendment): + Quarantined; + the 7 recovery/compensation
# event names (exact spellings frozen — the {Started} vs {Requested} asymmetry is intentional;
# TenantDeprovision* became emitting in 07D-2b.2b via RecoveryCompensationService). Kept in
# LOCKSTEP with the copies in tests/control_plane/test_onboarding_orchestration.py.
EXPECTED_STATES = {
    "Registered",
    "Provisioning",
    "Verifying",
    "Ready",
    "Suspended",
    "Failed",
    "Quarantined",
    "Decommissioned",
}
EXPECTED_EVENT_ACTIONS = {
    "TenantRegistered",
    "DatabaseProvisionRequested",
    "DatabaseProvisionSucceeded",
    "DatabaseProvisionFailed",
    "DatabaseAssociated",
    "SecretReferenceRegistered",
    "TenantSchemaApplicationStarted",
    "TenantSchemaApplicationSucceeded",
    "TenantSchemaApplicationFailed",
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
    "TenantQuarantined",
    "OnboardingRecoveryStarted",
    "OnboardingRecoveryCompleted",
    "OnboardingRecoveryFailed",
    "TenantDeprovisionRequested",
    "TenantDeprovisionCompleted",
    "TenantDeprovisionFailed",
}
_CONTROL_STORE_METHODS = frozenset(
    {
        "is_reachable",
        "schema_version",
        "put_tenant",
        # PRD 07D-2e (D-2e-2): the dedicated optimistic-concurrency lifecycle write — the ONLY
        # port addition of the CAS slice, moved in lockstep with the ControlStore ABC.
        "compare_and_swap_tenant",
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


class _ResolveError(RuntimeError):
    """Unique sentinel raised by the SecretStore.resolve() path (distinct from any connect error)."""


class _RaisingResolveStore(_FakeSecretStore):
    """A SecretStore whose resolve() always raises _ResolveError (the D-14 resolve-failure path)."""

    def resolve(self, ref: SecretRef) -> SecretValue:
        raise _ResolveError("control-db secret reference unresolvable")


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


class _FilteringFakeCursor(_FakeCursor):
    """A fake cursor that HONORS `WHERE tenant_id <> %s`: fetchall() filters self.rows by the bound
    subject param from the executed SQL. This makes data-level subject exclusion observable — if the
    adapter dropped or inverted the WHERE clause, the subject row would leak and the test would fail."""

    def fetchall(self):
        if self.executed:
            sql, params = self.executed[-1]
            if "tenant_id <> %s" in sql.lower() and params:
                subject = str(params[0])
                return [r for r in self.rows if str(r[0]) != subject]
        return self.rows


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


# Canonical durable-ledger column order — the contract the adapter SQL, the row decode, and the DDL
# all share. _LEDGER_COLUMNS is the SELECT projection (inventory key + the 7 evidence fields);
# _INSERT_COLUMNS adds recorded_at (write-only freshness). Used by the alignment tests below.
_DATA_COLUMNS = (
    "system_identifier",
    "database_identity",
    "observed_target",
    "secret_ref_key",
    "sentinel_namespace",
    "sentinel_token",
    "sentinel_written",
)
_LEDGER_COLUMNS = ("tenant_id",) + _DATA_COLUMNS
_INSERT_COLUMNS = _LEDGER_COLUMNS + ("recorded_at",)


def _insert_columns():
    """The adapter INSERT column list (between the first '(' after the table and ') VALUES')."""
    seg = ledger_mod._UPSERT.lower().split("insert into", 1)[1]
    inner = seg[seg.index("(") + 1 : seg.index(")")]
    return tuple(c.strip() for c in inner.split(","))


def _select_columns():
    """The adapter SELECT projection column list (between 'select' and 'from')."""
    proj = ledger_mod._SELECT_EXCLUDING.lower().split("select", 1)[1].split("from", 1)[0]
    return tuple(c.strip() for c in proj.split(","))


def _parse_ddl_columns(sql):
    """Ordered [(name, definition_lower), ...] for each column in the CREATE TABLE body — comments
    stripped, paren-depth-aware top-level-comma split (so `default now()` does not break parsing)."""
    body = _ddl_body(sql)
    start = body.index("(")
    depth = 0
    end = start
    for i in range(start, len(body)):
        if body[i] == "(":
            depth += 1
        elif body[i] == ")":
            depth -= 1
            if depth == 0:
                end = i
                break
    inner = body[start + 1 : end]
    chunks = []
    buf = ""
    depth = 0
    for ch in inner:
        if ch == "(":
            depth += 1
            buf += ch
        elif ch == ")":
            depth -= 1
            buf += ch
        elif ch == "," and depth == 0:
            chunks.append(buf)
            buf = ""
        else:
            buf += ch
    if buf.strip():
        chunks.append(buf)
    cols = []
    for c in chunks:
        toks = c.split()
        if toks:
            cols.append((toks[0], " ".join(toks)))
    return cols


def _with_ledger_env(value):
    """Set/clear SP2_CP_DISTINCTNESS_LEDGER (value=None -> unset); returns a restore() callable."""
    saved = os.environ.get(cp_main.DISTINCTNESS_LEDGER_ENV)
    if value is None:
        os.environ.pop(cp_main.DISTINCTNESS_LEDGER_ENV, None)
    else:
        os.environ[cp_main.DISTINCTNESS_LEDGER_ENV] = value

    def restore():
        if saved is None:
            os.environ.pop(cp_main.DISTINCTNESS_LEDGER_ENV, None)
        else:
            os.environ[cp_main.DISTINCTNESS_LEDGER_ENV] = saved

    return restore


# PRD 07D-2a: the durable ledger is selectable only in the ALL-FOUR-postgres composition (coherence
# matrix RULE 1 — ledger=postgres alone, or ledger+control-store without provisioning, would let
# fabricated in-memory evidence be durably recorded). These tests therefore compose all four.
_ALL_SELECTOR_ENVS = (
    cp_main.CONTROL_STORE_ENV,
    cp_main.PROVISIONING_ADAPTER_ENV,
    cp_main.TENANT_SCHEMA_APPLICATOR_ENV,
    cp_main.DISTINCTNESS_LEDGER_ENV,
)


def _with_all_selectors_postgres():
    """Set ALL FOUR selectors to 'postgres'; returns a restore() callable."""
    saved = {name: os.environ.get(name) for name in _ALL_SELECTOR_ENVS}
    for name in _ALL_SELECTOR_ENVS:
        os.environ[name] = "postgres"

    def restore():
        for name, old in saved.items():
            if old is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = old

    return restore


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


def test_postgres_ledger_selection_composes_durable_lazily() -> None:
    # PRD 07D-1 (was: deferred), under the 07D-2a coherence matrix: the durable ledger is selected
    # via the ALL-FOUR-postgres composition (RULE 1 — ledger-alone is a forbidden mix) — still
    # lazy-connect (construction opens NO connection; the connect recorder proves zero I/O) over
    # the B-7B control-store secret binding.
    restore_e = _with_all_selectors_postgres()
    calls = []
    restore_c = _patch_connect(lambda *a, **k: calls.append((a, k)))
    try:
        cp = cp_main.ControlPlane()
        assert isinstance(cp.provisioning._ledger, ledger_mod.PostgresDistinctnessLedger), "postgres must select the durable ledger"
        assert calls == [], "durable-ledger selection must open no connection at construction (lazy)"
    finally:
        restore_c()
        restore_e()


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


# === PRD 06 B-2 tests-only hardening (V3 WP-H1..H6 + addendum WP-H7..H15) ========================
def test_durable_evidence_excluding_excludes_subject_row() -> None:
    # WP-H1 / WP-H8: data-level subject exclusion. The filtering fake honors WHERE tenant_id <> %s,
    # so a dropped/inverted clause leaks the subject row and fails this test (not just SQL shape).
    rows = [
        ("t1", "sysA", "t1:1", "sp2_tenant_t1", "sp2_tenant_t1", "dv_sentinel_t1", "tok1", True),
        ("t2", "sysB", "t2:2", "sp2_tenant_t2", "sp2_tenant_t2", "dv_sentinel_t2", "tok2", True),
    ]
    cur = _FilteringFakeCursor(rows=rows)
    restore = _patch_connect(_FakeConn(cur))
    try:
        inv = _adapter().evidence_excluding("t1")
        sql, params = cur.executed[0]
        assert "where tenant_id <> %s" in sql.lower() and params == ("t1",)  # WP-H8 shape
        assert "t1" not in inv, "subject tenant must be excluded at the data level"
        assert set(inv.keys()) == {"t2"}
    finally:
        restore()


def test_inmemory_subject_exclusion_is_data_level() -> None:
    # WP-H9: the in-memory ledger (production default) genuinely filters — the SUBJECT is the
    # dropped key (not merely "one key dropped"), and the kept evidence round-trips exactly.
    led = InMemoryDistinctnessLedger()
    led.record_evidence("t1", _ev("t1", database_identity="t1:AA"))
    led.record_evidence("t2", _ev("t2", database_identity="t2:BB"))
    out = led.evidence_excluding("t1")
    assert set(out.keys()) == {"t2"}
    assert "t1" not in out
    assert out["t2"].database_identity == "t2:BB"


def test_durable_read_field_fidelity_all_seven() -> None:
    # WP-H2: every reconstructed DistinctnessEvidence field decodes from the correct row column.
    # The fed tuple is built in the adapter's ACTUAL SELECT projection order, with a distinct value
    # per column, so a decode transposition is caught. All seven live fields are asserted.
    select_cols = _select_columns()
    assert select_cols[0] == "tenant_id"
    values = {c: f"V_{c}" for c in select_cols}
    values["tenant_id"] = "tX"
    values["sentinel_written"] = True
    row = tuple(values[c] for c in select_cols)
    cur = _FakeCursor(rows=[row])
    restore = _patch_connect(_FakeConn(cur))
    try:
        ev = _adapter().evidence_excluding("subject")["tX"]
        assert ev.system_identifier == "V_system_identifier"
        assert ev.database_identity == "V_database_identity"
        assert ev.observed_target == "V_observed_target"
        assert ev.secret_ref_key == "V_secret_ref_key"
        assert ev.sentinel_namespace == "V_sentinel_namespace"
        assert ev.sentinel_token == "V_sentinel_token"
        assert ev.sentinel_written is True
        assert set(_DATA_COLUMNS) == {f.name for f in dataclasses.fields(DistinctnessEvidence)}
    finally:
        restore()


def test_durable_read_null_and_bool_coercion() -> None:
    # WP-H12: NULL sentinel_token decodes to None (not "None"); a falsey sentinel_written -> False.
    select_cols = _select_columns()
    values = {c: f"v_{c}" for c in select_cols}
    values["tenant_id"] = "tN"
    values["sentinel_token"] = None
    values["sentinel_written"] = 0
    row = tuple(values[c] for c in select_cols)
    cur = _FakeCursor(rows=[row])
    restore = _patch_connect(_FakeConn(cur))
    try:
        ev = _adapter().evidence_excluding("s")["tN"]
        assert ev.sentinel_token is None, "NULL sentinel_token must decode to None, not 'None'"
        assert ev.sentinel_written is False, "falsey sentinel_written must coerce to False"
    finally:
        restore()


def test_write_insert_param_ddl_alignment() -> None:
    # WP-H3: INSERT column order == record_evidence param order == DDL column order, proven with a
    # DISTINCT value per field so a write-side transposition is caught (the existing upsert test uses
    # equal observed_target/secret_ref_key values and would miss that swap).
    insert_cols = _insert_columns()
    ddl_order = tuple(name for name, _ in _parse_ddl_columns(_DDL.read_text(encoding="utf-8")))
    assert insert_cols == _INSERT_COLUMNS, insert_cols
    assert ddl_order == _INSERT_COLUMNS, ddl_order
    ev = _ev(
        "tW",
        system_identifier="SYS",
        database_identity="DBID",
        observed_target="TGT",
        secret_ref_key="REF",
        sentinel_namespace="NS",
        sentinel_token="TOK",
        sentinel_written=True,
    )
    cur = _FakeCursor()
    restore = _patch_connect(_FakeConn(cur))
    try:
        _adapter().record_evidence("tW", ev)
        _, params = cur.executed[0]
        by_col = dict(zip(insert_cols, params))
        assert by_col["tenant_id"] == "tW"
        assert by_col["system_identifier"] == "SYS"
        assert by_col["database_identity"] == "DBID"
        assert by_col["observed_target"] == "TGT"
        assert by_col["secret_ref_key"] == "REF"
        assert by_col["sentinel_namespace"] == "NS"
        assert by_col["sentinel_token"] == "TOK"
        assert by_col["sentinel_written"] is True
    finally:
        restore()


def test_read_select_ddl_alignment() -> None:
    # WP-H10: the SELECT projection order == the canonical column order == the DDL data-column order
    # (the read-side twin of WP-H3). The decode r[i]->field mapping is pinned by the read-fidelity
    # test above; this pins that the DB columns the decode reads are the ones it expects.
    assert _select_columns() == _LEDGER_COLUMNS, _select_columns()
    ddl_order = tuple(name for name, _ in _parse_ddl_columns(_DDL.read_text(encoding="utf-8")))
    assert ddl_order == _INSERT_COLUMNS
    assert _LEDGER_COLUMNS == _INSERT_COLUMNS[:-1]  # SELECT omits recorded_at (write-only)


def test_resolve_failure_fails_closed_all_methods() -> None:
    # WP-H11 / WP-H4: a SecretStore.resolve() failure on ANY operation fails closed (propagates the
    # exact resolve error) and never reaches psycopg.connect (proving the resolve path, not connect).
    connect_calls = []
    restore = _patch_connect(lambda *a, **k: connect_calls.append((a, k)))
    try:
        adapter = ledger_mod.PostgresDistinctnessLedger(_RaisingResolveStore(), _CONTROL_REF)
        for op in (
            lambda: adapter.record_evidence("t1", _ev("t1")),
            lambda: adapter.evidence_excluding("t1"),
            lambda: adapter.remove("t1"),
        ):
            raised = False
            try:
                op()
            except _ResolveError:
                raised = True
            assert raised, "resolve() failure must propagate (fail-closed) on every method"
        assert connect_calls == [], "connect must never be reached when resolve() fails"
    finally:
        restore()


def test_ledger_flag_normalization_table() -> None:
    # WP-H5 (07D-1 update): only unset/''/'in_memory' (after strip+lower) map to in-memory;
    # 'postgres' SELECTS the durable ledger (composition activation); every OTHER token fails
    # closed with ValueError (never a silent fallback).
    for value in (None, "", "in_memory", " in_memory ", "IN_MEMORY", "In_Memory"):
        restore = _with_ledger_env(value)
        try:
            cp = cp_main.ControlPlane()
            assert isinstance(cp.provisioning._ledger, InMemoryDistinctnessLedger), f"{value!r} -> in-memory"
        finally:
            restore()
    # 07D-2a: 'postgres' selects the durable ledger only in the ALL-FOUR composition (RULE 1).
    restore = _with_all_selectors_postgres()
    try:
        cp = cp_main.ControlPlane()
        assert isinstance(cp.provisioning._ledger, ledger_mod.PostgresDistinctnessLedger), "'postgres' -> durable"
    finally:
        restore()
    for value in ("durable", "control_db", "true", "x"):
        restore = _with_ledger_env(value)
        try:
            raised = False
            try:
                cp_main.ControlPlane()
            except ValueError:
                raised = True
            assert raised, f"{value!r} must fail closed with ValueError (no silent fallback)"
        finally:
            restore()


def test_unknown_selection_raises_with_zero_io() -> None:
    # WP-H13 (07D-1 update): the unsupported selection is a pure string check — it raises
    # ValueError with NO psycopg.connect before raising (no partial side effect / no live I/O).
    connect_calls = []
    restore_c = _patch_connect(lambda *a, **k: connect_calls.append((a, k)))
    try:
        for value in ("durable", "control_db", "true", "x"):
            restore_e = _with_ledger_env(value)
            try:
                raised = False
                try:
                    cp_main.ControlPlane()
                except ValueError:
                    raised = True
                assert raised, f"{value!r} must raise ValueError"
            finally:
                restore_e()
        assert connect_calls == [], "a rejected selection must not open a connection before raising"
    finally:
        restore_c()


def test_ddl_set_equality_pk_and_nullability() -> None:
    # WP-H6: exact column set == {tenant_id, recorded_at} + evidence fields; tenant_id PRIMARY KEY;
    # sentinel_token nullable; every other required column NOT NULL. Robust per-column parse.
    cols = dict(_parse_ddl_columns(_DDL.read_text(encoding="utf-8")))
    ev_fields = {f.name for f in dataclasses.fields(DistinctnessEvidence)}
    assert set(cols) == ev_fields | {"tenant_id", "recorded_at"}, set(cols)
    assert "primary key" in cols["tenant_id"]
    assert "not null" not in cols["sentinel_token"], "sentinel_token must be nullable"
    for required in (ev_fields - {"sentinel_token"}) | {"recorded_at"}:
        assert "not null" in cols[required], f"{required} must be NOT NULL"


def test_adapter_sql_columns_subset_of_ddl() -> None:
    # WP-H14: every column the adapter SQL references exists in the DDL (closed-world), and the upsert
    # is single-row-per-tenant (conflict target == tenant_id, the first INSERT column / PK).
    ddl_cols = {name for name, _ in _parse_ddl_columns(_DDL.read_text(encoding="utf-8"))}
    referenced = set(_insert_columns()) | set(_select_columns()) | {"tenant_id"}
    set_clause = ledger_mod._UPSERT.lower().split("do update set", 1)[1]
    referenced |= {seg.split("=", 1)[0].strip() for seg in set_clause.split(",")}
    assert referenced <= ddl_cols, f"adapter references columns absent from DDL: {referenced - ddl_cols}"
    assert "on conflict (tenant_id) do update" in ledger_mod._UPSERT.lower()
    assert _insert_columns()[0] == "tenant_id"


# === PRD 07D-2c — typed fingerprint-collision refusal (adapter mapping + in-memory parity) =======
class _SqlstateError(RuntimeError):
    """Driver-shaped error carrying a SQLSTATE (the duck-typed attribute the adapter maps on)."""

    def __init__(self, msg: str, sqlstate: str) -> None:
        super().__init__(msg)
        self.sqlstate = sqlstate


class _ExcRaisingCursor(_FakeCursor):
    """Fake cursor whose execute raises a GIVEN exception (records the SQL first)."""

    def __init__(self, exc: Exception) -> None:
        super().__init__()
        self._exc = exc

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        raise self._exc


def test_2c_durable_collision_sqlstate_maps_to_typed_error() -> None:
    # MC-1 kill site (unit leg): a unique-violation SQLSTATE 23505 from record_evidence maps to
    # the typed, driver-free DistinctnessCollisionError; no commit; the connection still closes.
    driver_exc = _SqlstateError("unique violation", "23505")
    cur = _ExcRaisingCursor(driver_exc)
    conn = _FakeConn(cur)
    restore = _patch_connect(conn)
    try:
        raised = None
        try:
            _adapter().record_evidence("t2", _ev("t2"))
        except DistinctnessCollisionError as exc:
            raised = exc
        assert raised is not None, "SQLSTATE 23505 must map to DistinctnessCollisionError"
        assert raised.__cause__ is driver_exc, "the driver error must be chained as the cause"
        assert conn.committed == 0, "a losing write must not commit"
        assert conn.closed == 1, "the connection must still be closed"
    finally:
        restore()


def test_2c_durable_other_errors_propagate_unmapped() -> None:
    # D-4: EVERY other error keeps propagating unchanged (the fail-closed-by-raise contract is
    # untouched): a non-23505 SQLSTATE and a sqlstate-less error both surface as themselves.
    for exc in (_SqlstateError("not-null violation", "23502"), RuntimeError("connection dropped")):
        cur = _ExcRaisingCursor(exc)
        conn = _FakeConn(cur)
        restore = _patch_connect(conn)
        try:
            raised = None
            try:
                _adapter().record_evidence("t1", _ev("t1"))
            except Exception as got:
                raised = got
            assert raised is exc, f"non-collision errors must propagate unchanged, got {raised!r}"
            assert not isinstance(raised, DistinctnessCollisionError)
            assert conn.committed == 0 and conn.closed == 1
        finally:
            restore()


def test_2c_collision_parity_in_memory_and_durable() -> None:
    # D-5 parity pair (MC-2 kill site): both ledgers raise the IDENTICAL typed error under the
    # IDENTICAL predicate — ANOTHER tenant already holding an equal fingerprint. Same-tenant
    # re-record (upsert) stays legal; distinct-fingerprint multi-tenant recording stays legal.
    led = InMemoryDistinctnessLedger()
    led.record_evidence("t1", _ev("t1", system_identifier="sysX", database_identity="db:9"))
    led.record_evidence("t1", _ev("t1", system_identifier="sysX", database_identity="db:9"))  # same-tenant upsert legal
    led.record_evidence("t2", _ev("t2"))  # distinct fingerprint legal
    in_memory_raised = None
    try:
        led.record_evidence("t3", _ev("t3", system_identifier="sysX", database_identity="db:9"))
    except DistinctnessCollisionError as exc:
        in_memory_raised = exc
    assert in_memory_raised is not None, "in-memory: an equal fingerprint under another tenant must refuse"
    assert set(led.evidence_excluding("").keys()) == {"t1", "t2"}, "the losing write must record nothing"

    cur = _ExcRaisingCursor(_SqlstateError("unique violation", "23505"))
    restore = _patch_connect(_FakeConn(cur))
    try:
        durable_raised = None
        try:
            _adapter().record_evidence("t3", _ev("t3", system_identifier="sysX", database_identity="db:9"))
        except DistinctnessCollisionError as exc:
            durable_raised = exc
        assert durable_raised is not None, "durable: the mapped 23505 must refuse identically"
    finally:
        restore()
    assert type(in_memory_raised) is type(durable_raised) is DistinctnessCollisionError, "IDENTICAL typed error on both paths"


_TESTS = [
    test_inmemory_inventory_semantics,
    test_default_ledger_is_in_memory,
    test_postgres_ledger_selection_composes_durable_lazily,
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
    test_durable_evidence_excluding_excludes_subject_row,
    test_inmemory_subject_exclusion_is_data_level,
    test_durable_read_field_fidelity_all_seven,
    test_durable_read_null_and_bool_coercion,
    test_write_insert_param_ddl_alignment,
    test_read_select_ddl_alignment,
    test_resolve_failure_fails_closed_all_methods,
    test_ledger_flag_normalization_table,
    test_unknown_selection_raises_with_zero_io,
    test_ddl_set_equality_pk_and_nullability,
    test_adapter_sql_columns_subset_of_ddl,
    test_no_new_lifecycle_states,
    test_no_new_audit_vocabulary,
    test_control_store_port_frozen,
    test_distinctness_ledger_abc_unchanged,
    test_ddl_is_reference_only_idempotent_additive,
    test_ledger_row_matches_evidence_fields,
    test_adapter_applies_no_ddl,
    test_2c_durable_collision_sqlstate_maps_to_typed_error,
    test_2c_durable_other_errors_propagate_unmapped,
    test_2c_collision_parity_in_memory_and_durable,
]

if __name__ == "__main__":
    for _t in _TESTS:
        _t()
        print("PASS:", _t.__name__)
    print("ALL PASSED")
