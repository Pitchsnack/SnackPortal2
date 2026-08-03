"""DBR-AR-2D V3 — retained standing-topology witnesses — operator harness (standalone-only; PRD DBR-AR-2D V3).

An OPERATOR TOOL, not application runtime code and not a test: under an explicit Dan START-GATE it
delivers the remaining DBR-AR-2 contract §16 STANDING-ENVIRONMENT witnesses (proofs 1/2 standing
halves, 4, 8, 12) over the retained local B5-4/B5-4A standing topology —

    apply   (Dan-authorized, exactly once): secure full logical backup of the standing Control DB
            OUTSIDE the repository, then the governed manual apply of the reviewed, blob-pinned
            routing-audit DDL (010_routing_audit.sql then 011_routing_audit_append_only.sql — the
            exact repository paths, exact order, never a wildcard) to the retained local standing
            Control database ONLY, then exact catalog verification.
    run     (Dan-authorized, exactly once): the standing witness — the REAL composed request path

                InboundRequest -> Gateway.handle (in-process, real composed Gateway)
                  -> real Auth Router (build_authenticate_server_from_env)
                  -> real Database Router dispatch (build_dispatch_server_from_env) with the REAL
                     DURABLE routing-audit chain composed (SP2_DBR_ROUTING_AUDIT_BASE_URL ->
                     BoundedRoutingAuditPolicy -> HttpRoutingAudit -> the Control-Plane ingest edge
                     build_routing_audit_server_from_env -> PostgresRoutingAuditStore -> the
                     STANDING Control DB)
                  -> exactly one standing physical tenant database

            executing the exact S1–S5 matrix and producing EXACTLY the four predeclared durable
            evidence rows (S3, the dormant Auth-edge denial, adds ZERO routing-audit rows).

Commands (stdlib argparse; work happens ONLY after an explicit subcommand — import performs no I/O):

    plan     read-only: B5-4 6/6 + B5-4A 12/12 + Smoke C V2 status delegation (subprocess,
             status-only argv), reviewed DDL blob pins, the standing 001-009 automatic-apply-order
             pin (AST of the B5-4 operator source — never an import), Control/alpha/beta identity
             probes, dormant no-secret/no-DB/no-schema proof, the complete before-state families,
             the exact intended schema + four-row delta, stage classification, and the refusal
             posture for prior/partial evidence. No mutation, no server, no backup.
    apply    Dan-authorized for the V3 execution only: re-runs preconditions; creates the secure
             full logical Control-DB backup outside the repository (pg_dump --format=custom,
             credentials passed by ENVIRONMENT to the child process — never argv; sha256 recorded;
             `pg_restore --list` readability witness); verifies the reviewed blob pins; verifies
             the exact standing Control DB identity by probe; applies 010 exactly once then 011
             exactly once; verifies the exact schema objects; stops on any mismatch. REFUSES when
             the complete schema already exists or ANY evidence row exists (exactly-once).
    run      the standing witness, exactly once: re-runs preconditions; REFUSES if any
             control_routing_audit row exists (rerun refusal — durable, cross-process); captures a
             fresh pre-run snapshot; composes and hosts the real seams on loopback ephemeral ports
             (test-owned daemon threads; one single-threaded server each — harness hosting only);
             executes S1–S5 serially; proves the exact four-row delta and every per-scenario
             obligation; drains pools, stops every server, restores every touched environment key
             in ``finally``; requires before == after outside the exact allowed delta.
    status   read-only, fail-closed: B5-4 6/6 + B5-4A 12/12 delegation, exact schema census (the
             20-column contract, identity PK, unique event_id, the exact CHECK set, the exact
             trigger set, the append-only function), EXACTLY the four predeclared evidence rows in
             emission order (no fifth row), the 001-009 automatic-apply-order pin, dormant and
             alpha/beta preservation, zero V3 residue outside control_routing_audit, no leftover
             in-process listener, and the locked activation posture. Healthy prerequisites alone
             NEVER claim witness completion (fail closed): status is green only over the exact
             delivered standing evidence.

There is deliberately NO removal command, NO row deletion, NO trigger bypass, and NO destructive
rollback of any kind: the applied schema and the four evidence rows are the intended durable standing-state
change (PRD DBR-AR-2D V3 §4/§8); recovery from a failed apply is a reviewed idempotent re-run per
the operator runbook, never an invented destructive path. The subprocess seams are exactly: the
three status-only standing-operator delegations, one read-only ``git rev-parse HEAD`` (evidence
binds to the tested commit), one ``pg_dump`` (backup), and one ``pg_restore --list`` (readability
witness). The B5-4/B5-4A/Smoke C operator modules are NEVER imported.

DRIVER/VENDOR CONTAINMENT. No static database-driver import (psycopg is located via importlib at
call time) and no JWT/crypto vendor import (tokens are minted by the blessed B5-5 fixture,
``tests/api_gateway/crypto_fixture.py``, loaded lazily by file location). Module import is inert
(no I/O, no env mutation, no socket, no thread). Backend/provider imports are lazy, inside
commands. Runbook: ``infrastructure/runbooks/dbr_ar_2_durable_routing_audit.md`` (invoked from
``backend/`` as ``python tests/control_plane/requires_pg/dbr_ar_2d_standing_witnesses.py <cmd>``).

SECRET HYGIENE (D-14). DSNs are resolved in-memory by reference and NEVER printed, logged, or
written to any evidence artifact; every emitted identity is redacted to scheme+host+port+database;
backup credentials pass to the child process by environment only; stored evidence rows are scanned
to carry no DSN/password/token-shaped value. The backup archive is written OUTSIDE the repository
and is never committed or attached.

NO OVERCLAIM. A green run delivers the DBR-AR-2 contract §16 standing-environment witnesses over
the retained LOCAL standing topology at database granularity — nothing about production readiness,
deployment, cluster-level distinctness, or activation. DBR-AR-2 — CLOSED (Dan-authorized governance
decision, 2026-07-16); this closure closes zero B5 activation blockers, the blocker census remains
nine with 8 of 9 OPEN, and production remains NOT READY / DO-NOT-ACTIVATE. DBR-AR-2E —
production-activation evidence consolidated (Outcome A — REMAIN NOT READY / DO-NOT-ACTIVATE).
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib
import importlib.util
import os
import pathlib
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlsplit, urlunsplit

_THIS = pathlib.Path(__file__).resolve()
_BACKEND_ROOT = _THIS.parents[3]
_REPO_ROOT = _THIS.parents[4]
sys.path.insert(0, str(_BACKEND_ROOT))  # backend on path (the requires_pg harness idiom); no package import happens at module scope

# The standing operators (same directory). NEVER imported — subprocess, status-only argv.
_B5_4_OPS = _THIS.parent / "b5_standing_topology.py"
_B5_4A_OPS = _THIS.parent / "b5_standing_auth_fixture.py"
_SMOKE_C_OPS = _THIS.parent / "smoke_c_integrated_live_proof.py"
_STATUS_COMMAND = "status"  # the ONLY standing-operator subcommand this operator may ever invoke
_B5_4_PASS_COUNT = 6
_B5_4A_PASS_COUNT = 12

# The blessed B5-5 RS256 fixture (loaded lazily by file location; vendors stay contained there).
_CRYPTO_FIXTURE_PATH = _BACKEND_ROOT / "tests" / "api_gateway" / "crypto_fixture.py"

# The reviewed DBR-AR-2B DDL — exact repository paths, applied 010 then 011, each exactly once.
_CONTROL_DDL_DIR = _REPO_ROOT / "infrastructure" / "db" / "control"
_DDL_010 = _CONTROL_DDL_DIR / "010_routing_audit.sql"
_DDL_011 = _CONTROL_DDL_DIR / "011_routing_audit_append_only.sql"
# The merged V2 disposable-proof harness (same directory) is the SINGLE reviewed-pin authority:
# its _REVIEWED_010_BLOB/_REVIEWED_011_BLOB literals are cross-checked in the default suite by
# test_b7c1_control_audit_ddl_blob_pins.py and the B7C1R2 pin-completeness meta-guard. This
# operator deliberately declares NO second hand-copied pin literal — it derives the pins from
# that harness's SOURCE by AST (never an import) and fails closed when either is absent.
_V2_HARNESS = _THIS.parent / "test_dbr_ar_2d_routing_audit_live_pg.py"

# The retained standing topology (PRD DBR-AR-2D V3 §3) — the ONLY authorized target family.
CONTROL_DB_NAME = "snackportal2_control_local"
TENANT_ALPHA = "b5_standing_alpha"
TENANT_BETA = "b5_standing_beta"
TENANT_DORMANT = "b5_standing_dormant"
PRINCIPAL = "b5_standing_member"
ALPHA_DB = "sp2_tenant_b5_standing_alpha"
BETA_DB = "sp2_tenant_b5_standing_beta"
ASSOCIATION_VERSION = "1"

# The V2 disposable proof database — must remain ABSENT on the standing cluster at all times.
_V2_PROOF_DB = "sp2_dbr_ar_2d_proof"

# The B5-4 automatic standing apply order (pinned; re-derived from the B5-4 operator SOURCE by
# AST — never an import). DDL 010/011 must NEVER appear in it (manual V3 apply only).
_EXPECTED_AUTO_APPLY_ORDER: Tuple[str, ...] = (
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

# The test-process issuer contract carried by SP2_AR_ISSUERS (public JWK only; fixture-built).
ISSUER = "https://dbr-ar-2d-v3.issuer.local"
AUDIENCE = "snackportal2-internal"

# The deterministic V3 evidence prefix and the operator actor for the router-edge-direct legs.
EVIDENCE_PREFIX = "dbr2dv3"
OPS_ACTOR = "dbr_ar_2d_v3_standing_ops"
S1_CORRELATION = "dbr2dv3-s1-alpha"
S2_CORRELATION = "dbr2dv3-s2-beta"
S3_CORRELATION = "dbr2dv3-s3-dormant-auth"  # Auth-edge denial: adds ZERO routing-audit rows
S4_CORRELATION = "dbr2dv3-s4-dormant-router"
S5_CORRELATION = "dbr2dv3-s5-anomaly"

# The EXACT predeclared durable evidence rows (PRD DBR-AR-2D V3 §7), in required emission
# (identity-id) order: S1 Route(alpha), S2 Route(beta), S4 RouteDenied(dormant),
# S5 IsolationAnomaly(alpha->beta). There is NO fifth V3 row. Store-assigned fields
# (id / event_id / occurred_at / recorded_at) and the gateway-owned request_ref of S1/S2 are
# asserted structurally, not pinned here.
EXPECTED_EVIDENCE_ROWS: Tuple[Dict[str, Any], ...] = (
    {
        "correlation_id": "dbr2dv3-s1-alpha",
        "action": "Route",
        "outcome": "success",
        "actor_ref": "b5_standing_member",
        "tenant_ref": "b5_standing_alpha",
        "resolved_tenant_ref": "b5_standing_alpha",
        "public_code": None,
        "error_class": None,
        "association_store_ref": "tenant/b5_standing_alpha/dsn",
        "association_version": "1",
        "lane": "interactive",
        "source_service": "database_router",
        "source_version": "4",
        "event_version": 1,
    },
    {
        "correlation_id": "dbr2dv3-s2-beta",
        "action": "Route",
        "outcome": "success",
        "actor_ref": "b5_standing_member",
        "tenant_ref": "b5_standing_beta",
        "resolved_tenant_ref": "b5_standing_beta",
        "public_code": None,
        "error_class": None,
        "association_store_ref": "tenant/b5_standing_beta/dsn",
        "association_version": "1",
        "lane": "interactive",
        "source_service": "database_router",
        "source_version": "4",
        "event_version": 1,
    },
    {
        "correlation_id": "dbr2dv3-s4-dormant-router",
        "action": "RouteDenied",
        "outcome": "denied:not_ready",
        "actor_ref": "dbr_ar_2d_v3_standing_ops",
        "tenant_ref": "b5_standing_dormant",
        "resolved_tenant_ref": None,
        "public_code": "not_ready",
        "error_class": None,
        "association_store_ref": None,
        "association_version": None,
        "lane": None,
        "source_service": "database_router",
        "source_version": "4",
        "event_version": 1,
    },
    {
        "correlation_id": "dbr2dv3-s5-anomaly",
        "action": "IsolationAnomaly",
        "outcome": "anomaly:tenant_binding",
        "actor_ref": "dbr_ar_2d_v3_standing_ops",
        "tenant_ref": "b5_standing_alpha",
        "resolved_tenant_ref": "b5_standing_beta",
        "public_code": None,
        "error_class": None,
        "association_store_ref": None,
        "association_version": None,
        "lane": None,
        "source_service": "database_router",
        "source_version": "4",
        "event_version": 1,
    },
)

# Environment keys this operator may SET during run (existing names only; every prior value is
# restored in ``finally``). No ``*_PORT`` key is ever set (unset -> the seams' ephemeral default);
# the unset census is explicitly cleared for the run so ambient values can never select a fixed
# port, a foreign host, or a foreign audit timeout.
_ENV_SELECTOR_KEYS = (
    "SP2_CP_CONTROL_STORE",
    "SP2_CP_PROVISIONING_ADAPTER",
    "SP2_CP_TENANT_SCHEMA_APPLICATOR",
    "SP2_CP_DISTINCTNESS_LEDGER",
)
_ENV_URL_KEYS = (
    "SP2_CP_READ_HOST",
    "SP2_CP_ROUTING_AUDIT_HOST",
    "SP2_AR_CONTROL_PLANE_READ_BASE_URL",
    "SP2_AR_ISSUERS",
    "SP2_DBR_ROUTING_READ_BASE_URL",
    "SP2_DBR_ROUTING_AUDIT_BASE_URL",
    "SP2_GW_AUTH_ROUTER_BASE_URL",
    "SP2_GW_DB_ROUTER_BASE_URL",
)
_ENV_UNSET_KEYS = (
    "SP2_CP_READ_PORT",
    "SP2_CP_ROUTING_AUDIT_PORT",
    "SP2_AR_AUTHENTICATE_HOST",
    "SP2_AR_AUTHENTICATE_PORT",
    "SP2_DBR_DISPATCH_HOST",
    "SP2_DBR_DISPATCH_PORT",
    "SP2_DBR_ROUTING_AUDIT_TIMEOUT_SECONDS",
)
_ENV_TOUCHED_KEYS = _ENV_SELECTOR_KEYS + _ENV_URL_KEYS + _ENV_UNSET_KEYS

_SECRET_DIR_ENV = "SNACKPORTAL_TENANT_SECRET_DIR"  # EXISTING shared-convention name (no new env variable)

READINESS_TIMEOUT_SECONDS = 30.0
SHUTDOWN_TIMEOUT_SECONDS = 10.0
HTTP_PROBE_TIMEOUT_SECONDS = 2.0
LOOPBACK_HOST = "127.0.0.1"

# The ONLY raw SQL this operator may execute outside the two reviewed DDL files — read-only
# SELECTs (census-pinned by the boundary guard; every sink argument must statically resolve to
# one of these, or to the validated read-only content-digest template below).
_SQL_CURRENT_DATABASE = "SELECT current_database()"
_SQL_SERVER_VERSION = "SELECT current_setting('server_version_num')"
_SQL_PG_DATABASE_PRESENT = "SELECT 1 FROM pg_database WHERE datname = %s"
_SQL_PG_TENANT_DATABASES = "SELECT datname FROM pg_database WHERE datname LIKE 'sp2_tenant_%' ORDER BY datname"
_SQL_CONTROL_OBJECT = "SELECT to_regclass(%s)"
_SQL_ROUTING_TABLE = "SELECT to_regclass('control_routing_audit')"
_SQL_ROUTING_COUNT = "SELECT count(*) FROM control_routing_audit"
_SQL_ROUTING_ROWS = (
    "SELECT id, event_id::text, event_version, occurred_at, recorded_at, correlation_id, actor_ref, action, outcome,"
    " source_service, source_version, request_ref, trace_ref, tenant_ref, resolved_tenant_ref, public_code, error_class,"
    " association_store_ref, association_version, lane FROM control_routing_audit ORDER BY id ASC"
)
_SQL_ROUTING_COLUMNS = (
    "SELECT column_name, data_type, is_nullable, is_identity, identity_generation, column_default"
    " FROM information_schema.columns WHERE table_schema='public' AND table_name='control_routing_audit'"
    " ORDER BY ordinal_position"
)
_SQL_ROUTING_PK = (
    "SELECT kcu.column_name FROM information_schema.table_constraints tc"
    " JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name"
    " AND tc.table_schema = kcu.table_schema"
    " WHERE tc.table_schema='public' AND tc.table_name='control_routing_audit' AND tc.constraint_type='PRIMARY KEY'"
)
_SQL_ROUTING_UNIQUE = (
    "SELECT kcu.column_name FROM information_schema.table_constraints tc"
    " JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name"
    " AND tc.table_schema = kcu.table_schema"
    " WHERE tc.table_schema='public' AND tc.table_name='control_routing_audit' AND tc.constraint_type='UNIQUE'"
)
_SQL_ROUTING_CHECKS = (
    "SELECT conname FROM pg_constraint WHERE conrelid = 'control_routing_audit'::regclass AND contype = 'c' ORDER BY conname"
)
_SQL_ROUTING_TRIGGERS = (
    "SELECT tgname FROM pg_trigger WHERE tgrelid = 'control_routing_audit'::regclass AND NOT tgisinternal ORDER BY tgname"
)
_SQL_ROUTING_FUNCTION = "SELECT 1 FROM pg_proc WHERE proname = 'control_routing_audit_append_only'"
# Read-only per-table content digest (FULL-content witness, not a bare count). The identifier is
# validated against the imported bootstrap census + shape regex before interpolation.
_SQL_TABLE_DIGEST_TEMPLATE = "SELECT count(*), COALESCE(md5(string_agg(t::text, '|' ORDER BY t::text)), 'empty') FROM {table} t"
_TABLE_NAME_RE = re.compile(r"^[a-z_][a-z0-9_.]*$")

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
_NOT_NULL_COLS = {
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
# The EXACT authored CHECK-constraint set of DDL 010 and the EXACT trigger set of DDL 011
# (OBS-2D-1: exact sets, not membership).
_EXPECTED_CHECKS = [
    "control_routing_audit_action_check",
    "control_routing_audit_event_version_check",
    "control_routing_audit_source_service_check",
]
_EXPECTED_TRIGGERS = ["control_routing_audit_no_mutation", "control_routing_audit_no_truncate"]

# Last in-process run evidence (populated ONLY by cmd_run in this process; read by cmd_status).
_LAST_RUN: Dict[str, Any] = {}
# In-process registry of live (server, thread, base_url) triples — must be empty at status time.
_ACTIVE_SERVERS: List[Tuple[Any, Any, str]] = []


class OpsConfigError(Exception):
    """Non-sensitive operator-configuration/refusal error (never carries a DSN, token, or secret)."""


# ------------------------------------------------------------------------------------------------
# shared low-level helpers (replicated requires_pg idioms; no backend import at module scope)
# ------------------------------------------------------------------------------------------------
def _psycopg() -> Any:
    """The database driver, located at call time (no static import — Driver Containment Standard)."""
    return importlib.import_module("psycopg")


def _crypto_fixture() -> Any:
    """The blessed B5-5 RS256 fixture, loaded lazily by file location (import-inert by contract).

    No JWT/crypto vendor is imported HERE — the fixture is the single containment-allowed module.
    Registered under a private name BEFORE exec (the Smoke C V2 precedent); repeat loads reuse it."""
    name = "dbr_ar_2d_v3_crypto_fixture"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, _CRYPTO_FIXTURE_PATH)
    if spec is None or spec.loader is None:
        raise OpsConfigError("the B5-5 crypto fixture module could not be located — refused")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


def _redacted(dsn: str) -> str:
    """Non-sensitive connection identity: scheme + host + port + database. NEVER userinfo/query (D-14)."""
    parts = urlsplit(dsn)
    host = parts.hostname or ""
    port = f":{parts.port}" if parts.port else ""
    return f"{parts.scheme}://{host}{port}{parts.path}"


def _swap_db(base_dsn: str, dbname: str) -> str:
    """``base_dsn`` with its database path replaced (the requires_pg ``_pg.swap_db`` idiom, replicated)."""
    parts = urlsplit(base_dsn)
    return urlunsplit((parts.scheme, parts.netloc, "/" + dbname, parts.query, parts.fragment))


def _connect(dsn: str) -> Any:
    """Open a short-lived connection; a failure is reported with the REDACTED identity only."""
    psycopg = _psycopg()
    try:
        return psycopg.connect(dsn, connect_timeout=10)
    except Exception:
        raise OpsConfigError(f"cannot connect to {_redacted(dsn)} (fail closed; see the runbook prerequisites)") from None


def _resolve_dsns() -> Tuple[str, str]:
    """Resolve (control_store_dsn, provisioning_admin_dsn) BY REFERENCE through the existing
    ``EnvReferenceSecretStore`` env/file convention (D-14; no literal is ever configured here).
    Fail-closed: an unresolved reference names the REFERENCE, never a value."""
    from control_plane import main as cp_main
    from shared.adapters.providers.env_reference_secret_store import DEFAULT_ALLOWED, EnvReferenceSecretStore
    from shared.secrets import SecretRef

    control_ref = (os.environ.get(cp_main.CONTROL_STORE_DSN_REF_ENV) or cp_main.DEFAULT_CONTROL_STORE_DSN_REF).strip()
    admin_ref = cp_main.PROVISIONING_ADMIN_DSN_REF
    secrets = EnvReferenceSecretStore(allowed=frozenset({*DEFAULT_ALLOWED, control_ref, admin_ref}))
    resolved: List[str] = []
    for ref in (control_ref, admin_ref):
        try:
            resolved.append(secrets.resolve(SecretRef(store_ref=ref, version="1")).material)
        except LookupError:
            raise OpsConfigError(f"unresolved DSN secret reference {ref!r}@1 — set the documented env/file secret") from None
    return resolved[0], resolved[1]


def _validated_secret_dir() -> pathlib.Path:
    """The infrastructure-owned tenant-secret root: absolute AND outside the repository worktree.
    Needed READ-ONLY here (inventory witness + dormant-absence probe); this tool never writes under it."""
    raw = (os.environ.get(_SECRET_DIR_ENV) or "").strip()
    if not raw:
        raise OpsConfigError(f"{_SECRET_DIR_ENV} is not set (required: an absolute directory OUTSIDE the repository)")
    path = pathlib.Path(raw)
    if not path.is_absolute():
        raise OpsConfigError(f"{_SECRET_DIR_ENV} must be an ABSOLUTE path (got a relative one) — refused")
    resolved = path.resolve()
    try:
        resolved.relative_to(_REPO_ROOT)
    except ValueError:
        return resolved
    raise OpsConfigError(f"{_SECRET_DIR_ENV} resolves INSIDE the repository worktree — refused (secrets never enter the repo)")


def _validated_backup_dir(raw: str) -> pathlib.Path:
    """The operator-provided backup directory: absolute AND outside the repository worktree.

    The backup archive must never enter the repository (it is never committed or attached)."""
    candidate = pathlib.Path((raw or "").strip())
    if not str(candidate):
        raise OpsConfigError("--backup-dir is required (an absolute directory OUTSIDE the repository)")
    if not candidate.is_absolute():
        raise OpsConfigError("--backup-dir must be an ABSOLUTE path (got a relative one) — refused")
    resolved = candidate.resolve()
    try:
        resolved.relative_to(_REPO_ROOT)
    except ValueError:
        return resolved
    raise OpsConfigError("--backup-dir resolves INSIDE the repository worktree — refused (backups never enter the repo)")


def _expected_targets() -> None:
    """Cross-check the pinned physical database names against the live naming convention (fail closed)."""
    from control_plane.provisioning import tenant_database_name

    if tenant_database_name(TENANT_ALPHA) != ALPHA_DB or tenant_database_name(TENANT_BETA) != BETA_DB:
        raise OpsConfigError("tenant database naming convention drifted from the pinned expectation — refused")


def _git_blob_sha1(path: pathlib.Path) -> str:
    data = path.read_bytes().replace(b"\r\n", b"\n")  # autocrlf normalization (the git blob is LF)
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def _reviewed_blob_pins() -> Tuple[str, str]:
    """The reviewed (010, 011) LF-blob pins, read from the merged V2 harness SOURCE by AST.

    The V2 harness is the single pin authority (cross-checked in the default suite by the b7c1
    blob-pins guard and the B7C1R2 pin-completeness meta-guard); a mangled or missing pin fails
    closed here BEFORE any connection or SQL."""
    found: Dict[str, str] = {}
    for node in ast.walk(ast.parse(_V2_HARNESS.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in ("_REVIEWED_010_BLOB", "_REVIEWED_011_BLOB"):
                    found[target.id] = node.value.value
    pins = (found.get("_REVIEWED_010_BLOB", ""), found.get("_REVIEWED_011_BLOB", ""))
    if not all(len(pin) == 40 and all(c in "0123456789abcdef" for c in pin) for pin in pins):
        raise OpsConfigError("the V2 harness reviewed blob pins are absent or malformed — STOP (no DDL may be applied)")
    return pins


def _verify_reviewed_blobs() -> None:
    """PRD DBR-AR-2D V3 §6.2: recompute both LF-normalized git-blob SHA-1 pins and STOP before any
    connection or SQL on any mismatch (pure file I/O — do not 'fix' DDL here)."""
    reviewed_010, reviewed_011 = _reviewed_blob_pins()
    b010, b011 = _git_blob_sha1(_DDL_010), _git_blob_sha1(_DDL_011)
    if b010 != reviewed_010:
        raise OpsConfigError(f"010 blob {b010} != reviewed {reviewed_010} — STOP before connect/apply (do not fix DDL here)")
    if b011 != reviewed_011:
        raise OpsConfigError(f"011 blob {b011} != reviewed {reviewed_011} — STOP before connect/apply (do not fix DDL here)")


def _auto_apply_order_from_b5_source() -> Tuple[str, ...]:
    """The B5-4 operator's ``_CONTROL_DDL_ORDER`` literal, read from its SOURCE by AST (the B5-5
    no-new-invocation census stays intact: the module is never imported)."""
    tree = ast.parse(_B5_4_OPS.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_CONTROL_DDL_ORDER" for t in node.targets):
            return tuple(str(v) for v in ast.literal_eval(node.value))
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "_CONTROL_DDL_ORDER"
            and node.value is not None
        ):
            return tuple(str(v) for v in ast.literal_eval(node.value))
    raise OpsConfigError("the B5-4 operator no longer carries _CONTROL_DDL_ORDER — refused")


def _assert_auto_apply_order_unchanged() -> None:
    order = _auto_apply_order_from_b5_source()
    if order != _EXPECTED_AUTO_APPLY_ORDER:
        raise OpsConfigError(f"the automatic standing apply order drifted from 001-009: {order}")
    for name in (_DDL_010.name, _DDL_011.name):
        if name in order:
            raise OpsConfigError(f"{name} is enrolled in the automatic standing apply order — forbidden (manual V3 apply only)")


def _one(cur: Any, sql: str, params: Tuple[Any, ...] = ()) -> Any:
    cur.execute(sql, params)
    row = cur.fetchone()
    return row[0] if row else None


def _table_digest(cur: Any, qualified: str) -> Tuple[int, str]:
    """Read-only full-content digest of one bootstrap table (validated identifier only)."""
    if not _TABLE_NAME_RE.match(qualified):
        raise OpsConfigError(f"invalid table identifier for the content digest: {qualified!r}")
    cur.execute(_SQL_TABLE_DIGEST_TEMPLATE.format(table=qualified))
    count, digest = cur.fetchone()
    return int(count), str(digest)


# ------------------------------------------------------------------------------------------------
# standing-operator delegation (subprocess-only; status-only argv) + the tested-commit witness
# ------------------------------------------------------------------------------------------------
def _b5_4_status_argv() -> List[str]:
    """The EXACT original-B5-4 invocation: status-only argv (no other subcommand is constructible)."""
    return [sys.executable, str(_B5_4_OPS), _STATUS_COMMAND]


def _b5_4a_status_argv() -> List[str]:
    """The EXACT B5-4A invocation: status-only argv (no other subcommand is constructible)."""
    return [sys.executable, str(_B5_4A_OPS), _STATUS_COMMAND]


def _smoke_c_status_argv() -> List[str]:
    """The EXACT Smoke C V2 invocation: status-only argv (no other subcommand is constructible)."""
    return [sys.executable, str(_SMOKE_C_OPS), _STATUS_COMMAND]


def _git_head_argv() -> List[str]:
    """The EXACT read-only tested-commit witness argv (evidence binds to exactly this commit)."""
    return ["git", "rev-parse", "HEAD"]


def _delegate(argv: List[str], timeout: float) -> Tuple[int, str]:
    proc = subprocess.run(argv, cwd=str(_BACKEND_ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def _b5_4_status() -> Tuple[int, str]:
    return _delegate(_b5_4_status_argv(), 600)


def _b5_4a_status() -> Tuple[int, str]:
    return _delegate(_b5_4a_status_argv(), 900)


def _smoke_c_status() -> Tuple[int, str]:
    return _delegate(_smoke_c_status_argv(), 1200)


def _git_head() -> str:
    code, out = _delegate(_git_head_argv(), 60)
    if code != 0:
        raise OpsConfigError("git rev-parse HEAD failed — the evidence record must bind to the tested commit")
    return out.strip()


def _b5_4_status_problem(exit_code: int, output: str) -> Optional[str]:
    """None iff the original B5-4 standing topology reports the complete 6/6 PASS set."""
    if exit_code != 0:
        return f"B5-4 status exited {exit_code}"
    if output.count("PASS:") != _B5_4_PASS_COUNT or "STATUS OK" not in output:
        return "B5-4 status output does not show the complete 6/6 PASS set"
    return None


def _b5_4a_status_problem(exit_code: int, output: str) -> Optional[str]:
    """None iff B5-4A reports its own 12 extension PASS lines over a 6/6 B5-4 delegation."""
    if exit_code != 0:
        return f"B5-4A status exited {exit_code}"
    if "B5-4 STATUS = 6/6 PASS" not in output or "STATUS OK" not in output:
        return "B5-4A status output does not show the 6/6 delegation and STATUS OK"
    if output.count("PASS:") != _B5_4A_PASS_COUNT:
        return f"B5-4A status output does not show the complete {_B5_4A_PASS_COUNT}-check PASS set"
    return None


def _smoke_c_status_problem(exit_code: int, output: str) -> Optional[str]:
    """None iff the Smoke C V2 prerequisites report green with zero residue (STATUS OK)."""
    if exit_code != 0:
        return f"Smoke C V2 status exited {exit_code}"
    if "STATUS OK" not in output or "FAIL" in output:
        return "Smoke C V2 status output is not the green prerequisite set"
    return None


# ------------------------------------------------------------------------------------------------
# environment patching (save/restore discipline — no global leakage after execution)
# ------------------------------------------------------------------------------------------------
class _EnvPatch:
    """Set/unset environment keys with the prior value recorded; ``restore()`` runs in ``finally``.

    Only keys in the pinned ``_ENV_TOUCHED_KEYS`` census may pass through here (fail closed)."""

    def __init__(self) -> None:
        self._saved: Dict[str, Optional[str]] = {}

    def set(self, key: str, value: Optional[str]) -> None:
        if key not in _ENV_TOUCHED_KEYS:
            raise OpsConfigError(f"environment key {key!r} is outside the pinned touch census — refused")
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


def _compose_snapshot_plane(patch: _EnvPatch) -> Any:
    """Compose the control-store-standalone plane (PRD 07D-2a RULE 2) for READ-ONLY state snapshots.

    Forces the three live-side selectors to ``in_memory`` (deny-guarded onboarding — this operator's
    snapshot path is physically incapable of provisioning) and asserts both facts (the B5-4A idiom)."""
    from control_plane import main as cp_main

    patch.set("SP2_CP_CONTROL_STORE", "postgres")
    for name in ("SP2_CP_PROVISIONING_ADAPTER", "SP2_CP_TENANT_SCHEMA_APPLICATOR", "SP2_CP_DISTINCTNESS_LEDGER"):
        patch.set(name, "in_memory")
    cp = cp_main.create_app()
    if type(cp.store).__name__ != "PostgresControlStore":
        raise OpsConfigError("snapshot plane is not backed by the durable ControlStore — refused")
    if type(cp.onboarding).__name__ != "_MixedPostureOnboardingGuard":
        raise OpsConfigError("snapshot plane exposes a live onboarding surface — refused (deny-guard required)")
    return cp


def _close_plane(cp: Any) -> None:
    """Best-effort close of the durable store's cached connection (the 07D finally idiom)."""
    try:
        if getattr(cp.store, "_conn_cache", None) is not None:
            cp.store._conn_cache.close()
    except Exception:
        pass


