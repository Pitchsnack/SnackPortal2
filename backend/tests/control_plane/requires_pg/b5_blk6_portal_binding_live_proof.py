"""B5-BLK-6C-C — real Control-DB portal-composition disposable proof (operator module; MANUAL_ONLY).

Closes the exact B5-BLK-6C readiness gap: the Gateway-composed CONTROL portal read (startup/investor
directory + MembershipsForPrincipal) had only ever been proven over an in-memory ControlStore. This
operator proves the SAME accepted composition topology over a REAL PostgreSQL Control database:

    fresh disposable Control DB (created by THIS run, dropped in ``finally``)
    -> control DDL 001-009 only (the accepted ``_apply_control_ddl`` pattern, lockstep-read against
       the accepted helper's own apply order — the ops harness itself is never imported, by guard)
    -> direct-SQL seed on the B-7A scratch-SQL seam (``'{}'::jsonb`` — the MCC-AR-1 runtime write defect
       means the seed must NEVER route through ``put_directory_record``)
    -> real ``PostgresControlStore``-backed ``ControlPlane`` (explicit ``store=`` injection)
    -> the existing loopback Control-Plane read edge (``make_server``; PRD 07E-1)
    -> the production ``HttpControlPlaneRead`` adapter selected through the REAL env seam
       (``build_control_plane_read_from_env`` / SP2_GW_CONTROL_READ_BASE_URL)
    -> the existing API Gateway with ``control_read`` injected (``build_gateway``)
    -> every required 6C-C scenario (success, empty, fail-closed, envelope, IC-007-negative, pagination
       limitation, malformed/oversized/unavailable) with exact audit cardinality
    -> mandatory ``finally`` teardown; ``pg_database`` datname census proves ZERO retained artifact.

HONESTY / NON-CLAIMS (binding). The ``workspace_memberships_read`` success event is observed with an
IN-MEMORY recorder (AD-1 Option A no-sink port) — this proof claims NO durable audit persistence and no
operator audit retrieval (Stage C scope). ImportInitiation is an accepted-initiation ENVELOPE only and
TenantOperation is a references-only dispatch outcome against a stub router — neither is a persistent
business write or a real tenant-DB operation; the proof asserts the Control-DB row census is UNCHANGED
by both (rows_before == rows_after). The gateway adapter composes ONE directory page only (no cursor or
limit is sent; ``next_cursor`` is never followed) — this proof pins that limitation and claims NO
pagination support. No served northbound ingress, no Lovable integration, no tenant-DB routing, no
cross-cluster distinctness, no production database identity, no positive IC-007 capability. B5-BLK-6
remains OPEN; B5-BLK-5 remains OPEN; production remains NOT READY / DO-NOT-ACTIVATE.

SECRET HYGIENE (D-14). The admin DSN arrives as a parameter (resolved by the wrapper from
SNACKPORTAL_TEST_DSN) and is never printed; every transcript line is swept by the wrapper for
DSN/password/token/PEM leakage. Import of this module is inert (no I/O, no env mutation, no socket);
the database driver is reached ONLY through the sanctioned provider adapter (``PostgresControlStore``,
lazily imported inside the run — Driver Containment Standard).
"""

from __future__ import annotations

import ast
import os
import pathlib
import sys
import threading
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _pg  # noqa: E402  (standalone live-PG helpers: swap_db; the wrapper owns dsn()/skip policy)

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))  # backend on path

# Pure-stdlib backend modules only at module scope (the 07D/DBR-AR-2D precedent); every
# psycopg-bearing or composition-heavy module is imported lazily inside run_proof.
from api_gateway.adapters.providers.http_control_plane_read import HttpControlPlaneRead  # noqa: E402
from api_gateway.main import GW_CONTROL_READ_BASE_URL_ENV, build_control_plane_read_from_env, build_gateway  # noqa: E402
from api_gateway.models import (  # noqa: E402
    AuditAction,
    AuthResult,
    GatewayAuditEvent,
    InboundRequest,
    RouteOutcome,
    carrier_mismatch,
    unauthenticated,
)
from api_gateway.portal import (  # noqa: E402
    GlobalInvestorSummaryDTO,
    GlobalStartupSummaryDTO,
    ImportInitiationDTO,
    WorkspaceMembershipDTO,
    serialize_portal_dto,
)
from api_gateway.ports import AuditEmitterPort, AuthenticatorPort, RouterDispatchPort  # noqa: E402

