"""CLM 2-Day Stage B controlled-local rehearsal — DISPOSABLE live-PostgreSQL proof (standalone-only).

The MANUAL_ONLY, operator-run, human-START-GATED rehearsal that drives the ONE D-42 controlled-local
journey end to end through the REAL served topology (D-42; IC-005/IC-009/IC-010 CLM sections):

    controlled-local OIDC login (RS256, Keycloak-shaped issuer via the crypto fixture)
      -> principal-only Gateway authentication
      -> served GET /memberships                          (returns ACME)
      -> backend-validated ACME selection                 (signed tenant claim, D-04 membership)
      -> served GET /tenant/startups/<startup_ref>        (one synthetic ACME Startup)
      -> served PATCH /tenant/startups/<startup_ref>      (bounded short_description update)
      -> re-read persistence proof
      -> unauthorized ZETA access                         (fail-closed 403, no ZETA data)
      -> four durable audit events                        (workspace_memberships_read,
                                                           tenant_startup_read, tenant_startup_update,
                                                           RouteDenied)
      -> physical multi-database routing proof            (only the ACME DB touched; ZETA untouched)
      -> rollback and restore                             (before == after, exact original local state)

against three real, rehearsal-owned PostgreSQL databases created fresh with safe identity readback:
sp2_clm_control / sp2_clm_acme / sp2_clm_zeta. Every principal, membership, tenant, and Startup row
is SYNTHETIC and LOCAL. The served edges (control-plane read, Gateway-audit ingest, auth authenticate,
Database-Router dispatch, the Stage B tenant Startup operations edge, and the northbound served Gateway
edge) are hosted on loopback ephemeral ports from the EXISTING production env-seam factories; the
journey is driven through a REAL stdlib HTTP client — the harness never calls the gateway core
in-process.

ISOLATION & SAFETY. Everything runs in the rehearsal-owned scratch databases created from the
SNACKPORTAL_TEST_DSN admin connection at start and DROPPED in a ``finally``. The DSN must point ONLY at
a disposable, non-production instance; it must NEVER point at production, shared staging, the standing
Control database, or any tenant database. The repo DDL files are read + blob-pinned only, never
modified. No standing SnackPortal2 database is named, read, or touched by this file.

SECRET HYGIENE (D-14). SNACKPORTAL_TEST_DSN reaches the rehearsal only through the ``_pg`` runner; no
descriptor value is printed, logged, committed, or served. Tenant DSNs live only in a rehearsal-owned
scratch secret directory (deleted in ``finally``) resolved in-memory by the REAL EnvTenantSecretStore;
the Control-store DSN travels by SecretRef through the REAL EnvReferenceSecretStore binding. The
registry rows carry SecretRef references only. RS256 material comes only from
tests/api_gateway/crypto_fixture.py, loaded by file location (the sole module allowed to import
jwt/cryptography). The Gateway composition holds base URLs only — no credential.

MANUAL_ONLY / START-GATE. Deliberately MANUAL_ONLY, operator-run, disposable: an explicit human
START-GATE (Dan) is required before any execution, per
infrastructure/runbooks/clm_2day_stage_b_rehearsal.md. Registered as a justified MANUAL_ONLY exception
in tests/architecture/test_live_pg_workflow_runset_completeness.py; the automatic live-pg workflow loop
is unchanged and never runs this file.

DEFAULT SUITE. IGNORED by the default test run (pyproject addopts ``--ignore=tests/control_plane/requires_pg``).
Run it standalone against a disposable instance:
  python backend/tests/control_plane/requires_pg/test_pg_clm_2day_stage_b_rehearsal.py
With SNACKPORTAL_TEST_DSN unset (or psycopg absent) it clean-skips (exit 0, no DB touched).

NO OVERCLAIM. DISPOSABLE-ONLY: it does not touch the retained standing topology, does not standing-enroll
any DDL, does not activate production, and does not close any B5 blocker (7 of 9 remain OPEN; Production
NOT READY / DO-NOT-ACTIVATE). The composition is rehearsal-local wiring of the REAL production factories.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib
import shutil
import sys
import tempfile
import threading
import time
from http.client import HTTPConnection
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _pg  # noqa: E402  (standalone live-PG runner)

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))  # backend on path

_REH_CTL = "sp2_clm_control"
_REH_ACME = "sp2_clm_acme"
_REH_ZETA = "sp2_clm_zeta"
_REHEARSAL_DBS = (_REH_CTL, _REH_ACME, _REH_ZETA)

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
_CONTROL = _REPO_ROOT / "infrastructure" / "db" / "control"
_DDL_012 = _CONTROL / "012_gateway_operational_audit.sql"
_DDL_013 = _CONTROL / "013_gateway_operational_audit_append_only.sql"
_CRYPTO_FIXTURE_PATH = pathlib.Path(__file__).resolve().parents[2] / "api_gateway" / "crypto_fixture.py"

# Rehearsal LF-normalized git-blob SHA-1 pins for the Gateway-audit control DDL (D-42 widened 012's
# action CHECK to seven values + the record_ref column; 013 is unchanged). A mismatch STOPS the
# exercise BEFORE any connection is opened.
_REHEARSAL_BLOB_012 = "87c38a968f8ab89886ef7ce4d9d7fafb7a179271"
_REHEARSAL_BLOB_013 = "199664d1afb9e6e0a37e8609f42e4e1528771472"

# Control DDL applied UNPINNED beside 012/013 (base control schema: tenants, memberships, directory).
# 010/011 (routing audit) and 014/015 (import audit) are deliberately ABSENT — the router uses the
# in-memory audit sink and no import runs.
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

_ACME, _ZETA = "acme", "zeta"
_STARTUP_REF = "clm-startup-0001"
_ACME_DISPLAY = "CLM Synthetic Alpha Co"
_ZETA_DISPLAY = "CLM Synthetic Zeta Co"
_ORIGINAL_DESCRIPTION = "the original synthetic short description"
_NEW_DESCRIPTION = "the bounded updated short description"
_PRINCIPAL = "clm-rehearsal-agent"
_ISSUER = "http://127.0.0.1:8814/realms/sp2-clm-local"  # Keycloak-shaped controlled-local issuer
_AUDIENCE = "snackportal2-clm"
_CORRELATION_MEMBERSHIPS = "corr-clm-memberships"
_CORRELATION_READ = "corr-clm-read"
_CORRELATION_UPDATE = "corr-clm-update"
_CORRELATION_ZETA = "corr-clm-zeta-denied"
_FIXED_TS = "2026-07-22T00:00:00+00:00"

_READINESS_TIMEOUT_SECONDS = 30.0

_ENV_TOUCHED_KEYS = (
    "SP2_CP_READ_HOST",
    "SP2_CP_READ_PORT",
    "SP2_CP_CONTROL_STORE",
    "SP2_CP_CONTROL_STORE_DSN_REF",
    "SP2_CP_PROVISIONING_ADAPTER",
    "SP2_CP_TENANT_SCHEMA_APPLICATOR",
    "SP2_CP_DISTINCTNESS_LEDGER",
    "SNACKPORTAL_SECRET_CONTROL_CONTROL_STORE_DSN_V1",
    "SP2_CP_GATEWAY_AUDIT_HOST",
    "SP2_CP_GATEWAY_AUDIT_PORT",
    "SP2_AR_CONTROL_PLANE_READ_BASE_URL",
    "SP2_AR_ISSUERS",
    "SP2_AR_AUTHENTICATE_HOST",
    "SP2_AR_AUTHENTICATE_PORT",
    "SP2_DBR_ROUTING_READ_BASE_URL",
    "SP2_DBR_DISPATCH_HOST",
    "SP2_DBR_DISPATCH_PORT",
    "SP2_DBR_TENANT_STARTUP_HOST",
    "SP2_DBR_TENANT_STARTUP_PORT",
    "SNACKPORTAL_TENANT_SECRET_DIR",
    "SP2_GW_AUTH_ROUTER_BASE_URL",
    "SP2_GW_CONTROL_READ_BASE_URL",
    "SP2_GW_DB_ROUTER_BASE_URL",
    "SP2_GW_TENANT_STARTUP_BASE_URL",
    "SP2_GW_AUDIT_SINK_BASE_URL",
    "SP2_GW_EDGE_HOST",
    "SP2_GW_EDGE_PORT",
    "SP2_GW_EDGE_ALLOWED_ORIGINS",
    "SP2_GW_IMPORT_BASE_URL",
)


def _git_blob_sha1(path: pathlib.Path) -> str:
    data = path.read_bytes().replace(b"\r\n", b"\n")  # autocrlf normalization (the git blob is LF)
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def _verify_rehearsal_blob_pins() -> None:
    b012, b013 = _git_blob_sha1(_DDL_012), _git_blob_sha1(_DDL_013)
    assert b012 == _REHEARSAL_BLOB_012, f"012 blob {b012} != pinned {_REHEARSAL_BLOB_012} — STOP before connect/apply"
    assert b013 == _REHEARSAL_BLOB_013, f"013 blob {b013} != pinned {_REHEARSAL_BLOB_013} — STOP before connect/apply"
    print(f"PASS: CLM-0 rehearsal DDL blob pins verified BEFORE any connection (012={b012[:12]}…, 013={b013[:12]}…)")


def _scalar(conn: Any, sql: str, params: Tuple[Any, ...] = ()) -> Any:
    row = conn.execute(sql, params).fetchone()
    return row[0] if row else None


def _serve(server: Any) -> threading.Thread:
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread


def _stop(server: Any, thread: Optional[threading.Thread]) -> None:
    server.shutdown()
    server.server_close()
    if thread is not None:
        thread.join(timeout=5)


def _await_ready(label: str, probe: Callable[[], bool]) -> None:
    deadline = time.monotonic() + _READINESS_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        try:
            if probe():
                return
        except Exception:
            pass
        time.sleep(0.05)
    raise AssertionError(f"{label} did not become ready within {_READINESS_TIMEOUT_SECONDS}s (fail closed)")


class _EnvPatch:
    def __init__(self) -> None:
        self._saved: Dict[str, Optional[str]] = {}

    def set(self, key: str, value: Optional[str]) -> None:
        import os

        assert key in _ENV_TOUCHED_KEYS, f"environment key {key!r} is outside the pinned touch census — refused"
        if key not in self._saved:
            self._saved[key] = os.environ.get(key)
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value

    def restore(self) -> None:
        import os

        for key, prior in self._saved.items():
            if prior is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = prior
        self._saved.clear()


def _crypto_fixture() -> Any:
    name = "clm_rehearsal_crypto_fixture"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, _CRYPTO_FIXTURE_PATH)
    assert spec is not None and spec.loader is not None, f"cannot load crypto fixture at {_CRYPTO_FIXTURE_PATH}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _served(
    base_url: str, method: str, path: str, headers: Optional[Dict[str, str]] = None, body: bytes = b""
) -> Tuple[int, Dict[str, str], bytes]:
    parts = urlsplit(base_url)
    last: Optional[BaseException] = None
    for attempt in range(3):
        conn = HTTPConnection(parts.hostname or "127.0.0.1", parts.port, timeout=10)
        try:
            conn.request(method, path, body=body if body else None, headers=dict(headers or {}))
            resp = conn.getresponse()
            return resp.status, {k.lower(): v for k, v in resp.getheaders()}, resp.read()
        except OSError as exc:  # single-threaded loopback abort artifact (Windows) — bounded retry
            last = exc
            time.sleep(0.05 * (attempt + 1))
        finally:
            conn.close()
    raise AssertionError(f"served request failed three times: {last!r}")


def _digest(conn: Any) -> str:
    rows = conn.execute(
        "SELECT global_startup_id, company_name, short_description, investment_stage FROM startups ORDER BY global_startup_id"
    ).fetchall()
    return hashlib.sha256(json.dumps([list(map(str, r)) for r in rows], sort_keys=True).encode("utf-8")).hexdigest()


# --- the exercise ---------------------------------------------------------------------------------
def test_pg_clm_2day_stage_b_rehearsal(admin_dsn: str) -> None:
    # PROOF CLM-0 — rehearsal blob pins verified BEFORE any connection or SQL (STOP rule).
    _verify_rehearsal_blob_pins()

    from api_gateway.main import build_gateway_edge_server_from_env
    from auth_router.main import build_authenticate_server_from_env
    from control_plane.adapters.providers.postgres_store import PostgresControlStore
    from control_plane.adapters.providers.postgres_tenant_schema_applicator import PostgresTenantSchemaApplicator
    from control_plane.main import build_gateway_audit_server_from_env, build_read_server_from_env
    from database_router.main import build_dispatch_server_from_env, build_tenant_startup_server_from_env
    from shared.secrets import SecretRef

    fixture = _crypto_fixture()

    admin = PostgresControlStore(admin_dsn)._conn
    admin.autocommit = True
    server_num = int(_scalar(admin, "SELECT current_setting('server_version_num')"))
    assert server_num >= 110000, f"PostgreSQL >= 11 required (server_version_num={server_num})"

    env = _EnvPatch()
    active_servers: List[Tuple[Any, Optional[threading.Thread]]] = []
    ctl_conn = acme_conn = zeta_conn = None
    secret_dir: Optional[str] = None

    def _host(server: Any) -> threading.Thread:
        thread = _serve(server)
        active_servers.append((server, thread))
        return thread

    try:
        # PROOF CLM-1 — three disposable, physically distinct databases, lifecycle-owned by THIS run.
        for name in _REHEARSAL_DBS:
            admin.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()", (name,))
            admin.execute(f'DROP DATABASE IF EXISTS "{name}"')
            admin.execute(f'CREATE DATABASE "{name}"')
        ctl_dsn = _pg.swap_db(admin_dsn, _REH_CTL)
        acme_dsn = _pg.swap_db(admin_dsn, _REH_ACME)
        zeta_dsn = _pg.swap_db(admin_dsn, _REH_ZETA)
        ctl_conn = PostgresControlStore(ctl_dsn)._conn
        ctl_conn.autocommit = True
        acme_conn = PostgresControlStore(acme_dsn)._conn
        acme_conn.autocommit = True
        zeta_conn = PostgresControlStore(zeta_dsn)._conn
        zeta_conn.autocommit = True
        identities = {
            _scalar(ctl_conn, "SELECT current_database()"),
            _scalar(acme_conn, "SELECT current_database()"),
            _scalar(zeta_conn, "SELECT current_database()"),
        }
        assert identities == set(_REHEARSAL_DBS), f"safe identity readback must show three distinct physical databases: {identities}"
        print(f"PASS: CLM-1 three disposable physically distinct databases created fresh ({', '.join(_REHEARSAL_DBS)})")

        # PROOF CLM-2 — control DDL on the disposable Control DB ONLY: 001-009 then 012 then 013.
        with ctl_conn.cursor() as cur:
            for name in _CONTROL_DDL_UNPINNED:
                cur.execute((_CONTROL / name).read_text(encoding="utf-8"))
            cur.execute(_DDL_012.read_text(encoding="utf-8"))
            cur.execute(_DDL_013.read_text(encoding="utf-8"))
        assert _scalar(ctl_conn, "SELECT to_regclass('control_gateway_audit')") is not None, "control_gateway_audit must exist after apply"
        assert _scalar(ctl_conn, "SELECT to_regclass('control_routing_audit')") is None, "010/011 must NOT be applied by this rehearsal"
        assert _scalar(ctl_conn, "SELECT to_regclass('control_import_audit')") is None, "014/015 must NOT be applied by this rehearsal"
        print("PASS: CLM-2 control DDL applied to the disposable Control DB only (001-009, then 012, then 013; 010/011/014/015 absent)")

        # PROOF CLM-3 — scratch secret directory + the 14-file tenant template on BOTH tenant DBs.
        secret_dir = tempfile.mkdtemp(prefix="sp2_clm_secrets_")
        for tenant_id, tenant_dsn in ((_ACME, acme_dsn), (_ZETA, zeta_dsn)):
            ref_dir = pathlib.Path(secret_dir) / "tenant" / tenant_id
            ref_dir.mkdir(parents=True)
            (ref_dir / "dsn@1").write_text(tenant_dsn, encoding="utf-8")
            (ref_dir / "chainkey@1").write_text(f"clm-rehearsal-chainkey-{tenant_id}", encoding="utf-8")
        env.set("SNACKPORTAL_TENANT_SECRET_DIR", secret_dir)
        tenant_secrets_store = __import__(
            "database_router.adapters.providers.env_tenant_secret_store", fromlist=["EnvTenantSecretStore"]
        ).EnvTenantSecretStore()
        applicator = PostgresTenantSchemaApplicator(tenant_secrets_store)
        applicator.apply_schema(_ACME, target=_REH_ACME, association_ref=SecretRef(store_ref=f"tenant/{_ACME}/dsn", version="1"))
        applicator.apply_schema(_ZETA, target=_REH_ZETA, association_ref=SecretRef(store_ref=f"tenant/{_ZETA}/dsn", version="1"))
        for tconn in (acme_conn, zeta_conn):
            assert _scalar(tconn, "SELECT to_regclass('startups')") is not None, "startups must exist after the tenant template"
        print("PASS: CLM-3 14-file tenant template applied to both disposable tenant DBs (real applicator)")

        # PROOF CLM-4 — SecretRef-only registry + memberships (agent -> ACME ONLY) + synthetic Startup rows.
        for tenant_id in (_ACME, _ZETA):
            ctl_conn.execute(
                "INSERT INTO control_tenants (tenant_id, organization_ref, lifecycle_state, expected_schema_version,"
                " assoc_store_ref, assoc_version, federation_config_ref, created_at, updated_at)"
                " VALUES (%s, 'clm_org', 'Ready', '1', %s, '1', 'clm_fed', %s, %s)",
                (tenant_id, f"tenant/{tenant_id}/dsn", _FIXED_TS, _FIXED_TS),
            )
        # The principal is a member of ACME ONLY — never ZETA (the unauthorized-tenant denial leg).
        ctl_conn.execute(
            "INSERT INTO control_memberships (principal_ref, tenant_id, role) VALUES (%s, %s, 'TENANT_AGENT')", (_PRINCIPAL, _ACME)
        )
        # Synthetic Startup rows: one per tenant DB (ZETA's exists to prove it is NEVER returned).
        acme_conn.execute(
            "INSERT INTO startups (global_startup_id, company_name, short_description, investment_stage) VALUES (%s, %s, %s, 'seed')",
            (_STARTUP_REF, _ACME_DISPLAY, _ORIGINAL_DESCRIPTION),
        )
        zeta_conn.execute(
            "INSERT INTO startups (global_startup_id, company_name, short_description, investment_stage) VALUES (%s, %s, %s, 'seed')",
            (_STARTUP_REF, _ZETA_DISPLAY, "zeta private description — must never be exposed"),
        )
        for row in ctl_conn.execute("SELECT * FROM control_tenants").fetchall():
            for cell in row:
                assert "postgresql" not in str(cell), "the registry must never store a raw DSN (SecretRef only)"
        before_digest = _digest(acme_conn)
        print("PASS: CLM-4 SecretRef-only registry (ACME/ZETA Ready), ACME-only membership, and synthetic Startup rows seeded")

        # PROOF CLM-5 — the six served edges from the existing production env-seam factories.
        for key in (
            "SP2_CP_READ_PORT",
            "SP2_CP_GATEWAY_AUDIT_PORT",
            "SP2_AR_AUTHENTICATE_HOST",
            "SP2_AR_AUTHENTICATE_PORT",
            "SP2_DBR_DISPATCH_HOST",
            "SP2_DBR_DISPATCH_PORT",
            "SP2_DBR_TENANT_STARTUP_HOST",
            "SP2_DBR_TENANT_STARTUP_PORT",
            "SP2_GW_EDGE_PORT",
            "SP2_GW_EDGE_ALLOWED_ORIGINS",
            "SP2_GW_IMPORT_BASE_URL",
            "SP2_CP_PROVISIONING_ADAPTER",
            "SP2_CP_TENANT_SCHEMA_APPLICATOR",
            "SP2_CP_DISTINCTNESS_LEDGER",
            "SP2_CP_CONTROL_STORE_DSN_REF",
        ):
            env.set(key, None)
        env.set("SNACKPORTAL_SECRET_CONTROL_CONTROL_STORE_DSN_V1", ctl_dsn)
        env.set("SP2_CP_CONTROL_STORE", "postgres")

        # Edge 1 — Control-Plane read edge (routing views + memberships) over the disposable Control DB.
        env.set("SP2_CP_READ_HOST", "127.0.0.1")
        read_built = build_read_server_from_env()
        assert read_built is not None, "the Control-Plane read edge seam must activate"
        read_server, read_base = read_built
        _host(read_server)
        _await_ready("control-plane read edge", lambda: _served(read_base, "GET", f"/internal/routing/tenants/{_ACME}")[0] == 200)

        # Edge 2 — Gateway-audit ingest edge over the disposable Control DB (durable store).
        env.set("SP2_CP_GATEWAY_AUDIT_HOST", "127.0.0.1")
        audit_built = build_gateway_audit_server_from_env()
        assert audit_built is not None, "the Gateway-audit ingest seam must activate"
        audit_server, audit_base = audit_built
        _host(audit_server)

        # Edge 3 — Auth authenticate edge (RS256/OIDC; controlled-local Keycloak-shaped issuer).
        keypair = fixture.generate_rs256_keypair()

        def _mint(tenant: Optional[str]) -> str:
            return str(
                fixture.mint_rs256_token(keypair, issuer=_ISSUER, audience=_AUDIENCE, subject=_PRINCIPAL, tenant=tenant, ttl_seconds=3600)
            )

        principal_token = _mint(None)  # tenantless: the principal-only context (login + memberships)
        acme_token = _mint(_ACME)  # IdP-minted tenant-claim token (ACME selection)
        zeta_token = _mint(_ZETA)  # IdP-minted tenant-claim token for a tenant the principal is NOT a member of
        env.set("SP2_AR_CONTROL_PLANE_READ_BASE_URL", read_base)
        env.set("SP2_AR_ISSUERS", fixture.issuer_env_json(keypair, issuer=_ISSUER, audience=_AUDIENCE))
        env.set("SP2_AR_AUTHENTICATE_HOST", "127.0.0.1")
        auth_built = build_authenticate_server_from_env()
        assert auth_built is not None, "the Auth authenticate seam must activate"
        auth_server, auth_base = auth_built
        _host(auth_server)
        _await_ready("auth authenticate edge", lambda: _served(auth_base, "POST", "/internal/auth/probe")[0] == 404)

        # Edge 4 — Database-Router dispatch edge (structurally required by the gateway composition;
        # the single-route CLM tenant Startup path never calls it).
        env.set("SP2_DBR_ROUTING_READ_BASE_URL", read_base)
        env.set("SP2_DBR_DISPATCH_HOST", "127.0.0.1")
        dispatch_built = build_dispatch_server_from_env()
        assert dispatch_built is not None, "the Database-Router dispatch seam must activate"
        dispatch_server, dispatch_base = dispatch_built
        _host(dispatch_server)

        # Edge 5 — the Stage B tenant Startup operations internal edge (Gateway -> Database Router).
        env.set("SP2_DBR_TENANT_STARTUP_HOST", "127.0.0.1")
        tenant_startup_built = build_tenant_startup_server_from_env()
        assert tenant_startup_built is not None, "the tenant Startup operations seam must activate"
        tenant_startup_server, tenant_startup_base = tenant_startup_built
        _host(tenant_startup_server)

        # Edge 6 — the northbound served Gateway edge fronting the full composition (durable audit on).
        env.set("SP2_GW_AUTH_ROUTER_BASE_URL", auth_base)
        env.set("SP2_GW_CONTROL_READ_BASE_URL", read_base)
        env.set("SP2_GW_DB_ROUTER_BASE_URL", dispatch_base)
        env.set("SP2_GW_TENANT_STARTUP_BASE_URL", tenant_startup_base)
        env.set("SP2_GW_AUDIT_SINK_BASE_URL", audit_base)
        env.set("SP2_GW_EDGE_HOST", "127.0.0.1")
        edge_built = build_gateway_edge_server_from_env()
        assert edge_built is not None, "the served Gateway Edge seam must activate"
        edge_server, edge_base = edge_built
        _host(edge_server)
        _await_ready("served gateway edge", lambda: _served(edge_base, "GET", "/health")[0] == 200)
        print(f"PASS: CLM-5 six served edges hosted on loopback ephemeral ports ({len(active_servers)} processes; all env-seam factories)")

        def _audit_rows() -> List[Tuple[Any, ...]]:
            return ctl_conn.execute(
                "SELECT action, outcome, actor_ref, tenant_ref, record_ref, correlation_id FROM control_gateway_audit ORDER BY id"
            ).fetchall()

        def _startup_count(tconn: Any) -> int:
            return int(_scalar(tconn, "SELECT count(*) FROM startups"))

        # PROOF CLM-6 — OIDC login -> principal-only context -> served GET /memberships returns ACME.
        status, _, payload = _served(
            edge_base,
            "GET",
            "/memberships",
            headers={"Authorization": "Bearer " + principal_token, "x-correlation-id": _CORRELATION_MEMBERSHIPS},
        )
        assert status == 200, f"CLM-6: served /memberships must answer 200 for the principal-only login: {status} {payload!r}"
        memberships = json.loads(payload)["memberships"]
        assert [m["tenant_id"] for m in memberships] == [_ACME], f"CLM-6: the principal is a member of ACME only: {memberships}"
        assert memberships[0]["role"] == "TENANT_AGENT"
        print("PASS: CLM-6 OIDC principal-only login -> served GET /memberships returns exactly the ACME membership")

        # PROOF CLM-7 — backend-validated ACME selection -> served GET /tenant/startups/<ref> -> one ACME Startup.
        status, _, payload = _served(
            edge_base,
            "GET",
            f"/tenant/startups/{_STARTUP_REF}",
            headers={"Authorization": "Bearer " + acme_token, "X-Tenant-Id": _ACME, "x-correlation-id": _CORRELATION_READ},
        )
        assert status == 200, f"CLM-7: served ACME read must answer 200: {status} {payload!r}"
        detail = json.loads(payload)
        assert detail["record_ref"] == _STARTUP_REF and detail["display_name"] == _ACME_DISPLAY, f"CLM-7: ACME detail contract: {detail}"
        assert detail["short_description"] == _ORIGINAL_DESCRIPTION and detail["record_residency"] == "tenant"
        assert set(detail.keys()) == {
            "record_ref",
            "display_name",
            "short_description",
            "investment_stage",
            "record_origin",
            "record_residency",
            "record_type",
            "lineage_reference",
        }, f"CLM-7: exactly the eight CLM read-DTO fields: {sorted(detail.keys())}"
        assert _ZETA_DISPLAY not in payload.decode("utf-8"), "CLM-7: the ACME read must never surface ZETA data"
        print("PASS: CLM-7 backend-validated ACME selection -> served GET returns exactly the one synthetic ACME Startup")

        # PROOF CLM-8 — served PATCH short_description -> 200 updated; the update response AND a durable
        # (direct-SQL) re-read confirm persistence. The persistence witness is the direct-SQL read
        # rather than a second served GET, so the durable audit evidence set stays exactly the four
        # ratified events (a served re-read would lawfully emit a second tenant_startup_read).
        status, _, payload = _served(
            edge_base,
            "PATCH",
            f"/tenant/startups/{_STARTUP_REF}",
            headers={
                "Authorization": "Bearer " + acme_token,
                "X-Tenant-Id": _ACME,
                "x-correlation-id": _CORRELATION_UPDATE,
                "Content-Type": "application/json",
            },
            body=json.dumps({"short_description": _NEW_DESCRIPTION}).encode("utf-8"),
        )
        assert status == 200, f"CLM-8: served bounded update must answer 200: {status} {payload!r}"
        assert json.loads(payload)["short_description"] == _NEW_DESCRIPTION, "CLM-8: the update response must carry the new value"
        assert (
            _scalar(acme_conn, "SELECT short_description FROM startups WHERE global_startup_id = %s", (_STARTUP_REF,)) == _NEW_DESCRIPTION
        ), "CLM-8: durable persistence (direct-SQL witness)"
        print("PASS: CLM-8 served bounded PATCH persisted short_description; direct-SQL re-read confirms it")

        # PROOF CLM-9 — unauthorized ZETA access -> fail-closed 403, no ZETA data, ZETA physically untouched.
        status, _, payload = _served(
            edge_base,
            "GET",
            f"/tenant/startups/{_STARTUP_REF}",
            headers={"Authorization": "Bearer " + zeta_token, "X-Tenant-Id": _ZETA, "x-correlation-id": _CORRELATION_ZETA},
        )
        assert (status, payload) == (403, b""), (
            f"CLM-9: an unauthorized ZETA request must be denied fail-closed 403 empty-body: {status} {payload!r}"
        )
        assert _startup_count(zeta_conn) == 1, "CLM-9: the ZETA physical DB is untouched (its one synthetic row is unchanged)"
        assert _scalar(zeta_conn, "SELECT short_description FROM startups") == "zeta private description — must never be exposed", (
            "CLM-9: ZETA data unchanged"
        )
        print("PASS: CLM-9 unauthorized ZETA access denied fail-closed 403; no ZETA data exposed; ZETA physically untouched")

        # PROOF CLM-10 — the four durable audit events (references only; short_description NEVER present).
        rows = _audit_rows()
        actions = [r[0] for r in rows]
        assert actions == ["workspace_memberships_read", "tenant_startup_read", "tenant_startup_update", "RouteDenied"], (
            f"CLM-10: exactly the four CLM audit events in order: {actions}"
        )
        by_action = {r[0]: r for r in rows}
        assert by_action["workspace_memberships_read"][1] == "success" and by_action["workspace_memberships_read"][3] is None
        assert (
            by_action["tenant_startup_read"][1] == "success"
            and by_action["tenant_startup_read"][3] == _ACME
            and by_action["tenant_startup_read"][4] == _STARTUP_REF
        )
        assert by_action["tenant_startup_update"][1] == "success" and by_action["tenant_startup_update"][4] == _STARTUP_REF
        assert by_action["RouteDenied"][1] == "rejected", "CLM-10: the ZETA denial reuses the existing class-3 RouteDenied record"
        for row in rows:
            for cell in row:
                assert _NEW_DESCRIPTION not in str(cell) and _ORIGINAL_DESCRIPTION not in str(cell), (
                    "CLM-10: the short_description value must never appear in any audit row"
                )
        print("PASS: CLM-10 four durable audit events present (memberships_read, tenant_startup_read/update, RouteDenied); references only")

        # PROOF CLM-11 — physical multi-database routing proof.
        assert _startup_count(acme_conn) == 1 and _startup_count(zeta_conn) == 1, "CLM-11: one Startup row per physical tenant DB"
        assert _scalar(acme_conn, "SELECT current_database()") == _REH_ACME, "CLM-11: ACME identity readback intact"
        assert _scalar(zeta_conn, "SELECT current_database()") == _REH_ZETA, "CLM-11: ZETA identity readback intact"
        print("PASS: CLM-11 physical multi-database routing proof (ACME success reached only the ACME DB; ZETA never returned tenant data)")

        # PROOF CLM-12 — rollback and restore: return ACME to the exact original local state.
        acme_conn.execute("UPDATE startups SET short_description = %s WHERE global_startup_id = %s", (_ORIGINAL_DESCRIPTION, _STARTUP_REF))
        after_restore_digest = _digest(acme_conn)
        assert after_restore_digest == before_digest, "CLM-12: rollback must restore the EXACT original local ACME state (digest match)"
        print("PASS: CLM-12 rollback and restore returned the ACME physical DB to the exact original local state (before == after)")

    finally:
        # PROOF CLM-13 — deterministic shutdown of every served process, then disposal of the topology.
        stopped = 0
        for server, thread in reversed(list(active_servers)):
            try:
                _stop(server, thread)
                stopped += 1
            except Exception:
                pass
        del active_servers[:]
        for conn in (ctl_conn, acme_conn, zeta_conn):
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
        env.restore()
        if secret_dir is not None:
            shutil.rmtree(secret_dir, ignore_errors=True)
        remaining = 0
        for name in _REHEARSAL_DBS:
            admin.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()", (name,))
            admin.execute(f'DROP DATABASE IF EXISTS "{name}"')
            remaining += int(_scalar(admin, "SELECT count(*) FROM pg_database WHERE datname = %s", (name,)))
        print(f"PASS: CLM-13 deterministic shutdown ({stopped} served processes) and disposal (retained datname count = {remaining})")
        admin.close()
        assert remaining == 0, "every disposable rehearsal database must be removed after the run"


if __name__ == "__main__":
    _pg.run([test_pg_clm_2day_stage_b_rehearsal])