# ------------------------------------------------------------------------------------------------
# routing-audit schema census + evidence reads (read-only)
# ------------------------------------------------------------------------------------------------
def _routing_schema_census(cur: Any) -> Optional[Dict[str, Any]]:
    """The full catalog census of ``control_routing_audit`` (None while the table is absent)."""
    if _one(cur, _SQL_ROUTING_TABLE) is None:
        return None
    cur.execute(_SQL_ROUTING_COLUMNS)
    cols = cur.fetchall()
    cur.execute(_SQL_ROUTING_PK)
    pk = [r[0] for r in cur.fetchall()]
    cur.execute(_SQL_ROUTING_UNIQUE)
    unique = [r[0] for r in cur.fetchall()]
    cur.execute(_SQL_ROUTING_CHECKS)
    checks = [r[0] for r in cur.fetchall()]
    cur.execute(_SQL_ROUTING_TRIGGERS)
    triggers = [r[0] for r in cur.fetchall()]
    function_present = _one(cur, _SQL_ROUTING_FUNCTION) is not None
    return {
        "columns": [tuple(c) for c in cols],
        "column_names": [c[0] for c in cols],
        "pk": pk,
        "unique": unique,
        "checks": checks,
        "triggers": triggers,
        "function_present": function_present,
    }


def _routing_schema_problem(census: Optional[Dict[str, Any]]) -> Optional[str]:
    """None iff the census is EXACTLY the reviewed DDL 010/011 shape (exact sets — OBS-2D-1)."""
    if census is None:
        return "control_routing_audit is absent"
    if census["column_names"] != _EXPECTED_COLS:
        return f"exact 20-column contract violated: {census['column_names']}"
    meta = {c[0]: c for c in census["columns"]}
    if not (meta["id"][1] == "bigint" and meta["id"][3] == "YES" and meta["id"][4] == "ALWAYS"):
        return "id must be bigint GENERATED ALWAYS AS IDENTITY"
    if meta["event_id"][1] != "uuid":
        return "event_id must be uuid"
    if "now()" not in (meta["recorded_at"][5] or ""):
        return "recorded_at must carry the DB DEFAULT now()"
    for name in _EXPECTED_COLS:
        expected_nullable = "NO" if name in _NOT_NULL_COLS else "YES"
        if meta[name][2] != expected_nullable:
            return f"{name} nullability must be {expected_nullable}"
    if census["pk"] != ["id"]:
        return f"PRIMARY KEY must be (id): {census['pk']}"
    if census["unique"] != ["event_id"]:
        return f"UNIQUE must be (event_id): {census['unique']}"
    if census["checks"] != _EXPECTED_CHECKS:
        return f"exact CHECK-constraint set violated: {census['checks']}"
    if census["triggers"] != _EXPECTED_TRIGGERS:
        return f"exact trigger set violated: {census['triggers']}"
    if not census["function_present"]:
        return "control_routing_audit_append_only() is absent"
    return None


