"""DBR-AR-2D — durable routing-audit DISPOSABLE live-PostgreSQL proof (standalone-only; SNACKPORTAL_TEST_DSN).

The disposable/hosted sub-slice of the DBR-AR-2D live proof (PRD DBR-AR-2D V2): against a real,
proof-owned PostgreSQL database it applies the reviewed, blob-pinned routing-audit DDL
(infrastructure/db/control/010_routing_audit.sql then 011_routing_audit_append_only.sql — exact
paths, exact order, each exactly once, never a wildcard) and proves the REAL persistence path
end-to-end:

    DatabaseRouter.route() -> BoundedRoutingAuditPolicy -> HttpRoutingAudit
        -> Control-Plane ingest edge (build_routing_audit_server)
        -> PostgresRoutingAuditStore -> disposable PostgreSQL

Test doubles are used ONLY for the tenant connection/pool side of ``route()`` (routing-read view,
tenant secret store, tenant connection factory — the 2C-precedent local doubles); every component
on the audit persistence path is the real production class. Proof set (PRD DBR-AR-2D V2 §7/§8):
reviewed-blob STOP-before-connect; live schema evidence from the PostgreSQL catalogs (exact 20
columns, identity ordering authority, unique ``event_id``, DB-assigned ``recorded_at``, the two
frozen CHECK vocabularies, both append-only triggers); all four event classes (``Route`` /
``RouteControl`` / ``RouteDenied`` / ``IsolationAnomaly``) durably recorded through the wire;
INSERTED / DUPLICATE_MATCH / CONFLICT idempotency with no extra row on replay or conflict;
caller-unbound ``id`` / ``recorded_at`` (forbidden wire keys rejected); durable ordering by the
identity column; fresh store + fresh server reconstruction over the same disposable database
(rows persist; replay stays DUPLICATE_MATCH); direct-SQL UPDATE / DELETE / TRUNCATE rejection
with rows unchanged; bounded DB/transport failure with NO fallback, NO buffering, and NO
secret/SQL/topology leakage (contract §11 conditions 1 and 3 witnessed live); and guaranteed
proof-database teardown.

ISOLATION & SAFETY (PRD DBR-AR-2D V2 §6). Everything runs in the proof-owned scratch DATABASE
``sp2_dbr_ar_2d_proof`` created from the SNACKPORTAL_TEST_DSN admin connection at start and
DROPPED in a ``finally`` — the proof owns the full lifecycle. The DSN must point ONLY at a
disposable, non-production instance (the local throwaway container or the ephemeral CI service);
it must NEVER point at production, shared staging, the standing Control database, or any tenant
database. The repo DDL files are read + blob-pinned only, never modified. No standing SnackPortal2
database is named, read, or touched by this file.

SECRET HYGIENE (D-14). SNACKPORTAL_TEST_DSN is used by NAME only; its value (and the in-memory
unreachable DSN derived from it) is never printed, logged, or written. Stored rows are asserted to
contain no DSN/password substring; every error surface is asserted non-leaking.

DRIVER CONTAINMENT. This file imports NO database driver. PostgreSQL is reached only through the
sanctioned provider adapters (``PostgresRoutingAuditStore`` for the durable path;
``PostgresControlStore._conn`` for scratch SQL — the B-7A harness precedent), imported lazily
inside the exercise so the module clean-skips without psycopg (the 07D precedent). The ingest
server is hosted on a test-owned daemon thread (the 2C wire-proof precedent; production servers
stay single-threaded and thread-free).

DEFAULT SUITE. IGNORED by the default test run (pyproject addopts
``--ignore=tests/control_plane/requires_pg``). Run it standalone against a disposable instance:
  python backend/tests/control_plane/requires_pg/test_dbr_ar_2d_routing_audit_live_pg.py
With SNACKPORTAL_TEST_DSN unset (or psycopg absent) it clean-skips (exit 0, no DB touched).

NO OVERCLAIM. This proof is DISPOSABLE-ONLY: it does not touch the retained standing topology,
does not deliver the standing-environment DBR-AR-2D witnesses (contract §16 proofs 4/8/12), does
not standing-enroll DDL 010/011, does not close DBR-AR-2, and does not change the activation gate.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys
import threading
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlsplit, urlunsplit

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _pg  # noqa: E402  (standalone live-PG runner: SNACKPORTAL_TEST_DSN, available()/run()/swap_db())

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))  # backend on path

# Pure-stdlib backend modules only at module scope (clean-skip without psycopg — the 07D
# precedent); the psycopg-bearing provider module is imported lazily inside the exercise.
from database_router.adapters.providers.http_routing_audit import HttpRoutingAudit, RoutingAuditTransportError  # noqa: E402
from database_router.cache import RoutingViewCache  # noqa: E402
from database_router.main import BoundedRoutingAuditPolicy, build_router  # noqa: E402
from database_router.models import RoutingDenied, RoutingTarget, TenantRoutingView  # noqa: E402
from database_router.ports import ConnectionFactory, ControlPlaneRoutingReadPort, TenantConnection  # noqa: E402
from database_router.resolver import RoutingResolver  # noqa: E402
from database_router.router import DatabaseRouter  # noqa: E402
from shared.context import RequestContext  # noqa: E402
from shared.secrets import SecretRef, SecretStore, SecretValue  # noqa: E402

# The proof-owned scratch database (PRD DBR-AR-2D V2 §6): created and dropped by THIS file only.
# The name is collision-free vs every standing Control/tenant database name and every sibling
# harness scratch family (no standing name appears anywhere in this file, by guard).
_PROOF_DB = "sp2_dbr_ar_2d_proof"

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
_CONTROL = _REPO_ROOT / "infrastructure" / "db" / "control"
_DDL_010 = _CONTROL / "010_routing_audit.sql"
_DDL_011 = _CONTROL / "011_routing_audit_append_only.sql"

# Reviewed DBR-AR-2B DDL blobs (full LF-normalized git-blob SHA-1). The applied bytes MUST equal
# these reviewed-and-merged blobs; a mismatch STOPS the exercise BEFORE any connection is opened
# or any SQL is applied (PRD DBR-AR-2D V2 §7.1 — do not "fix" DDL here). Cross-checked in the
# default suite by tests/architecture/test_b7c1_control_audit_ddl_blob_pins.py.
_REVIEWED_010_BLOB = "0c5eeecd5e20ef9fe4f11293b6c6561ae7cc897e"
_REVIEWED_011_BLOB = "cea40fc62c063e9f711fdb7ac90b00a8859586d4"

_INGEST_PATH = "/internal/routing-audit/events"

# The exact 20-column contract of DDL 010 in ordinal order (id + recorded_at are store-assigned).
_EXPECTED_COLS = [
    "id",
    "event_id",
    "event_version",
    "occurred_at",
    "recorded_at",
    "correlation_id",
    "actor_ref",
    "action",
    "outcome",
    "source_service",
    "source_version",
    "request_ref",
    "trace_ref",
    "tenant_ref",
    "resolved_tenant_ref",
    "public_code",
    "error_class",
    "association_store_ref",
    "association_version",
    "lane",
]
_NOT_NULL = {
    "id",
    "event_id",
    "event_version",
    "occurred_at",
    "recorded_at",
    "correlation_id",
    "actor_ref",
    "action",
    "outcome",
    "source_service",
    "source_version",
}


# --- helpers (stdlib only; the driver is reached solely via the sanctioned adapters) --------------
def _git_blob_sha1(path: pathlib.Path) -> str:
    data = path.read_bytes().replace(b"\r\n", b"\n")  # autocrlf normalization (the git blob is LF)
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def _verify_reviewed_blobs() -> None:
    """PRD DBR-AR-2D V2 §7.1: resolve the committed blob IDs and STOP before connecting or
    applying SQL if either diverges from the reviewed pin (pure file I/O — no DB, no socket)."""
    b010, b011 = _git_blob_sha1(_DDL_010), _git_blob_sha1(_DDL_011)
    assert b010 == _REVIEWED_010_BLOB, f"010 blob {b010} != reviewed {_REVIEWED_010_BLOB} — STOP before connect/apply (do not fix DDL here)"
    assert b011 == _REVIEWED_011_BLOB, f"011 blob {b011} != reviewed {_REVIEWED_011_BLOB} — STOP before connect/apply (do not fix DDL here)"
    print(f"PASS: 2D-0 reviewed DDL blob pins verified BEFORE any connection (010={b010[:12]}…, 011={b011[:12]}…)")


def _derive_unreachable_dsn(dsn: str) -> str:
    """Derive an unreachable DSN IN MEMORY from `dsn` (port -> 1, short connect-timeout). Never
    printed/written (the B-7A precedent). Keeps userinfo so no separate secret handling is needed."""
    p = urlsplit(dsn)
    auth = ""
    if p.username:
        auth = p.username + ((":" + p.password) if p.password else "") + "@"
    netloc = f"{auth}{p.hostname or 'localhost'}:1"  # port 1 -> connection refused (fast, deterministic)
    query = (p.query + "&" if p.query else "") + "connect_timeout=2"
    return urlunsplit((p.scheme, netloc, p.path, query, p.fragment))


def _raises(conn: Any, sql: str, params: Tuple[Any, ...] = ()) -> bool:
    """True iff `sql` raised (autocommit isolation: a rejected statement is its own aborted
    single-statement transaction, so the connection stays usable — the B-7A precedent)."""
    try:
        conn.execute(sql, params)
        return False
    except Exception:
        return True


def _scalar(conn: Any, sql: str, params: Tuple[Any, ...] = ()) -> Any:
    row = conn.execute(sql, params).fetchone()
    return row[0] if row else None


def _rows(conn: Any) -> List[Tuple[Any, ...]]:
    """Every durable row in identity order — the total-order authority (ORDER BY id ASC)."""
    return list(
        conn.execute(
            "SELECT id, event_id::text, event_version, occurred_at, recorded_at, correlation_id, actor_ref, action, outcome,"
            " source_service, source_version, request_ref, trace_ref, tenant_ref, resolved_tenant_ref, public_code, error_class,"
            " association_store_ref, association_version, lane FROM control_routing_audit ORDER BY id ASC"
        ).fetchall()
    )


def _count(conn: Any) -> int:
    return int(_scalar(conn, "SELECT count(*) FROM control_routing_audit"))


def _post(base_url: str, payload: Dict[str, object]) -> Tuple[int, Dict[str, object]]:
    """POST one envelope to the ingest edge; return (status, decoded two-key body)."""
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(base_url + _INGEST_PATH, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=10) as resp:
            return int(resp.status), json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        return int(exc.code), json.loads(raw.decode("utf-8")) if raw else {}


def _wire_event(event_id: str, correlation_id: str) -> Dict[str, object]:
    """A references-only wire event with EXACTLY the seventeen approved keys (MC9)."""
    return {
        "event_id": event_id,
        "event_version": 1,
        "occurred_at": "2026-07-14T00:00:00+00:00",
        "correlation_id": correlation_id,
        "actor_ref": "principal_d2d",
        "action": "Route",
        "outcome": "success",
        "source_service": "database_router",
        "source_version": "4",
        "request_ref": "req-d2d-wire",
        "tenant_ref": "d2dt1",
        "resolved_tenant_ref": "d2dt1",
        "public_code": None,
        "error_class": None,
        "association_store_ref": "tenant/d2dt1/db",
        "association_version": "1",
        "lane": "interactive",
    }


def _ctx(correlation_id: str, tenant: Optional[str], *, role: str = "TENANT_ADMIN") -> RequestContext:
    return RequestContext(
        correlation_id=correlation_id, request_id="req-" + correlation_id, active_tenant_id=tenant, principal_ref="principal_d2d", role=role
    )


# --- tenant-side test doubles (PRD DBR-AR-2D V2 §8: doubles ONLY for the connection/pool side) ----
class _ProofRoutingRead(ControlPlaneRoutingReadPort):
    def __init__(self) -> None:
        self._views: Dict[str, TenantRoutingView] = {}

    def add(self, tenant_id: str) -> None:
        self._views[tenant_id] = TenantRoutingView(
            tenant_id=tenant_id,
            lifecycle_state="Ready",
            ready=True,
            database_association_ref=SecretRef(f"tenant/{tenant_id}/db", "1"),
            expected_schema_version="1",
        )

    def get_routing_view(self, tenant_id: str) -> Optional[TenantRoutingView]:
        return self._views.get(tenant_id)


class _ProofSecretStore(SecretStore):
    def resolve(self, ref: SecretRef) -> SecretValue:
        return SecretValue(material=f"descriptor::{ref.store_ref}@{ref.version}")

    def current_version(self, store_ref: str) -> str:
        return "1"


class _ProofConnection(TenantConnection):
    def __init__(self, tenant_id: str, association_version: str) -> None:
        self._tenant_id = tenant_id
        self._version = association_version
        self.closed = False

    @property
    def tenant_id(self) -> str:
        return self._tenant_id

    @property
    def association_version(self) -> str:
        return self._version

    def is_alive(self) -> bool:
        return not self.closed

    def begin(self) -> None:
        return None

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None

    def reset(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True

    def execute(self, statement: str, params: tuple = ()) -> None:  # type: ignore[type-arg]
        return None

    def query(self, statement: str, params: tuple = ()) -> list:  # type: ignore[type-arg]
        return []


class _ProofConnectionFactory(ConnectionFactory):
    def __init__(self) -> None:
        self.opened: List[_ProofConnection] = []

    def open(self, tenant_id: str, association_version: str, descriptor: str) -> TenantConnection:
        conn = _ProofConnection(tenant_id, association_version)
        self.opened.append(conn)
        return conn


class _PassThroughPool:
    """Hands back a preset connection and records discards (the 2A/2C local-double precedent —
    the real pool's own binding check would intercept a misbound connection before the router's
    D-30 L3 check, and the condition-1 leg needs an observable discard)."""

    def __init__(self, conn: _ProofConnection) -> None:
        self._conn = conn
        self.discarded: List[_ProofConnection] = []

    def acquire(self, tenant_id: str, association_version: str, open_fn: Any) -> _ProofConnection:
        return self._conn

    def release(self, conn: _ProofConnection) -> None:
        return None

    def discard(self, conn: _ProofConnection) -> None:
        self.discarded.append(conn)
        conn.close()


def _direct_router(read: _ProofRoutingRead, pool: _PassThroughPool, audit: Any) -> DatabaseRouter:
    return DatabaseRouter(
        resolver=RoutingResolver(read, RoutingViewCache(ttl_seconds=15.0), supported_schema_versions=("1",)),
        pool=pool,  # type: ignore[arg-type]
        secret_store=_ProofSecretStore(),
        connection_factory=_ProofConnectionFactory(),
        audit=audit,
    )


def _policy(base_url: str, timeout: float = 5.0) -> BoundedRoutingAuditPolicy:
    """The REAL composed audit chain: bounded policy over the real transport client."""
    return BoundedRoutingAuditPolicy(HttpRoutingAudit(base_url, timeout=timeout), transport_error=RoutingAuditTransportError)


def _serve(server: Any) -> threading.Thread:
    """Host the real ingest server on a test-owned daemon thread (the 2C wire-proof precedent;
    production stays thread-free — this is harness hosting only)."""
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread


def _stop(server: Any, thread: Optional[threading.Thread]) -> None:
    server.shutdown()
    server.server_close()
    if thread is not None:
        thread.join(timeout=5)


# --- the exercise ---------------------------------------------------------------------------------
def test_dbr_ar_2d_disposable_live_proof(admin_dsn: str) -> None:
    # PROOF 2D-0 — reviewed blob pins verified BEFORE any connection or SQL (§7.1 STOP rule).
    _verify_reviewed_blobs()

    # Lazy provider imports (07D precedent): psycopg stays confined to the sanctioned zone and the
    # module clean-skips without it. PostgresControlStore is the B-7A-precedent scratch-SQL seam.
    from control_plane.adapters.providers.http_routing_audit_api import build_routing_audit_server
    from control_plane.adapters.providers.postgres_store import PostgresControlStore, PostgresRoutingAuditStore

    # Admin connection (autocommit: CREATE/DROP DATABASE are non-transactional).
    admin_store = PostgresControlStore(admin_dsn)
    admin = admin_store._conn
    admin.autocommit = True
    server_num = int(_scalar(admin, "SELECT current_setting('server_version_num')"))
    assert server_num >= 110000, f"PostgreSQL >= 11 required (server_version_num={server_num})"

    # PROOF 2D-1 — disposable proof database, lifecycle-owned by THIS run (leftover dropped first).
    admin.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()", (_PROOF_DB,))
    admin.execute(f'DROP DATABASE IF EXISTS "{_PROOF_DB}"')
    admin.execute(f'CREATE DATABASE "{_PROOF_DB}"')
    proof_dsn = _pg.swap_db(admin_dsn, _PROOF_DB)

    sql_store = PostgresControlStore(proof_dsn)
    conn = sql_store._conn
    conn.autocommit = True  # expected-error isolation (B-7A §16.13 precedent)
    try:
        assert _scalar(conn, "SELECT to_regclass('control_routing_audit')") is None, "control_routing_audit must be ABSENT before apply"
        print(f"PASS: 2D-1 disposable proof database created fresh ({_PROOF_DB}; table absent before apply)")

        # PROOF 2D-2 — apply exactly 010 then 011 (exact repo paths, each exactly once, no wildcard).
        with conn.cursor() as cur:
            cur.execute(_DDL_010.read_text(encoding="utf-8"))
            cur.execute(_DDL_011.read_text(encoding="utf-8"))
        assert _scalar(conn, "SELECT to_regclass('control_routing_audit')") is not None, "control_routing_audit must exist after apply"
        print("PASS: 2D-2 DDL applied in order (010_routing_audit.sql then 011_routing_audit_append_only.sql)")

        # PROOF 2D-3 — live schema evidence from the PostgreSQL catalogs (§7.3).
        cols = conn.execute(
            "SELECT column_name, data_type, is_nullable, is_identity, identity_generation, column_default"
            " FROM information_schema.columns WHERE table_schema='public' AND table_name='control_routing_audit'"
            " ORDER BY ordinal_position"
        ).fetchall()
        names = [c[0] for c in cols]
        assert names == _EXPECTED_COLS, f"exact 20-column contract violated: {names}"
        meta = {c[0]: c for c in cols}
        assert meta["id"][1] == "bigint" and meta["id"][3] == "YES" and meta["id"][4] == "ALWAYS", (
            "id must be bigint GENERATED ALWAYS AS IDENTITY"
        )
        assert meta["event_id"][1] == "uuid", "event_id must be uuid"
        assert meta["event_version"][1] == "integer", "event_version must be integer"
        for name in ("occurred_at", "recorded_at"):
            assert meta[name][1] == "timestamp with time zone", f"{name} must be timestamptz"
        assert "now()" in (meta["recorded_at"][5] or ""), "recorded_at must carry the DB DEFAULT now() (store-assigned, never caller-bound)"
        for name in _EXPECTED_COLS:
            expected_nullable = "NO" if name in _NOT_NULL else "YES"
            assert meta[name][2] == expected_nullable, f"{name} nullability must be {expected_nullable}"
            if name not in ("id", "event_id", "event_version", "occurred_at", "recorded_at"):
                assert meta[name][1] == "text", f"{name} must be text (references only — no JSON/body/credential/topology column)"
        pk = conn.execute(
            "SELECT kcu.column_name FROM information_schema.table_constraints tc"
            " JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name"
            " AND tc.table_schema = kcu.table_schema"
            " WHERE tc.table_schema='public' AND tc.table_name='control_routing_audit' AND tc.constraint_type='PRIMARY KEY'"
        ).fetchall()
        assert [r[0] for r in pk] == ["id"], "PRIMARY KEY must be (id) — the durable total-ordering authority"
        unique_cols = conn.execute(
            "SELECT kcu.column_name FROM information_schema.table_constraints tc"
            " JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name"
            " AND tc.table_schema = kcu.table_schema"
            " WHERE tc.table_schema='public' AND tc.table_name='control_routing_audit' AND tc.constraint_type='UNIQUE'"
        ).fetchall()
        assert [r[0] for r in unique_cols] == ["event_id"], "event_id must carry the UNIQUE idempotency constraint"
        checks = [
            r[0]
            for r in conn.execute(
                "SELECT conname FROM pg_constraint WHERE conrelid = 'control_routing_audit'::regclass AND contype = 'c' ORDER BY conname"
            ).fetchall()
        ]
        assert "control_routing_audit_action_check" in checks, "the frozen action CHECK must exist"
        assert "control_routing_audit_source_service_check" in checks, "the frozen source_service CHECK must exist"
        triggers = [
            r[0]
            for r in conn.execute(
                "SELECT tgname FROM pg_trigger WHERE tgrelid = 'control_routing_audit'::regclass AND NOT tgisinternal ORDER BY tgname"
            ).fetchall()
        ]
        assert triggers == ["control_routing_audit_no_mutation", "control_routing_audit_no_truncate"], (
            f"append-only triggers missing: {triggers}"
        )
        print(
            "PASS: 2D-3 live schema evidence (20 cols/types/order, identity PK, unique event_id, DB-default recorded_at, CHECKs, triggers)"
        )

        # PROOF 2D-4 — the REAL end-to-end path: all four event classes durably recorded.
        store_a = PostgresRoutingAuditStore(dsn=proof_dsn)
        server_a, base_a = build_routing_audit_server(store_a, host="127.0.0.1", port=0)
        thread_a = _serve(server_a)
        try:
            read = _ProofRoutingRead()
            read.add("d2dt1")
            policy_a = _policy(base_a)
            factory = _ProofConnectionFactory()
            router = build_router(read=read, secret_store=_ProofSecretStore(), connection_factory=factory, audit=policy_a)

            result = router.route(_ctx("cid-d2d-route", "d2dt1"))
            assert result.target is RoutingTarget.TENANT and result.tenant_id == "d2dt1" and result.connection is not None, (
                "the allowed tenant route must be handed back AFTER its durable record committed (audit-before-hand-back)"
            )
            router.release(result)

            control = router.route(_ctx("cid-d2d-control", None, role="CONTROL"))
            assert control.target is RoutingTarget.CONTROL, "the control route must be handed back after its durable record"

            try:
                router.route(_ctx("cid-d2d-denied", "d2dghost"))
                raise AssertionError("an unknown tenant must be denied")
            except RoutingDenied as denied:
                assert denied.public_code == "not_found" and denied.http_status == 404

            divergent = _ProofConnection("d2dother", "1")
            anomaly_pool = _PassThroughPool(divergent)
            anomaly_router = _direct_router(read, anomaly_pool, policy_a)
            try:
                anomaly_router.route(_ctx("cid-d2d-anomaly", "d2dt1"))
                raise AssertionError("a tenant-binding fault must be denied")
            except RoutingDenied as denied:
                assert denied.public_code == "routing_isolation_fault" and denied.http_status == 503
            assert anomaly_pool.discarded == [divergent], "the misbound connection must be discarded (D-30 L3)"

            rows = _rows(conn)
            assert [r[7] for r in rows] == ["Route", "RouteControl", "RouteDenied", "IsolationAnomaly"], (
                f"exactly one durable row per decision, in emission order: {[r[7] for r in rows]}"
            )
            route_row, control_row, denied_row, anomaly_row = rows
            assert route_row[8] == "success" and route_row[13] == "d2dt1" and route_row[14] == "d2dt1", "Route row fields"
            assert route_row[17] == "tenant/d2dt1/db" and route_row[18] == "1" and route_row[19] == "interactive", (
                "Route row must carry the D-14 association REFERENCE (never a resolved value) + version + lane"
            )
            assert control_row[8] == "success" and control_row[13] is None and control_row[15] is None, "RouteControl row fields"
            assert denied_row[8] == "denied:not_found" and denied_row[15] == "not_found" and denied_row[13] == "d2dghost", (
                "RouteDenied row fields"
            )
            assert anomaly_row[8] == "anomaly:tenant_binding" and anomaly_row[13] == "d2dt1" and anomaly_row[14] == "d2dother", (
                "IsolationAnomaly row must record both the authenticated and the actually-bound tenant references"
            )
            for row in rows:
                assert row[6] == "principal_d2d" and row[9] == "database_router" and row[10] == "4" and row[2] == 1, "common row fields"
                assert row[4] is not None and getattr(row[4], "tzinfo", None) is not None, "recorded_at must be DB-assigned and tz-aware"
                assert row[12] is None, "trace_ref is a reserved column and must stay NULL (not a wire field)"
            print(
                "PASS: 2D-4 end-to-end path (router -> policy -> HTTP -> ingest -> store -> PostgreSQL;"
                " Route/RouteControl/RouteDenied/IsolationAnomaly)"
            )

            # PROOF 2D-5 — wire idempotency + conflict (INSERTED / DUPLICATE_MATCH / CONFLICT; no extra rows).
            baseline = _count(conn)
            envelope = {"version": 1, "event": _wire_event("00000000-0000-4000-8000-00000000002d", "cid-d2d-wire")}
            status, body = _post(base_a, envelope)
            assert (status, body) == (200, {"version": 1, "result": "INSERTED"}), f"first submission must be INSERTED: {status} {body}"
            status, body = _post(base_a, envelope)
            assert (status, body) == (200, {"version": 1, "result": "DUPLICATE_MATCH"}), (
                f"identical replay must be DUPLICATE_MATCH: {status} {body}"
            )
            assert _count(conn) == baseline + 1, "an identical replay must add NO second row"
            conflict = {"version": 1, "event": dict(_wire_event("00000000-0000-4000-8000-00000000002d", "cid-d2d-DIFFERENT"))}
            status, body = _post(base_a, conflict)
            assert (status, body) == (409, {"version": 1, "result": "CONFLICT"}), (
                f"a changed replay must be the bounded CONFLICT: {status} {body}"
            )
            assert _count(conn) == baseline + 1, "a conflicting replay must add NO row"
            stored = _scalar(
                conn, "SELECT correlation_id FROM control_routing_audit WHERE event_id = %s", ("00000000-0000-4000-8000-00000000002d",)
            )
            assert stored == "cid-d2d-wire", "the original row must survive a conflicting replay unchanged"
            print("PASS: 2D-5 idempotency/conflict on the wire (INSERTED -> DUPLICATE_MATCH -> 409 CONFLICT; row count stable)")

            # PROOF 2D-6 — database authority: caller-unbound id/recorded_at; frozen vocabularies; ordering.
            for forbidden_key, value in (("id", 999), ("recorded_at", "2026-07-14T00:00:00+00:00")):
                bad = {
                    "version": 1,
                    "event": dict(_wire_event("00000000-0000-4000-8000-0000000000bd", "cid-d2d-bad"), **{forbidden_key: value}),
                }
                status, body = _post(base_a, bad)
                assert (status, body) == (400, {"version": 1, "result": "INVALID"}), (
                    f"caller-bound {forbidden_key} must be rejected: {status}"
                )
            bad_action = {"version": 1, "event": dict(_wire_event("00000000-0000-4000-8000-0000000000ba", "cid-d2d-bad"), action="Hacked")}
            status, body = _post(base_a, bad_action)
            assert (status, body) == (400, {"version": 1, "result": "INVALID"}), "an unknown action must be rejected at the edge"
            bad_service = {
                "version": 1,
                "event": dict(_wire_event("00000000-0000-4000-8000-0000000000b5", "cid-d2d-bad"), source_service="api_gateway"),
            }
            status, body = _post(base_a, bad_service)
            assert (status, body) == (400, {"version": 1, "result": "INVALID"}), "an unknown source_service must be rejected at the edge"
            assert _count(conn) == baseline + 1, "rejected envelopes must add NO row"
            assert _raises(
                conn,
                "INSERT INTO control_routing_audit (event_id, event_version, occurred_at, correlation_id, actor_ref, action, outcome,"
                " source_service, source_version) VALUES (%s, 1, now(), 'c', 'a', 'Hacked', 'success', 'database_router', '4')",
                ("00000000-0000-4000-8000-0000000000c1",),
            ), "the DB action CHECK must reject an out-of-vocabulary action"
            assert _raises(
                conn,
                "INSERT INTO control_routing_audit (event_id, event_version, occurred_at, correlation_id, actor_ref, action, outcome,"
                " source_service, source_version) VALUES (%s, 1, now(), 'c', 'a', 'Route', 'success', 'api_gateway', '4')",
                ("00000000-0000-4000-8000-0000000000c2",),
            ), "the DB source_service CHECK must reject a foreign emitter"
            assert _raises(
                conn,
                "INSERT INTO control_routing_audit (event_id, event_version, occurred_at, correlation_id, actor_ref, action, outcome,"
                " source_service, source_version) VALUES (%s, 1, now(), 'c', 'a', 'Route', 'success', 'database_router', '4')",
                ("00000000-0000-4000-8000-00000000002d",),
            ), "the UNIQUE event_id key must reject a raw duplicate insert at the database"
            ids = [r[0] for r in _rows(conn)]
            assert ids == sorted(ids) and len(set(ids)) == len(ids), f"identity ordering must be strictly increasing: {ids}"
            assert [r[5] for r in _rows(conn)] == [
                "cid-d2d-route",
                "cid-d2d-control",
                "cid-d2d-denied",
                "cid-d2d-anomaly",
                "cid-d2d-wire",
            ], "ORDER BY id must reproduce the exact insertion order (timestamps are never the ordering authority)"
            print("PASS: 2D-6 database authority (id/recorded_at caller-unbound; CHECK + UNIQUE enforced; durable ordering by identity)")

            # PROOF 2D-7 — restart durability: fresh store + fresh server over the SAME disposable DB.
            snapshot = _rows(conn)
        finally:
            _stop(server_a, thread_a)
            store_a.release()
        store_b = PostgresRoutingAuditStore(dsn=proof_dsn)
        server_b, base_b = build_routing_audit_server(store_b, host="127.0.0.1", port=0)
        thread_b = _serve(server_b)
        try:
            assert _rows(conn) == snapshot, "every durable row must survive store release + server stop (restart durability)"
            status, body = _post(base_b, {"version": 1, "event": _wire_event("00000000-0000-4000-8000-00000000002d", "cid-d2d-wire")})
            assert (status, body) == (200, {"version": 1, "result": "DUPLICATE_MATCH"}), (
                "a replay against the FRESH store/server must stay the idempotent DUPLICATE_MATCH"
            )
            assert _rows(conn) == snapshot, "the fresh-instance replay must add NO row"
            print(
                "PASS: 2D-7 restart durability (fresh PostgresRoutingAuditStore + fresh ingest server;"
                " rows persist; replay stays DUPLICATE_MATCH)"
            )

            # PROOF 2D-8 — append-only enforcement: UPDATE / DELETE / TRUNCATE rejected; rows unchanged.
            assert _raises(conn, "UPDATE control_routing_audit SET outcome = 'mutated' WHERE id = %s", (snapshot[0][0],)), (
                "UPDATE must be rejected"
            )
            assert _raises(conn, "DELETE FROM control_routing_audit WHERE id = %s", (snapshot[0][0],)), "DELETE must be rejected"
            assert _raises(conn, "TRUNCATE control_routing_audit"), "TRUNCATE must be rejected"
            assert _rows(conn) == snapshot, "rows must be byte-identical after the rejected UPDATE/DELETE/TRUNCATE"
            print("PASS: 2D-8 append-only enforced live (UPDATE/DELETE/TRUNCATE each rejected; rows unchanged)")

            # PROOF 2D-9 — bounded failure with NO fallback and NO leakage (§11 conditions 1 and 3, live).
            # (a) ingest edge up, store's database unreachable -> bounded 503 UNAVAILABLE two-key envelope.
            store_x = PostgresRoutingAuditStore(dsn=_derive_unreachable_dsn(admin_dsn))
            server_x, base_x = build_routing_audit_server(store_x, host="127.0.0.1", port=0)
            thread_x = _serve(server_x)
            try:
                status, body = _post(base_x, {"version": 1, "event": _wire_event("00000000-0000-4000-8000-0000000000fa", "cid-d2d-down")})
                assert (status, body) == (503, {"version": 1, "result": "UNAVAILABLE"}), (
                    "a store-DB outage must collapse to the bounded two-key UNAVAILABLE envelope"
                )
                assert set(body.keys()) == {"version", "result"}, "no SQL/topology/exception detail may cross the ingest edge"
                # (b) condition 1 through the full chain: the allowed route fails closed, the acquired
                # connection is discarded, and the denial is the bounded non-leaking 503 bucket.
                held = _ProofConnection("d2dt1", "1")
                cond1_pool = _PassThroughPool(held)
                policy_x = _policy(base_x)
                router_x = _direct_router(read, cond1_pool, policy_x)
                try:
                    router_x.route(_ctx("cid-d2d-cond1", "d2dt1"))
                    raise AssertionError("an allowed route whose durable audit failed must NOT be handed back")
                except RoutingDenied as denied:
                    assert denied.public_code == "routing_audit_unavailable" and denied.http_status == 503
                    text = f"{denied} {denied.public_code} {denied.reason}"
                    for leaked in ("postgresql://", "SELECT", "INSERT", "control_routing_audit", ":1/"):
                        assert leaked not in text, f"the condition-1 denial must never leak transport/SQL/topology detail ({leaked!r})"
                assert cond1_pool.discarded == [held] and held.closed, "the acquired connection must be discarded before the denial"
                # (c) condition 3: the ORIGINAL denial is preserved and the lost record is counted.
                try:
                    router_x.route(_ctx("cid-d2d-cond3", "d2dghost"))
                    raise AssertionError("the request must stay denied")
                except RoutingDenied as denied:
                    assert denied.public_code == "not_found" and denied.http_status == 404, (
                        "the original denial must be preserved unchanged"
                    )
                assert policy_x.degradation_snapshot() == {"route_denied_audit_failures": 1, "isolation_anomaly_audit_failures": 0}
            finally:
                _stop(server_x, thread_x)
                store_x.release()
            # (d) ingest edge unreachable entirely (refused port) -> same bounded condition-1 posture.
            policy_y = _policy("http://127.0.0.1:1", timeout=1.0)
            held_y = _ProofConnection("d2dt1", "1")
            pool_y = _PassThroughPool(held_y)
            router_y = _direct_router(read, pool_y, policy_y)
            try:
                router_y.route(_ctx("cid-d2d-refused", "d2dt1"))
                raise AssertionError("an allowed route with an unreachable ingest edge must NOT be handed back")
            except RoutingDenied as denied:
                assert denied.public_code == "routing_audit_unavailable" and denied.http_status == 503
            assert pool_y.discarded == [held_y], "the acquired connection must be discarded on transport unavailability too"
            # (e) durable mode never falls back and never buffers: the durable store gained NO row
            # from any failure leg, and nothing flushes later (no queue/outbox exists by design).
            assert _rows(conn) == snapshot, "no failure leg may write a fallback row or flush a buffered event"
            # (f) reference-only stored rows: no DSN/password substring in any durable cell (D-14).
            secret_parts = [admin_dsn]
            password = urlsplit(admin_dsn).password
            if password:
                secret_parts.append(password)
            for row in _rows(conn):
                for cell in row:
                    for secret in secret_parts:
                        assert secret not in str(cell), "stored cells must never contain the DSN/password (references only)"
            print(
                "PASS: 2D-9 bounded failure semantics live (503 UNAVAILABLE envelope; condition-1 discard+deny;"
                " condition-3 preserve+count; no fallback row; no leakage)"
            )
        finally:
            _stop(server_b, thread_b)
            store_b.release()
            try:
                conn.close()
            except Exception:
                pass
    finally:
        # PROOF 2D-10 — guaranteed teardown: the proof database is REMOVED (never retained).
        try:
            conn.close()
        except Exception:
            pass
        admin.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()", (_PROOF_DB,))
        admin.execute(f'DROP DATABASE IF EXISTS "{_PROOF_DB}"')
        remaining = _scalar(admin, "SELECT count(*) FROM pg_database WHERE datname = %s", (_PROOF_DB,))
        print(f"PASS: 2D-10 proof database torn down (datname count for {_PROOF_DB} = {remaining})")
        admin.close()
        assert remaining == 0, "the disposable proof database must be removed after the proof"


if __name__ == "__main__":
    _pg.run([test_dbr_ar_2d_disposable_live_proof])
