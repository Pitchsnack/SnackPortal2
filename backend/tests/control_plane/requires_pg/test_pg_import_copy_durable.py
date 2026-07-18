"""W1a composed-core import copy + durable Import Audit — DISPOSABLE live-PostgreSQL proof (standalone-only).

The MANUAL_ONLY disposable proof of the W1a composed-core persistent import path and its durable Import
operational audit. Against three real, proof-owned PostgreSQL databases it applies the reviewed, blob-pinned
control Import-audit DDL (infrastructure/db/control/014_import_operational_audit.sql then
015_import_operational_audit_append_only.sql — exact paths, exact order, each exactly once, never a wildcard)
plus control 001-009 (unpinned) and the enrolled 14-file tenant template (including tenant 008), and proves the
REAL composed path end-to-end:

    Gateway.handle(/import/<ref>)  -> HttpImportInitiation -> served internal Import edge
      -> ImportService.start_import -> PgRoutedSessionProvider -> DatabaseRouter.route() (BULK)
         -> exactly one physical tenant database (sp2_w1a_import_proof_t1)
      -> startups upsert (ON CONFLICT global_startup_id) + atomic tenant-resident lineage + checkpoint
      -> BoundedImportAuditPolicy -> DurableImportAuditEmitter -> Import-audit ingest edge
         -> PostgresImportAuditStore -> control_import_audit (sp2_w1a_import_proof_control)

Proof set (phases W1A-0..W1A-12): reviewed-blob STOP-before-connect; three disposable databases created fresh;
live schema evidence (control_import_audit 12 cols, identity PK, unique audit_id, DB-default recorded_at, the
five-action / source_service / event_version CHECKs, both append-only triggers; the plain non-partial
startups_global_startup_id_key on each tenant DB); a fresh composed journey -> 200 ``created`` with the t1
startups row + lineage row read back and exactly three durable audit rows; idempotent replay -> 200
``replayed`` with row/lineage counts unchanged and exactly two more audit rows; a noop journey; physical
isolation (t2 untouched; a dual-carrier straddle -> 403 with zero rows and zero audit); DB-authority negatives
(a duplicate global_startup_id direct INSERT -> unique violation; UPDATE/DELETE/TRUNCATE on control_import_audit
each rejected); a post-commit audit-failure drill (ingest stopped -> 503, key preserved; restored -> replay
confirms exactly once); and guaranteed teardown of all three disposable databases.

ISOLATION & SAFETY. Everything runs in the proof-owned scratch databases sp2_w1a_import_proof_control /
sp2_w1a_import_proof_t1 / sp2_w1a_import_proof_t2 created from the SNACKPORTAL_TEST_DSN admin connection at
start and DROPPED in a ``finally`` — the proof owns the full lifecycle. The DSN must point ONLY at a disposable,
non-production instance; it must NEVER point at production, shared staging, the standing Control database, or any
tenant database. The repo DDL files are read + blob-pinned only, never modified. No standing SnackPortal2
database is named, read, or touched by this file.

SECRET HYGIENE (D-14). SNACKPORTAL_TEST_DSN is used through the ``_pg`` runner ONLY; no descriptor value is
printed, logged, or written, and the tenant descriptors are resolved in-memory through a proof-local
``SecretStore``. Stored rows are asserted to contain no descriptor/password substring.

DRIVER CONTAINMENT. This file imports NO database driver at module scope. PostgreSQL is reached only through the
sanctioned provider adapters, imported lazily inside the exercise so the module clean-skips without psycopg. The
served edges are hosted on test-owned daemon threads (production servers stay single-threaded and thread-free).

DEFAULT SUITE. IGNORED by the default test run (pyproject addopts ``--ignore=tests/control_plane/requires_pg``).
Run it standalone against a disposable instance:
  python backend/tests/control_plane/requires_pg/test_pg_import_copy_durable.py
With SNACKPORTAL_TEST_DSN unset (or psycopg absent) it clean-skips (exit 0, no DB touched).

NO OVERCLAIM. This proof is DISPOSABLE-ONLY: it does not touch the retained standing topology, does not
standing-enroll DDL 014/015, does not deliver operator retrieval, does not close any B5 blocker, and does not
change the activation gate. The routing view/secret resolution is proof-local (a disposable composition of the
REAL DatabaseRouter, PsycopgConnectionFactory, ImportService, LineageEmit, edges and stores).
"""