# The proof-owned disposable Control database (created and dropped by THIS run only; collision-free
# vs every standing database name and every sibling harness scratch family).
_PROOF_DB = "sp2_b5_blk6_portal_proof"

# The canonical control DDL directory (files are READ here and never embedded or modified).
_CONTROL_DDL_DIR = pathlib.Path(__file__).resolve().parents[4] / "infrastructure" / "db" / "control"

# The canonical control DDL apply order this proof REQUIRES (lockstep-asserted against the accepted
# helper's own ``_CONTROL_DDL_ORDER`` before any SQL runs). Exactly 001-009 — nothing more.
_EXPECTED_CONTROL_DDL_ORDER: Tuple[str, ...] = (
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

# The EXACT public-table census 001-009 creates. Set equality below proves both directions:
# nothing missing AND nothing extra (no routing-audit table, no tenant table — no other DDL ran).
_CONTROL_TABLES: Tuple[str, ...] = (
    "control_distinctness_ledger",
    "control_audit",
    "control_tenants",
    "control_memberships",
    "control_federation",
    "control_directory",
)

# The complete scenario census. The wrapper refuses a proof-complete claim unless EVERY label
# executed — a skipped/hollow run can never claim success (non-skippability, 6C-C §7.5).
SCENARIO_LABELS: Tuple[str, ...] = (
    "startup-directory",
    "investor-directory",
    "live-read-through-identity",
    "memberships-nonempty-audit",
    "memberships-empty-audit",
    "unsupported-kind-fail-closed",
    "client-kind-and-self-scope",
    "import-initiation-envelope",
    "tenant-operation-dispatch",
    "ic007-negatives",
    "pagination-one-page-limitation",
    "malformed-response",
    "oversized-response",
    "control-read-unavailable",
)

_FIXED_TS = "2026-07-18T00:00:00+00:00"  # deterministic seed timestamps (all-text columns; MCC §9)

_TRANSCRIPT: List[str] = []


def _say(line: str) -> None:
    _TRANSCRIPT.append(line)
    print(line)


def _scalar(conn: Any, sql: str, params: Tuple[Any, ...] = ()) -> Any:
    row = conn.execute(sql, params).fetchone()
    return row[0] if row else None


def _accepted_helper_ddl_order() -> Tuple[str, ...]:
    """The accepted B5-4 helper's own ``_CONTROL_DDL_ORDER``, read WITHOUT importing the ops harness.

    An accepted guard (test_b5_5_smoke_c_spec_and_crypto_fixture) pins that only the B5-4 proof may
    IMPORT ``b5_standing_topology`` — so this proof lockstep-reads the accepted apply order by AST
    (read-only) and replicates the apply pattern locally instead of invoking the ops harness.
    """
    source = (pathlib.Path(__file__).resolve().parent / "b5_standing_topology.py").read_text(encoding="utf-8")
    for node in ast.parse(source).body:
        targets = node.targets if isinstance(node, ast.Assign) else ([node.target] if isinstance(node, ast.AnnAssign) else [])
        if any(isinstance(t, ast.Name) and t.id == "_CONTROL_DDL_ORDER" for t in targets):
            value = node.value
            if isinstance(value, ast.Tuple):
                return tuple(e.value for e in value.elts if isinstance(e, ast.Constant) and isinstance(e.value, str))
    raise AssertionError("could not locate the accepted helper's _CONTROL_DDL_ORDER (lockstep read failed)")


def _apply_control_ddl(control_dsn: str, store_cls: Any) -> None:
    """Apply the canonical control DDL 001-009 in ONE transaction (single commit; templates read-only).

    The accepted B5-4 ``_apply_control_ddl`` pattern, replicated: missing assets refuse before any
    connection; any failure rolls back with no partial pass committed. The database driver is reached
    only through the sanctioned provider adapter (``store_cls`` = ``PostgresControlStore``).
    """
    missing = [name for name in _EXPECTED_CONTROL_DDL_ORDER if not (_CONTROL_DDL_DIR / name).is_file()]
    assert not missing, f"canonical control DDL assets missing on disk: {missing}"
    store = store_cls(control_dsn)
    conn = store._conn
    try:
        with conn.cursor() as cur:
            for name in _EXPECTED_CONTROL_DDL_ORDER:
                cur.execute((_CONTROL_DDL_DIR / name).read_text(encoding="utf-8"))
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        store.release()


class _ProofAuthenticator(AuthenticatorPort):
    """Minimal IC-005 authenticator double (token-ref -> principal/tenant/role; fail-closed).

    A LOCAL double by design: authentication is not the 6C-C surface under proof (the real
    IC-005 path is Smoke-C-proven); the CONTROL read composition behind it is.
    """

    def __init__(self) -> None:
        self._tokens: Dict[str, Tuple[str, Optional[str], Optional[str]]] = {}

    def add_token(self, token: str, *, principal: str, tenant: Optional[str], role: Optional[str]) -> None:
        self._tokens[token] = (principal, tenant, role)

    def authenticate(self, authorization: Optional[str], recognized_carriers: Sequence[str], correlation_id: str) -> AuthResult:
        if authorization is None or authorization not in self._tokens:
            raise unauthenticated()
        principal, tenant, role = self._tokens[authorization]
        if tenant is not None:
            for carrier in recognized_carriers:
                if carrier != tenant:
                    raise carrier_mismatch()
        return AuthResult(correlation_id=correlation_id, principal_ref=principal, active_tenant_id=tenant, role=role)


class _ProofRouter(RouterDispatchPort):
    """Stub router: records handoffs, returns the references-only success RouteOutcome.

    TenantOperation/ImportInitiation legs are ENVELOPE/DISPATCH proofs only — no database is
    routed, no business write occurs, and no real business result may be claimed from this stub.
    """

    def __init__(self) -> None:
        self.handoffs: List[Tuple[Any, Any]] = []

    def dispatch(self, context: Any, decision: Any) -> RouteOutcome:
        self.handoffs.append((context, decision))
        return RouteOutcome(status=200, public_code="ok", dispatched=True)


class _RecordingAudit(AuditEmitterPort):
    """IN-MEMORY audit recorder (AD-1 Option A). Observation only — NEVER durable persistence."""

    def __init__(self) -> None:
        self.events: List[GatewayAuditEvent] = []

    def emit(self, event: GatewayAuditEvent) -> None:
        self.events.append(event)


class _MalformedEdgeHandler(BaseHTTPRequestHandler):
    """Fault-injecting Control-Plane edge: every GET answers 200 with a non-JSON body."""

    def do_GET(self) -> None:  # noqa: N802 (http.server API)
        payload = b"this is not json"
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args: object) -> None:
        return