def _routing_rows(cur: Any) -> List[Tuple[Any, ...]]:
    """Every durable routing-audit row in identity order (the total-order authority)."""
    if _one(cur, _SQL_ROUTING_TABLE) is None:
        return []
    cur.execute(_SQL_ROUTING_ROWS)
    return [tuple(r) for r in cur.fetchall()]


def _row_as_dict(row: Tuple[Any, ...]) -> Dict[str, Any]:
    return dict(zip(_EXPECTED_COLS, row, strict=False))


def evaluate_evidence_rows(rows: List[Tuple[Any, ...]]) -> Optional[str]:
    """None iff ``rows`` is EXACTLY the predeclared four-row V3 matrix in emission order.

    Pure (no I/O): the boundary guard feeds mutant row sets and requires a named failure."""
    if len(rows) != len(EXPECTED_EVIDENCE_ROWS):
        return f"{len(rows)} routing-audit row(s), expected exactly {len(EXPECTED_EVIDENCE_ROWS)}"
    ids = [r[0] for r in rows]
    if ids != sorted(ids) or len(set(ids)) != len(ids):
        return f"identity ordering must be strictly increasing: {ids}"
    event_ids = [r[1] for r in rows]
    if len(set(event_ids)) != len(event_ids):
        return "event_id values must be unique"
    for index, (row, expected) in enumerate(zip(rows, EXPECTED_EVIDENCE_ROWS, strict=False)):
        actual = _row_as_dict(row)
        for field, value in expected.items():
            if actual.get(field) != value:
                return f"row {index + 1} field {field!r} is {actual.get(field)!r}, expected {value!r}"
        if actual["trace_ref"] is not None:
            return f"row {index + 1} trace_ref must stay NULL (reserved column, never a wire field)"
        if actual["recorded_at"] is None or getattr(actual["recorded_at"], "tzinfo", None) is None:
            return f"row {index + 1} recorded_at must be DB-assigned and tz-aware"
    correlations = {str(r[5]) for r in rows}
    if S3_CORRELATION in correlations:
        return "the dormant Auth-edge denial (S3) must add ZERO routing-audit rows"
    for correlation in correlations:
        if not correlation.startswith(EVIDENCE_PREFIX):
            return f"foreign correlation id in the evidence set: {correlation!r}"
    return None