from __future__ import annotations

import hashlib
import pathlib
import sys
import threading
from typing import Any, Dict, Optional, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _pg  # noqa: E402  (standalone live-PG runner: SNACKPORTAL_TEST_DSN, available()/run()/swap_db())

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))  # backend on path

# The three proof-owned scratch databases: created and dropped by THIS file only. Collision-free vs every
# standing Control/tenant database name and every sibling harness scratch family.
_PROOF_CTL = "sp2_w1a_import_proof_control"
_PROOF_T1 = "sp2_w1a_import_proof_t1"
_PROOF_T2 = "sp2_w1a_import_proof_t2"

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
_CONTROL = _REPO_ROOT / "infrastructure" / "db" / "control"
_DDL_014 = _CONTROL / "014_import_operational_audit.sql"
_DDL_015 = _CONTROL / "015_import_operational_audit_append_only.sql"

# Reviewed W1a control-audit DDL blobs (full LF-normalized git-blob SHA-1). A mismatch STOPS the exercise BEFORE
# any connection is opened. Cross-checked in the default suite by test_b7c1_control_audit_ddl_blob_pins.py.
_REVIEWED_014_BLOB = "73436f9681163c8a86ee230f51206062b06735c5"
_REVIEWED_015_BLOB = "ba594e3cd6eb070790bde6015f5225960c0d62ed"

# Control DDL applied UNPINNED beside 014/015 (their blobs are pinned by the b7c1 guard; this proof only needs
# the base control schema present). 001-009, in order.
_CONTROL_DDL_UNPINNED = (
    "001_distinctness_ledger.sql",
    "002_provisioning_audit.sql",
    "003_provisioning_audit_append_only.sql",
    "004_control_tenants.sql",
    "005_control_memberships.sql",
    "006_control_federation.sql",
    "007_control_directory.sql",
    "008_distinctness_fingerprint_unique.sql",
    "009_control_tenants_cas_version.sql",
)

_T1_ID, _T2_ID = "t1", "t2"
_T1_REF, _T2_REF = "tenant/t1/dsn", "tenant/t2/dsn"
_SOURCE_REF = "g1"
_DISPLAY = "Acme Inc"


def _git_blob_sha1(path: pathlib.Path) -> str:
    data = path.read_bytes().replace(b"\r\n", b"\n")  # autocrlf normalization (the git blob is LF)
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def _verify_reviewed_blobs() -> None:
    """Resolve the committed blob IDs and STOP before connecting or applying SQL if either diverges from the
    reviewed pin (pure file I/O — no DB, no socket)."""
    b014, b015 = _git_blob_sha1(_DDL_014), _git_blob_sha1(_DDL_015)
    assert b014 == _REVIEWED_014_BLOB, f"014 blob {b014} != reviewed {_REVIEWED_014_BLOB} — STOP before connect/apply (do not fix DDL here)"
    assert b015 == _REVIEWED_015_BLOB, f"015 blob {b015} != reviewed {_REVIEWED_015_BLOB} — STOP before connect/apply (do not fix DDL here)"
    print(f"PASS: W1A-0 reviewed DDL blob pins verified BEFORE any connection (014={b014[:12]}…, 015={b015[:12]}…)")


def _scalar(conn: Any, sql: str, params: Tuple[Any, ...] = ()) -> Any:
    row = conn.execute(sql, params).fetchone()
    return row[0] if row else None


def _raises(conn: Any, sql: str, params: Tuple[Any, ...] = ()) -> bool:
    try:
        conn.execute(sql, params)
        return False
    except Exception:
        return True


def _serve(server: Any) -> threading.Thread:
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread


