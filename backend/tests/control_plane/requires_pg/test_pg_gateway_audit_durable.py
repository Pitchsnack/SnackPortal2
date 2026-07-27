"""Gateway Audit V1a — durable Gateway-audit DISPOSABLE live-PostgreSQL proof (standalone-only; SNACKPORTAL_TEST_DSN).

The MANUAL_ONLY disposable proof of the Gateway Operational Audit Persistence V1a durable path:
against a real, proof-owned PostgreSQL database it applies the reviewed, blob-pinned Gateway-audit
DDL (infrastructure/db/control/012_gateway_operational_audit.sql then
013_gateway_operational_audit_append_only.sql — exact paths, exact order, each exactly once, never a
wildcard) and proves the REAL persistence path end-to-end:

    Gateway DurableAuditEmitter -> Control-Plane ingest edge (build_gateway_audit_server)
        -> PostgresGatewayAuditStore -> disposable PostgreSQL

Every event crosses the real HTTP wire (the gateway's own ``DurableAuditEmitter`` transport client
and raw ``_post`` probes); the store is never called directly. Proof set: reviewed-blob
STOP-before-connect; live schema evidence from the PostgreSQL catalogs (exact 14 columns — the D-42
``record_ref`` reference column included — identity ordering authority, unique ``audit_id``,
DB-assigned ``recorded_at``, the frozen action / event_version / source_service CHECKs, both
append-only triggers); one durable ``workspace_memberships_read`` success event persisted through
the wire; one durable D-43 ``CarrierMismatch/rejected`` denial row persisted through the wire with
its REQUIRED opaque ``carrier_ref`` and NO tenant/record reference (Post-10C.3 corrective —
duplicate replay idempotent; invalid outcome and missing/malformed ``carrier_ref`` refused with no
row); INSERTED / DUPLICATE_MATCH /
CONFLICT idempotency with no extra row on replay or conflict; caller-unbound ``id`` / ``recorded_at``
(forbidden wire keys rejected); durable ordering by the identity column; fresh store + fresh server
reconstruction over the same disposable database (rows persist; replay stays DUPLICATE_MATCH);
direct-SQL UPDATE / DELETE / TRUNCATE rejection with rows unchanged (the CarrierMismatch row
included); and reference-only stored rows (no DSN/password substring). Guaranteed proof-database
teardown.

ISOLATION & SAFETY. Everything runs in the proof-owned scratch DATABASE ``sp2_gateway_audit_v1a_proof``
created from the SNACKPORTAL_TEST_DSN admin connection at start and DROPPED in a ``finally`` — the
proof owns the full lifecycle. The DSN must point ONLY at a disposable, non-production instance; it
must NEVER point at production, shared staging, the standing Control database, or any tenant
database. The repo DDL files are read + blob-pinned only, never modified. No standing SnackPortal2
database is named, read, or touched by this file.

SECRET HYGIENE (D-14). SNACKPORTAL_TEST_DSN is used by NAME only; its value is never printed, logged,
or written. Stored rows are asserted to contain no DSN/password substring.

DRIVER CONTAINMENT. This file imports NO database driver. PostgreSQL is reached only through the
sanctioned provider adapters (``PostgresGatewayAuditStore`` for the durable path;
``PostgresControlStore._conn`` for scratch SQL), imported lazily inside the exercise so the module
clean-skips without psycopg. The ingest server is hosted on a test-owned daemon thread (production
servers stay single-threaded and thread-free).

DEFAULT SUITE. IGNORED by the default test run (pyproject addopts
``--ignore=tests/control_plane/requires_pg``). Run it standalone against a disposable instance:
  python backend/tests/control_plane/requires_pg/test_pg_gateway_audit_durable.py
With SNACKPORTAL_TEST_DSN unset (or psycopg absent) it clean-skips (exit 0, no DB touched).

NO OVERCLAIM. This proof is DISPOSABLE-ONLY: it does not touch the retained standing topology, does
not standing-enroll DDL 012/013, does not deliver V1b operator retrieval, does not close any B5
blocker, and does not change the activation gate.
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

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _pg  # noqa: E402  (standalone live-PG runner: SNACKPORTAL_TEST_DSN, available()/run()/swap_db())

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))  # backend on path

# Pure-stdlib backend modules only at module scope (clean-skip without psycopg); the psycopg-bearing
# provider modules are imported lazily inside the exercise.
from api_gateway.adapters.providers.durable_audit_emitter import (  # noqa: E402
    DurableAuditEmitter,
    DurableAuditTransportError,
)
from api_gateway.models import AuditAction, GatewayAuditEvent  # noqa: E402

# The proof-owned scratch database: created and dropped by THIS file only. The name is collision-free
# vs every standing Control/tenant database name and every sibling harness scratch family.
_PROOF_DB = "sp2_gateway_audit_v1a_proof"

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
_CONTROL = _REPO_ROOT / "infrastructure" / "db" / "control"
_DDL_012 = _CONTROL / "012_gateway_operational_audit.sql"
_DDL_013 = _CONTROL / "013_gateway_operational_audit_append_only.sql"

# Reviewed Gateway Audit V1a DDL blobs (full LF-normalized git-blob SHA-1). The applied bytes MUST
# equal these reviewed-and-merged blobs; a mismatch STOPS the exercise BEFORE any connection is
# opened or any SQL is applied. Cross-checked in the default suite by
# tests/architecture/test_b7c1_control_audit_ddl_blob_pins.py.
_REVIEWED_012_BLOB = "87c38a968f8ab89886ef7ce4d9d7fafb7a179271"
_REVIEWED_013_BLOB = "199664d1afb9e6e0a37e8609f42e4e1528771472"

_INGEST_PATH = "/internal/gateway-audit/events"

# The exact 14-column contract of DDL 012 in ordinal order (id + recorded_at are store-assigned;
# record_ref is the D-42 CLM tenant-resident reference column — nullable, references only).
_EXPECTED_COLS = [
    "id",
    "audit_id",
    "event_version",
    "occurred_at",
    "recorded_at",
    "correlation_id",
    "action",
    "outcome",
    "source_service",
    "actor_ref",
    "subject_ref",
    "tenant_ref",
    "carrier_ref",
    "record_ref",
]
_NOT_NULL = {
    "id",
    "audit_id",
    "event_version",
    "occurred_at",
    "recorded_at",
    "correlation_id",
    "action",
    "outcome",
    "source_service",
}

_AUDIT_ID = "0123456789abcdef0123456789abcdef"


# --- helpers (stdlib only; the driver is reached solely via the sanctioned adapters) --------------
def _git_blob_sha1(path: pathlib.Path) -> str:
    data = path.read_bytes().replace(b"\r\n", b"\n")  # autocrlf normalization (the git blob is LF)
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def _verify_reviewed_blobs() -> None:
    """Resolve the committed blob IDs and STOP before connecting or applying SQL if either diverges
    from the reviewed pin (pure file I/O — no DB, no socket)."""
    b012, b013 = _git_blob_sha1(_DDL_012), _git_blob_sha1(_DDL_013)
    assert b012 == _REVIEWED_012_BLOB, f"012 blob {b012} != reviewed {_REVIEWED_012_BLOB} — STOP before connect/apply (do not fix DDL here)"
    assert b013 == _REVIEWED_013_BLOB, f"013 blob {b013} != reviewed {_REVIEWED_013_BLOB} — STOP before connect/apply (do not fix DDL here)"
    print(f"PASS: GWA-0 reviewed DDL blob pins verified BEFORE any connection (012={b012[:12]}…, 013={b013[:12]}…)")


def _scalar(conn: Any, sql: str, params: Tuple[Any, ...] = ()) -> Any:
    row = conn.execute(sql, params).fetchone()
    return row[0] if row else None


def _rows(conn: Any) -> List[Tuple[Any, ...]]:
    """Every durable row in identity order — the total-order authority (ORDER BY id ASC)."""
    return list(
        conn.execute(
            "SELECT id, audit_id, event_version, occurred_at, recorded_at, correlation_id, action, outcome,"
            " source_service, actor_ref, subject_ref, tenant_ref, carrier_ref, record_ref"
            " FROM control_gateway_audit ORDER BY id ASC"
        ).fetchall()
    )


def _count(conn: Any) -> int:
    return int(_scalar(conn, "SELECT count(*) FROM control_gateway_audit"))


def _raises(conn: Any, sql: str, params: Tuple[Any, ...] = ()) -> bool:
    """True iff `sql` raised (autocommit isolation: a rejected statement is its own aborted
    single-statement transaction, so the connection stays usable)."""
    try:
        conn.execute(sql, params)
        return False
    except Exception:
        return True


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


def _wire(audit_id: str, correlation_id: str, **over: object) -> Dict[str, object]:
    """A references-only wire event with EXACTLY the eleven approved Gateway-edge keys
    (D-42 CLM adds ``record_ref``; null on the memberships success event)."""
    event: Dict[str, object] = {
        "audit_id": audit_id,
        "event_version": 1,
        "occurred_at": "2026-07-18T00:00:00+00:00",
        "correlation_id": correlation_id,
        "action": "workspace_memberships_read",
        "outcome": "success",
        "actor_ref": "principal_gwa",
        "subject_ref": "principal_gwa",
        "tenant_ref": None,
        "carrier_ref": None,
        "record_ref": None,
    }
    event.update(over)
    return event


def _cm_wire(audit_id: str, correlation_id: str, **over: object) -> Dict[str, object]:
    """A references-only D-43 ``CarrierMismatch/rejected`` wire event (eleven keys; the
    REQUIRED opaque ``carrier_ref``; no tenant/record reference — the denial is pre-routing)."""
    event: Dict[str, object] = {
        "audit_id": audit_id,
        "event_version": 1,
        "occurred_at": "2026-07-27T00:00:00+00:00",
        "correlation_id": correlation_id,
        "action": "CarrierMismatch",
        "outcome": "rejected",
        "actor_ref": None,
        "subject_ref": None,
        "tenant_ref": None,
        "carrier_ref": "carrier:tenant-b",
        "record_ref": None,
    }
    event.update(over)
    return event


def _success_event(audit_id: str, correlation_id: str) -> GatewayAuditEvent:
    return GatewayAuditEvent(
        action=AuditAction.WORKSPACE_MEMBERSHIPS_READ,
        correlation_id=correlation_id,
        outcome="success",
        actor_ref="principal_gwa",
        subject_ref="principal_gwa",
        audit_id=audit_id,
        occurred_at="2026-07-18T00:00:00+00:00",
        event_version=1,
    )


def _cm_denial_event(audit_id: str, correlation_id: str) -> GatewayAuditEvent:
    """The D-43 CarrierMismatch denial event as the gateway emits it (references only)."""
    return GatewayAuditEvent(
        action=AuditAction.CARRIER_MISMATCH,
        correlation_id=correlation_id,
        outcome="rejected",
        carrier_ref="carrier:tenant-b",
        audit_id=audit_id,
        occurred_at="2026-07-27T00:00:00+00:00",
        event_version=1,
    )


def _serve(server: Any) -> threading.Thread:
    """Host the real ingest server on a test-owned daemon thread (production stays thread-free)."""
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread


def _stop(server: Any, thread: Optional[threading.Thread]) -> None:
    server.shutdown()
    server.server_close()
    if thread is not None:
        thread.join(timeout=5)


# --- the exercise ---------------------------------------------------------------------------------
def test_gateway_audit_v1a_disposable_live_proof(admin_dsn: str) -> None:
    # PROOF GWA-0 — reviewed blob pins verified BEFORE any connection or SQL (STOP rule).
    _verify_reviewed_blobs()

    # Lazy provider imports: psycopg stays confined to the sanctioned zone and the module clean-skips
    # without it. PostgresControlStore is the scratch-SQL seam.
    from control_plane.adapters.providers.http_gateway_audit_api import build_gateway_audit_server
    from control_plane.adapters.providers.postgres_store import PostgresControlStore, PostgresGatewayAuditStore

    # Admin connection (autocommit: CREATE/DROP DATABASE are non-transactional).
    admin_store = PostgresControlStore(admin_dsn)
    admin = admin_store._conn
    admin.autocommit = True
    server_num = int(_scalar(admin, "SELECT current_setting('server_version_num')"))
    assert server_num >= 110000, f"PostgreSQL >= 11 required (server_version_num={server_num})"

    # PROOF GWA-1 — disposable proof database, lifecycle-owned by THIS run (leftover dropped first).
    admin.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()", (_PROOF_DB,))
    admin.execute(f'DROP DATABASE IF EXISTS "{_PROOF_DB}"')
    admin.execute(f'CREATE DATABASE "{_PROOF_DB}"')
    proof_dsn = _pg.swap_db(admin_dsn, _PROOF_DB)

    sql_store = PostgresControlStore(proof_dsn)
    conn = sql_store._conn
    conn.autocommit = True  # expected-error isolation
    try:
        assert _scalar(conn, "SELECT to_regclass('control_gateway_audit')") is None, "control_gateway_audit must be ABSENT before apply"
        print(f"PASS: GWA-1 disposable proof database created fresh ({_PROOF_DB}; table absent before apply)")

        # PROOF GWA-2 — apply exactly 012 then 013 (exact repo paths, each exactly once, no wildcard).
        with conn.cursor() as cur:
            cur.execute(_DDL_012.read_text(encoding="utf-8"))
            cur.execute(_DDL_013.read_text(encoding="utf-8"))
        assert _scalar(conn, "SELECT to_regclass('control_gateway_audit')") is not None, "control_gateway_audit must exist after apply"
        print("PASS: GWA-2 DDL applied in order (012_gateway_operational_audit.sql then 013_gateway_operational_audit_append_only.sql)")

        # PROOF GWA-3 — live schema evidence from the PostgreSQL catalogs.
        cols = conn.execute(
            "SELECT column_name, data_type, is_nullable, is_identity, identity_generation, column_default"
            " FROM information_schema.columns WHERE table_schema='public' AND table_name='control_gateway_audit'"
            " ORDER BY ordinal_position"
        ).fetchall()
        names = [c[0] for c in cols]
        assert names == _EXPECTED_COLS, f"exact 13-column contract violated: {names}"
        meta = {c[0]: c for c in cols}
        assert meta["id"][1] == "bigint" and meta["id"][3] == "YES" and meta["id"][4] == "ALWAYS", (
            "id must be bigint GENERATED ALWAYS AS IDENTITY"
        )
        assert meta["audit_id"][1] == "text", "audit_id must be text"
        assert meta["event_version"][1] == "integer", "event_version must be integer"
        for name in ("occurred_at", "recorded_at"):
            assert meta[name][1] == "timestamp with time zone", f"{name} must be timestamptz"
        assert "now()" in (meta["recorded_at"][5] or ""), "recorded_at must carry the DB DEFAULT now() (store-assigned, never caller-bound)"
        for name in _EXPECTED_COLS:
            expected_nullable = "NO" if name in _NOT_NULL else "YES"
            assert meta[name][2] == expected_nullable, f"{name} nullability must be {expected_nullable}"
            if name not in ("id", "event_version", "occurred_at", "recorded_at"):
                assert meta[name][1] == "text", f"{name} must be text (references only — no JSON/body/credential/topology column)"
        pk = conn.execute(
            "SELECT kcu.column_name FROM information_schema.table_constraints tc"
            " JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name"
            " AND tc.table_schema = kcu.table_schema"
            " WHERE tc.table_schema='public' AND tc.table_name='control_gateway_audit' AND tc.constraint_type='PRIMARY KEY'"
        ).fetchall()
        assert [r[0] for r in pk] == ["id"], "PRIMARY KEY must be (id) — the durable total-ordering authority"
        unique_cols = conn.execute(
            "SELECT kcu.column_name FROM information_schema.table_constraints tc"
            " JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name"
            " AND tc.table_schema = kcu.table_schema"
            " WHERE tc.table_schema='public' AND tc.table_name='control_gateway_audit' AND tc.constraint_type='UNIQUE'"
        ).fetchall()
        assert [r[0] for r in unique_cols] == ["audit_id"], "audit_id must carry the UNIQUE idempotency constraint"
        checks = [
            r[0]
            for r in conn.execute(
                "SELECT conname FROM pg_constraint WHERE conrelid = 'control_gateway_audit'::regclass AND contype = 'c' ORDER BY conname"
            ).fetchall()
        ]
        for check in (
            "control_gateway_audit_action_check",
            "control_gateway_audit_event_version_check",
            "control_gateway_audit_source_service_check",
        ):
            assert check in checks, f"the frozen {check} must exist"
        triggers = [
            r[0]
            for r in conn.execute(
                "SELECT tgname FROM pg_trigger WHERE tgrelid = 'control_gateway_audit'::regclass AND NOT tgisinternal ORDER BY tgname"
            ).fetchall()
        ]
        assert triggers == ["control_gateway_audit_no_mutation", "control_gateway_audit_no_truncate"], (
            f"append-only triggers missing: {triggers}"
        )
        print(
            "PASS: GWA-3 live schema evidence (14 cols/types/order, identity PK, unique audit_id, DB-default recorded_at, CHECKs, triggers)"
        )

        # PROOF GWA-4 — the REAL end-to-end path: one durable success event through the gateway emitter.
        store_a = PostgresGatewayAuditStore(dsn=proof_dsn)
        server_a, base_a = build_gateway_audit_server(store_a, host="127.0.0.1", port=0)
        thread_a = _serve(server_a)
        try:
            emitter = DurableAuditEmitter(base_a, timeout=5.0)
            assert emitter.emit(_success_event(_AUDIT_ID, "cid-gwa-1")) is None, (
                "the durable emitter must persist the success event (INSERTED)"
            )
            assert _count(conn) == 1, "exactly one durable row for one success event"
            (row,) = _rows(conn)
            assert row[1] == _AUDIT_ID and row[6] == "workspace_memberships_read" and row[7] == "success"
            assert row[8] == "api_gateway" and row[9] == row[10] == "principal_gwa" and row[11] is None and row[12] is None
            assert row[13] is None, "the memberships success event persists no record reference"
            assert row[4] is not None and getattr(row[4], "tzinfo", None) is not None, "recorded_at must be DB-assigned and tz-aware"
            print("PASS: GWA-4 end-to-end path (DurableAuditEmitter -> ingest -> store -> PG; one success row persisted)")

            # PROOF GWA-5 — wire idempotency + conflict (INSERTED / DUPLICATE_MATCH / CONFLICT; no extra rows).
            assert emitter.emit(_success_event(_AUDIT_ID, "cid-gwa-1")) is None, (
                "an identical replay through the emitter is DUPLICATE_MATCH success"
            )
            assert _count(conn) == 1, "an identical replay must add NO second row"
            status, body = _post(base_a, {"version": 1, "event": _wire(_AUDIT_ID, "cid-gwa-DIFFERENT")})
            assert (status, body) == (409, {"version": 1, "result": "CONFLICT"}), (
                f"a changed replay must be the bounded CONFLICT: {status} {body}"
            )
            assert _count(conn) == 1, "a conflicting replay must add NO row"
            assert _scalar(conn, "SELECT correlation_id FROM control_gateway_audit WHERE audit_id = %s", (_AUDIT_ID,)) == "cid-gwa-1", (
                "the original row must survive a conflicting replay unchanged"
            )
            print("PASS: GWA-5 idempotency/conflict on the wire (INSERTED -> DUPLICATE_MATCH -> 409 CONFLICT; row count stable)")

            # PROOF GWA-6 — database authority: caller-unbound id/recorded_at; frozen vocabularies; ordering.
            for forbidden_key, value in (("id", 999), ("recorded_at", "2026-07-18T00:00:00+00:00"), ("source_service", "api_gateway")):
                bad = {"version": 1, "event": dict(_wire("11111111111111111111111111111111", "cid-gwa-bad"), **{forbidden_key: value})}
                status, body = _post(base_a, bad)
                assert (status, body) == (400, {"version": 1, "result": "INVALID"}), (
                    f"caller-bound {forbidden_key} must be rejected: {status}"
                )
            # Out-of-vocabulary actions, unwired anomaly actions, and success-shaped envelopes
            # carrying a wired DENIAL action (invalid action/outcome combination) are all refused.
            for bad_action in ("Hacked", "RouteDenied", "IsolationAnomaly", "CarrierMismatch"):
                status, body = _post(
                    base_a, {"version": 1, "event": _wire("22222222222222222222222222222222", "cid-gwa-bad", action=bad_action)}
                )
                assert (status, body) == (400, {"version": 1, "result": "INVALID"}), f"action {bad_action} must be rejected at the edge"
            assert _count(conn) == 1, "rejected envelopes must add NO row"
            assert _raises(
                conn,
                "INSERT INTO control_gateway_audit (audit_id, event_version, occurred_at, correlation_id, action, outcome, source_service)"
                " VALUES (%s, 1, now(), 'c', 'Hacked', 'success', 'api_gateway')",
                ("33333333333333333333333333333333",),
            ), "the DB action CHECK must reject an out-of-vocabulary action"
            assert _raises(
                conn,
                "INSERT INTO control_gateway_audit (audit_id, event_version, occurred_at, correlation_id, action, outcome, source_service)"
                " VALUES (%s, 1, now(), 'c', 'workspace_memberships_read', 'success', 'database_router')",
                ("44444444444444444444444444444444",),
            ), "the DB source_service CHECK must reject a foreign emitter"
            assert _raises(
                conn,
                "INSERT INTO control_gateway_audit (audit_id, event_version, occurred_at, correlation_id, action, outcome, source_service)"
                " VALUES (%s, 0, now(), 'c', 'workspace_memberships_read', 'success', 'api_gateway')",
                ("55555555555555555555555555555555",),
            ), "the DB event_version CHECK must reject a non-positive version"
            assert _raises(
                conn,
                "INSERT INTO control_gateway_audit (audit_id, event_version, occurred_at, correlation_id, action, outcome, source_service)"
                " VALUES (%s, 1, now(), 'c', 'workspace_memberships_read', 'success', 'api_gateway')",
                (_AUDIT_ID,),
            ), "the UNIQUE audit_id key must reject a raw duplicate insert at the database"
            print("PASS: GWA-6 database authority (id/recorded_at/source_service caller-unbound; CHECK + UNIQUE enforced)")

            # PROOF GWA-6B — D-43 CarrierMismatch durable denial row (Post-10C.3 corrective):
            # the references-only CarrierMismatch/rejected event crosses the real wire through
            # the gateway's own transport client and persists with its REQUIRED opaque
            # carrier_ref; the pre-routing denial persists NO actor/subject/tenant/record
            # reference; replay is idempotent; an invalid outcome and a missing/malformed
            # carrier_ref are each refused with NO row. Uses only existing DDL 012/013.
            cm_id = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
            assert emitter.emit(_cm_denial_event(cm_id, "cid-gwa-cm")) is None, (
                "the durable emitter must persist the CarrierMismatch denial event (INSERTED)"
            )
            assert _count(conn) == 2, "exactly one durable row for one CarrierMismatch denial event"
            cm_row = next(r for r in _rows(conn) if r[1] == cm_id)
            assert cm_row[6] == "CarrierMismatch" and cm_row[7] == "rejected" and cm_row[8] == "api_gateway"
            assert cm_row[5] == "cid-gwa-cm", "the correlation reference must persist verbatim"
            assert cm_row[12] == "carrier:tenant-b", "the opaque carrier_ref must persist verbatim"
            assert cm_row[12].startswith("carrier:") and len(cm_row[12]) <= 64, "carrier_ref stays opaque + bounded (IC-005:116)"
            assert cm_row[9] is None and cm_row[10] is None and cm_row[11] is None and cm_row[13] is None, (
                "the pre-routing denial persists no actor/subject/tenant/record reference"
            )
            assert emitter.emit(_cm_denial_event(cm_id, "cid-gwa-cm")) is None, (
                "an identical CarrierMismatch replay through the emitter is DUPLICATE_MATCH success"
            )
            assert _count(conn) == 2, "a CarrierMismatch replay must add NO second row"
            for bad in (
                _cm_wire("bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "cid-gwa-cm-bad", outcome="success"),  # invalid outcome
                _cm_wire("bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "cid-gwa-cm-bad", carrier_ref=None),  # missing carrier_ref
                _cm_wire("bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "cid-gwa-cm-bad", carrier_ref="tenant-b"),  # non-opaque carrier_ref
                _cm_wire("bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "cid-gwa-cm-bad", tenant_ref="tenant-b"),  # fabricated tenant ref
            ):
                status, body = _post(base_a, {"version": 1, "event": bad})
                assert (status, body) == (400, {"version": 1, "result": "INVALID"}), (
                    f"an invalid CarrierMismatch envelope must be refused: {status} {body}"
                )
            assert _count(conn) == 2, "refused CarrierMismatch envelopes must add NO row"
            print(
                "PASS: GWA-6B D-43 CarrierMismatch durable denial row (opaque carrier_ref persisted; no fabricated refs;"
                " replay idempotent; invalid outcome / missing / malformed carrier_ref refused with no row)"
            )

            snapshot = _rows(conn)
        finally:
            _stop(server_a, thread_a)
            store_a.release()

        # PROOF GWA-7 — restart durability: fresh store + fresh server over the SAME disposable DB.
        store_b = PostgresGatewayAuditStore(dsn=proof_dsn)
        server_b, base_b = build_gateway_audit_server(store_b, host="127.0.0.1", port=0)
        thread_b = _serve(server_b)
        try:
            assert _rows(conn) == snapshot, "every durable row must survive store release + server stop (restart durability)"
            assert DurableAuditEmitter(base_b, timeout=5.0).emit(_success_event(_AUDIT_ID, "cid-gwa-1")) is None, (
                "a replay against the FRESH store/server must stay the idempotent DUPLICATE_MATCH success"
            )
            assert _rows(conn) == snapshot, "the fresh-instance replay must add NO row"
            print("PASS: GWA-7 restart durability (fresh store + fresh server; rows persist; replay stays DUPLICATE_MATCH)")

            # PROOF GWA-8 — append-only enforcement: UPDATE / DELETE / TRUNCATE rejected; rows unchanged.
            assert _raises(conn, "UPDATE control_gateway_audit SET outcome = 'mutated' WHERE id = %s", (snapshot[0][0],)), (
                "UPDATE must be rejected"
            )
            assert _raises(conn, "DELETE FROM control_gateway_audit WHERE id = %s", (snapshot[0][0],)), "DELETE must be rejected"
            # D-43: the CarrierMismatch denial row enjoys the SAME append-only protection.
            cm_protected = next(r for r in snapshot if r[6] == "CarrierMismatch")
            assert _raises(conn, "UPDATE control_gateway_audit SET outcome = 'success' WHERE id = %s", (cm_protected[0],)), (
                "UPDATE of the CarrierMismatch row must be rejected"
            )
            assert _raises(conn, "DELETE FROM control_gateway_audit WHERE id = %s", (cm_protected[0],)), (
                "DELETE of the CarrierMismatch row must be rejected"
            )
            assert _raises(conn, "TRUNCATE control_gateway_audit"), "TRUNCATE must be rejected"
            assert _rows(conn) == snapshot, "rows must be byte-identical after the rejected UPDATE/DELETE/TRUNCATE"
            print("PASS: GWA-8 append-only enforced live (UPDATE/DELETE/TRUNCATE rejected; CarrierMismatch row included; rows unchanged)")

            # PROOF GWA-9 — bounded failure with NO fallback and NO leakage.
            store_x = PostgresGatewayAuditStore(
                dsn=_pg.swap_db(admin_dsn, "sp2_gateway_audit_v1a_absent")
            )  # a database that does not exist
            server_x, base_x = build_gateway_audit_server(store_x, host="127.0.0.1", port=0)
            thread_x = _serve(server_x)
            try:
                status, body = _post(base_x, {"version": 1, "event": _wire("66666666666666666666666666666666", "cid-gwa-down")})
                assert (status, body) == (503, {"version": 1, "result": "UNAVAILABLE"}), (
                    "a store-DB outage must collapse to the bounded UNAVAILABLE envelope"
                )
                assert set(body.keys()) == {"version", "result"}, "no SQL/topology/exception detail may cross the ingest edge"
                try:
                    DurableAuditEmitter(base_x, timeout=5.0).emit(_success_event("77777777777777777777777777777777", "cid-gwa-down"))
                    raise AssertionError("the emitter must fail closed when the store DB is unreachable")
                except DurableAuditTransportError as exc:
                    assert exc.kind == "unavailable"
            finally:
                _stop(server_x, thread_x)
                store_x.release()
            assert _rows(conn) == snapshot, "no failure leg may write a fallback row or flush a buffered event"
            # Reference-only stored rows: no DSN/password substring in any durable cell (D-14).
            from urllib.parse import urlsplit

            secret_parts = [admin_dsn]
            password = urlsplit(admin_dsn).password
            if password:
                secret_parts.append(password)
            for row in _rows(conn):
                for cell in row:
                    for secret in secret_parts:
                        assert secret not in str(cell), "stored cells must never contain the DSN/password (references only)"
            print("PASS: GWA-9 bounded failure semantics live (503 UNAVAILABLE envelope; emitter fail-closed; no fallback row; no leakage)")
        finally:
            _stop(server_b, thread_b)
            store_b.release()
            try:
                conn.close()
            except Exception:
                pass
    finally:
        # PROOF GWA-10 — guaranteed teardown: the proof database is REMOVED (never retained).
        try:
            conn.close()
        except Exception:
            pass
        admin.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()", (_PROOF_DB,))
        admin.execute(f'DROP DATABASE IF EXISTS "{_PROOF_DB}"')
        remaining = _scalar(admin, "SELECT count(*) FROM pg_database WHERE datname = %s", (_PROOF_DB,))
        print(f"PASS: GWA-10 proof database torn down (datname count for {_PROOF_DB} = {remaining})")
        admin.close()
        assert remaining == 0, "the disposable proof database must be removed after the proof"


if __name__ == "__main__":
    _pg.run([test_gateway_audit_v1a_disposable_live_proof])