def _req(
    method: str,
    path: str,
    token: Optional[str],
    *,
    host: str = "",
    headers: Optional[Dict[str, str]] = None,
    query: Optional[Dict[str, str]] = None,
) -> InboundRequest:
    return InboundRequest(method=method, path=path, host=host, headers=headers or {}, query=query or {}, authorization=token)


def _select_control_read(base_url: str) -> HttpControlPlaneRead:
    """Select the production adapter through the REAL env seam (never a hand-rolled default)."""
    os.environ[GW_CONTROL_READ_BASE_URL_ENV] = base_url
    port = build_control_plane_read_from_env()
    assert isinstance(port, HttpControlPlaneRead), "the env seam must yield the production HttpControlPlaneRead"
    return port


def _success_events(audit: _RecordingAudit) -> List[GatewayAuditEvent]:
    return [e for e in audit.events if e.action is AuditAction.WORKSPACE_MEMBERSHIPS_READ]


def _row_census(conn: Any) -> Dict[str, int]:
    return {table: int(_scalar(conn, f"SELECT count(*) FROM {table}")) for table in _CONTROL_TABLES}


def run_proof(admin_dsn: str) -> Dict[str, Any]:  # noqa: C901 (one linear governed proof arc)
    """Execute the full 6C-C proof arc against a fresh disposable Control DB; ALWAYS tear down."""
    _TRANSCRIPT.clear()
    evidence: Dict[str, Any] = {"scenarios": {}, "transcript": _TRANSCRIPT}

    def _done(label: str, **details: Any) -> None:
        assert label in SCENARIO_LABELS, f"unknown scenario label {label!r}"
        evidence["scenarios"][label] = {"executed": True, **details}
        _say(f"PASS: {label}")

    # Lazy composition/provider imports (Driver Containment Standard; the DBR-AR-2D precedent).
    from control_plane import main as cp_main
    from control_plane.adapters.providers.http_read_api import make_server
    from control_plane.adapters.providers.postgres_store import PostgresControlStore

    # Refuse a live-composition environment: the four control-plane composition selectors (read
    # via the cp_main constants — no literal env name here) must be at their in-memory defaults;
    # this proof composes its plane by EXPLICIT store injection only.
    for selector in (
        cp_main.CONTROL_STORE_ENV,
        cp_main.PROVISIONING_ADAPTER_ENV,
        cp_main.TENANT_SCHEMA_APPLICATOR_ENV,
        cp_main.DISTINCTNESS_LEDGER_ENV,
    ):
        value = (os.environ.get(selector) or "in_memory").strip().lower()
        assert value in ("", "in_memory"), f"refusing to run with {selector} set to a non-default composition (fail closed)"

    env_before = os.environ.get(GW_CONTROL_READ_BASE_URL_ENV)

    admin_store = PostgresControlStore(admin_dsn)
    admin = admin_store._conn
    admin.autocommit = True  # CREATE/DROP DATABASE are non-transactional
    server_num = int(_scalar(admin, "SELECT current_setting('server_version_num')"))
    assert server_num >= 110000, f"PostgreSQL >= 11 required (server_version_num={server_num})"

    # Disposable-DB pre-flight: the name must NOT exist (refuse-if-exists — never adopt leftovers).
    pre = int(_scalar(admin, "SELECT count(*) FROM pg_database WHERE datname = %s", (_PROOF_DB,)))
    assert pre == 0, f"disposable database name already exists (datname count {pre}) — refusing; drop it manually and re-run"
    cluster_before = sorted(r[0] for r in admin.execute("SELECT datname FROM pg_database").fetchall())
    admin.execute(f'CREATE DATABASE "{_PROOF_DB}"')
    _say(f"PASS: disposable Control DB created fresh ({_PROOF_DB}; pre-create datname count was 0)")
    proof_dsn = _pg.swap_db(admin_dsn, _PROOF_DB)

    seed_store: Optional[Any] = None
    plane_store: Optional[Any] = None
    server: Optional[HTTPServer] = None
    fault_server: Optional[HTTPServer] = None
    try:
        # --- DDL 001-009 only, via the accepted helper PATTERN (lockstep-asserted first) -----------
        assert _accepted_helper_ddl_order() == _EXPECTED_CONTROL_DDL_ORDER, (
            "the accepted _CONTROL_DDL_ORDER drifted from the pinned 001-009 set — refusing to apply"
        )
        _apply_control_ddl(proof_dsn, PostgresControlStore)

        seed_store = PostgresControlStore(proof_dsn)
        seed = seed_store._conn
        seed.autocommit = True  # direct-SQL seed: each statement its own transaction (B-7A/MCC idiom)
        assert _scalar(seed, "SELECT current_database()") == _PROOF_DB
        tables = {r[0] for r in seed.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'").fetchall()}
        assert tables == set(_CONTROL_TABLES), f"public-table census must be EXACTLY the 001-009 set; got {sorted(tables)}"
        assert _scalar(seed, "SELECT to_regclass('control_routing_audit')") is None, "the durable routing-audit table must be ABSENT"
        _say("PASS: control DDL 001-009 applied; public-table census exact (no routing-audit table, no tenant DDL)")

        # --- direct-SQL seed under MCC-AR-1 (never the runtime write API) --------------------------
        for record_id, display in (("b5c-s-001", "Proof Startup One"), ("b5c-s-002", "Proof Startup Two")):
            seed.execute(
                "INSERT INTO control_directory (directory, record_id, display_name, attributes) VALUES (%s,%s,%s,'{}'::jsonb)",
                ("GlobalStartupDirectory", record_id, display),
            )
        for record_id, display in (("b5c-i-001", "Proof Investor One"), ("b5c-i-002", "Proof Investor Two")):
            seed.execute(
                "INSERT INTO control_directory (directory, record_id, display_name, attributes) VALUES (%s,%s,%s,'{}'::jsonb)",
                ("GlobalInvestorDirectory", record_id, display),
            )
        for tenant_id in ("b5c_t1", "b5c_t2"):
            seed.execute(
                "INSERT INTO control_tenants (tenant_id, organization_ref, lifecycle_state, expected_schema_version,"
                " assoc_store_ref, assoc_version, federation_config_ref, created_at, updated_at)"
                " VALUES (%s,'b5c_org','Ready','1',%s,'1','b5c_fed',%s,%s)",
                (tenant_id, f"ref-{tenant_id}", _FIXED_TS, _FIXED_TS),
            )
        for principal, tenant_id, role in (("b5c_member", "b5c_t1", "MASTER_AGENT"), ("b5c_member", "b5c_t2", "TENANT_AGENT")):
            seed.execute("INSERT INTO control_memberships (principal_ref, tenant_id, role) VALUES (%s,%s,%s)", (principal, tenant_id, role))
        _say("PASS: direct-SQL seed complete (2 startups, 2 investors, 2 tenants, 2 memberships; '{}'::jsonb per MCC-AR-1)")

        # --- real composition: Postgres-backed ControlPlane -> loopback edge -> env-seam adapter ---
        plane_store = PostgresControlStore(proof_dsn)
        plane = cp_main.ControlPlane(store=plane_store)
        server, base = make_server(plane, "127.0.0.1", 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        control_read = _select_control_read(base)

        authn = _ProofAuthenticator()
        authn.add_token("tok-member", principal="b5c_member", tenant=None, role="CONTROL")
        authn.add_token("tok-empty", principal="b5c_empty", tenant=None, role="CONTROL")
        authn.add_token("tok-t1", principal="b5c_agent", tenant="b5c_t1", role="TENANT_AGENT")
        router = _ProofRouter()
        audit = _RecordingAudit()
        gateway = build_gateway(authenticator=authn, router=router, control_read=control_read, audit=audit)
        _say(f"PASS: real composition assembled (PostgresControlStore -> ControlPlane -> loopback edge {base.split(':')[0]}:*)")

        # --- S1: startup directory non-empty (0 success audit events; composed, not routed) --------
        resp = gateway.handle(_req("GET", "/directory/startup", "tok-member"))
        assert (resp.status, resp.public_code, resp.dispatched) == (200, "ok", True)
        assert isinstance(resp.portal_dto, GlobalStartupSummaryDTO)
        assert tuple(e.record_ref for e in resp.portal_dto.records) == ("b5c-s-001", "b5c-s-002")
        assert resp.portal_dto.records[0].display_name == "Proof Startup One"
        assert (resp.portal_dto.record_origin, resp.portal_dto.record_residency) == ("global", "global")
        assert resp.portal_dto.record_type == "GlobalStartupDirectory"
        assert router.handoffs == [] and audit.events == []
        _done("startup-directory", records=2, audit_events=0)

        # --- S2: investor directory non-empty (0 success audit events) -----------------------------
        resp = gateway.handle(_req("GET", "/directory/investor", "tok-member"))
        assert isinstance(resp.portal_dto, GlobalInvestorSummaryDTO)
        assert tuple(e.record_ref for e in resp.portal_dto.records) == ("b5c-i-001", "b5c-i-002")
        assert resp.portal_dto.record_type == "GlobalInvestorDirectory"
        assert router.handoffs == [] and audit.events == []
        _done("investor-directory", records=2, audit_events=0)

        # --- S3: live read-through — the composed read tracks the disposable DB's live content -----
        seed.execute(
            "INSERT INTO control_directory (directory, record_id, display_name, attributes) VALUES (%s,%s,%s,'{}'::jsonb)",
            ("GlobalStartupDirectory", "b5c-s-003", "Proof Startup Three"),
        )
        resp = gateway.handle(_req("GET", "/directory/startup", "tok-member"))
        assert isinstance(resp.portal_dto, GlobalStartupSummaryDTO)
        assert tuple(e.record_ref for e in resp.portal_dto.records) == ("b5c-s-001", "b5c-s-002", "b5c-s-003")
        assert audit.events == []
        _done("live-read-through-identity", database=_PROOF_DB, records_after_insert=3)

        # --- S4: memberships non-empty -> EXACTLY ONE workspace_memberships_read (full shape) ------
        resp = gateway.handle(_req("GET", "/memberships", "tok-member", headers={"X-Correlation-Id": "cid-6cc-4"}))
        assert (resp.status, resp.public_code, resp.dispatched) == (200, "ok", True)
        assert isinstance(resp.portal_dto, WorkspaceMembershipDTO)
        assert tuple((m.tenant_id, m.role, m.display_ref) for m in resp.portal_dto.memberships) == (
            ("b5c_t1", "MASTER_AGENT", "ref:tenant/b5c_t1/display"),
            ("b5c_t2", "TENANT_AGENT", "ref:tenant/b5c_t2/display"),
        )
        assert router.handoffs == []
        assert len(_success_events(audit)) == 1 and len(audit.events) == 1
        (event,) = _success_events(audit)
        assert event.action.value == "workspace_memberships_read" and event.outcome == "success"
        assert event.actor_ref == event.subject_ref == "b5c_member"
        assert event.event_version == 1
        assert event.tenant_ref is None and event.carrier_ref is None
        assert event.correlation_id == "cid-6cc-4"
        assert isinstance(event.audit_id, str) and event.audit_id
        int(event.audit_id, 16)
        assert isinstance(event.occurred_at, str) and event.occurred_at
        assert datetime.fromisoformat(event.occurred_at).utcoffset() == timedelta(0)
        for field_value in (event.correlation_id, event.actor_ref, event.subject_ref, event.audit_id, event.occurred_at):
            assert "b5c_t1" not in str(field_value) and "MASTER_AGENT" not in str(field_value)  # references only, no content
        _say("NOTE: the success event above is observed with an IN-MEMORY recorder — no durable audit persistence is claimed")
        _done("memberships-nonempty-audit", success_events=1)

        # --- S5: memberships EMPTY is a lawful success -> still exactly one event ------------------
        resp = gateway.handle(_req("GET", "/memberships", "tok-empty"))
        assert (resp.status, resp.public_code) == (200, "ok")
        assert isinstance(resp.portal_dto, WorkspaceMembershipDTO) and resp.portal_dto.memberships == ()
        assert len(_success_events(audit)) == 2
        empty_event = _success_events(audit)[-1]
        assert empty_event.actor_ref == empty_event.subject_ref == "b5c_empty" and empty_event.event_version == 1
        _done("memberships-empty-audit", success_events_total=2)

        # --- S6: unsupported kind / Global Deal / malformed remainder -> consistent fail-closed ----
        for path in ("/directory/deal", "/directory", "/directory/startup/b5c-s-001"):
            resp = gateway.handle(_req("GET", path, "tok-member"))
            assert (resp.status, resp.public_code) == (403, "forbidden"), path
            assert resp.portal_dto is None, path
        assert len(_success_events(audit)) == 2  # no success event on any denial
        assert [e.action for e in audit.events].count(AuditAction.ROUTE_DENIED) == 3
        _done("unsupported-kind-fail-closed", denied_paths=3)

        # --- S7: client-controlled kind/subject values are NEVER read -------------------------------
        resp = gateway.handle(_req("GET", "/directory/startup", "tok-member", query={"kind": "deal"}))
        assert isinstance(resp.portal_dto, GlobalStartupSummaryDTO)  # the query never selects the kind
        resp = gateway.handle(_req("GET", "/memberships", "tok-member", query={"p": "victim"}))
        assert resp.status == 200
        scoped = _success_events(audit)[-1]
        assert scoped.actor_ref == scoped.subject_ref == "b5c_member"  # self-scoped; never the client value
        for f_value in (scoped.actor_ref, scoped.subject_ref, scoped.correlation_id, scoped.audit_id):
            assert "victim" not in str(f_value)
        _done("client-kind-and-self-scope", success_events_total=3)

        # --- S8: ImportInitiation is an ENVELOPE only — nothing is created --------------------------
        rows_before = _row_census(seed)
        events_before = len(audit.events)
        resp = gateway.handle(_req("POST", "/import/global-startup/b5c-s-001", "tok-t1"))
        assert (resp.status, resp.public_code, resp.dispatched) == (200, "ok", True)
        assert isinstance(resp.portal_dto, ImportInitiationDTO)
        assert resp.portal_dto.initiation == "accepted"
        assert resp.portal_dto.source_ref == "global-startup/b5c-s-001"
        assert resp.portal_dto.target_tenant_ref == "b5c_t1"
        assert len(router.handoffs) == 1  # dispatched through the stub router (references only)
        rows_after = _row_census(seed)
        assert rows_before == rows_after, "ImportInitiation must persist NOTHING (envelope/dispatch proof only)"
        assert len(audit.events) == events_before
        _done("import-initiation-envelope", rows_unchanged=True, persistent_write_claim=False)

        # --- S9: TenantOperation is a references-only dispatch outcome — no DTO, no business result -
        rows_before = _row_census(seed)
        resp = gateway.handle(_req("POST", "/tenant/deals", "tok-t1"))
        assert (resp.status, resp.public_code, resp.dispatched) == (200, "ok", True)
        assert resp.portal_dto is None  # dispatch semantics only — never a tenant business DTO
        assert len(router.handoffs) == 2
        assert _row_census(seed) == rows_before, "TenantOperation must persist NOTHING (stub-router dispatch proof only)"
        _done("tenant-operation-dispatch", rows_unchanged=True, business_result_claim=False)

        # --- S10: negative IC-007 set ---------------------------------------------------------------
        handoffs_before = len(router.handoffs)
        resp = gateway.handle(_req("GET", "/tenant/x", "tok-t1", host="b5c_t1.snackportal.example", headers={"X-Tenant-Id": "b5c_t2"}))
        assert (resp.status, resp.public_code) == (403, "isolation_anomaly") and resp.portal_dto is None
        assert len(router.handoffs) == handoffs_before  # a straddle attempt never reaches dispatch
        resp = gateway.handle(_req("GET", "/shared/deals", "tok-member"))
        assert (resp.status, resp.public_code) == (403, "unknown_route") and resp.portal_dto is None
        directory_bytes = serialize_portal_dto(gateway.handle(_req("GET", "/directory/startup", "tok-member")).portal_dto)
        for needle in (b"b5c_t1", b"b5c_t2", b"tenant_id"):
            assert needle not in directory_bytes, "directory DTOs must remain tenant-anonymous (D-35)"
        cluster_now = sorted(r[0] for r in admin.execute("SELECT datname FROM pg_database").fetchall())
        assert cluster_now == sorted([*cluster_before, _PROOF_DB]), "the run may create NO database beyond the disposable Control DB"
        assert len(_success_events(audit)) == 3  # zero prohibited/extra success events
        _done("ic007-negatives", straddle_denied=True, unknown_route_denied=True, tenant_anonymous=True, no_extra_database=True)

        # --- S11: pagination limitation — ONE page only; next_cursor never followed -----------------
        for i in range(4, 121):
            seed.execute(
                "INSERT INTO control_directory (directory, record_id, display_name, attributes) VALUES (%s,%s,%s,'{}'::jsonb)",
                ("GlobalStartupDirectory", f"b5c-s-{i:03d}", f"Proof Startup {i}"),
            )
        total = int(_scalar(seed, "SELECT count(*) FROM control_directory WHERE directory = 'GlobalStartupDirectory'"))
        assert total == 120
        resp = gateway.handle(_req("GET", "/directory/startup", "tok-member"))
        assert isinstance(resp.portal_dto, GlobalStartupSummaryDTO)
        assert len(resp.portal_dto.records) == 100, "the adapter composes exactly the edge's single default page"
        assert resp.portal_dto.records[0].record_ref == "b5c-s-001" and resp.portal_dto.records[-1].record_ref == "b5c-s-100"
        assert len(resp.portal_dto.records) < total  # the remainder is NOT fetched: no cursor sent, none followed
        _say("NOTE: one directory page only — the Gateway adapter sends no cursor/limit and never follows next_cursor;")
        _say("      this proof claims NO pagination support (pinned limitation, not a capability)")
        _done("pagination-one-page-limitation", db_records=total, composed_records=100, pagination_claimed=False)

        # --- S12: malformed Control-Plane response -> 503 unavailable, zero success events ----------
        fault_server = HTTPServer(("127.0.0.1", 0), _MalformedEdgeHandler)
        threading.Thread(target=fault_server.serve_forever, daemon=True).start()
        fault_base = f"http://127.0.0.1:{fault_server.server_address[1]}"
        fault_audit = _RecordingAudit()
        fault_gateway = build_gateway(
            authenticator=authn, router=_ProofRouter(), control_read=_select_control_read(fault_base), audit=fault_audit
        )
        for path in ("/memberships", "/directory/startup"):
            resp = fault_gateway.handle(_req("GET", path, "tok-member"))
            assert (resp.status, resp.public_code) == (503, "unavailable"), path
            assert resp.portal_dto is None
        assert fault_audit.events == []
        _done("malformed-response", status=503, success_events=0)

        # --- S13: oversized Control-Plane response -> 503 unavailable, zero success events ----------
        over_audit = _RecordingAudit()
        over_gateway = build_gateway(
            authenticator=authn,
            router=_ProofRouter(),
            control_read=HttpControlPlaneRead(base, max_response_bytes=8),  # the REAL adapter, tightened bound
            audit=over_audit,
        )
        for path in ("/memberships", "/directory/startup"):
            resp = over_gateway.handle(_req("GET", path, "tok-member"))
            assert (resp.status, resp.public_code) == (503, "unavailable"), path
            assert resp.portal_dto is None
        assert over_audit.events == []
        _done("oversized-response", status=503, success_events=0)

        # --- S14: Control read unavailable (stopped edge) -> 503, no success event ------------------
        server.shutdown()
        server.server_close()
        server = None  # already closed; the finally teardown must not double-close it
        events_before = len(audit.events)
        for path in ("/memberships", "/directory/startup"):
            resp = gateway.handle(_req("GET", path, "tok-member"))
            assert (resp.status, resp.public_code) == (503, "unavailable"), path
            assert resp.portal_dto is None
        assert len(audit.events) == events_before and len(_success_events(audit)) == 3
        _done("control-read-unavailable", status=503, success_events_total=3)

        # --- exact final audit census over the primary recorder -------------------------------------
        actions = sorted(e.action.value for e in audit.events)
        assert actions == sorted(["workspace_memberships_read"] * 3 + ["RouteDenied"] * 4 + ["IsolationAnomaly"]), actions
        evidence["audit_actions"] = actions
        _say("PASS: exact audit census — 3 workspace_memberships_read, 4 RouteDenied, 1 IsolationAnomaly, nothing else")
    finally:
        # --- mandatory teardown: ALWAYS runs; the disposable DB is never retained -------------------
        if env_before is None:
            os.environ.pop(GW_CONTROL_READ_BASE_URL_ENV, None)
        else:
            os.environ[GW_CONTROL_READ_BASE_URL_ENV] = env_before
        for srv in (server, fault_server):
            if srv is not None:
                try:
                    srv.shutdown()
                    srv.server_close()
                except Exception:
                    pass
        for store in (plane_store, seed_store):
            if store is not None:
                try:
                    store.release()
                except Exception:
                    pass
        admin.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()", (_PROOF_DB,))
        admin.execute(f'DROP DATABASE IF EXISTS "{_PROOF_DB}"')
        remaining = int(_scalar(admin, "SELECT count(*) FROM pg_database WHERE datname = %s", (_PROOF_DB,)))
        evidence["datname_count"] = remaining
        admin.close()
        assert remaining == 0, "the disposable Control DB must be removed by teardown (zero retained artifact)"
        _say("disposable database datname count == 0")
    return evidence