def _leak_scan_rows(rows: List[Tuple[Any, ...]], secret_parts: List[str]) -> Optional[str]:
    """None iff no stored cell carries a DSN/password/token-shaped value (D-14; contract §9).

    The marker strings are built dynamically so no secret-shaped literal exists in this source
    (the no-token-literal hygiene rule; the boundary guard scans this file for planted ones)."""
    markers = ("postgresql" + "://", "ey" + "J", "-----" + "BEGIN")
    for row in rows:
        for cell in row:
            text = str(cell)
            for secret in secret_parts:
                if secret and secret in text:
                    return "a stored cell carries the resolved DSN/password (references only)"
            for marker in markers:
                if marker in text:
                    return f"a stored cell carries a secret/token/DSN-shaped value ({marker!r})"
    return None


# ------------------------------------------------------------------------------------------------
# read-only state snapshot (before/after allowed-delta witness — FULL families, not counts)
# ------------------------------------------------------------------------------------------------
def _tenant_row_snapshot(cp: Any, tenant_id: str) -> Optional[Dict[str, Any]]:
    rec = cp.store.get_tenant(tenant_id)
    if rec is None:
        return None
    return {
        "lifecycle_state": rec.lifecycle_state.value,
        "organization_ref": rec.organization_ref,
        "expected_schema_version": rec.expected_schema_version,
        "federation_config_ref": rec.federation_config_ref,
        "assoc_store_ref": rec.database_association_ref.store_ref,
        "assoc_version": rec.database_association_ref.version,
        "cas_version": getattr(rec, "version", None),
    }


def _snapshot_state() -> Dict[str, Any]:
    """The complete read-only witness snapshot: FULL Control-DB row families through the
    ControlStore port, the routing-audit schema census + full rows, the pg_database census,
    full-content tenant-DB table digests, the secret-root inventory, and the touched env view."""
    from control_plane.federation import FederationStore
    from control_plane.recovery import BOOTSTRAP_TABLE_SET

    control_dsn, admin_dsn = _resolve_dsns()
    secret_dir = _validated_secret_dir()

    patch = _EnvPatch()
    try:
        cp = _compose_snapshot_plane(patch)
        try:
            tenant_ids = sorted(str(t) for t in cp.store.list_tenant_ids())
            memberships = sorted((m.principal_ref, m.tenant_id, m.role.value) for m in cp.store.list_memberships())
            audit_rows = [
                (rec.tenant_id, rec.action, rec.actor, rec.from_state, rec.to_state, getattr(rec, "correlation_id", None))
                for rec in cp.store.list_audit()
            ]
            federation_store = FederationStore(cp.store)
            federation = {tid: (federation_store.get(tid) is not None) for tid in (TENANT_ALPHA, TENANT_BETA, TENANT_DORMANT)}
            tenants = {tid: _tenant_row_snapshot(cp, tid) for tid in tenant_ids}
        finally:
            _close_plane(cp)
    finally:
        patch.restore()

    conn = _connect(control_dsn)
    try:
        with conn.cursor() as cur:
            control_identity = str(_one(cur, _SQL_CURRENT_DATABASE))
            routing_census = _routing_schema_census(cur)
            routing_rows = _routing_rows(cur)
    finally:
        conn.close()

    aconn = _connect(admin_dsn)
    try:
        with aconn.cursor() as cur:
            cur.execute(_SQL_PG_TENANT_DATABASES)
            pg_tenant_databases = sorted(str(row[0]) for row in cur.fetchall())
            from control_plane.provisioning import tenant_database_name

            cur.execute(_SQL_PG_DATABASE_PRESENT, (tenant_database_name(TENANT_DORMANT),))
            dormant_database_present = cur.fetchone() is not None
            cur.execute(_SQL_PG_DATABASE_PRESENT, (_V2_PROOF_DB,))
            proof_database_present = cur.fetchone() is not None
    finally:
        aconn.close()

    tenant_db_state: Dict[str, Dict[str, Any]] = {}
    for tid, target in ((TENANT_ALPHA, ALPHA_DB), (TENANT_BETA, BETA_DB)):
        tconn = _connect(_swap_db(admin_dsn, target))
        try:
            with tconn.cursor() as cur:
                current_database = str(_one(cur, _SQL_CURRENT_DATABASE))
                tables = {qualified: _table_digest(cur, qualified) for qualified in sorted(BOOTSTRAP_TABLE_SET)}
                tenant_db_state[tid] = {"current_database": current_database, "tables": tables}
        finally:
            tconn.close()

    secret_root_files = sorted(str(p.relative_to(secret_dir)).replace("\\", "/") for p in secret_dir.rglob("*") if p.is_file())
    env_view = {key: os.environ.get(key) for key in (*_ENV_TOUCHED_KEYS, _SECRET_DIR_ENV)}

    return {
        "control_identity": control_identity,
        "tenant_ids": tenant_ids,
        "tenants": tenants,
        "memberships": memberships,
        "audit_rows": audit_rows,
        "federation": federation,
        "routing_schema_present": routing_census is not None,
        "routing_schema_census": routing_census,
        "routing_rows": routing_rows,
        "pg_tenant_databases": pg_tenant_databases,
        "dormant_database_present": dormant_database_present,
        "proof_database_present": proof_database_present,
        "tenant_db_state": tenant_db_state,
        "secret_root_files": secret_root_files,
        "env": env_view,
    }


# The snapshot keys the standing run may CHANGE (exactly the evidence rows; the schema census is
# established by `apply` BEFORE the pre-run snapshot, so it is identical on both sides).
_RUN_ALLOWED_DELTA_KEYS = ("routing_rows",)


def snapshot_delta_problem(before: Dict[str, Any], after: Dict[str, Any]) -> Optional[str]:
    """None iff before == after outside the exact allowed delta AND the delta is exactly the
    predeclared four evidence rows over an empty table (pure; guard-testable)."""
    for key in sorted(set(before) | set(after)):
        if key in _RUN_ALLOWED_DELTA_KEYS:
            continue
        if before.get(key) != after.get(key):
            return f"standing state drifted outside the allowed delta (key {key!r})"
    if before.get("routing_rows"):
        return "the pre-run snapshot must carry ZERO routing-audit rows (rerun refusal)"
    return evaluate_evidence_rows(list(after.get("routing_rows") or []))


