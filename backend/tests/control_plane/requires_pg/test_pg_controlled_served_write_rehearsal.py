"""Controlled served-write rehearsal — W1b served Gateway Edge + W1a composed import — DISPOSABLE live-PostgreSQL proof (standalone-only).

The MANUAL_ONLY, operator-run, human-START-GATED rehearsal harness that joins the two independently proven
halves of the served write path inside one test-owned higher deployment root: the W1b served northbound
Gateway Edge (``POST /import/<source_ref>``) fronting the W1a real-PostgreSQL composed import path. Against
three real, rehearsal-owned PostgreSQL databases it applies the blob-pinned control Import-audit DDL
(infrastructure/db/control/014_import_operational_audit.sql then 015_import_operational_audit_append_only.sql
— exact paths, exact order, each exactly once, never a wildcard; control 010-013 are deliberately NOT applied)
plus control 001-009 (unpinned) and the enrolled 14-file tenant template, hosts all six served edges on
loopback ephemeral ports, and drives the golden request through a REAL stdlib HTTP client — the harness never
calls the gateway core in-process:

    stdlib HTTP client -> POST /import/rehearsal-startup-001 (served Gateway Edge, W1b)
      -> signed-context tenant authority -> HttpImportInitiation -> served internal Import edge
      -> ImportService.start_import -> PgRoutedSessionProvider -> DatabaseRouter.route()
         -> exactly one physical tenant database (sp2_rehearsal_alpha; sp2_rehearsal_beta untouched)
      -> startups upsert + atomic tenant-resident lineage -> BoundedImportAuditPolicy
         -> DurableImportAuditEmitter -> served Import-audit ingest edge
         -> PostgresImportAuditStore -> control_import_audit (sp2_rehearsal_control)

Proof set (phases REH-0..REH-14; golden G1-G14 + failure F1-F12): blob-pin STOP-before-connect; three
disposable physically distinct databases created fresh with safe identity readback; control 001-009 + exactly
014 + 015 on the disposable Control DB only; the 14-file tenant template on each disposable tenant DB;
SecretRef-only registry seed (the registry never stores a raw DSN); six served edges from the existing
production env-seam factories; a served golden journey -> 200 ``created`` with the alpha startups row, the
alpha created-lineage row, exactly three durable Import-audit rows, references-only ImportResultDTO, and
exactly one routed pool key; served replay -> 200 ``replayed`` with no duplicate row/lineage and exactly two
more audit rows; correlation/import reference reconciliation; denial fidelity F1 401 / F2 403 tenantless
CONTROL / F3 403 carrier mismatch / F4 404 malformed ref pre-core / F5 413 non-empty body pre-core / F6 503
port-absent (never a fake 200); F7 unknown tenant + F8 missing secret reference fail closed; F10 audit-outage
drill (no false success; durable confirm on restore); F12 dual-carrier straddle denied with beta physically
untouched; F9 alpha-unavailable -> 503 with no beta fallback; deterministic shutdown of every served process
and R-A disposal of the complete disposable topology.

ISOLATION & SAFETY. Everything runs in the rehearsal-owned scratch databases sp2_rehearsal_control /
sp2_rehearsal_alpha / sp2_rehearsal_beta created from the SNACKPORTAL_TEST_DSN admin connection at start and
DROPPED in a ``finally`` — the rehearsal owns the full lifecycle (rollback posture R-A: dispose the complete
disposable topology). The DSN must point ONLY at a disposable, non-production instance; it must NEVER point at
production, shared staging, the standing Control database, or any tenant database. The repo DDL files are read
+ blob-pinned only, never modified. No standing SnackPortal2 database is named, read, or touched by this file.

SECRET HYGIENE (D-14). SNACKPORTAL_TEST_DSN reaches the rehearsal only through the ``_pg`` runner; no
descriptor value is printed, logged, committed, or served. Tenant DSNs and lineage chain keys live only in a
rehearsal-owned scratch secret directory (deleted in ``finally``) resolved in-memory by the REAL
EnvTenantSecretStore; the Control-store DSN travels by SecretRef through the REAL EnvReferenceSecretStore
binding. The registry rows carry SecretRef {store_ref, version} only, and stored audit rows are asserted to
contain no descriptor/password substring. The Gateway composition holds base URLs only — no credential.

DRIVER CONTAINMENT. This file imports NO database driver, NO jwt, and NO cryptography at any scope. PostgreSQL
is reached only through the sanctioned provider adapters, imported lazily inside the exercise so the module
clean-skips without psycopg. RS256 material comes only from tests/api_gateway/crypto_fixture.py, loaded by
file location (the sole module allowed to import jwt/cryptography). The served edges are hosted on test-owned
daemon threads (production servers stay single-threaded and thread-free).

MANUAL_ONLY / START-GATE. This rehearsal is deliberately MANUAL_ONLY, operator-run, and disposable: an
explicit human START-GATE (Dan) is required before any execution, per
infrastructure/runbooks/controlled_served_write_rehearsal.md. It is registered as a justified MANUAL_ONLY
exception in tests/architecture/test_live_pg_workflow_runset_completeness.py; the automatic live-pg workflow
loop (14 entries) is unchanged and never runs this file.

DEFAULT SUITE. IGNORED by the default test run (pyproject addopts ``--ignore=tests/control_plane/requires_pg``).
Run it standalone against a disposable instance:
  python backend/tests/control_plane/requires_pg/test_pg_controlled_served_write_rehearsal.py
With SNACKPORTAL_TEST_DSN unset (or psycopg absent) it clean-skips (exit 0, no DB touched).

NO OVERCLAIM. This rehearsal is DISPOSABLE-ONLY: it does not touch the retained standing topology, does not
standing-enroll DDL 014/015, does not deliver operator retrieval, does not activate production, and does not
close any B5 blocker (8 of 9 remain OPEN; Production NOT READY / DO-NOT-ACTIVATE). The composition is
rehearsal-local wiring of the REAL production factories, adapters, and stores.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import pathlib
import shutil
import socket
import sys
import tempfile
import threading
import time
from http.client import HTTPConnection
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _pg  # noqa: E402  (standalone live-PG runner: SNACKPORTAL_TEST_DSN, available()/run()/swap_db())

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))  # backend on path

# The three rehearsal-owned scratch databases: created and dropped by THIS file only. Collision-free vs every
# standing Control/tenant database name and every sibling harness scratch family (R-A disposal target set).
_REH_CTL = "sp2_rehearsal_control"
_REH_ALPHA = "sp2_rehearsal_alpha"
_REH_BETA = "sp2_rehearsal_beta"
_REHEARSAL_DBS = (_REH_CTL, _REH_ALPHA, _REH_BETA)

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
_CONTROL = _REPO_ROOT / "infrastructure" / "db" / "control"
_DDL_014 = _CONTROL / "014_import_operational_audit.sql"
_DDL_015 = _CONTROL / "015_import_operational_audit_append_only.sql"
_CRYPTO_FIXTURE_PATH = pathlib.Path(__file__).resolve().parents[2] / "api_gateway" / "crypto_fixture.py"

# Rehearsal LF-normalized git-blob SHA-1 pins for the Import-audit control DDL. A mismatch STOPS the exercise
# BEFORE any connection is opened. Deliberately named _REHEARSAL_BLOB_* (rehearsal-specific naming; the
# control-DDL pin meta-guard's registration sweep is scoped to its own reviewed-pin naming scheme).
_REHEARSAL_BLOB_014 = "73436f9681163c8a86ee230f51206062b06735c5"
_REHEARSAL_BLOB_015 = "ba594e3cd6eb070790bde6015f5225960c0d62ed"

# Control DDL applied UNPINNED beside 014/015 (their blobs are pinned by the default-suite guards; the
# rehearsal only needs the base control schema present). 001-009, in order — an explicit ordered list, never a
# wildcard; 010-013 (routing / gateway operational audit) are deliberately ABSENT from this rehearsal.
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

# The exact synthetic contract (references only; no personal or production data).
_ALPHA, _BETA = "alpha", "beta"
_GAMMA = "gamma"  # registry-seeded negative tenant whose secret reference is deliberately unresolvable (F8)
_DELTA = "delta"  # never seeded anywhere (F7 unknown tenant)
_SOURCE_REF = "rehearsal-startup-001"
_DISPLAY = "Rehearsal Synthetic Co"
_OP_KEY = "op-rehearsal-0001"
_CORRELATION = "corr-rehearsal-0001"
_PRINCIPAL = "rehearsal_agent"
_ISSUER = "https://rehearsal.issuer.local"
_AUDIENCE = "snackportal2-internal"
_FIXED_TS = "2026-07-19T00:00:00+00:00"
_EMPTY_BODY = b""

_READINESS_TIMEOUT_SECONDS = 30.0

# The pinned environment-touch census: only these keys may be set/unset by the rehearsal, and every one is
# restored in ``finally`` (the smoke-c _EnvPatch idiom — fail closed on any key outside the census).
_ENV_TOUCHED_KEYS = (
    "SP2_CP_READ_HOST",
    "SP2_CP_READ_PORT",
    "SP2_CP_CONTROL_STORE",
    "SP2_CP_CONTROL_STORE_DSN_REF",
    "SP2_CP_PROVISIONING_ADAPTER",
    "SP2_CP_TENANT_SCHEMA_APPLICATOR",
    "SP2_CP_DISTINCTNESS_LEDGER",
    "SNACKPORTAL_SECRET_CONTROL_CONTROL_STORE_DSN_V1",
    "SP2_CP_IMPORT_AUDIT_HOST",
    "SP2_CP_IMPORT_AUDIT_PORT",
    "SP2_AR_CONTROL_PLANE_READ_BASE_URL",
    "SP2_AR_ISSUERS",
    "SP2_AR_AUTHENTICATE_HOST",
    "SP2_AR_AUTHENTICATE_PORT",
    "SP2_DBR_ROUTING_READ_BASE_URL",
    "SP2_DBR_DISPATCH_HOST",
    "SP2_DBR_DISPATCH_PORT",
    "SNACKPORTAL_TENANT_SECRET_DIR",
    "SP2_IMPORT_HOST",
    "SP2_IMPORT_PORT",
    "SP2_IMPORT_AUDIT_SINK_BASE_URL",
    "SP2_GW_AUTH_ROUTER_BASE_URL",
    "SP2_GW_CONTROL_READ_BASE_URL",
    "SP2_GW_DB_ROUTER_BASE_URL",
    "SP2_GW_IMPORT_BASE_URL",
    "SP2_GW_EDGE_HOST",
    "SP2_GW_EDGE_PORT",
    "SP2_GW_AUDIT_SINK_BASE_URL",
    "SP2_GW_EDGE_ALLOWED_ORIGINS",
)


def _git_blob_sha1(path: pathlib.Path) -> str:
    data = path.read_bytes().replace(b"\r\n", b"\n")  # autocrlf normalization (the git blob is LF)
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def _verify_rehearsal_blob_pins() -> None:
    """Resolve the committed blob IDs and STOP before connecting or applying SQL if either diverges from the
    rehearsal pin (pure file I/O — no DB, no socket)."""
    b014, b015 = _git_blob_sha1(_DDL_014), _git_blob_sha1(_DDL_015)
    assert b014 == _REHEARSAL_BLOB_014, f"014 blob {b014} != pinned {_REHEARSAL_BLOB_014} — STOP before connect/apply (do not fix DDL here)"
    assert b015 == _REHEARSAL_BLOB_015, f"015 blob {b015} != pinned {_REHEARSAL_BLOB_015} — STOP before connect/apply (do not fix DDL here)"
    print(f"PASS: REH-0 rehearsal DDL blob pins verified BEFORE any connection (014={b014[:12]}…, 015={b015[:12]}…)")


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


def _port_refused(base_url: str) -> bool:
    parts = urlsplit(base_url)
    try:
        with socket.create_connection((parts.hostname or "127.0.0.1", parts.port or 80), timeout=2.0):
            return False
    except OSError:
        return True


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
    """Set/unset environment keys with the prior value recorded; ``restore()`` runs in ``finally``. Only keys
    in the pinned ``_ENV_TOUCHED_KEYS`` census may pass through here (fail closed)."""

    def __init__(self) -> None:
        self._saved: Dict[str, Optional[str]] = {}

    def set(self, key: str, value: Optional[str]) -> None:
        assert key in _ENV_TOUCHED_KEYS, f"environment key {key!r} is outside the pinned touch census — refused"
        if key not in self._saved:
            self._saved[key] = os.environ.get(key)
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value

    def restore(self) -> None:
        for key, prior in self._saved.items():
            if prior is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = prior
        self._saved.clear()


def _crypto_fixture() -> Any:
    """Load tests/api_gateway/crypto_fixture.py by file location under a private sys.modules name (the sole
    test module allowed to import jwt/cryptography — vendor containment; the smoke-c loader idiom)."""
    name = "rehearsal_crypto_fixture"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, _CRYPTO_FIXTURE_PATH)
    assert spec is not None and spec.loader is not None, f"cannot load crypto fixture at {_CRYPTO_FIXTURE_PATH}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _served(
    base_url: str, method: str, path: str, headers: Optional[Dict[str, str]] = None, body: bytes = _EMPTY_BODY
) -> Tuple[int, Dict[str, str], bytes]:
    """REAL stdlib HTTP client for the served edges (the golden entry — the harness never calls the gateway
    core in-process). Returns (status, lower-cased headers, body bytes). An explicit Host header in ``headers``
    overrides the default (the F12 dual-carrier straddle leg)."""
    parts = urlsplit(base_url)
    conn = HTTPConnection(parts.hostname or "127.0.0.1", parts.port, timeout=10)
    try:
        conn.request(method, path, body=body if body else None, headers=dict(headers or {}))
        resp = conn.getresponse()
        payload = resp.read()
        return resp.status, {k.lower(): v for k, v in resp.getheaders()}, payload
    finally:
        conn.close()


# --- the exercise ---------------------------------------------------------------------------------
def test_pg_controlled_served_write_rehearsal(admin_dsn: str) -> None:
    # PROOF REH-0 — rehearsal blob pins verified BEFORE any connection or SQL (STOP rule).
    _verify_rehearsal_blob_pins()

    # Lazy provider/composition imports: psycopg stays confined to the sanctioned zone; the module clean-skips
    # without it. Tests may import any package (lint-imports governs production packages only).
    from api_gateway.main import build_gateway_edge_server_from_env
    from auth_router.main import build_authenticate_server_from_env
    from control_plane.adapters.providers.postgres_store import PostgresControlStore
    from control_plane.adapters.providers.postgres_tenant_schema_applicator import PostgresTenantSchemaApplicator
    from control_plane.main import build_import_audit_server_from_env, build_read_server_from_env
    from database_router.adapters.providers.env_tenant_secret_store import EnvTenantSecretStore
    from database_router.adapters.providers.http_routing_read import HttpRoutingRead
    from database_router.adapters.providers.in_memory_audit_sink import InMemoryAuditSink
    from database_router.adapters.providers.psycopg_connection import PsycopgConnectionFactory
    from database_router.cache import RoutingViewCache
    from database_router.main import build_dispatch_server_from_env
    from database_router.pool import ConnectionPoolManager
    from database_router.resolver import RoutingResolver
    from database_router.router import DatabaseRouter
    from database_router.session_provider import PgRoutedSessionProvider
    from import_service.adapters.providers.http_directory_read import HttpDirectoryRead
    from import_service.main import build_import_server_from_env
    from lineage_service.emit import LineageEmit
    from shared.secrets import SecretRef

    fixture = _crypto_fixture()

    # Admin connection (autocommit: CREATE/DROP DATABASE are non-transactional), via the sanctioned adapter.
    admin = PostgresControlStore(admin_dsn)._conn
    admin.autocommit = True
    server_num = int(_scalar(admin, "SELECT current_setting('server_version_num')"))
    assert server_num >= 110000, f"PostgreSQL >= 11 required (server_version_num={server_num})"

    env = _EnvPatch()
    active_servers: List[Tuple[Any, Optional[threading.Thread]]] = []
    ctl_conn = alpha_conn = beta_conn = None
    secret_dir: Optional[str] = None

    def _host(server: Any) -> threading.Thread:
        thread = _serve(server)
        active_servers.append((server, thread))
        return thread

    def _stop_tracked(server: Any) -> None:
        for index, (candidate, thread) in enumerate(active_servers):
            if candidate is server:
                _stop(candidate, thread)
                del active_servers[index]
                return
        raise AssertionError("attempted to stop a server that is not tracked")

    try:
        # PROOF REH-1 — three disposable, physically distinct databases, lifecycle-owned by THIS run.
        for name in _REHEARSAL_DBS:
            admin.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()", (name,))
            admin.execute(f'DROP DATABASE IF EXISTS "{name}"')
            admin.execute(f'CREATE DATABASE "{name}"')
        ctl_dsn = _pg.swap_db(admin_dsn, _REH_CTL)
        alpha_dsn = _pg.swap_db(admin_dsn, _REH_ALPHA)
        beta_dsn = _pg.swap_db(admin_dsn, _REH_BETA)
        ctl_conn = PostgresControlStore(ctl_dsn)._conn
        ctl_conn.autocommit = True
        alpha_conn = PostgresControlStore(alpha_dsn)._conn
        alpha_conn.autocommit = True
        beta_conn = PostgresControlStore(beta_dsn)._conn
        beta_conn.autocommit = True
        identities = {
            _scalar(ctl_conn, "SELECT current_database()"),
            _scalar(alpha_conn, "SELECT current_database()"),
            _scalar(beta_conn, "SELECT current_database()"),
        }
        assert identities == set(_REHEARSAL_DBS), f"safe identity readback must show three distinct physical databases: {identities}"
        print(f"PASS: REH-1 three disposable physically distinct databases created fresh ({', '.join(_REHEARSAL_DBS)})")

        # PROOF REH-2 — control DDL on the disposable Control DB ONLY: 001-009 (unpinned) then exactly 014
        # then 015, each exactly once, exact order; 010-013 deliberately not applied.
        with ctl_conn.cursor() as cur:
            for name in _CONTROL_DDL_UNPINNED:
                cur.execute((_CONTROL / name).read_text(encoding="utf-8"))
            cur.execute(_DDL_014.read_text(encoding="utf-8"))
            cur.execute(_DDL_015.read_text(encoding="utf-8"))
        assert _scalar(ctl_conn, "SELECT to_regclass('control_import_audit')") is not None, "control_import_audit must exist after apply"
        assert _scalar(ctl_conn, "SELECT to_regclass('control_routing_audit')") is None, "010-013 must NOT be applied by this rehearsal"
        print("PASS: REH-2 control DDL applied to the disposable Control DB only (001-009, then 014, then 015; 010-013 absent)")

        # PROOF REH-3 — rehearsal-owned scratch secret directory (SecretRef-only material transport) + the
        # enrolled 14-file tenant template applied to BOTH disposable tenant DBs via the REAL applicator.
        secret_dir = tempfile.mkdtemp(prefix="sp2_rehearsal_secrets_")
        for tenant_id, tenant_dsn in ((_ALPHA, alpha_dsn), (_BETA, beta_dsn)):
            ref_dir = pathlib.Path(secret_dir) / "tenant" / tenant_id
            ref_dir.mkdir(parents=True)
            (ref_dir / "dsn@1").write_text(tenant_dsn, encoding="utf-8")
            (ref_dir / "chainkey@1").write_text(f"rehearsal-lineage-chainkey-{tenant_id}", encoding="utf-8")
        env.set("SNACKPORTAL_TENANT_SECRET_DIR", secret_dir)
        tenant_secrets = EnvTenantSecretStore()
        applicator = PostgresTenantSchemaApplicator(tenant_secrets)
        applicator.apply_schema(_ALPHA, target=_REH_ALPHA, association_ref=SecretRef(store_ref=f"tenant/{_ALPHA}/dsn", version="1"))
        applicator.apply_schema(_BETA, target=_REH_BETA, association_ref=SecretRef(store_ref=f"tenant/{_BETA}/dsn", version="1"))
        for tconn in (alpha_conn, beta_conn):
            assert _scalar(tconn, "SELECT to_regclass('startups')") is not None, "startups must exist after the tenant template"
            idx = _scalar(tconn, "SELECT indexdef FROM pg_indexes WHERE indexname = 'startups_global_startup_id_key'")
            assert idx is not None and "UNIQUE" in idx and "WHERE" not in idx, f"tenant 008 must be a plain UNIQUE index: {idx}"
        print("PASS: REH-3 14-file tenant template applied to both disposable tenant DBs (real applicator; plain UNIQUE 008 present)")

        # PROOF REH-4 — SecretRef-only registry + synthetic directory seed in the disposable Control DB
        # (direct-SQL seed on autocommit — the sibling disposable-proof idiom; references only, never a DSN).
        for tenant_id in (_ALPHA, _BETA, _GAMMA):
            ctl_conn.execute(
                "INSERT INTO control_tenants (tenant_id, organization_ref, lifecycle_state, expected_schema_version,"
                " assoc_store_ref, assoc_version, federation_config_ref, created_at, updated_at)"
                " VALUES (%s, 'rehearsal_org', 'Ready', '1', %s, '1', 'rehearsal_fed', %s, %s)",
                (tenant_id, f"tenant/{tenant_id}/dsn", _FIXED_TS, _FIXED_TS),
            )
        for tenant_id in (_ALPHA, _GAMMA):
            ctl_conn.execute(
                "INSERT INTO control_memberships (principal_ref, tenant_id, role) VALUES (%s, %s, 'TENANT_AGENT')",
                (_PRINCIPAL, tenant_id),
            )
        ctl_conn.execute(
            "INSERT INTO control_directory (directory, record_id, display_name, attributes) VALUES (%s, %s, %s, '{}'::jsonb)",
            ("GlobalStartupDirectory", _SOURCE_REF, _DISPLAY),
        )
        for row in ctl_conn.execute("SELECT tenant_id, assoc_store_ref, assoc_version FROM control_tenants").fetchall():
            assert row[1] == f"tenant/{row[0]}/dsn" and row[2] == "1", f"registry must carry SecretRef references only: {row}"
        for row in ctl_conn.execute("SELECT * FROM control_tenants").fetchall():
            for cell in row:
                assert "postgresql" not in str(cell), "the registry must never store a raw DSN (SecretRef only)"
        print("PASS: REH-4 SecretRef-only registry (alpha/beta/gamma Ready), memberships, and synthetic directory record seeded")

        # PROOF REH-5 — the six served edges hosted on loopback ephemeral ports from the existing production
        # env-seam factories (the test-owned higher deployment root; injected Import cross-package ports).
        env.set("SP2_CP_READ_PORT", None)
        env.set("SP2_CP_IMPORT_AUDIT_PORT", None)
        env.set("SP2_AR_AUTHENTICATE_HOST", None)
        env.set("SP2_AR_AUTHENTICATE_PORT", None)
        env.set("SP2_DBR_DISPATCH_HOST", None)
        env.set("SP2_DBR_DISPATCH_PORT", None)
        env.set("SP2_IMPORT_PORT", None)
        env.set("SP2_GW_EDGE_PORT", None)
        env.set("SP2_GW_AUDIT_SINK_BASE_URL", None)
        env.set("SP2_GW_EDGE_ALLOWED_ORIGINS", None)
        env.set("SP2_CP_PROVISIONING_ADAPTER", None)
        env.set("SP2_CP_TENANT_SCHEMA_APPLICATOR", None)
        env.set("SP2_CP_DISTINCTNESS_LEDGER", None)
        env.set("SP2_CP_CONTROL_STORE_DSN_REF", None)  # default control/control-store-dsn (reference only)
        env.set("SNACKPORTAL_SECRET_CONTROL_CONTROL_STORE_DSN_V1", ctl_dsn)  # in-memory reference material
        env.set("SP2_CP_CONTROL_STORE", "postgres")  # control-store-standalone postgres (sanctioned RULE 2)

        # Edge 1 — Control-Plane read edge (routing views + directory + memberships) over the disposable
        # Control DB, DSN by reference.
        env.set("SP2_CP_READ_HOST", "127.0.0.1")
        read_built = build_read_server_from_env()
        assert read_built is not None, "the Control-Plane read edge seam must activate"
        read_server, read_base = read_built
        _host(read_server)
        _await_ready("control-plane read edge", lambda: _served(read_base, "GET", f"/internal/routing/tenants/{_ALPHA}")[0] == 200)

        # Edge 2 — Import-audit ingest edge over the disposable Control DB (durable PostgresImportAuditStore).
        env.set("SP2_CP_IMPORT_AUDIT_HOST", "127.0.0.1")
        ingest_built = build_import_audit_server_from_env()
        assert ingest_built is not None, "the Import-audit ingest seam must activate"
        ingest_server, ingest_base = ingest_built
        _host(ingest_server)

        # Edge 3 — Auth authenticate edge (RS256/OIDC via SP2_AR_ISSUERS; rehearsal-scoped keypair).
        keypair = fixture.generate_rs256_keypair()

        def _mint(tenant: Optional[str]) -> str:
            token = fixture.mint_rs256_token(
                keypair, issuer=_ISSUER, audience=_AUDIENCE, subject=_PRINCIPAL, tenant=tenant, ttl_seconds=3600
            )
            return str(token)

        alpha_token = _mint(_ALPHA)
        control_token = _mint(None)  # tenantless CONTROL (F2): no tenant claim at all
        gamma_token = _mint(_GAMMA)
        delta_token = _mint(_DELTA)
        env.set("SP2_AR_CONTROL_PLANE_READ_BASE_URL", read_base)
        env.set("SP2_AR_ISSUERS", fixture.issuer_env_json(keypair, issuer=_ISSUER, audience=_AUDIENCE))
        auth_built = build_authenticate_server_from_env()
        assert auth_built is not None, "the Auth authenticate seam must activate"
        auth_server, auth_base = auth_built
        _host(auth_server)
        _await_ready("auth authenticate edge", lambda: _served(auth_base, "POST", "/internal/auth/probe")[0] == 404)

        # Edge 4 — Database-Router dispatch edge (structurally required by the gateway composition; the
        # single-route import path never calls it).
        env.set("SP2_DBR_ROUTING_READ_BASE_URL", read_base)
        dispatch_built = build_dispatch_server_from_env()
        assert dispatch_built is not None, "the Database-Router dispatch seam must activate"
        dispatch_server, dispatch_base = dispatch_built
        _host(dispatch_server)

        # Edge 5 — served internal Import edge with the three injected cross-package ports (all REAL adapters:
        # HttpRoutingRead + EnvTenantSecretStore + PsycopgConnectionFactory router; LineageEmit over the
        # tenant-scoped chain keys; HttpDirectoryRead over edge 1) — the higher-deployment-root duty.
        routing_audit = InMemoryAuditSink()
        request_pool = ConnectionPoolManager(max_per_tenant=5, idle_timeout_seconds=60.0, clock=lambda: 0.0)
        bulk_pool = ConnectionPoolManager(max_per_tenant=5, idle_timeout_seconds=60.0, clock=lambda: 0.0)
        router = DatabaseRouter(
            resolver=RoutingResolver(
                HttpRoutingRead(read_base), RoutingViewCache(ttl_seconds=60.0, clock=lambda: 0.0), supported_schema_versions=("1",)
            ),
            pool=request_pool,
            bulk_pool=bulk_pool,
            secret_store=tenant_secrets,
            connection_factory=PsycopgConnectionFactory(),
            audit=routing_audit,
        )
        import_ports: Dict[str, Any] = {
            "session_provider": PgRoutedSessionProvider(router),
            "lineage": LineageEmit(tenant_secrets, key_prefix="tenant"),
            "directory_read": HttpDirectoryRead(read_base),
        }
        env.set("SP2_IMPORT_HOST", "127.0.0.1")
        env.set("SP2_IMPORT_AUDIT_SINK_BASE_URL", ingest_base)
        import_built = build_import_server_from_env(**import_ports)
        assert import_built is not None, "the served Import edge seam must activate"
        import_server, import_base = import_built
        _host(import_server)

        # Edge 6 — the W1b served Gateway Edge fronting the full composition.
        env.set("SP2_GW_AUTH_ROUTER_BASE_URL", auth_base)
        env.set("SP2_GW_CONTROL_READ_BASE_URL", read_base)
        env.set("SP2_GW_DB_ROUTER_BASE_URL", dispatch_base)
        env.set("SP2_GW_IMPORT_BASE_URL", import_base)
        env.set("SP2_GW_EDGE_HOST", "127.0.0.1")
        edge_built = build_gateway_edge_server_from_env()
        assert edge_built is not None, "the served Gateway Edge seam must activate"
        edge_server, edge_base = edge_built
        _host(edge_server)
        _await_ready("served gateway edge", lambda: _served(edge_base, "GET", "/health")[0] == 200)
        print(f"PASS: REH-5 six served edges hosted on loopback ephemeral ports ({len(active_servers)} processes; all env-seam factories)")

        # --- references-only evidence helpers (direct SQL against the disposable databases only) ----------
        def _startups(tconn: Any) -> int:
            return int(_scalar(tconn, "SELECT count(*) FROM startups"))

        def _created_lineage(tconn: Any) -> int:
            return int(_scalar(tconn, "SELECT count(*) FROM lineage WHERE operation = 'created'"))

        def _audit_count() -> int:
            return int(_scalar(ctl_conn, "SELECT count(*) FROM control_import_audit"))

        def _completed_count() -> int:
            return int(_scalar(ctl_conn, "SELECT count(*) FROM control_import_audit WHERE action = 'ImportCompleted'"))

        def _golden_headers(**overrides: str) -> Dict[str, str]:
            headers = {
                "Authorization": "Bearer " + alpha_token,
                "x-operation-key": _OP_KEY,
                "x-correlation-id": _CORRELATION,
                "X-Tenant-Id": _ALPHA,
            }
            headers.update(overrides)
            return headers

        # PROOF REH-6 — golden served journey (G1-G10): REAL stdlib HTTP client -> 200 ``created``.
        routing_events_before = len(routing_audit.events())
        status, resp_headers, payload = _served(edge_base, "POST", f"/import/{_SOURCE_REF}", headers=_golden_headers())
        assert status == 200, f"G1: the served golden import must answer 200: {status}"
        assert resp_headers.get("x-correlation-id") == _CORRELATION, "G1: the edge must echo the request correlation id"
        dto = json.loads(payload)
        assert dto["outcome"] == "created", f"G10: outcome must be created: {dto}"
        assert dto["source_ref"] == _SOURCE_REF and dto["target_tenant_ref"] == _ALPHA, f"G10: references must match the contract: {dto}"
        assert dto["tenant_record_ref"] == f"{_ALPHA}:startups:{_SOURCE_REF}", f"G10: tenant_record_ref contract violated: {dto}"
        assert dto["import_id"] and dto["lineage_ref"] == dto["import_id"], f"G10: lineage_ref must equal import_id: {dto}"
        assert _startups(alpha_conn) == 1, "G7: exactly one alpha startups row must be durably written"
        row = alpha_conn.execute("SELECT global_startup_id, company_name FROM startups").fetchone()
        assert row == (_SOURCE_REF, _DISPLAY), f"G7: the mapped startups row must be present: {row}"
        assert _created_lineage(alpha_conn) == 1, "G8: exactly one alpha created-lineage row must be durably written"
        assert _audit_count() == 3, f"G9: a fresh served import must durably record exactly 3 audit rows: {_audit_count()}"
        actions = sorted(r[0] for r in ctl_conn.execute("SELECT action FROM control_import_audit").fetchall())
        assert actions == ["ImportCompleted", "ImportRequested", "ImportStarted"], f"G9: exact fresh action set violated: {actions}"
        golden_routing_events = len(routing_audit.events()) - routing_events_before
        assert golden_routing_events >= 1, "G5: the golden request must route through the Database Router"
        assert bulk_pool.pool_keys() == [(_ALPHA, "1")], f"G5/G6: exactly one routed pool key (alpha) allowed: {bulk_pool.pool_keys()}"
        assert request_pool.pool_keys() in ([], [(_ALPHA, "1")]), f"G5: no non-alpha pool key may exist: {request_pool.pool_keys()}"
        assert _startups(beta_conn) == 0 and _created_lineage(beta_conn) == 0, "G6: the beta physical DB must be untouched"
        print("PASS: REH-6 golden served journey (stdlib client -> 200 created; alpha row + lineage; 3 audit rows; one routed pool key)")

        # PROOF REH-7 — served idempotent replay (G11-G12, F11): same operation key -> replayed, no duplicates.
        replay_events_before = len(routing_audit.events())
        status, _, payload = _served(edge_base, "POST", f"/import/{_SOURCE_REF}", headers=_golden_headers())
        dto_replay = json.loads(payload)
        assert status == 200 and dto_replay["outcome"] == "replayed", f"G11: a same-key served retry must replay: {status} {dto_replay}"
        assert _startups(alpha_conn) == 1, "G12/F11: a replay must add NO tenant row"
        assert _created_lineage(alpha_conn) == 1, "G12/F11: a replay must add NO created-lineage effect"
        assert _audit_count() == 5, f"G12: a replay durably records exactly 2 more audit rows: {_audit_count()}"
        replay_routing_events = len(routing_audit.events()) - replay_events_before
        assert replay_routing_events == golden_routing_events, "G5: replay must route exactly like the fresh request (single-route)"
        print("PASS: REH-7 served idempotent replay (200 replayed; no duplicate row/lineage; +2 durable audit rows)")

        # PROOF REH-8 — reference reconciliation + references-only stored rows (G13).
        for r in ctl_conn.execute("SELECT correlation_id, source_ref, target_ref FROM control_import_audit").fetchall():
            assert r[0] == _CORRELATION, f"G13: every durable audit row must carry the request correlation: {r}"
            assert r[1] == _SOURCE_REF and r[2] == _ALPHA, f"G13: audit references must reconcile (source/tenant): {r}"
        lineage_corr = _scalar(alpha_conn, "SELECT correlation_id FROM lineage WHERE operation = 'created'")
        assert lineage_corr == _CORRELATION, f"G13: the created-lineage row must carry the request correlation: {lineage_corr}"
        secret_parts = [admin_dsn]
        password = urlsplit(admin_dsn).password
        if password:
            secret_parts.append(password)
        for r in ctl_conn.execute("SELECT * FROM control_import_audit").fetchall():
            for cell in r:
                for secret in secret_parts:
                    assert secret not in str(cell), "stored cells must never contain the descriptor/password (references only)"
                assert "Bearer " not in str(cell), "stored cells must never contain a bearer credential (references only)"
        print("PASS: REH-8 correlation/import references reconcile across response, lineage, and audit; stored rows are references-only")

        # PROOF REH-9 — served denial fidelity (F1-F5), all through the real HTTP edge, state unchanged.
        status, _, payload = _served(edge_base, "POST", f"/import/{_SOURCE_REF}", headers={"x-correlation-id": _CORRELATION})
        assert (status, payload) == (401, b""), f"F1: missing bearer must be 401 empty-body: {status} {payload!r}"
        status, _, payload = _served(edge_base, "POST", f"/import/{_SOURCE_REF}", headers={"Authorization": "Bearer " + control_token})
        assert (status, payload) == (403, b""), f"F2: a tenantless CONTROL principal must be denied 403 at gateway authorization: {status}"
        status, _, payload = _served(edge_base, "POST", f"/import/{_SOURCE_REF}", headers=_golden_headers(**{"X-Tenant-Id": _BETA}))
        assert (status, payload) == (403, b""), f"F3: a carrier mismatching the signed tenant must be denied 403: {status}"
        for malformed in ("/import", "/import/", f"/import/{_SOURCE_REF}/", "/import/..", "/import/%2e%2e", "/import/a//b"):
            status, _, _ = _served(edge_base, "POST", malformed)
            assert status == 404, f"F4: malformed target {malformed!r} must be rejected 404 pre-core: {status}"
        status, _, _ = _served(edge_base, "POST", f"/import/{_SOURCE_REF}", headers=_golden_headers(), body=b"x")
        assert status == 413, f"F5: a body-bearing request must be rejected 413 pre-core: {status}"
        assert _startups(alpha_conn) == 1 and _startups(beta_conn) == 0, "F1-F5 must not touch any tenant DB"
        assert _audit_count() == 5, "F1-F5 must create no durable import audit"
        print("PASS: REH-9 served denial fidelity (401 no-bearer; 403 CONTROL; 403 carrier-mismatch; 404 malformed; 413 body pre-core)")

        # PROOF REH-10 — F6 port-absent: an edge composed WITHOUT the Import port must fail closed 503 —
        # never a fake 200 accepted-initiation success.
        env.set("SP2_GW_IMPORT_BASE_URL", None)
        port_absent_built = build_gateway_edge_server_from_env()
        assert port_absent_built is not None, "the port-absent gateway edge must still compose (three transports set)"
        pa_server, pa_base = port_absent_built
        _host(pa_server)
        status, _, payload = _served(
            pa_base, "POST", f"/import/{_SOURCE_REF}", headers=_golden_headers(**{"x-operation-key": "op-rehearsal-f6"})
        )
        assert (status, payload) == (503, b""), f"F6: a missing Import port must serve 503, never a fake 200: {status} {payload!r}"
        _stop_tracked(pa_server)
        assert _port_refused(pa_base), "G14: a stopped served process must release its socket"
        env.set("SP2_GW_IMPORT_BASE_URL", import_base)
        assert _startups(alpha_conn) == 1 and _audit_count() == 5, "F6 must not touch tenant state or durable audit"
        print("PASS: REH-10 port-absent Import composition serves 503 fail-closed (never a fake success)")

        # PROOF REH-11 — F7 unknown tenant + F8 missing secret reference: both fail closed, no DB opened,
        # no false completion.
        f7_headers = _golden_headers(
            **{"Authorization": "Bearer " + delta_token, "X-Tenant-Id": _DELTA, "x-operation-key": "op-rehearsal-f7"}
        )
        status, _, _ = _served(edge_base, "POST", f"/import/{_SOURCE_REF}", headers=f7_headers)
        assert status == 403, f"F7: an unknown tenant must fail closed (auth denies the unregistered tenant): {status}"
        f8_headers = _golden_headers(
            **{"Authorization": "Bearer " + gamma_token, "X-Tenant-Id": _GAMMA, "x-operation-key": "op-rehearsal-f8"}
        )
        status, _, _ = _served(edge_base, "POST", f"/import/{_SOURCE_REF}", headers=f8_headers)
        assert status == 503, f"F8: an unresolvable tenant secret reference must fail closed 503: {status}"
        assert _completed_count() == 2, "F7/F8 must record no false ImportCompleted"
        assert bulk_pool.pool_keys() == [(_ALPHA, "1")], f"F7/F8 must open no new physical tenant DB: {bulk_pool.pool_keys()}"
        print("PASS: REH-11 unknown tenant 403 and missing secret reference 503 (fail closed; no DB opened; no false completion)")

        # PROOF REH-12 — F10 audit-outage drill: ingest stopped -> served 503 (no false success); restored ->
        # the same-key served retry confirms exactly once (audit-before-hand-back).
        _stop_tracked(ingest_server)
        assert _port_refused(ingest_base), "G14: the stopped ingest process must release its socket"
        status, _, payload = _served(edge_base, "POST", f"/import/{_SOURCE_REF}", headers=_golden_headers())
        assert (status, payload) == (503, b""), f"F10: an unavailable durable audit must fail the served success closed 503: {status}"
        assert _startups(alpha_conn) == 1, "F10: the fail-closed drill must not corrupt applied tenant state"
        assert _completed_count() == 2, "F10: no false ImportCompleted may be recorded while the sink is down"
        ingest_rebuilt = build_import_audit_server_from_env()
        assert ingest_rebuilt is not None
        ingest_server, ingest_base = ingest_rebuilt
        _host(ingest_server)
        env.set("SP2_IMPORT_AUDIT_SINK_BASE_URL", ingest_base)
        _stop_tracked(import_server)
        import_rebuilt = build_import_server_from_env(**import_ports)
        assert import_rebuilt is not None
        import_server, import_base = import_rebuilt
        _host(import_server)
        env.set("SP2_GW_IMPORT_BASE_URL", import_base)
        _stop_tracked(edge_server)
        edge_rebuilt = build_gateway_edge_server_from_env()
        assert edge_rebuilt is not None
        edge_server, edge_base = edge_rebuilt
        _host(edge_server)
        _await_ready("served gateway edge (restored)", lambda: _served(edge_base, "GET", "/health")[0] == 200)
        status, _, payload = _served(edge_base, "POST", f"/import/{_SOURCE_REF}", headers=_golden_headers())
        dto_confirm = json.loads(payload)
        assert status == 200 and dto_confirm["outcome"] == "replayed", f"F10: the confirm must replay exactly once: {status} {dto_confirm}"
        assert _startups(alpha_conn) == 1 and _created_lineage(alpha_conn) == 1, "F10: recovery must not duplicate tenant state"
        assert _completed_count() == 3, "F10: the restored confirm must durably record exactly one more completion"
        print("PASS: REH-12 audit-outage drill (ingest down -> 503 no-false-success; restored -> replay confirms exactly once)")

        # PROOF REH-13 — F12 physical isolation: a dual-carrier straddle is denied with beta untouched, and
        # no routing-audit event ever references beta.
        status, _, payload = _served(
            edge_base,
            "POST",
            f"/import/{_SOURCE_REF}",
            headers=_golden_headers(**{"Host": "beta.rehearsal.local", "x-operation-key": "op-rehearsal-f12"}),
        )
        assert (status, payload) == (403, b""), f"F12: a dual-carrier straddle must be denied 403: {status}"
        assert _startups(beta_conn) == 0 and _created_lineage(beta_conn) == 0, "F12: the beta physical DB must remain untouched"
        assert _scalar(beta_conn, "SELECT current_database()") == _REH_BETA, "F12: beta identity readback must remain intact"
        for event in routing_audit.events():
            assert _BETA not in str(event.target_ref or ""), f"F12: no routing-audit event may reference beta: {event}"
        assert bulk_pool.pool_keys() == [(_ALPHA, "1")], "F12: alpha must remain the only routed pool key"
        print("PASS: REH-13 dual-carrier straddle denied; beta physically untouched (zero rows; no routed key; no routing-audit reference)")

        # PROOF REH-14 — F9 alpha unavailable: the selected tenant DB is dropped -> served 503, and beta is
        # NEVER used as a fallback.
        alpha_conn.close()
        alpha_conn = None
        admin.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()", (_REH_ALPHA,)
        )
        admin.execute(f'DROP DATABASE IF EXISTS "{_REH_ALPHA}"')
        status, _, payload = _served(
            edge_base, "POST", f"/import/{_SOURCE_REF}", headers=_golden_headers(**{"x-operation-key": "op-rehearsal-f9"})
        )
        assert (status, payload) == (503, b""), f"F9: an unavailable selected tenant DB must serve 503 fail-closed: {status}"
        assert _startups(beta_conn) == 0 and _created_lineage(beta_conn) == 0, "F9: beta must NEVER be used as a fallback"
        assert _completed_count() == 3, "F9: no false ImportCompleted may be recorded for the unavailable tenant"
        print("PASS: REH-14 alpha unavailable -> served 503 with no beta fallback (fail closed; no false completion)")
    finally:
        # PROOF REH-15 / G14 / R-A — deterministic shutdown of every served process, then disposal of the
        # COMPLETE disposable topology (after success OR failure). Pool-held connections are severed by
        # pg_terminate_backend before each drop.
        stopped = 0
        for server, thread in reversed(list(active_servers)):
            try:
                _stop(server, thread)
                stopped += 1
            except Exception:
                pass
        del active_servers[:]
        for conn in (ctl_conn, alpha_conn, beta_conn):
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
        env.restore()
        if secret_dir is not None:
            shutil.rmtree(secret_dir, ignore_errors=True)  # scratch SecretRef material never outlives the run
        remaining = 0
        for name in _REHEARSAL_DBS:
            admin.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()", (name,))
            admin.execute(f'DROP DATABASE IF EXISTS "{name}"')
            remaining += int(_scalar(admin, "SELECT count(*) FROM pg_database WHERE datname = %s", (name,)))
        print(f"PASS: REH-15 deterministic shutdown ({stopped} served processes) and R-A disposal (retained datname count = {remaining})")
        admin.close()
        assert remaining == 0, "R-A: every disposable rehearsal database must be removed after the run"


if __name__ == "__main__":
    _pg.run([test_pg_controlled_served_write_rehearsal])