def _stop(server: Any, thread: Optional[threading.Thread]) -> None:
    server.shutdown()
    server.server_close()
    if thread is not None:
        thread.join(timeout=5)


# --- the exercise ---------------------------------------------------------------------------------
def test_w1a_import_copy_durable_live_proof(admin_dsn: str) -> None:
    # PROOF W1A-0 — reviewed blob pins verified BEFORE any connection or SQL (STOP rule).
    _verify_reviewed_blobs()

    # Lazy provider/composition imports: psycopg stays confined to the sanctioned zone; the module clean-skips
    # without it. Tests may import any package (lint-imports governs production packages only).
    from api_gateway.adapters.providers.http_import_initiation import HttpImportInitiation
    from api_gateway.main import build_gateway
    from api_gateway.models import AuthResult, InboundRequest, RouteOutcome, carrier_mismatch
    from api_gateway.ports import AuthenticatorPort, RouterDispatchPort
    from control_plane.adapters.providers.http_import_audit_api import build_import_audit_server
    from control_plane.adapters.providers.postgres_store import PostgresControlStore, PostgresImportAuditStore
    from control_plane.adapters.providers.postgres_tenant_schema_applicator import PostgresTenantSchemaApplicator
    from database_router.adapters.providers.in_memory_audit_sink import InMemoryAuditSink
    from database_router.adapters.providers.psycopg_connection import PsycopgConnectionFactory
    from database_router.cache import RoutingViewCache
    from database_router.models import TenantRoutingView
    from database_router.pool import ConnectionPoolManager
    from database_router.ports import ControlPlaneRoutingReadPort
    from database_router.resolver import RoutingResolver
    from database_router.router import DatabaseRouter
    from database_router.session_provider import PgRoutedSessionProvider
    from import_service.adapters.providers.durable_audit_emitter import DurableImportAuditEmitter, ImportAuditTransportError
    from import_service.adapters.providers.http_import_api import build_import_server
    from import_service.adapters.providers.startup_directory_source import StartupDirectorySource
    from import_service.main import BoundedImportAuditPolicy, build_import_service
    from import_service.ports import DirectoryPage, DirectoryReadPort, GlobalDirectoryRecordView
    from lineage_service.emit import LineageEmit
    from shared.secrets import SecretRef, SecretStore, SecretValue

    # -- proof-local composition doubles (all satisfying the REAL production ports) ------------------
    class _FixedSecretStore(SecretStore):
        def __init__(self, mapping: Dict[str, str]) -> None:
            self._m = mapping

        def resolve(self, ref: SecretRef) -> SecretValue:
            if ref.store_ref in self._m:
                return SecretValue(material=self._m[ref.store_ref])
            return SecretValue(material="w1a-proof-lineage-hmac-" + ref.store_ref)  # deterministic per-ref key

        def current_version(self, store_ref: str) -> str:
            return "1"

    class _FixedRoutingRead(ControlPlaneRoutingReadPort):
        def __init__(self) -> None:
            self._views = {
                _T1_ID: TenantRoutingView(_T1_ID, "Ready", True, SecretRef(_T1_REF, "1"), "1"),
                _T2_ID: TenantRoutingView(_T2_ID, "Ready", True, SecretRef(_T2_REF, "1"), "1"),
            }

        def get_routing_view(self, tenant_id: str):
            return self._views.get(tenant_id)

    class _FixedDirectoryRead(DirectoryReadPort):
        def get_record(self, kind: str, record_id: str) -> Optional[GlobalDirectoryRecordView]:
            if kind == "startup" and record_id == _SOURCE_REF:
                return GlobalDirectoryRecordView(
                    directory="GlobalStartupDirectory", record_id=record_id, display_name=_DISPLAY, attributes={}
                )
            return None

        def page(self, kind: str, cursor: Optional[str], limit: int) -> DirectoryPage:
            return DirectoryPage(records=[], next_cursor=None)

    class _StubAuth(AuthenticatorPort):
        def __init__(self, tenant: str) -> None:
            self._tenant = tenant

        def authenticate(self, authorization: Optional[str], recognized_carriers: Any, correlation_id: str) -> AuthResult:
            for carrier in recognized_carriers:
                if carrier != self._tenant:
                    raise carrier_mismatch()
            return AuthResult(correlation_id=correlation_id, principal_ref="ops", active_tenant_id=self._tenant, role="TENANT_AGENT")

    class _NoDispatchRouter(RouterDispatchPort):
        def dispatch(self, context: Any, decision: Any) -> RouteOutcome:  # pragma: no cover — must NEVER be called
            raise AssertionError("single-route violated: the composed import path must not call the Database Router dispatch")

    # Admin connection (autocommit: CREATE/DROP DATABASE are non-transactional).
    admin = PostgresControlStore(admin_dsn)._conn  # raw connection via the sanctioned adapter (no direct driver import)
    admin.autocommit = True
    server_num = int(_scalar(admin, "SELECT current_setting('server_version_num')"))
    assert server_num >= 110000, f"PostgreSQL >= 11 required (server_version_num={server_num})"

    ingest_server = ingest_thread = import_server = import_thread = None
    ctl_conn = t1_conn = t2_conn = None
    try:
        # PROOF W1A-1 — three disposable proof databases, lifecycle-owned by THIS run (leftovers dropped first).
        for name in (_PROOF_CTL, _PROOF_T1, _PROOF_T2):
            admin.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()", (name,))
            admin.execute(f'DROP DATABASE IF EXISTS "{name}"')
            admin.execute(f'CREATE DATABASE "{name}"')
        ctl_dsn = _pg.swap_db(admin_dsn, _PROOF_CTL)
        t1_dsn = _pg.swap_db(admin_dsn, _PROOF_T1)
        t2_dsn = _pg.swap_db(admin_dsn, _PROOF_T2)
        print(f"PASS: W1A-1 three disposable proof databases created fresh ({_PROOF_CTL}, {_PROOF_T1}, {_PROOF_T2})")

        # PROOF W1A-2 — apply control 001-009 (unpinned) then 014 then 015 (each exactly once, exact order).
        ctl_conn = PostgresControlStore(ctl_dsn)._conn
        ctl_conn.autocommit = True
        with ctl_conn.cursor() as cur:
            for name in _CONTROL_DDL_UNPINNED:
                cur.execute((_CONTROL / name).read_text(encoding="utf-8"))
            cur.execute(_DDL_014.read_text(encoding="utf-8"))
            cur.execute(_DDL_015.read_text(encoding="utf-8"))
        assert _scalar(ctl_conn, "SELECT to_regclass('control_import_audit')") is not None, "control_import_audit must exist after apply"
        print("PASS: W1A-2 control DDL applied (001-009 unpinned, then 014_import_operational_audit.sql, then 015)")

        # PROOF W1A-3 — the 14-file enrolled tenant template applied to BOTH disposable tenant databases.
        secrets = _FixedSecretStore({_T1_REF: t1_dsn, _T2_REF: t2_dsn})
        applicator = PostgresTenantSchemaApplicator(secrets)
        applicator.apply_schema(_T1_ID, target=_PROOF_T1, association_ref=SecretRef(store_ref=_T1_REF, version="1"))
        applicator.apply_schema(_T2_ID, target=_PROOF_T2, association_ref=SecretRef(store_ref=_T2_REF, version="1"))
        t1_conn = PostgresControlStore(t1_dsn)._conn
        t1_conn.autocommit = True
        t2_conn = PostgresControlStore(t2_dsn)._conn
        t2_conn.autocommit = True
        for tconn in (t1_conn, t2_conn):
            assert _scalar(tconn, "SELECT to_regclass('startups')") is not None, "startups must exist after the tenant template"
            idx = _scalar(tconn, "SELECT indexdef FROM pg_indexes WHERE indexname = 'startups_global_startup_id_key'")
            assert idx is not None and "UNIQUE" in idx and "WHERE" not in idx, f"008 must be a plain UNIQUE index: {idx}"
        print("PASS: W1A-3 14-file tenant template applied to both tenant DBs; plain UNIQUE startups_global_startup_id_key present")

        # PROOF W1A-4 — live control_import_audit schema evidence from the PostgreSQL catalogs.
        cols = ctl_conn.execute(
            "SELECT column_name, data_type, is_nullable, is_identity, column_default FROM information_schema.columns"
            " WHERE table_schema='public' AND table_name='control_import_audit' ORDER BY ordinal_position"
        ).fetchall()
        names = [c[0] for c in cols]
        assert names == [
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
            "target_ref",
            "source_ref",
        ], f"exact 12-column contract violated: {names}"
        meta = {c[0]: c for c in cols}
        assert meta["id"][3] == "YES", "id must be GENERATED ALWAYS AS IDENTITY"
        assert "now()" in (meta["recorded_at"][4] or ""), "recorded_at must carry the DB DEFAULT now()"
        checks = [
            r[0]
            for r in ctl_conn.execute(
                "SELECT conname FROM pg_constraint WHERE conrelid='control_import_audit'::regclass AND contype='c'"
            ).fetchall()
        ]
        for check in (
            "control_import_audit_action_check",
            "control_import_audit_event_version_check",
            "control_import_audit_source_service_check",
        ):
            assert check in checks, f"the frozen {check} must exist"
        triggers = sorted(
            r[0]
            for r in ctl_conn.execute(
                "SELECT tgname FROM pg_trigger WHERE tgrelid='control_import_audit'::regclass AND NOT tgisinternal"
            ).fetchall()
        )
        assert triggers == ["control_import_audit_no_mutation", "control_import_audit_no_truncate"], (
            f"append-only triggers missing: {triggers}"
        )
        print(
            "PASS: W1A-4 live control_import_audit schema (12 cols, identity PK, DB-default recorded_at, 3 CHECKs, 2 append-only triggers)"
        )

        # --- compose the REAL stack (disposable): ingest edge + import service (router->t1/t2) + import edge + gateway
        def _audit_count() -> int:
            return int(_scalar(ctl_conn, "SELECT count(*) FROM control_import_audit"))

        def _startups(tconn: Any) -> int:
            return int(_scalar(tconn, "SELECT count(*) FROM startups"))

        def _lineage(tconn: Any) -> int:
            return int(_scalar(tconn, "SELECT count(*) FROM lineage"))

        def _build_import_edge() -> Tuple[Any, str]:
            resolver = RoutingResolver(
                _FixedRoutingRead(), RoutingViewCache(ttl_seconds=60.0, clock=lambda: 0.0), supported_schema_versions=("1",)
            )
            router = DatabaseRouter(
                resolver=resolver,
                pool=ConnectionPoolManager(max_per_tenant=5, idle_timeout_seconds=60.0, clock=lambda: 0.0),
                bulk_pool=ConnectionPoolManager(max_per_tenant=5, idle_timeout_seconds=60.0, clock=lambda: 0.0),
                secret_store=secrets,
                connection_factory=PsycopgConnectionFactory(),
                audit=InMemoryAuditSink(),
            )
            policy = BoundedImportAuditPolicy(
                DurableImportAuditEmitter(ingest_base, timeout=5.0), transport_error=ImportAuditTransportError
            )
            directory = _FixedDirectoryRead()
            service = build_import_service(
                session_provider=PgRoutedSessionProvider(router),
                lineage=LineageEmit(secrets),
                directory_read=directory,
                directory_source=StartupDirectorySource(directory),
                audit=policy,
                batch_size=2,
            )
            return build_import_server(service, host="127.0.0.1", port=0)

        def _gateway(import_base: str) -> Any:
            return build_gateway(
                authenticator=_StubAuth(_T1_ID),
                router=_NoDispatchRouter(),
                import_initiation=HttpImportInitiation(import_base, timeout=5.0),
            )

        # PROOF W1A-5 — the ingest edge over the disposable control DB (real store).
        ingest_server, ingest_base = build_import_audit_server(PostgresImportAuditStore(dsn=ctl_dsn), host="127.0.0.1", port=0)
        ingest_thread = _serve(ingest_server)

        # PROOF W1A-6 — fresh composed journey -> 200 created; t1 row + lineage; exactly three durable audit rows.
        import_server, import_base = _build_import_edge()
        import_thread = _serve(import_server)
        gateway = _gateway(import_base)

        def _import(operation_key: str, *, host: str = "", extra_headers: Optional[Dict[str, str]] = None) -> Any:
            headers = {"x-correlation-id": "cid-" + operation_key, "x-operation-key": operation_key}
            if extra_headers:
                headers.update(extra_headers)
            return gateway.handle(
                InboundRequest(method="POST", path=f"/import/{_SOURCE_REF}", host=host, headers=headers, authorization="Bearer tok")
            )

        resp = _import("op-created")
        assert (resp.status, resp.public_code) == (200, "ok"), f"fresh import must be 200 ok: {resp.status} {resp.public_code}"
        dto = resp.portal_dto
        assert dto is not None and dto.outcome == "created" and dto.tenant_record_ref == f"{_T1_ID}:startups:{_SOURCE_REF}", f"DTO: {dto}"
        assert _startups(t1_conn) == 1 and _lineage(t1_conn) >= 1, "the tenant startups row + lineage must be written"
        row = t1_conn.execute("SELECT global_startup_id, company_name FROM startups").fetchone()
        assert row == (_SOURCE_REF, _DISPLAY), f"the mapped startups row must be present: {row}"
        assert _audit_count() == 3, (
            f"a fresh import must durably record exactly 3 audit rows (Requested/Started/Completed): {_audit_count()}"
        )
        print(
            "PASS: W1A-6 fresh composed journey (Gateway.handle -> import edge -> router -> t1; created; row+lineage; 3 durable audit rows)"
        )

        # PROOF W1A-7 — idempotent replay: same operation_key -> replayed; row/lineage unchanged; +2 audit rows.
        resp2 = _import("op-created")
        assert resp2.portal_dto is not None and resp2.portal_dto.outcome == "replayed", (
            f"a same-key retry must be replayed: {resp2.portal_dto}"
        )
        assert _startups(t1_conn) == 1, "a replay must add NO tenant row"
        assert _audit_count() == 5, f"a replay durably records exactly 2 more audit rows (Requested + Completed replayed): {_audit_count()}"
        print("PASS: W1A-7 idempotent replay (same operation_key -> replayed; no new row; +2 durable audit rows)")

        # PROOF W1A-8 — noop journey: a new key over the unchanged record -> noop (no new row).
        resp3 = _import("op-noop")
        assert resp3.portal_dto is not None and resp3.portal_dto.outcome == "noop", f"an unchanged re-copy must be noop: {resp3.portal_dto}"
        assert _startups(t1_conn) == 1, "a noop must add NO tenant row"
        print("PASS: W1A-8 noop journey (new operation_key, unchanged record -> noop; row count stable)")

        # PROOF W1A-9 — physical isolation: t2 untouched; a dual-carrier straddle -> 403 with zero effect.
        assert _startups(t2_conn) == 0 and _lineage(t2_conn) == 0, "the OTHER tenant database must be physically untouched"
        audit_before = _audit_count()
        straddle = _import("op-straddle", host="t2.base.tld", extra_headers={"x-tenant-id": _T1_ID})  # two distinct carriers
        assert straddle.status == 403 and straddle.portal_dto is None, "a dual-carrier straddle must be denied 403 with no DTO"
        assert _startups(t1_conn) == 1 and _startups(t2_conn) == 0, "a denied straddle must write no tenant row"
        assert _audit_count() == audit_before, "a denied straddle must emit no durable import audit (the Import Service never ran)"
        print("PASS: W1A-9 physical isolation (t2 untouched; dual-carrier straddle -> 403; zero rows; zero durable audit)")

        # PROOF W1A-10 — DB-authority negatives: 008 uniqueness + 015 append-only enforced by the database.
        assert _raises(t1_conn, "INSERT INTO startups (global_startup_id, company_name) VALUES (%s, %s)", (_SOURCE_REF, "Duplicate")), (
            "the tenant 008 UNIQUE index must reject a duplicate global_startup_id"
        )
        one_id = _scalar(ctl_conn, "SELECT id FROM control_import_audit ORDER BY id ASC LIMIT 1")
        assert _raises(ctl_conn, "UPDATE control_import_audit SET outcome = 'mutated' WHERE id = %s", (one_id,)), "UPDATE must be rejected"
        assert _raises(ctl_conn, "DELETE FROM control_import_audit WHERE id = %s", (one_id,)), "DELETE must be rejected"
        assert _raises(ctl_conn, "TRUNCATE control_import_audit"), "TRUNCATE must be rejected"
        assert _audit_count() == 8, (
            "the rejected direct mutations must leave the durable audit rows unchanged (3 fresh + 2 replay + 3 noop)"
        )
        print("PASS: W1A-10 database authority (008 UNIQUE rejects a duplicate; UPDATE/DELETE/TRUNCATE on control_import_audit rejected)")

        # PROOF W1A-11 — post-commit audit-failure drill: ingest down -> 503 fail-closed; restored -> replay confirms once.
        _stop(ingest_server, ingest_thread)
        ingest_server = ingest_thread = None
        down = _import("op-created")  # a same-key retry whose durable completion confirmation cannot land
        assert down.status == 503 and down.portal_dto is None, (
            "a terminal durable-audit failure must fail closed 503 (audit-before-hand-back)"
        )
        assert _startups(t1_conn) == 1, "the fail-closed drill must not corrupt the applied tenant state"
        ingest_server, ingest_base = build_import_audit_server(PostgresImportAuditStore(dsn=ctl_dsn), host="127.0.0.1", port=0)
        ingest_thread = _serve(ingest_server)
        # Rebuild the import edge so the emitter targets the restored ingest base URL.
        _stop(import_server, import_thread)
        import_server, import_base = _build_import_edge()
        import_thread = _serve(import_server)
        gateway = _gateway(import_base)
        recovered = _import("op-created")
        assert recovered.portal_dto is not None and recovered.portal_dto.outcome == "replayed", (
            "the confirming retry must replay exactly once"
        )
        assert _startups(t1_conn) == 1, "recovery must not duplicate the tenant row"
        print("PASS: W1A-11 post-commit audit-failure drill (ingest down -> 503 fail-closed; restored -> replay confirms exactly once)")

        # PROOF W1A-12 — reference-only stored rows (no descriptor/password substring in any durable cell).
        from urllib.parse import urlsplit

        secret_parts = [admin_dsn]
        password = urlsplit(admin_dsn).password
        if password:
            secret_parts.append(password)
        for r in ctl_conn.execute("SELECT * FROM control_import_audit").fetchall():
            for cell in r:
                for secret in secret_parts:
                    assert secret not in str(cell), "stored cells must never contain the descriptor/password (references only)"
        print("PASS: W1A-12 reference-only durable rows (no descriptor/password substring in any control_import_audit cell)")
    finally:
        # Guaranteed teardown: every server stopped, every connection closed, all three proof databases REMOVED.
        for server, thread in ((import_server, import_thread), (ingest_server, ingest_thread)):
            if server is not None:
                try:
                    _stop(server, thread)
                except Exception:
                    pass
        for conn in (ctl_conn, t1_conn, t2_conn):
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
        remaining = 0
        for name in (_PROOF_CTL, _PROOF_T1, _PROOF_T2):
            admin.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()", (name,))
            admin.execute(f'DROP DATABASE IF EXISTS "{name}"')
            remaining += int(_scalar(admin, "SELECT count(*) FROM pg_database WHERE datname = %s", (name,)))
        print(f"PASS: W1A-13 all three disposable proof databases torn down (retained datname count = {remaining})")
        admin.close()
        assert remaining == 0, "every disposable proof database must be removed after the proof"


if __name__ == "__main__":
    _pg.run([test_w1a_import_copy_durable_live_proof])