# ------------------------------------------------------------------------------------------------
# dormant-absence probes (no secret, no database, no schema — reference-only by design)
# ------------------------------------------------------------------------------------------------
def _dormant_absence_problem(admin_dsn: str, secret_dir: pathlib.Path) -> Optional[str]:
    from control_plane.adapters.providers.env_tenant_dsn_secret_store import EnvTenantDsnSecretStore
    from control_plane.onboarding import tenant_dsn_ref
    from control_plane.provisioning import tenant_database_name
    from database_router.adapters.providers.env_tenant_secret_store import EnvTenantSecretStore
    from shared.secrets import SecretRef

    ref = SecretRef(store_ref=tenant_dsn_ref(TENANT_DORMANT), version=ASSOCIATION_VERSION)
    problems: List[str] = []
    if (secret_dir / f"{ref.store_ref}@{ref.version}").is_file():
        problems.append("a dormant secret file exists under the tenant-secret root")
    for label, store in (("control-plane", EnvTenantDsnSecretStore()), ("database-router", EnvTenantSecretStore())):
        try:
            store.resolve(ref)
            problems.append(f"the {label} secret adapter resolves the dormant reference")
        except (LookupError, PermissionError):
            pass
    conn = _connect(admin_dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(_SQL_PG_DATABASE_PRESENT, (tenant_database_name(TENANT_DORMANT),))
            if cur.fetchone() is not None:
                problems.append("the would-be dormant database EXISTS (must remain absent; schema implied)")
    finally:
        conn.close()
    return "; ".join(problems) if problems else None


# ------------------------------------------------------------------------------------------------
# stage classification (the exactly-once discipline, durable across processes)
# ------------------------------------------------------------------------------------------------
STAGE_PRE_APPLY = "PRE_APPLY"
STAGE_PARTIAL_SCHEMA = "PARTIAL_SCHEMA"
STAGE_APPLIED_NO_EVIDENCE = "APPLIED_NO_EVIDENCE"
STAGE_COMPLETE = "COMPLETE"
STAGE_ANOMALOUS = "ANOMALOUS"


def classify_stage(census: Optional[Dict[str, Any]], rows: List[Tuple[Any, ...]]) -> str:
    """The V3 arc stage from the live schema census + evidence rows (pure; guard-testable)."""
    if census is None:
        return STAGE_ANOMALOUS if rows else STAGE_PRE_APPLY
    schema_problem = _routing_schema_problem(census)
    if schema_problem is not None:
        return STAGE_PARTIAL_SCHEMA if not rows else STAGE_ANOMALOUS
    if not rows:
        return STAGE_APPLIED_NO_EVIDENCE
    return STAGE_COMPLETE if evaluate_evidence_rows(rows) is None else STAGE_ANOMALOUS


def _live_stage(control_dsn: str) -> Tuple[str, Optional[Dict[str, Any]], List[Tuple[Any, ...]]]:
    conn = _connect(control_dsn)
    try:
        with conn.cursor() as cur:
            census = _routing_schema_census(cur)
            rows = _routing_rows(cur)
    finally:
        conn.close()
    return classify_stage(census, rows), census, rows


# ------------------------------------------------------------------------------------------------
# service hosting (loopback ephemeral; test-owned daemon threads; bounded readiness/shutdown)
# ------------------------------------------------------------------------------------------------
def _edge_endpoint(server: Any, method: str) -> Any:
    """The single registered route endpoint of a served edge app, for ``method``.

    The FastAPI edges close over their composed collaborator in the route function (as the
    stdlib handlers previously did in ``do_POST``), so this is the migrated lookup that
    ``_closure_value`` reads. READ-ONLY: no substitution, no mutation.
    """
    for route in getattr(server.app, "routes", []):
        if method in (getattr(route, "methods", None) or set()):
            return route.endpoint
    raise OpsConfigError(f"cannot locate a {method} route on the served edge — refused")


def _host(server: Any, base_url: str) -> Any:
    """Host ONE single-threaded server on a test-owned daemon thread (the Smoke C precedent;
    production servers stay single-threaded and thread-free — this is harness hosting only)."""
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    _ACTIVE_SERVERS.append((server, thread, base_url))
    return thread


def _stop_all() -> List[str]:
    """Stop every hosted server, join its thread (bounded), release its socket, and prove the port
    is refused afterwards. Returns a list of problems (empty == clean shutdown)."""
    problems: List[str] = []
    while _ACTIVE_SERVERS:
        server, thread, base_url = _ACTIVE_SERVERS.pop()
        try:
            server.shutdown()
        except Exception:
            problems.append(f"server.shutdown() failed for {base_url}")
        try:
            server.server_close()
        except Exception:
            problems.append(f"server.server_close() failed for {base_url}")
        thread.join(SHUTDOWN_TIMEOUT_SECONDS)
        if thread.is_alive():
            problems.append(f"server thread still alive after {SHUTDOWN_TIMEOUT_SECONDS}s for {base_url}")
        if not _port_refused(base_url):
            problems.append(f"listener still accepting connections after close: {base_url}")
    return problems


def _port_refused(base_url: str) -> bool:
    """True iff a fresh TCP connect to the (loopback, ephemeral) address is refused — port released."""
    parts = urlsplit(base_url)
    host, port = parts.hostname or LOOPBACK_HOST, parts.port or 0
    try:
        with socket.create_connection((host, port), timeout=HTTP_PROBE_TIMEOUT_SECONDS):
            return False
    except OSError:
        return True


def _http_status(url: str, *, post: bool = False) -> int:
    """One bounded probe request; returns the HTTP status (mapped from HTTPError for 4xx/5xx)."""
    request = urllib.request.Request(url, data=b"" if post else None, method="POST" if post else "GET")
    try:
        with urllib.request.urlopen(request, timeout=HTTP_PROBE_TIMEOUT_SECONDS) as response:
            return int(response.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)


def _await_ready(label: str, probe: Callable[[], bool]) -> None:
    """Bounded-deadline readiness wait (existing service contracts drive each probe)."""
    deadline = time.monotonic() + READINESS_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        try:
            if probe():
                return
        except Exception:
            pass
        time.sleep(0.05)
    raise OpsConfigError(f"{label} did not become ready within {READINESS_TIMEOUT_SECONDS}s (fail closed)")


def _await_audit_event(audit: Any, count_before: int, correlation_id: str) -> None:
    """Bounded wait for the correlation-bound auth audit event to land before sampling (the
    Smoke C precedent — the observable envelope can return while the single-threaded auth server
    thread is still completing the same request in-process)."""
    deadline = time.monotonic() + READINESS_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if any(event.correlation_id == correlation_id for event in audit.events()[count_before:]):
            return
        time.sleep(0.02)


def _closure_value(func: Any, name: str) -> Any:
    """READ-ONLY recovery of a composed object from a pinned adapter's handler closure (by NAME).

    The spec-pinned fused seams return only ``(server, base_url)``; the pool/audit witnesses need
    read access to the composed router/authenticator. No substitution, no mutation."""
    code = getattr(func, "__code__", None)
    cells = getattr(func, "__closure__", None)
    if code is None or cells is None:
        raise OpsConfigError(f"cannot recover {name!r}: handler carries no closure — refused")
    mapping = dict(zip(code.co_freevars, cells, strict=False))
    if name not in mapping:
        raise OpsConfigError(f"cannot recover {name!r}: not a free variable of the pinned handler — refused")
    return mapping[name].cell_contents


# ------------------------------------------------------------------------------------------------
# S5 local doubles (the accepted pass-through/misbound-connection precedent — V2 harness §8 /
# DBR-AR-2A/2C local-double lineage). Used ONLY for the controlled isolation-anomaly leg: the
# real pool's own binding check would intercept a misbound connection before the router's D-30 L3
# check, and the anomaly leg needs an observable discard. Duck-typed; carries NO real connection.
# ------------------------------------------------------------------------------------------------
class _MisboundConnection:
    """A tenant-bound connection DOUBLE whose binding deliberately diverges from the active tenant."""

    def __init__(self, tenant_id: str, association_version: str) -> None:
        self.tenant_id = tenant_id
        self.association_version = association_version
        self.closed = False

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

    def execute(self, statement: str, params: Tuple[Any, ...] = ()) -> None:
        return None

    def query(self, statement: str, params: Tuple[Any, ...] = ()) -> List[Any]:
        return []


class _PassThroughPool:
    """Hands back the preset misbound connection and records discards (observable D-30 L3 witness)."""

    def __init__(self, conn: _MisboundConnection) -> None:
        self._conn = conn
        self.discarded: List[_MisboundConnection] = []

    def acquire(self, tenant_id: str, association_version: str, open_fn: Any) -> _MisboundConnection:
        return self._conn

    def release(self, conn: _MisboundConnection) -> None:
        return None

    def discard(self, conn: _MisboundConnection) -> None:
        self.discarded.append(conn)
        conn.close()


# ------------------------------------------------------------------------------------------------
# backup (secure full logical backup OUTSIDE the repository; credentials by environment only)
# ------------------------------------------------------------------------------------------------
_BACKUP_BASENAME = "snackportal2_control_local.dbr_ar_2d_v3.pre_apply.dump"


def _pg_dump_argv(out_path: pathlib.Path) -> List[str]:
    """The EXACT backup argv: custom format, no password prompt, NO DSN/credential in argv."""
    return ["pg_dump", "--format=custom", "--no-password", "--file", str(out_path)]


def _pg_restore_list_argv(dump_path: pathlib.Path) -> List[str]:
    """The EXACT readability-witness argv: archive table-of-contents only, NO database touched."""
    return ["pg_restore", "--list", str(dump_path)]


def _backup_child_env(control_dsn: str) -> Dict[str, str]:
    """Child-process environment carrying the connection identity — never argv, never printed."""
    parts = urlsplit(control_dsn)
    env = dict(os.environ)
    env["PGHOST"] = parts.hostname or LOOPBACK_HOST
    env["PGPORT"] = str(parts.port or 5432)
    if parts.username:
        env["PGUSER"] = parts.username
    if parts.password:
        env["PGPASSWORD"] = parts.password
    env["PGDATABASE"] = (parts.path or "/").lstrip("/")
    return env


def _create_backup(control_dsn: str, backup_dir: pathlib.Path) -> Tuple[pathlib.Path, str]:
    """Create the full logical backup and return (path, sha256). Refuses to overwrite (a recovery
    re-run picks a fresh --backup-dir); verifies non-empty and pg_restore-readable."""
    if (urlsplit(control_dsn).path or "/").lstrip("/") != CONTROL_DB_NAME:
        raise OpsConfigError("the control-store DSN does not name the retained standing Control DB — refused")
    backup_dir.mkdir(parents=True, exist_ok=True)
    out_path = backup_dir / _BACKUP_BASENAME
    if out_path.exists():
        raise OpsConfigError("a backup archive already exists at the target path — refused (choose a fresh --backup-dir)")
    proc = subprocess.run(
        _pg_dump_argv(out_path),
        cwd=str(_BACKEND_ROOT),
        env=_backup_child_env(control_dsn),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
    )
    if proc.returncode != 0:
        raise OpsConfigError(f"pg_dump failed (exit {proc.returncode}) — fail closed; no DDL was applied")
    if not out_path.is_file() or out_path.stat().st_size == 0:
        raise OpsConfigError("the backup archive is missing or empty — fail closed; no DDL was applied")
    listing = subprocess.run(
        _pg_restore_list_argv(out_path),
        cwd=str(_BACKEND_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )
    if listing.returncode != 0:
        raise OpsConfigError("pg_restore --list cannot read the backup archive — fail closed; no DDL was applied")
    digest = hashlib.sha256(out_path.read_bytes()).hexdigest()
    return out_path, digest


# ------------------------------------------------------------------------------------------------
# plan
# ------------------------------------------------------------------------------------------------
def cmd_plan(_args: argparse.Namespace) -> int:
    control_dsn, admin_dsn = _resolve_dsns()
    secret_dir = _validated_secret_dir()
    print("DBR-AR-2D V3 standing witnesses — PLAN (read-only; no backup, no DDL, no server, no mutation)")
    failures = 0
    print(f"  tested commit     : {_git_head()}")
    for label, runner, evaluator in (
        ("B5-4 standing topology 6/6", _b5_4_status, _b5_4_status_problem),
        ("B5-4A standing auth fixture 12/12", _b5_4a_status, _b5_4a_status_problem),
        ("Smoke C V2 prerequisites + zero residue", _smoke_c_status, _smoke_c_status_problem),
    ):
        code, out = runner()
        problem = evaluator(code, out)
        if problem is None:
            print(f"  PASS: {label}")
        else:
            failures += 1
            print(f"  FAIL: {label} — {problem}")
    try:
        _verify_reviewed_blobs()
        reviewed_010, reviewed_011 = _reviewed_blob_pins()
        print(f"  PASS: reviewed DDL blob pins (010={reviewed_010[:12]}…, 011={reviewed_011[:12]}…; authority: the merged V2 harness)")
    except OpsConfigError as exc:
        failures += 1
        print(f"  FAIL: {exc}")
    try:
        _assert_auto_apply_order_unchanged()
        print("  PASS: automatic standing apply order remains exactly 001-009 (010/011 NOT enrolled)")
    except OpsConfigError as exc:
        failures += 1
        print(f"  FAIL: {exc}")
    _expected_targets()
    print(f"  control DB target : {_redacted(control_dsn)} (the ONLY DDL target of this arc)")
    print(f"  admin cluster     : {_redacted(admin_dsn)} (read-only identity probes; NEVER a DDL target)")
    conn = _connect(control_dsn)
    try:
        with conn.cursor() as cur:
            identity = str(_one(cur, _SQL_CURRENT_DATABASE))
            server_num = int(_one(cur, _SQL_SERVER_VERSION))
            control_census_missing = [t for t in ("control_audit", "control_tenants") if _one(cur, _SQL_CONTROL_OBJECT, (t,)) is None]
    finally:
        conn.close()
    if identity != CONTROL_DB_NAME or control_census_missing:
        failures += 1
        print(f"  FAIL: standing Control DB identity probe (current_database={identity!r}; missing={control_census_missing})")
    else:
        print(f"  PASS: standing Control DB identity confirmed by probe (current_database + 001-009 census; PG {server_num})")
    for tid, target in ((TENANT_ALPHA, ALPHA_DB), (TENANT_BETA, BETA_DB)):
        tconn = _connect(_swap_db(admin_dsn, target))
        try:
            with tconn.cursor() as cur:
                current = str(_one(cur, _SQL_CURRENT_DATABASE))
        finally:
            tconn.close()
        if current != target:
            failures += 1
            print(f"  FAIL: {tid} identity probe returned {current!r}, expected {target!r}")
        else:
            print(f"  PASS: {tid} -> physical database {target} (identity probe)")
    dormant_problem = _dormant_absence_problem(admin_dsn, secret_dir)
    if dormant_problem is None:
        print("  PASS: dormant has membership only — no secret, no database, no schema (reference-only)")
    else:
        failures += 1
        print(f"  FAIL: dormant absence — {dormant_problem}")
    stage, _census, rows = _live_stage(control_dsn)
    before = _snapshot_state()
    print(
        f"  before-state      : captured ({len(before['tenant_ids'])} tenants; {len(before['memberships'])} memberships;"
        f" {len(before['audit_rows'])} control_audit rows; {len(before['pg_tenant_databases'])} tenant DBs;"
        f" {len(before['secret_root_files'])} secret files)"
    )
    print(f"  stage             : {stage}")
    print("  intended schema   : exact DDL 010 table (20 columns) + DDL 011 append-only function/triggers — Control DB ONLY")
    print(f"  intended rows     : exactly {len(EXPECTED_EVIDENCE_ROWS)} durable evidence rows —")
    for expected in EXPECTED_EVIDENCE_ROWS:
        print(f"    {expected['correlation_id']:<28} {expected['action']:<17} {expected['outcome']}")
    print(f"  auth-edge witness : {S3_CORRELATION} adds ZERO routing-audit rows (denied before route())")
    print("  tenant mutation   : NONE — no tenant database receives DDL or rows; no dormant secret/DB/schema is created")
    print("  enrollment        : NONE — 010/011 stay OUT of the automatic standing apply order (manual V3 apply only)")
    if stage == STAGE_ANOMALOUS:
        failures += 1
        print(f"  FAIL: prior/partial V3 evidence is anomalous — refused ({evaluate_evidence_rows(rows) or 'schema drift'})")
    elif stage == STAGE_COMPLETE:
        print("  note              : the standing witness is COMPLETE — apply and run are both REFUSED (exactly-once)")
    if failures:
        print(f"PLAN FAILED ({failures} problem(s))")
        return 1
    print("PLAN OK")
    return 0


# ------------------------------------------------------------------------------------------------
# apply
# ------------------------------------------------------------------------------------------------
def cmd_apply(args: argparse.Namespace) -> int:
    backup_dir = _validated_backup_dir(getattr(args, "backup_dir", "") or "")
    control_dsn, admin_dsn = _resolve_dsns()
    secret_dir = _validated_secret_dir()
    print("DBR-AR-2D V3 standing witnesses — APPLY (Dan-authorized; backup-first; 010 then 011; Control DB ONLY)")
    for label, runner, evaluator in (
        ("B5-4 standing topology 6/6", _b5_4_status, _b5_4_status_problem),
        ("B5-4A standing auth fixture 12/12", _b5_4a_status, _b5_4a_status_problem),
    ):
        code, out = runner()
        problem = evaluator(code, out)
        if problem is not None:
            print(f"  FAIL: {label} — {problem}")
            print("APPLY REFUSED — the standing prerequisites are a hard gate (zero mutation)")
            return 1
        print(f"  PASS: {label}")
    dormant_problem = _dormant_absence_problem(admin_dsn, secret_dir)
    if dormant_problem is not None:
        print(f"  FAIL: dormant absence — {dormant_problem}")
        print("APPLY REFUSED (zero mutation)")
        return 1
    stage, _census, rows = _live_stage(control_dsn)
    if rows:
        print(f"  FAIL: {len(rows)} routing-audit row(s) already exist — the V3 evidence is exactly-once")
        print("APPLY REFUSED (zero mutation)")
        return 1
    if stage == STAGE_APPLIED_NO_EVIDENCE:
        print("  FAIL: the complete schema already exists — apply is exactly-once; the next governed step is `run`")
        print("APPLY REFUSED (zero mutation)")
        return 1
    if stage not in (STAGE_PRE_APPLY, STAGE_PARTIAL_SCHEMA):
        print(f"  FAIL: stage {stage} is not applyable")
        print("APPLY REFUSED (zero mutation)")
        return 1
    if stage == STAGE_PARTIAL_SCHEMA:
        print("  note: PARTIAL schema detected — the reviewed idempotent re-run completes it (runbook §2.3 recovery)")

    # Backup BEFORE any SQL (PRD §6.2.2): full logical backup, outside the repository.
    out_path, digest = _create_backup(control_dsn, backup_dir)
    print(f"  backup            : {out_path.name} under {out_path.parent} (outside repo; never committed)")
    print(f"  backup sha256     : {digest}")
    print("  backup readability: pg_restore --list OK (restore tooling witness; no database touched)")

    # Blob pins verified BEFORE any connection is used for DDL (§6.2.4 STOP rule).
    _verify_reviewed_blobs()
    print("  PASS: reviewed DDL blob pins verified BEFORE apply")

    conn = _connect(control_dsn)
    try:
        with conn.cursor() as cur:
            identity = str(_one(cur, _SQL_CURRENT_DATABASE))
            if identity != CONTROL_DB_NAME:
                raise OpsConfigError(f"connected database is {identity!r}, not the standing Control DB — STOP (no DDL applied)")
            if _one(cur, _SQL_CONTROL_OBJECT, ("control_audit",)) is None:
                raise OpsConfigError("the 001-009 census probe failed (control_audit absent) — STOP (no DDL applied)")
        with conn.cursor() as cur:
            cur.execute(_DDL_010.read_text(encoding="utf-8"))
        conn.commit()
        print("  applied           : 010_routing_audit.sql (exactly once)")
        with conn.cursor() as cur:
            cur.execute(_DDL_011.read_text(encoding="utf-8"))
        conn.commit()
        print("  applied           : 011_routing_audit_append_only.sql (exactly once)")
        with conn.cursor() as cur:
            census = _routing_schema_census(cur)
    except OpsConfigError:
        raise
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        raise OpsConfigError(
            f"DDL apply failed ({type(exc).__name__}) — STOP; capture redacted evidence; escalate (runbook §2.3)"
        ) from None
    finally:
        conn.close()
    problem = _routing_schema_problem(census)
    if problem is not None:
        print(f"  FAIL: post-apply schema verification — {problem}")
        print("APPLY FAILED (fail closed; escalate per the runbook — no destructive recovery exists)")
        return 1
    print("  PASS: exact schema objects verified (20 columns, identity PK, unique event_id, exact CHECK set, exact trigger set)")
    print("APPLY OK — the standing Control DB carries the reviewed routing-audit schema; next governed step: `run` (exactly once)")
    return 0


# ------------------------------------------------------------------------------------------------
# run
# ------------------------------------------------------------------------------------------------
def cmd_run(_args: argparse.Namespace) -> int:
    control_dsn, admin_dsn = _resolve_dsns()
    secret_dir = _validated_secret_dir()
    print("DBR-AR-2D V3 standing witnesses — RUN (the standing witness; EXACTLY ONCE)")

    for label, runner, evaluator in (
        ("B5-4 standing topology 6/6", _b5_4_status, _b5_4_status_problem),
        ("B5-4A standing auth fixture 12/12", _b5_4a_status, _b5_4a_status_problem),
    ):
        code, out = runner()
        problem = evaluator(code, out)
        if problem is not None:
            print(f"  FAIL: {label} — {problem}")
            print("RUN REFUSED — the standing prerequisites are a hard gate (nothing was started)")
            return 1
        print(f"  PASS: {label}")
    _verify_reviewed_blobs()
    stage, _census, rows = _live_stage(control_dsn)
    if stage != STAGE_APPLIED_NO_EVIDENCE:
        if rows:
            print(f"  FAIL: {len(rows)} routing-audit row(s) already exist — a second evidence-generating run is REFUSED")
        else:
            print(f"  FAIL: stage {stage} — `run` requires the applied schema with ZERO evidence rows")
        print("RUN REFUSED (nothing was started; zero mutation)")
        return 1
    dormant_problem = _dormant_absence_problem(admin_dsn, secret_dir)
    if dormant_problem is not None:
        print(f"  FAIL: dormant absence — {dormant_problem}")
        print("RUN REFUSED (nothing was started)")
        return 1

    commit = _git_head()
    before = _snapshot_state()
    print(f"  tested commit     : {commit}")
    print(
        f"  pre-run snapshot  : captured ({len(before['tenant_ids'])} tenants; {len(before['audit_rows'])} control_audit rows;"
        f" {len(before['routing_rows'])} routing-audit rows)"
    )

    evidence: Dict[str, Any] = {"commit": commit, "scenarios": {}, "services": {}, "shutdown_problems": []}
    env_before = {key: os.environ.get(key) for key in _ENV_TOUCHED_KEYS}
    patch = _EnvPatch()
    secret_parts: List[str] = [control_dsn, admin_dsn]
    password = urlsplit(control_dsn).password
    if password:
        secret_parts.append(password)
    try:
        _expected_targets()
        from api_gateway.main import build_authenticator_from_env, build_gateway, build_router_dispatch_from_env
        from api_gateway.models import DatabaseDomain, DispatchCategory, DispatchDecision, InboundRequest
        from auth_router.main import build_authenticate_server_from_env
        from control_plane.main import build_read_server_from_env, build_routing_audit_server_from_env
        from database_router.adapters.providers.env_tenant_secret_store import EnvTenantSecretStore
        from database_router.adapters.providers.http_routing_audit import HttpRoutingAudit, RoutingAuditTransportError
        from database_router.adapters.providers.http_routing_read import HttpRoutingRead
        from database_router.adapters.providers.psycopg_connection import PsycopgConnectionFactory
        from database_router.cache import RoutingViewCache
        from database_router.main import BoundedRoutingAuditPolicy, build_dispatch_server_from_env
        from database_router.models import RoutingDenied
        from database_router.resolver import RoutingResolver
        from database_router.router import DatabaseRouter
        from shared.context import RequestContext

        for key in _ENV_UNSET_KEYS:
            patch.set(key, None)  # ephemeral loopback defaults — never a fixed port, foreign host, or foreign timeout

        # --- Control Plane read edge (all-postgres posture over the standing Control DB) --------
        for key in _ENV_SELECTOR_KEYS:
            patch.set(key, "postgres")
        patch.set("SP2_CP_READ_HOST", LOOPBACK_HOST)
        composed_read = build_read_server_from_env()
        if composed_read is None:
            raise OpsConfigError("read-edge composition unexpectedly inactive — refused")
        read_server, read_url = composed_read
        _host(read_server, read_url)
        _await_ready("control-plane read edge", lambda: _http_status(f"{read_url}/internal/routing/tenants/{TENANT_ALPHA}") == 200)
        evidence["services"]["control_plane_read_edge"] = read_url
        print(f"  service ready     : control-plane read edge on {read_url}")

        # --- Control Plane DURABLE routing-audit ingest edge (the standing Control DB store) ----
        patch.set("SP2_CP_ROUTING_AUDIT_HOST", LOOPBACK_HOST)
        composed_ingest = build_routing_audit_server_from_env()
        if composed_ingest is None:
            raise OpsConfigError("routing-audit ingest composition unexpectedly inactive — refused")
        ingest_server, ingest_url = composed_ingest
        _host(ingest_server, ingest_url)
        _await_ready("routing-audit ingest edge", lambda: _http_status(f"{ingest_url}/internal/routing-audit/probe", post=True) == 404)
        evidence["services"]["routing_audit_ingest_edge"] = ingest_url
        print(f"  service ready     : durable routing-audit ingest edge on {ingest_url}")

        # --- fresh RS256 material (fixture-only; never printed) ---------------------------------
        fixture = _crypto_fixture()
        keypair = fixture.generate_rs256_keypair()
        tokens = {
            "alpha": fixture.mint_rs256_token(keypair, issuer=ISSUER, audience=AUDIENCE, subject=PRINCIPAL, tenant=TENANT_ALPHA),
            "beta": fixture.mint_rs256_token(keypair, issuer=ISSUER, audience=AUDIENCE, subject=PRINCIPAL, tenant=TENANT_BETA),
            "dormant": fixture.mint_rs256_token(keypair, issuer=ISSUER, audience=AUDIENCE, subject=PRINCIPAL, tenant=TENANT_DORMANT),
        }

        # --- Auth Router authenticate server -----------------------------------------------------
        patch.set("SP2_AR_CONTROL_PLANE_READ_BASE_URL", read_url)
        patch.set("SP2_AR_ISSUERS", fixture.issuer_env_json(keypair, issuer=ISSUER, audience=AUDIENCE))
        composed_auth = build_authenticate_server_from_env()
        if composed_auth is None:
            raise OpsConfigError("authenticate-server composition unexpectedly inactive — refused")
        auth_server, auth_url = composed_auth
        _host(auth_server, auth_url)
        _await_ready("auth-router authenticate edge", lambda: _http_status(f"{auth_url}/internal/auth/probe", post=True) == 404)
        authenticator = _closure_value(_edge_endpoint(auth_server, "POST"), "authenticator")
        if type(authenticator).__name__ != "Authenticator":
            raise OpsConfigError("recovered auth object is not the composed production Authenticator — refused")
        auth_audit = authenticator._audit  # the composed in-memory auth audit sink (read-only witness)
        evidence["services"]["auth_router_authenticate"] = auth_url
        print(f"  service ready     : auth-router authenticate edge on {auth_url}")

        # --- Database Router dispatch server with the REAL DURABLE audit chain composed ---------
        patch.set("SP2_DBR_ROUTING_READ_BASE_URL", read_url)
        patch.set("SP2_DBR_ROUTING_AUDIT_BASE_URL", ingest_url)
        composed_dispatch = build_dispatch_server_from_env()
        if composed_dispatch is None:
            raise OpsConfigError("dispatch-server composition unexpectedly inactive — refused")
        dispatch_server, dispatch_url = composed_dispatch
        _host(dispatch_server, dispatch_url)
        _await_ready("database-router dispatch edge", lambda: _http_status(f"{dispatch_url}/internal/dispatch/probe", post=True) == 404)
        router = _closure_value(_edge_endpoint(dispatch_server, "POST"), "router")
        if type(router).__name__ != "DatabaseRouter":
            raise OpsConfigError("recovered dispatch object is not the composed production DatabaseRouter — refused")
        if type(router._audit).__name__ != "BoundedRoutingAuditPolicy":
            raise OpsConfigError("the composed router does not hold the DURABLE routing-audit policy — refused (proof 8 requires it)")
        if type(router._factory).__name__ != "PsycopgConnectionFactory":
            raise OpsConfigError("the composed router does not hold the REAL psycopg connection factory — refused")
        if type(router._secrets).__name__ != "EnvTenantSecretStore":
            raise OpsConfigError("the composed router does not hold the REAL tenant secret store — refused")
        pool = router._pool  # the interactive-lane pool (read-only census + identity readback)
        evidence["services"]["database_router_dispatch"] = dispatch_url
        print(f"  service ready     : database-router dispatch edge on {dispatch_url} (durable audit composed)")

        # --- API Gateway (in-process; the real composed pipeline) --------------------------------
        patch.set("SP2_GW_AUTH_ROUTER_BASE_URL", auth_url)
        patch.set("SP2_GW_DB_ROUTER_BASE_URL", dispatch_url)
        gateway_authenticator = build_authenticator_from_env()
        gateway_router = build_router_dispatch_from_env()
        if gateway_authenticator is None or gateway_router is None:
            raise OpsConfigError("gateway transport seams unexpectedly inactive — refused")
        gateway = build_gateway(authenticator=gateway_authenticator, router=gateway_router)
        print("  service ready     : api-gateway pipeline composed in-process (Gateway.handle)")

        def rows_now() -> List[Tuple[Any, ...]]:
            conn = _connect(control_dsn)
            try:
                with conn.cursor() as cur:
                    return _routing_rows(cur)
            finally:
                conn.close()

        def pool_view() -> Dict[Tuple[str, str], Tuple[int, int]]:
            return {key: pool.counts(*key) for key in pool.pool_keys()}

        def routed_database_identity(tenant_id: str) -> Tuple[str, bool]:
            """``current_database()`` readback ON the exact pooled connection the route bound."""
            opened = {"new": False}

            def _refuse() -> Any:
                opened["new"] = True
                raise OpsConfigError("a NEW connection would have been opened — the route-bound connection was not reused")

            conn = pool.acquire(tenant_id, ASSOCIATION_VERSION, _refuse)
            try:
                result = conn.query("SELECT current_database() AS db")
                return str(result[0]["db"]), (not opened["new"])
            finally:
                pool.release(conn)

        # --- S1 / S2 — alpha and beta successes through the FULL composed path ------------------
        for label, correlation, token_key, tenant, own_db, other_tenant in (
            ("S1-alpha", S1_CORRELATION, "alpha", TENANT_ALPHA, ALPHA_DB, TENANT_BETA),
            ("S2-beta", S2_CORRELATION, "beta", TENANT_BETA, BETA_DB, TENANT_ALPHA),
        ):
            other_key = (other_tenant, ASSOCIATION_VERSION)
            pool_before = pool_view()
            response = gateway.handle(
                InboundRequest(
                    method="GET",
                    path="/tenant/deals",
                    headers={"X-Tenant-Id": tenant, "x-correlation-id": correlation},
                    authorization="Bearer " + tokens[token_key],
                )
            )
            pool_after = pool_view()
            observed = (response.status, response.public_code, response.dispatched)
            if observed != (200, "ok", True):
                raise OpsConfigError(f"{label}: gateway envelope is {observed!r}, expected (200, 'ok', True)")
            if response.category is None or response.category.value != "TENANT_OPERATION":
                raise OpsConfigError(f"{label}: success category is {response.category!r}")
            database, reused = routed_database_identity(tenant)
            if database != own_db:
                raise OpsConfigError(f"{label}: routed database is {database!r}, expected {own_db!r} — one request/one tenant/one DB")
            if not reused:
                raise OpsConfigError(f"{label}: the identity readback did not reuse the route-bound connection")
            other_delta = abs(sum(pool_after.get(other_key) or (0, 0)) - sum(pool_before.get(other_key) or (0, 0)))
            if other_delta != 0:
                raise OpsConfigError(f"{label}: the OTHER tenant's pool changed during a success row (non-touch violated)")
            scenario_rows = [r for r in rows_now() if str(r[5]) == correlation]
            if len(scenario_rows) != 1:
                raise OpsConfigError(f"{label}: {len(scenario_rows)} durable row(s) for {correlation}, expected exactly 1")
            if scenario_rows[0][7] != "Route":
                raise OpsConfigError(f"{label}: the durable row action is {scenario_rows[0][7]!r}, expected 'Route'")
            evidence["scenarios"][label] = {
                "correlation_id": correlation,
                "envelope": observed,
                "database": database,
                "readback_reused": reused,
                "other_pool_delta": other_delta,
                "durable_rows": 1,
            }
            print(f"  scenario {label:<9}: 200 ok dispatched=true db={database} durable Route row committed before hand-back")

        # --- S3 — dormant Auth-edge denial: bounded 403, internal tenant_not_ready, ZERO rows ---
        rows_before_s3 = rows_now()
        pool_before = pool_view()
        auth_events_before = len(auth_audit.events())
        response = gateway.handle(
            InboundRequest(
                method="GET",
                path="/tenant/deals",
                headers={"X-Tenant-Id": TENANT_DORMANT, "x-correlation-id": S3_CORRELATION},
                authorization="Bearer " + tokens["dormant"],
            )
        )
        _await_audit_event(auth_audit, auth_events_before, S3_CORRELATION)
        observed = (response.status, response.public_code, response.dispatched)
        if observed != (403, "forbidden", False):
            raise OpsConfigError(f"S3: gateway envelope is {observed!r}, expected (403, 'forbidden', False)")
        denial_codes = [
            event.outcome.split("denied:", 1)[1]
            for event in auth_audit.events()[auth_events_before:]
            if event.correlation_id == S3_CORRELATION and event.outcome.startswith("denied:")
        ]
        if denial_codes != ["tenant_not_ready"]:
            raise OpsConfigError(f"S3: internal denial code(s) {denial_codes!r}, expected exactly ['tenant_not_ready']")
        if rows_now() != rows_before_s3:
            raise OpsConfigError("S3: the dormant Auth-edge denial added routing-audit row(s) — must be ZERO")
        if pool_view() != pool_before:
            raise OpsConfigError("S3: the dormant Auth-edge denial changed tenant pool state — zero dispatch violated")
        dormant_problem = _dormant_absence_problem(admin_dsn, secret_dir)
        if dormant_problem is not None:
            raise OpsConfigError(f"S3: dormant absence violated — {dormant_problem}")
        evidence["scenarios"]["S3-dormant-auth"] = {
            "correlation_id": S3_CORRELATION,
            "envelope": observed,
            "internal_code": "tenant_not_ready",
            "durable_rows": 0,
        }
        print("  scenario S3       : 403 forbidden internal=tenant_not_ready — ZERO routing-audit rows; dormant untouched")

        # --- S4 — dormant Database-Router-edge denial over the REAL dispatch wire ---------------
        pool_before = pool_view()
        dispatch_client = gateway_router  # the REAL HttpRouterDispatch bound to the dispatch edge
        s4_context = RequestContext(
            correlation_id=S4_CORRELATION,
            request_id="req-" + S4_CORRELATION,
            active_tenant_id=TENANT_DORMANT,
            principal_ref=OPS_ACTOR,
            role="TENANT_AGENT",
        )
        s4_decision = DispatchDecision(
            category=DispatchCategory.TENANT_OPERATION, domain=DatabaseDomain.TENANT, target_tenant_id=TENANT_DORMANT
        )
        outcome = dispatch_client.dispatch(s4_context, s4_decision)
        if (outcome.status, outcome.public_code, outcome.dispatched) != (503, "not_ready", False):
            raise OpsConfigError(
                f"S4: dispatch outcome is {(outcome.status, outcome.public_code, outcome.dispatched)!r}, expected (503, 'not_ready', False)"
            )
        s4_rows = [r for r in rows_now() if str(r[5]) == S4_CORRELATION]
        if len(s4_rows) != 1 or s4_rows[0][7] != "RouteDenied" or s4_rows[0][15] != "not_ready":
            raise OpsConfigError(f"S4: expected exactly one durable RouteDenied(not_ready) row, got {s4_rows!r}")
        if s4_rows[0][11] != "req-" + S4_CORRELATION:
            raise OpsConfigError("S4: the durable row must carry the request reference")
        if pool_view() != pool_before:
            raise OpsConfigError("S4: the dormant router-edge denial changed tenant pool state — zero dispatch violated")
        dormant_problem = _dormant_absence_problem(admin_dsn, secret_dir)
        if dormant_problem is not None:
            raise OpsConfigError(f"S4: dormant absence violated — {dormant_problem}")
        evidence["scenarios"]["S4-dormant-router"] = {
            "correlation_id": S4_CORRELATION,
            "outcome": (outcome.status, outcome.public_code, outcome.dispatched),
            "durable_rows": 1,
        }
        print("  scenario S4       : 503 not_ready over the real dispatch wire — exactly one durable RouteDenied row; no dormant artifact")

        # --- S5 — controlled standing isolation anomaly (pass-through misbound connection) ------
        misbound = _MisboundConnection(TENANT_BETA, ASSOCIATION_VERSION)
        anomaly_pool = _PassThroughPool(misbound)
        anomaly_router = DatabaseRouter(
            resolver=RoutingResolver(HttpRoutingRead(read_url), RoutingViewCache(ttl_seconds=15.0), supported_schema_versions=("1",)),
            pool=anomaly_pool,  # type: ignore[arg-type]
            secret_store=EnvTenantSecretStore(),
            connection_factory=PsycopgConnectionFactory(),
            audit=BoundedRoutingAuditPolicy(HttpRoutingAudit(ingest_url, timeout=2.0), transport_error=RoutingAuditTransportError),
        )
        s5_context = RequestContext(
            correlation_id=S5_CORRELATION,
            request_id="req-" + S5_CORRELATION,
            active_tenant_id=TENANT_ALPHA,
            principal_ref=OPS_ACTOR,
            role="TENANT_AGENT",
        )
        try:
            anomaly_router.route(s5_context)
            raise OpsConfigError("S5: a tenant-binding fault must be denied — no route success is permitted")
        except RoutingDenied as denied:
            if denied.public_code != "routing_isolation_fault" or denied.http_status != 503:
                raise OpsConfigError(
                    f"S5: denial is ({denied.http_status}, {denied.public_code!r}), expected (503, 'routing_isolation_fault')"
                ) from None
        if anomaly_pool.discarded != [misbound] or not misbound.closed:
            raise OpsConfigError("S5: the misbound connection must be discarded and closed (D-30 L3)")
        s5_rows = [r for r in rows_now() if str(r[5]) == S5_CORRELATION]
        if len(s5_rows) != 1 or s5_rows[0][7] != "IsolationAnomaly":
            raise OpsConfigError(f"S5: expected exactly one durable IsolationAnomaly row, got {s5_rows!r}")
        if (s5_rows[0][13], s5_rows[0][14]) != (TENANT_ALPHA, TENANT_BETA):
            raise OpsConfigError("S5: the anomaly row must record both the authenticated and the actually-bound tenant references")
        evidence["scenarios"]["S5-anomaly"] = {
            "correlation_id": S5_CORRELATION,
            "denial": ("routing_isolation_fault", 503),
            "discarded": True,
            "durable_rows": 1,
        }
        print("  scenario S5       : routing_isolation_fault — misbound connection discarded; exactly one durable IsolationAnomaly row")

        # --- the exact final evidence set + reference-only content scan -------------------------
        final_rows = rows_now()
        problem = evaluate_evidence_rows(final_rows)
        if problem is not None:
            raise OpsConfigError(f"final evidence set: {problem}")
        leak = _leak_scan_rows(final_rows, secret_parts)
        if leak is not None:
            raise OpsConfigError(f"final evidence set: {leak}")
        evidence["final_rows"] = len(final_rows)
        print(
            f"  evidence rows     : exactly {len(final_rows)} (Route alpha, Route beta, RouteDenied dormant,"
            " IsolationAnomaly); references only"
        )

        # --- drain the tenant pools (close every pooled real connection) -------------------------
        for tenant_id, _version in list(pool.pool_keys()):
            pool.invalidate_version(tenant_id, "0")  # keep_version "0" matches nothing -> drains/closes all
        evidence["pools_drained"] = pool.pool_keys() == []
    except OpsConfigError as exc:
        print(f"  FAIL: {exc}")
        evidence["run_error"] = str(exc)
    except Exception as exc:
        print(f"  FAIL: unexpected error during the witness: {type(exc).__name__} (sanitized; fail closed)")
        evidence["run_error"] = type(exc).__name__
    finally:
        problems = _stop_all()
        evidence["shutdown_problems"] = problems
        evidence["ports_released"] = not problems
        patch.restore()
        evidence["env_restored"] = {key: os.environ.get(key) for key in _ENV_TOUCHED_KEYS} == env_before

    after = _snapshot_state()
    evidence["delta_problem"] = snapshot_delta_problem(before, after)
    evidence["before_equals_after_outside_delta"] = evidence["delta_problem"] is None

    failures = 0
    checks: List[Tuple[str, bool, str]] = [
        ("no scenario failure", "run_error" not in evidence, str(evidence.get("run_error"))),
        (
            "exact allowed delta (schema pre-established; exactly the four evidence rows)",
            evidence["before_equals_after_outside_delta"],
            str(evidence.get("delta_problem")),
        ),
        (
            "all services stopped; threads joined; ports released",
            bool(evidence.get("ports_released")),
            "; ".join(evidence.get("shutdown_problems") or []),
        ),
        ("tenant connection pools drained", bool(evidence.get("pools_drained")), "pool keys remain"),
        ("environment restored", bool(evidence.get("env_restored")), "touched keys differ from their prior values"),
    ]
    for name, ok, detail in checks:
        if ok:
            print(f"  PASS: {name}")
        else:
            failures += 1
            print(f"  FAIL: {name} — {detail}")

    for label, runner, evaluator in (
        ("B5-4 standing topology 6/6 preserved", _b5_4_status, _b5_4_status_problem),
        ("B5-4A standing auth fixture 12/12 preserved", _b5_4a_status, _b5_4a_status_problem),
    ):
        code, out = runner()
        problem = evaluator(code, out)
        if problem is None:
            print(f"  PASS: {label}")
        else:
            failures += 1
            print(f"  FAIL: {label} — {problem}")

    _LAST_RUN.clear()
    _LAST_RUN.update(evidence)
    status_rc = cmd_status(_args)
    if failures or status_rc:
        print(f"RUN FAILED ({failures} obligation(s) not holding; status exit {status_rc})")
        return 1
    print("RUN OK — the DBR-AR-2 contract §16 standing witnesses are delivered on the retained standing topology;")
    print("         DBR-AR-2 — CLOSED (Dan-authorized governance decision, 2026-07-16); this closure closes zero B5")
    print("         activation blockers, the blocker census remains nine with 8 of 9 OPEN, and production remains")
    print("         NOT READY / DO-NOT-ACTIVATE.")
    return 0


# ------------------------------------------------------------------------------------------------
# status
# ------------------------------------------------------------------------------------------------
def cmd_status(_args: argparse.Namespace) -> int:
    control_dsn, admin_dsn = _resolve_dsns()
    secret_dir = _validated_secret_dir()
    print("DBR-AR-2D V3 standing witnesses — STATUS (read-only; fail-closed)")
    failures = 0

    for label, runner, evaluator in (
        ("B5-4 standing topology 6/6", _b5_4_status, _b5_4_status_problem),
        ("B5-4A standing auth fixture 12/12", _b5_4a_status, _b5_4a_status_problem),
    ):
        code, out = runner()
        problem = evaluator(code, out)
        if problem is None:
            print(f"  PASS: {label}")
        else:
            failures += 1
            print(f"  FAIL: {label} — {problem}")

    conn = _connect(control_dsn)
    try:
        with conn.cursor() as cur:
            identity = str(_one(cur, _SQL_CURRENT_DATABASE))
            census = _routing_schema_census(cur)
            rows = _routing_rows(cur)
    finally:
        conn.close()

    def schema_problem() -> Optional[str]:
        if identity != CONTROL_DB_NAME:
            return f"connected database is {identity!r}, not the standing Control DB"
        return _routing_schema_problem(census)

    def evidence_problem() -> Optional[str]:
        return evaluate_evidence_rows(rows)

    def leak_problem() -> Optional[str]:
        secret_parts = [control_dsn, admin_dsn]
        password = urlsplit(control_dsn).password
        if password:
            secret_parts.append(password)
        return _leak_scan_rows(rows, secret_parts)

    def apply_order_problem() -> Optional[str]:
        try:
            _assert_auto_apply_order_unchanged()
        except OpsConfigError as exc:
            return str(exc)
        return None

    def dormant_problem() -> Optional[str]:
        patch = _EnvPatch()
        try:
            cp = _compose_snapshot_plane(patch)
            try:
                row = _tenant_row_snapshot(cp, TENANT_DORMANT)
            finally:
                _close_plane(cp)
        finally:
            patch.restore()
        if row is None:
            return "dormant registry row absent"
        if row["lifecycle_state"] != "Registered":
            return f"dormant lifecycle is {row['lifecycle_state']!r}, expected 'Registered'"
        return _dormant_absence_problem(admin_dsn, secret_dir)

    def alpha_beta_problem() -> Optional[str]:
        patch = _EnvPatch()
        try:
            cp = _compose_snapshot_plane(patch)
            try:
                snapshots = {tid: _tenant_row_snapshot(cp, tid) for tid in (TENANT_ALPHA, TENANT_BETA)}
            finally:
                _close_plane(cp)
        finally:
            patch.restore()
        for tid, target in ((TENANT_ALPHA, ALPHA_DB), (TENANT_BETA, BETA_DB)):
            row = snapshots[tid]
            if row is None or row["lifecycle_state"] != "Ready":
                return f"{tid} is not Ready"
            tconn = _connect(_swap_db(admin_dsn, target))
            try:
                with tconn.cursor() as cur:
                    current = str(_one(cur, _SQL_CURRENT_DATABASE))
            finally:
                tconn.close()
            if current != target:
                return f"{tid} identity probe returned {current!r}, expected {target!r}"
        return None

    def residue_problem() -> Optional[str]:
        snap = _snapshot_state()
        polluted = [
            entry
            for entry in snap["audit_rows"]
            if any(str(part).startswith(EVIDENCE_PREFIX) or str(part) == OPS_ACTOR for part in entry if part is not None)
        ]
        if polluted:
            return f"{len(polluted)} control_audit row(s) carry V3 identifiers (evidence lives ONLY in control_routing_audit)"
        for tid in snap["tenant_ids"]:
            if tid.startswith(EVIDENCE_PREFIX):
                return f"a V3-prefixed tenant row exists: {tid}"
        for principal, tenant, _role in snap["memberships"]:
            if principal.startswith(EVIDENCE_PREFIX) or tenant.startswith(EVIDENCE_PREFIX):
                return "a V3-prefixed membership row exists"
        if snap["proof_database_present"]:
            return "the V2 disposable proof database exists on the standing cluster"
        return None

    def listener_problem() -> Optional[str]:
        if _ACTIVE_SERVERS:
            return f"{len(_ACTIVE_SERVERS)} in-process server(s) still registered as live"
        return None

    def posture_problem() -> Optional[str]:
        contract = _REPO_ROOT / "docs" / "runtime" / "dbr_ar_2_durable_routing_audit_contract.md"
        norm = " ".join(contract.read_text(encoding="utf-8").lower().replace("*", "").replace("`", "").split())
        if "production runtime activation remains not ready / do-not-activate" not in norm:
            return "the contract doc no longer records the fail-closed activation posture"
        closure_sentence = (
            "dbr-ar-2 — closed (dan-authorized governance decision, 2026-07-16); this closure closes zero b5"
            " activation blockers, the blocker census remains nine with 8 of 9 open, and production remains"
            " not ready / do-not-activate."
        )
        if closure_sentence not in norm:
            return "the contract doc no longer records the exact canonical DBR-AR-2 closure sentence"
        if "dbr-ar-2e — production-activation evidence consolidated; outcome a is remain not ready / do-not-activate." not in norm:
            return "the contract doc no longer records the consolidated 2E status"
        return None

    checks: List[Tuple[str, Callable[[], Optional[str]]]] = [
        ("exact routing-audit schema on the standing Control DB", schema_problem),
        ("exactly the four predeclared evidence rows in emission order (no fifth row)", evidence_problem),
        ("evidence rows are references-only (no DSN/password/token-shaped cell)", leak_problem),
        ("automatic standing apply order remains exactly 001-009 (010/011 not enrolled)", apply_order_problem),
        ("dormant preserved: Registered membership-only; no secret, no database, no schema", dormant_problem),
        ("alpha/beta preserved: Ready on their own distinct physical databases", alpha_beta_problem),
        ("zero V3 residue outside control_routing_audit; no disposable proof database", residue_problem),
        ("no leftover in-process service/listener", listener_problem),
        ("locked activation posture intact (NOT READY; DBR-AR-2 closure record intact; 2E evidence consolidated)", posture_problem),
    ]
    for name, fn in checks:
        try:
            problem = fn()
        except OpsConfigError as exc:
            problem = str(exc)
        except Exception as exc:  # fail the CHECK, sanitized (driver messages may carry connection detail)
            problem = f"{type(exc).__name__} (fail closed)"
        if problem is None:
            print(f"  PASS: {name}")
        else:
            failures += 1
            print(f"  FAIL: {name} — {problem}")

    if _LAST_RUN:
        if _LAST_RUN.get("run_error") is None and _LAST_RUN.get("before_equals_after_outside_delta") is True:
            print(f"  PASS: last in-process run evidence complete (commit {_LAST_RUN.get('commit')})")
        else:
            failures += 1
            print("  FAIL: last in-process run evidence is INCOMPLETE — the witness may not be claimed from it")
    else:
        print("  INFO: no in-process run evidence in this process; the checks above verify the DURABLE standing")
        print("        evidence directly — healthy prerequisites alone NEVER constitute the witness (fail closed)")

    if failures:
        print(f"STATUS FAILED ({failures} check(s) not holding)")
        return 1
    print(
        "STATUS OK — standing witnesses delivered and preserved; the DBR-AR-2 closure record is intact"
        " (Dan-authorized governance decision, 2026-07-16); production activation remains blocked"
    )
    return 0


# ------------------------------------------------------------------------------------------------
# entrypoint
# ------------------------------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dbr_ar_2d_standing_witnesses",
        description="DBR-AR-2D V3 retained standing-topology witnesses (plan/apply/run/status; apply+run Dan-authorized, exactly once).",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("plan", help="read-only intent + prerequisite delegation + before-state (no backup, no DDL, no server)")
    apply_parser = sub.add_parser(
        "apply", help="Dan-authorized exactly-once: backup outside repo, then DDL 010 then 011 to the Control DB only"
    )
    apply_parser.add_argument(
        "--backup-dir", dest="backup_dir", required=True, help="absolute directory OUTSIDE the repository for the backup archive"
    )
    sub.add_parser("run", help="Dan-authorized exactly-once standing witness (S1-S5; refuses when any evidence row exists)")
    sub.add_parser("status", help="read-only fail-closed verification of the delivered standing witnesses")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    handlers: dict = {"plan": cmd_plan, "apply": cmd_apply, "run": cmd_run, "status": cmd_status}
    try:
        return int(handlers[args.command](args))
    except OpsConfigError as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
