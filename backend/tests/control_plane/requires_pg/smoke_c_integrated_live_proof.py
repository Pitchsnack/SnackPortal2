"""Smoke C V2 integrated live proof — operator harness (standalone-only; PRD Smoke C V2).

An OPERATOR TOOL, not application runtime code and not a test: it executes the SMOKE-C-SPEC-01
integrated live local topology proof over the PERMANENT B5-4/B5-4A standing state — read-only,
zero-mutation, leaving every standing row, audit row, secret file, and physical database unchanged.

    InboundRequest -> Gateway.handle (IN-PROCESS, the real composed Gateway)
      -> real Auth Router over the auth wire (build_authenticate_server_from_env; PyJwtSignatureVerifier
         + HttpControlPlaneRead against the standing Control DB read edge)
      -> real Database Router over the dispatch wire (build_dispatch_server_from_env; HttpRoutingRead
         + EnvTenantSecretStore + PsycopgConnectionFactory)
      -> exactly one standing physical tenant database
         (sp2_tenant_b5_standing_alpha | sp2_tenant_b5_standing_beta)

Commands (stdlib argparse; work happens ONLY after an explicit subcommand — import performs no I/O):

    plan      read-only: B5-4 6/6 + B5-4A 12/12 delegation (status-only subprocess), the exact nine
              binding SMOKE-C-SPEC-01 scenarios, the sanitized service topology intent (redacted
              identities; loopback/ephemeral ports), redacted secret REFERENCES only, and the
              statement that no mutation is planned. No server starts, no request runs.
    run       the integrated proof: revalidates B5-4/B5-4A, captures the complete read-only
              before-state, composes and hosts the real services on loopback ephemeral ports
              (test-owned daemon threads, one single-threaded server each — the SMOKE-C-SPEC-01 §3
              in-suite branch), executes every binding scenario serially, captures gateway
              observables AND the binding internal denial codes, proves alpha/beta database identity
              through the integrated path, proves zero tenant dispatch on every denial, stops every
              server and thread in ``finally``, drains all pools, proves port release, restores every
              touched environment key, captures the after-state, and requires before == after.
    status    read-only, fail-closed: B5-4 PASS, B5-4A PASS, spec + RS256 fixture found and pinned,
              standing alpha/beta/dormant prerequisites, zero residue, no leftover in-process
              service/listener, and the last in-process proof evidence when ``run`` executed in this
              process. Status NEVER claims the proof passed merely because prerequisites are healthy.

There is deliberately NO mutating subcommand of ANY kind — nothing is applied, removed, or reset by
this tool: the proof writes nothing, so nothing ever needs cleaning up afterwards. The ONLY subprocess
seams are the two status-only standing-operator delegations and one read-only ``git rev-parse HEAD``
(evidence binds to the tested commit); the B5-4/B5-4A operator modules are NEVER imported.

DRIVER/VENDOR CONTAINMENT. No static database-driver import (psycopg is located via importlib at
call time) and no JWT/crypto vendor import: every token is minted by the existing blessed B5-5
fixture (``tests/api_gateway/crypto_fixture.py``), loaded lazily by file location. Module import is
inert (no I/O, no env mutation, no socket, no thread). Backend/provider imports are lazy, inside
commands. Runbook: ``infrastructure/runbooks/smoke_c_integrated_live_proof.md`` (invoked from
``backend/`` as ``python tests/control_plane/requires_pg/smoke_c_integrated_live_proof.py <command>``).

SECRET HYGIENE (D-14). DSNs are resolved in-memory by reference and NEVER printed, logged, or
returned; every emitted identity is redacted to scheme+host+port+database; tokens and keys are never
printed, logged, or persisted (the private key exists in process memory only, per the fixture).

NO OVERCLAIM. A green ``run`` proves the LOCAL integrated request path at DATABASE granularity on
the standing fixture, exactly as SMOKE-C-SPEC-01 bounds it — nothing about production readiness,
deployment, supervision, TLS, ingress, durability, scale, or cluster-level distinctness. Routing
audit evidence is IN-MEMORY in this proof (DBR-AR-2 remains open). B5-BLK-4 remains OPEN; the
Physical Multi-Database MVP remains mandatory and is NOT completed by this harness.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import os
import pathlib
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
_STATUS_COMMAND = "status"  # the ONLY standing-operator subcommand this operator may ever invoke
_B5_4_PASS_COUNT = 6
_B5_4A_PASS_COUNT = 12

# The blessed B5-5 RS256 fixture (loaded lazily by file location; vendors stay contained there).
_CRYPTO_FIXTURE_PATH = _BACKEND_ROOT / "tests" / "api_gateway" / "crypto_fixture.py"
_SPEC_PATH = _REPO_ROOT / "docs" / "acceptance" / "SMOKE-C-SPEC-01.md"

SPEC_ID = "SMOKE-C-SPEC-01 v1.0"

# The permanent standing identifiers (PRD B5-4 / B5-4A). Targets are cross-checked at run time
# against the live naming convention and the command REFUSES on drift.
TENANT_ALPHA = "b5_standing_alpha"
TENANT_BETA = "b5_standing_beta"
TENANT_DORMANT = "b5_standing_dormant"
PRINCIPAL = "b5_standing_member"
ALPHA_DB = "sp2_tenant_b5_standing_alpha"
BETA_DB = "sp2_tenant_b5_standing_beta"
ASSOCIATION_VERSION = "1"

# Deterministic non-standing identifiers used ONLY inside signed claims on the wire (never rows).
UNKNOWN_TENANT_ID = "b5_smokec_v2_unknown"
UNAVAILABLE_PROBE_TENANT_ID = "b5_smokec_v2_unavail_probe"
UNKNOWN_KID = "b5-smokec-v2-unknown-kid"

# The test-process issuer contract carried by SP2_AR_ISSUERS (public JWK only; fixture-built).
ISSUER = "https://b5-smoke-c-v2.issuer.local"
UNKNOWN_ISSUER = "https://b5-smoke-c-v2-unknown.issuer.local"
AUDIENCE = "snackportal2-internal"
CORRELATION_PREFIX = "smokec-v2"

READINESS_TIMEOUT_SECONDS = 30.0
SHUTDOWN_TIMEOUT_SECONDS = 10.0
HTTP_PROBE_TIMEOUT_SECONDS = 2.0
LOOPBACK_HOST = "127.0.0.1"

_SECRET_DIR_ENV = "SNACKPORTAL_TENANT_SECRET_DIR"  # EXISTING shared-convention name (no new env variable)
_SMOKE_PREFIX = "smoke" + "_c_"  # built dynamically so no temporary-row identifier literal exists here

# The EXACT nine binding SMOKE-C-SPEC-01 scenarios (two happy-path rows + the seven failure-mode
# rows of the spec §5 table). ``internal_code`` is the binding auth-boundary code where the wire
# envelope collapses (spec §5: granular reasons never leak past the status bucket); ``database`` is
# the required routed physical database identity for success rows; ``token`` selects the mint leg.
SCENARIOS: Tuple[Dict[str, Any], ...] = (
    {
        "label": "alpha-success",
        "token": "alpha",
        "carrier": TENANT_ALPHA,
        "status": 200,
        "public_code": "ok",
        "dispatched": True,
        "internal_code": None,
        "database": ALPHA_DB,
        "read_edge_down": False,
    },
    {
        "label": "beta-success",
        "token": "beta",
        "carrier": TENANT_BETA,
        "status": 200,
        "public_code": "ok",
        "dispatched": True,
        "internal_code": None,
        "database": BETA_DB,
        "read_edge_down": False,
    },
    {
        "label": "dormant-not-ready",
        "token": "dormant",
        "carrier": TENANT_DORMANT,
        "status": 403,
        "public_code": "forbidden",
        "dispatched": False,
        "internal_code": "tenant_not_ready",
        "database": None,
        "read_edge_down": False,
    },
    {
        "label": "unknown-tenant",
        "token": "unknown",
        "carrier": UNKNOWN_TENANT_ID,
        "status": 403,
        "public_code": "forbidden",
        "dispatched": False,
        "internal_code": "tenant_access_denied",
        "database": None,
        "read_edge_down": False,
    },
    {
        "label": "carrier-mismatch",
        "token": "alpha",
        "carrier": TENANT_BETA,
        "status": 403,
        "public_code": "carrier_mismatch",
        "dispatched": False,
        "internal_code": "carrier_mismatch",
        "database": None,
        "read_edge_down": False,
    },
    {
        "label": "bad-signature",
        "token": "wrong-key",
        "carrier": TENANT_ALPHA,
        "status": 401,
        "public_code": "unauthenticated",
        "dispatched": False,
        "internal_code": "bad_signature",
        "database": None,
        "read_edge_down": False,
    },
    {
        "label": "unknown-kid",
        "token": "unknown-kid",
        "carrier": TENANT_ALPHA,
        "status": 401,
        "public_code": "unauthenticated",
        "dispatched": False,
        "internal_code": "unknown_kid",
        "database": None,
        "read_edge_down": False,
    },
    {
        "label": "unknown-issuer",
        "token": "unknown-issuer",
        "carrier": TENANT_ALPHA,
        "status": 401,
        "public_code": "unauthenticated",
        "dispatched": False,
        "internal_code": "unknown_issuer",
        "database": None,
        "read_edge_down": False,
    },
    {
        "label": "control-plane-unavailable",
        "token": "unavailable-probe",
        "carrier": UNAVAILABLE_PROBE_TENANT_ID,
        "status": 503,
        "public_code": "unavailable",
        "dispatched": False,
        "internal_code": "control_plane_unavailable",
        "database": None,
        "read_edge_down": True,
    },
)

# Environment keys this operator may SET during run (existing names only; every prior value is
# restored in ``finally``). Host values are pinned to the loopback host; NO ``*_PORT`` key is ever
# set (unset -> the seams' ephemeral default), and the five bind knobs below are explicitly UNSET
# for the duration of the run so ambient values can never select a fixed port or foreign host.
_ENV_SELECTOR_KEYS = (
    "SP2_CP_CONTROL_STORE",
    "SP2_CP_PROVISIONING_ADAPTER",
    "SP2_CP_TENANT_SCHEMA_APPLICATOR",
    "SP2_CP_DISTINCTNESS_LEDGER",
)
_ENV_URL_KEYS = (
    "SP2_CP_READ_HOST",
    "SP2_AR_CONTROL_PLANE_READ_BASE_URL",
    "SP2_AR_ISSUERS",
    "SP2_DBR_ROUTING_READ_BASE_URL",
    "SP2_GW_AUTH_ROUTER_BASE_URL",
    "SP2_GW_DB_ROUTER_BASE_URL",
)
_ENV_UNSET_KEYS = (
    "SP2_CP_READ_PORT",
    "SP2_AR_AUTHENTICATE_HOST",
    "SP2_AR_AUTHENTICATE_PORT",
    "SP2_DBR_DISPATCH_HOST",
    "SP2_DBR_DISPATCH_PORT",
)
_ENV_TOUCHED_KEYS = _ENV_SELECTOR_KEYS + _ENV_URL_KEYS + _ENV_UNSET_KEYS

# The ONLY raw SQL this operator may execute — read-only SELECTs (census-pinned by the boundary
# guard; every sink argument must statically resolve to one of these).
_SQL_PG_TENANT_DATABASES = "SELECT datname FROM pg_database WHERE datname LIKE 'sp2_tenant_%' ORDER BY datname"
_SQL_PG_DATABASE_PRESENT = "SELECT 1 FROM pg_database WHERE datname = %s"
_SQL_CURRENT_DATABASE = "SELECT current_database()"
_SQL_AGENTS_TOTAL = "SELECT count(*) FROM agents"
_SQL_SYSTEM_PRIMARY = "SELECT count(*) FROM agents WHERE agent_kind = 'system_primary'"
_SQL_SCHEMA_VERSION = "SELECT version FROM schema_version ORDER BY applied_at DESC LIMIT 1"
_SQL_ROUTED_IDENTITY = "SELECT current_database() AS db"

# Last in-process proof evidence (populated ONLY by cmd_run in this process; read by cmd_status).
_LAST_PROOF: Dict[str, Any] = {}
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
    The module is registered under a private name BEFORE exec (the stdlib dataclass machinery
    resolves ``cls.__module__`` through ``sys.modules``); repeat loads reuse the registration."""
    name = "smoke_c_v2_crypto_fixture"
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
    """Open a short-lived read-only-use connection; failures report the REDACTED identity only."""
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


def _expected_targets() -> None:
    """Cross-check the pinned physical database names against the live naming convention (fail closed)."""
    from control_plane.provisioning import tenant_database_name

    if tenant_database_name(TENANT_ALPHA) != ALPHA_DB or tenant_database_name(TENANT_BETA) != BETA_DB:
        raise OpsConfigError("tenant database naming convention drifted from the pinned expectation — refused")


# ------------------------------------------------------------------------------------------------
# standing-operator delegation (subprocess-only; status-only argv) + the tested-commit witness
# ------------------------------------------------------------------------------------------------
def _b5_4_status_argv() -> List[str]:
    """The EXACT original-B5-4 invocation: status-only argv (no other subcommand is constructible)."""
    return [sys.executable, str(_B5_4_OPS), _STATUS_COMMAND]


def _b5_4a_status_argv() -> List[str]:
    """The EXACT B5-4A invocation: status-only argv (no other subcommand is constructible)."""
    return [sys.executable, str(_B5_4A_OPS), _STATUS_COMMAND]


def _git_head_argv() -> List[str]:
    """The EXACT read-only tested-commit witness argv (evidence binds to exactly this commit)."""
    return ["git", "rev-parse", "HEAD"]


def _b5_4_status() -> Tuple[int, str]:
    proc = subprocess.run(
        _b5_4_status_argv(), cwd=str(_BACKEND_ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def _b5_4a_status() -> Tuple[int, str]:
    proc = subprocess.run(
        _b5_4a_status_argv(), cwd=str(_BACKEND_ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def _git_head() -> str:
    proc = subprocess.run(
        _git_head_argv(), cwd=str(_BACKEND_ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60
    )
    if proc.returncode != 0:
        raise OpsConfigError("git rev-parse HEAD failed — the evidence record must bind to the tested commit")
    return (proc.stdout or "").strip()


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

    Forces the three live-side selectors to ``in_memory`` (deny-guarded onboarding — this operator is
    physically incapable of provisioning) and asserts both facts, the B5-4A defense-in-depth idiom."""
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
# read-only state snapshot (before/after zero-mutation witness)
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
    """The complete read-only zero-mutation witness snapshot (Control DB via the ControlStore port
    + the pg_database census + tenant-DB invariants + secret-root inventory + touched env keys)."""
    from control_plane.federation import FederationStore

    _control_dsn, admin_dsn = _resolve_dsns()
    del _control_dsn  # the snapshot plane resolves its own store DSN by reference
    secret_dir = _validated_secret_dir()

    patch = _EnvPatch()
    try:
        cp = _compose_snapshot_plane(patch)
        try:
            tenant_ids = sorted(str(t) for t in cp.store.list_tenant_ids())
            memberships = sorted((m.principal_ref, m.tenant_id, m.role.value) for m in cp.store.list_memberships())
            audit_rows = cp.store.list_audit()
            dormant_register_audit = [
                {"actor": rec.actor, "from_state": rec.from_state, "to_state": rec.to_state}
                for rec in audit_rows
                if rec.tenant_id == TENANT_DORMANT and rec.action == "RegisterTenant"
            ]
            residue = (
                sum(1 for t in tenant_ids if t.startswith(_SMOKE_PREFIX))
                + sum(1 for m in memberships if m[0].startswith(_SMOKE_PREFIX) or m[1].startswith(_SMOKE_PREFIX))
                + sum(1 for rec in audit_rows if (rec.tenant_id or "").startswith(_SMOKE_PREFIX) or rec.actor.startswith(_SMOKE_PREFIX))
            )
            federation_store = FederationStore(cp.store)
            federation = {tid: (federation_store.get(tid) is not None) for tid in (TENANT_ALPHA, TENANT_BETA, TENANT_DORMANT)}
            tenants = {tid: _tenant_row_snapshot(cp, tid) for tid in tenant_ids}
        finally:
            _close_plane(cp)
    finally:
        patch.restore()

    conn = _connect(admin_dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(_SQL_PG_TENANT_DATABASES)
            pg_tenant_databases = sorted(str(row[0]) for row in cur.fetchall())
            from control_plane.provisioning import tenant_database_name

            cur.execute(_SQL_PG_DATABASE_PRESENT, (tenant_database_name(TENANT_DORMANT),))
            dormant_database_present = cur.fetchone() is not None
    finally:
        conn.close()

    tenant_db_invariants: Dict[str, Dict[str, Any]] = {}
    for tid, target in ((TENANT_ALPHA, ALPHA_DB), (TENANT_BETA, BETA_DB)):
        tconn = _connect(_swap_db(admin_dsn, target))
        try:
            with tconn.cursor() as cur:
                cur.execute(_SQL_CURRENT_DATABASE)
                current_database = str(cur.fetchone()[0])
                cur.execute(_SQL_AGENTS_TOTAL)
                agents_total = cur.fetchone()[0]
                cur.execute(_SQL_SYSTEM_PRIMARY)
                system_primary = cur.fetchone()[0]
                cur.execute(_SQL_SCHEMA_VERSION)
                schema_version = str(cur.fetchone()[0])
                tenant_db_invariants[tid] = {
                    "current_database": current_database,
                    "agents_total": agents_total,
                    "system_primary": system_primary,
                    "schema_version": schema_version,
                }
        finally:
            tconn.close()

    secret_root_files = sorted(str(p.relative_to(secret_dir)).replace("\\", "/") for p in secret_dir.rglob("*") if p.is_file())
    env_view = {key: os.environ.get(key) for key in (*_ENV_TOUCHED_KEYS, _SECRET_DIR_ENV)}

    return {
        "tenant_ids": tenant_ids,
        "tenants": tenants,
        "memberships": memberships,
        "audit_total": len(audit_rows),
        "dormant_register_audit": dormant_register_audit,
        "residue": residue,
        "federation": federation,
        "pg_tenant_databases": pg_tenant_databases,
        "dormant_database_present": dormant_database_present,
        "tenant_db_invariants": tenant_db_invariants,
        "secret_root_files": secret_root_files,
        "env": env_view,
    }


# ------------------------------------------------------------------------------------------------
# service hosting (loopback ephemeral; test-owned daemon threads; bounded readiness/shutdown)
# ------------------------------------------------------------------------------------------------
def _host(server: Any, base_url: str) -> Any:
    """Host ONE single-threaded server on a test-owned daemon thread (the Smoke A/B precedent;
    SMOKE-C-SPEC-01 §3 in-suite branch — no threading inside any server)."""
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
    """Bounded wait for the correlation-bound auth audit event to land before sampling.

    The gateway transport clients collapse fail-closed on a bounded timeout (IC-010 §L), so the
    OBSERVABLE envelope can return while the single-threaded server thread is still completing the
    same request in-process (seen on the deliberately-stopped-read-edge row). The audit event is the
    binding internal-code witness — sampling it needs the same bounded-deadline discipline as
    readiness. On timeout the sample proceeds and the evaluator fails closed on the missing code."""
    deadline = time.monotonic() + READINESS_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if any(event.correlation_id == correlation_id for event in audit.events()[count_before:]):
            return
        time.sleep(0.02)


def _closure_value(func: Any, name: str) -> Any:
    """READ-ONLY recovery of a composed object from a pinned adapter's handler closure (by NAME).

    The spec-pinned fused seams return only ``(server, base_url)``; the census/identity/audit
    witnesses need read access to the composed router/authenticator. No substitution, no mutation."""
    code = getattr(func, "__code__", None)
    cells = getattr(func, "__closure__", None)
    if code is None or cells is None:
        raise OpsConfigError(f"cannot recover {name!r}: handler carries no closure — refused")
    mapping = dict(zip(code.co_freevars, cells))
    if name not in mapping:
        raise OpsConfigError(f"cannot recover {name!r}: not a free variable of the pinned handler — refused")
    return mapping[name].cell_contents


# ------------------------------------------------------------------------------------------------
# pure evaluation predicates (exercised by the default-suite boundary guard with mutant evidence)
# ------------------------------------------------------------------------------------------------
def evaluate_scenario(expected: Dict[str, Any], observed: Optional[Dict[str, Any]]) -> Optional[str]:
    """None iff one observed scenario satisfies its binding SMOKE-C-SPEC-01 row exactly."""
    if observed is None or not observed.get("executed"):
        return "scenario was not executed (a skipped scenario can never count as passed)"
    envelope = (observed.get("status"), observed.get("public_code"), observed.get("dispatched"))
    expected_envelope = (expected["status"], expected["public_code"], expected["dispatched"])
    if envelope != expected_envelope:
        return f"gateway envelope is {envelope!r}, expected {expected_envelope!r}"
    if expected["internal_code"] is None:
        if observed.get("category") != "TENANT_OPERATION":
            return f"success category is {observed.get('category')!r}, expected 'TENANT_OPERATION'"
        if observed.get("database") != expected["database"]:
            return f"routed database is {observed.get('database')!r}, expected {expected['database']!r}"
        if observed.get("route_events") != 1:
            return f"{observed.get('route_events')!r} router Route event(s), expected exactly 1"
        if not observed.get("readback_reused"):
            return "the identity readback did not reuse the route-bound connection"
        if observed.get("other_pool_delta") != 0:
            return "the OTHER tenant's pool changed during a success row (non-touch violated)"
    else:
        if observed.get("internal_code") != expected["internal_code"]:
            return f"internal denial code is {observed.get('internal_code')!r}, expected {expected['internal_code']!r}"
        if observed.get("route_events") != 0:
            return "a denied request produced router audit event(s) — dispatch was reached"
        if observed.get("pool_delta") != 0:
            return "a denied request changed tenant pool state — a connection/pool acquisition happened"
        if observed.get("new_pool_keys") != 0:
            return "a denied request created a tenant pool key — a tenant bind was attempted"
    return None


def evaluate_run(evidence: Dict[str, Any]) -> List[Tuple[str, Optional[str]]]:
    """The named run-level obligations over a complete evidence record (pure; guard-testable)."""

    def scenarios_problem() -> Optional[str]:
        problems = []
        for expected in SCENARIOS:
            problem = evaluate_scenario(expected, evidence.get("scenarios", {}).get(expected["label"]))
            if problem is not None:
                problems.append(f"{expected['label']}: {problem}")
        extra = set(evidence.get("scenarios", {})) - {s["label"] for s in SCENARIOS}
        if extra:
            problems.append(f"unexpected extra scenario evidence: {sorted(extra)}")
        return "; ".join(problems) if problems else None

    def distinctness_problem() -> Optional[str]:
        alpha = (evidence.get("scenarios", {}).get("alpha-success") or {}).get("database")
        beta = (evidence.get("scenarios", {}).get("beta-success") or {}).get("database")
        if alpha != ALPHA_DB or beta != BETA_DB:
            return f"routed identities ({alpha!r}, {beta!r}) are not the two standing targets"
        if alpha == beta:
            return "both success rows routed to ONE database — distinctness violated"
        return None

    def mutation_problem() -> Optional[str]:
        if evidence.get("before_equals_after") is not True:
            diff = evidence.get("state_diff") or []
            return f"before-state != after-state (differing keys: {sorted(diff)})"
        return None

    def shutdown_problem() -> Optional[str]:
        problems = list(evidence.get("shutdown_problems") or [])
        if evidence.get("ports_released") is not True:
            problems.append("ports were not proven released")
        if evidence.get("pools_drained") is not True:
            problems.append("tenant connection pools were not drained/closed")
        return "; ".join(problems) if problems else None

    def env_problem() -> Optional[str]:
        if evidence.get("env_restored") is not True:
            return "touched environment keys were not restored to their prior values"
        return None

    return [
        ("every binding SMOKE-C-SPEC-01 scenario executed and exact", scenarios_problem()),
        ("alpha/beta database identity distinct and correct", distinctness_problem()),
        ("zero mutation (before-state equals after-state)", mutation_problem()),
        ("all services stopped; threads joined; ports released; pools drained", shutdown_problem()),
        ("environment restored", env_problem()),
    ]


def proof_complete(evidence: Dict[str, Any]) -> bool:
    """True iff the in-process evidence is complete and every run-level obligation holds.

    Status uses this — prerequisites alone can NEVER produce a proof claim (fail closed)."""
    if not evidence:
        return False
    return all(problem is None for _name, problem in evaluate_run(evidence))


# ------------------------------------------------------------------------------------------------
# plan
# ------------------------------------------------------------------------------------------------
def cmd_plan(_args: argparse.Namespace) -> int:
    control_dsn, admin_dsn = _resolve_dsns()
    secret_dir = _validated_secret_dir()
    print("Smoke C V2 integrated live proof — PLAN (read-only; no server, no request, no mutation)")
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
    if not _SPEC_PATH.is_file():
        failures += 1
        print(f"  FAIL: specification missing: {_SPEC_PATH}")
    print(f"  spec              : {SPEC_ID} ({_SPEC_PATH.name})")
    print(f"  control read edge : over {_redacted(control_dsn)} (all-postgres posture; loopback ephemeral)")
    print(f"  admin cluster     : {_redacted(admin_dsn)} (read-only pg_database census + tenant-DB invariants)")
    print(f"  tenant secrets    : references tenant/<id>/dsn@{ASSOCIATION_VERSION} under {secret_dir} (values never printed)")
    print(f"  services          : CP read edge + Auth Router + DB Router dispatch on {LOOPBACK_HOST} ephemeral ports;")
    print("                      API Gateway composed in-process (Gateway.handle; no ingress server exists or is added)")
    print(f"  scenarios         : {len(SCENARIOS)} binding rows")
    for scenario in SCENARIOS:
        internal = scenario["internal_code"] or "-"
        target = scenario["database"] or "-"
        print(
            f"    {scenario['label']:<26} -> {scenario['status']} {scenario['public_code']:<16} "
            f"dispatched={str(scenario['dispatched']).lower():<5} internal={internal:<26} db={target}"
        )
    print("  mutation intent   : NONE — read-only proof; no Control DB write, no tenant DB write, no audit write,")
    print("                      no secret/file write, no temporary row, and no mutating subcommand exists")
    if failures:
        print(f"PLAN FAILED ({failures} problem(s))")
        return 1
    print("PLAN OK")
    return 0


# ------------------------------------------------------------------------------------------------
# run
# ------------------------------------------------------------------------------------------------
def _mint_tokens(fixture: Any) -> Tuple[Any, Dict[str, str]]:
    """Fresh keypairs + one freshly minted RS256 token per scenario leg (fixture-only; RS256-only)."""
    keypair = fixture.generate_rs256_keypair()
    wrong_keypair = fixture.generate_rs256_keypair()

    def mint(**kwargs: Any) -> str:
        return fixture.mint_rs256_token(kwargs.pop("keypair", keypair), issuer=ISSUER, audience=AUDIENCE, subject=PRINCIPAL, **kwargs)

    tokens = {
        "alpha": mint(tenant=TENANT_ALPHA),
        "beta": mint(tenant=TENANT_BETA),
        "dormant": mint(tenant=TENANT_DORMANT),
        "unknown": mint(tenant=UNKNOWN_TENANT_ID),
        "unavailable-probe": mint(tenant=UNAVAILABLE_PROBE_TENANT_ID),
        "wrong-key": mint(keypair=wrong_keypair, tenant=TENANT_ALPHA, kid_override=keypair.kid),
        "unknown-kid": mint(tenant=TENANT_ALPHA, kid_override=UNKNOWN_KID),
        "unknown-issuer": fixture.mint_rs256_token(
            keypair, issuer=UNKNOWN_ISSUER, audience=AUDIENCE, subject=PRINCIPAL, tenant=TENANT_ALPHA
        ),
    }
    return keypair, tokens


def _routed_database_identity(pool: Any, tenant_id: str) -> Tuple[str, bool]:
    """``current_database()`` readback ON the exact pooled connection the integrated route bound.

    ``pool.acquire`` with a refusing ``open_fn`` MUST reuse the idle route-bound connection — a new
    connection can never satisfy this witness. Read-only; the connection is released afterwards."""
    opened = {"new": False}

    def _refuse() -> Any:
        opened["new"] = True
        raise OpsConfigError("a NEW connection would have been opened — the route-bound connection was not reused")

    conn = pool.acquire(tenant_id, ASSOCIATION_VERSION, _refuse)
    try:
        rows = conn.query(_SQL_ROUTED_IDENTITY)
        return str(rows[0]["db"]), (not opened["new"])
    finally:
        pool.release(conn)


def _pool_view(pool: Any) -> Dict[Tuple[str, str], Tuple[int, int]]:
    return {key: pool.counts(*key) for key in pool.pool_keys()}


def cmd_run(_args: argparse.Namespace) -> int:
    _resolve_dsns()  # config completeness (fail closed before any action)
    _validated_secret_dir()
    print("Smoke C V2 integrated live proof — RUN (read-only proof; zero-mutation contract)")

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

    commit = _git_head()
    before = _snapshot_state()
    print(f"  tested commit     : {commit}")
    print(f"  before-state      : captured ({len(before['tenant_ids'])} tenants; audit total {before['audit_total']})")

    evidence: Dict[str, Any] = {
        "spec": SPEC_ID,
        "commit": commit,
        "scenarios": {},
        "services": {},
        "shutdown_problems": [],
        "audit_disclosure": "routing/auth audit evidence is in-memory in this proof; DBR-AR-2 (durable routing audit) remains open",
    }
    env_before = {key: os.environ.get(key) for key in _ENV_TOUCHED_KEYS}
    patch = _EnvPatch()
    read_edge_stopped = False
    try:
        _expected_targets()
        from api_gateway.main import build_authenticator_from_env, build_gateway, build_router_dispatch_from_env
        from api_gateway.models import InboundRequest
        from auth_router.main import build_authenticate_server_from_env
        from control_plane.main import build_read_server_from_env
        from database_router.main import build_dispatch_server_from_env

        for key in _ENV_UNSET_KEYS:
            patch.set(key, None)  # ephemeral loopback defaults — never a fixed port or foreign host

        # --- Control Plane read edge (all-postgres posture over the standing Control DB) --------
        for key in _ENV_SELECTOR_KEYS:
            patch.set(key, "postgres")
        patch.set("SP2_CP_READ_HOST", LOOPBACK_HOST)
        composed_read = build_read_server_from_env()
        if composed_read is None:
            raise OpsConfigError("read-edge composition unexpectedly inactive — refused")
        read_server, read_url = composed_read
        read_thread = _host(read_server, read_url)
        _await_ready("control-plane read edge", lambda: _http_status(f"{read_url}/internal/routing/tenants/{TENANT_ALPHA}") == 200)
        evidence["services"]["control_plane_read_edge"] = read_url
        print(f"  service ready     : control-plane read edge on {read_url}")

        # --- fresh RS256 material (fixture-only; never printed) ---------------------------------
        fixture = _crypto_fixture()
        keypair, tokens = _mint_tokens(fixture)
        evidence["token"] = {"kid": keypair.kid, "issuer": ISSUER, "audience": AUDIENCE, "subject": PRINCIPAL}

        # --- Auth Router authenticate server -----------------------------------------------------
        patch.set("SP2_AR_CONTROL_PLANE_READ_BASE_URL", read_url)
        patch.set("SP2_AR_ISSUERS", fixture.issuer_env_json(keypair, issuer=ISSUER, audience=AUDIENCE))
        composed_auth = build_authenticate_server_from_env()
        if composed_auth is None:
            raise OpsConfigError("authenticate-server composition unexpectedly inactive — refused")
        auth_server, auth_url = composed_auth
        _host(auth_server, auth_url)
        _await_ready("auth-router authenticate edge", lambda: _http_status(f"{auth_url}/internal/auth/probe", post=True) == 404)
        authenticator = _closure_value(auth_server.RequestHandlerClass.do_POST, "authenticator")
        if type(authenticator).__name__ != "Authenticator":
            raise OpsConfigError("recovered auth object is not the composed production Authenticator — refused")
        auth_audit = authenticator._audit  # the composed in-memory auth audit sink (read-only witness)
        evidence["services"]["auth_router_authenticate"] = auth_url
        print(f"  service ready     : auth-router authenticate edge on {auth_url}")

        # --- Database Router dispatch server -----------------------------------------------------
        patch.set("SP2_DBR_ROUTING_READ_BASE_URL", read_url)
        composed_dispatch = build_dispatch_server_from_env()
        if composed_dispatch is None:
            raise OpsConfigError("dispatch-server composition unexpectedly inactive — refused")
        dispatch_server, dispatch_url = composed_dispatch
        _host(dispatch_server, dispatch_url)
        _await_ready("database-router dispatch edge", lambda: _http_status(f"{dispatch_url}/internal/dispatch/probe", post=True) == 404)
        router = _closure_value(dispatch_server.RequestHandlerClass.do_POST, "router")
        if type(router).__name__ != "DatabaseRouter":
            raise OpsConfigError("recovered dispatch object is not the composed production DatabaseRouter — refused")
        if type(router._factory).__name__ != "PsycopgConnectionFactory":
            raise OpsConfigError("the composed router does not hold the REAL psycopg connection factory — refused")
        if type(router._secrets).__name__ != "EnvTenantSecretStore":
            raise OpsConfigError("the composed router does not hold the REAL tenant secret store — refused")
        router_audit = router._audit  # the composed in-memory routing audit sink (read-only witness)
        pool = router._pool  # the interactive-lane pool (read-only census + identity readback)
        evidence["services"]["database_router_dispatch"] = dispatch_url
        print(f"  service ready     : database-router dispatch edge on {dispatch_url}")

        # --- API Gateway (in-process; the real composed pipeline) --------------------------------
        patch.set("SP2_GW_AUTH_ROUTER_BASE_URL", auth_url)
        patch.set("SP2_GW_DB_ROUTER_BASE_URL", dispatch_url)
        gateway_authenticator = build_authenticator_from_env()
        gateway_router = build_router_dispatch_from_env()
        if gateway_authenticator is None or gateway_router is None:
            raise OpsConfigError("gateway transport seams unexpectedly inactive — refused")
        gateway = build_gateway(authenticator=gateway_authenticator, router=gateway_router)
        print("  service ready     : api-gateway pipeline composed in-process (Gateway.handle)")

        # --- the nine binding scenarios, serially -------------------------------------------------
        for index, scenario in enumerate(SCENARIOS, start=1):
            label = str(scenario["label"])
            if scenario["read_edge_down"] and not read_edge_stopped:
                read_server.shutdown()
                read_server.server_close()
                read_thread.join(SHUTDOWN_TIMEOUT_SECONDS)
                if read_thread.is_alive() or not _port_refused(read_url):
                    raise OpsConfigError("could not stop the read edge for the unavailability row — refused")
                _ACTIVE_SERVERS[:] = [entry for entry in _ACTIVE_SERVERS if entry[0] is not read_server]
                read_edge_stopped = True
                print("  read edge stopped : deliberately, for the control-plane-unavailable row")
            correlation_id = f"{CORRELATION_PREFIX}-{index:02d}-{label}"
            pool_before_view = _pool_view(pool)
            auth_events_before = len(auth_audit.events())
            route_events_before = len(router_audit.events())
            response = gateway.handle(
                InboundRequest(
                    method="GET",
                    path="/tenant/deals",
                    headers={"X-Tenant-Id": str(scenario["carrier"]), "x-correlation-id": correlation_id},
                    authorization="Bearer " + tokens[str(scenario["token"])],
                )
            )
            _await_audit_event(auth_audit, auth_events_before, correlation_id)
            pool_after_view = _pool_view(pool)
            new_auth_events = [e for e in auth_audit.events()[auth_events_before:] if e.correlation_id == correlation_id]
            new_route_events = [e for e in router_audit.events()[route_events_before:] if e.correlation_id == correlation_id]
            denial_codes = [e.outcome.split("denied:", 1)[1] for e in new_auth_events if e.outcome.startswith("denied:")]
            observed: Dict[str, Any] = {
                "executed": True,
                "correlation_id": correlation_id,
                "status": response.status,
                "public_code": response.public_code,
                "dispatched": response.dispatched,
                "category": response.category.value if response.category is not None else None,
                "internal_code": denial_codes[0] if denial_codes else None,
                "auth_events": [(e.action, e.outcome) for e in new_auth_events],
                "route_events": len(new_route_events),
                "pool_delta": 0,
                "new_pool_keys": 0,
                "database": None,
                "readback_reused": None,
                "other_pool_delta": None,
            }
            if scenario["internal_code"] is not None:
                keys = set(pool_before_view) | set(pool_after_view)
                observed["pool_delta"] = sum(1 for key in keys if pool_before_view.get(key) != pool_after_view.get(key))
                observed["new_pool_keys"] = len(set(pool_after_view) - set(pool_before_view))
            else:
                own_key = (str(scenario["carrier"]), ASSOCIATION_VERSION)
                other_tenant = TENANT_BETA if scenario["carrier"] == TENANT_ALPHA else TENANT_ALPHA
                other_key = (other_tenant, ASSOCIATION_VERSION)
                database, reused = _routed_database_identity(pool, str(scenario["carrier"]))
                observed["database"] = database
                observed["readback_reused"] = reused
                observed["other_pool_delta"] = abs(
                    sum(pool_after_view.get(other_key) or (0, 0)) - sum(pool_before_view.get(other_key) or (0, 0))
                )
                observed["own_pool_counts"] = pool.counts(*own_key)
            evidence["scenarios"][label] = observed
            shown_internal = observed["internal_code"] or "-"
            shown_db = observed["database"] or "-"
            print(
                f"  scenario {index:>2}/9    : {label:<26} -> {observed['status']} {observed['public_code']:<16} "
                f"dispatched={str(observed['dispatched']).lower():<5} internal={shown_internal:<26} db={shown_db}"
            )

        # --- drain the tenant pools (close every pooled real connection) -------------------------
        for tenant_id, _version in list(pool.pool_keys()):
            pool.invalidate_version(tenant_id, "0")  # keep_version "0" matches nothing -> drains/closes all
        evidence["pools_drained"] = pool.pool_keys() == []
    except OpsConfigError:
        raise
    except Exception as exc:
        print(f"  FAIL: unexpected error during the proof: {type(exc).__name__} (sanitized; fail closed)")
        evidence["unexpected_error"] = type(exc).__name__
    finally:
        problems = _stop_all()
        evidence["shutdown_problems"] = problems
        evidence["ports_released"] = not problems
        patch.restore()
        evidence["env_restored"] = {key: os.environ.get(key) for key in _ENV_TOUCHED_KEYS} == env_before

    after = _snapshot_state()
    diff = sorted(key for key in before if before[key] != after.get(key))
    evidence["before_equals_after"] = before == after
    evidence["state_diff"] = diff
    print(f"  after-state       : captured; before == after -> {evidence['before_equals_after']}")
    print(f"  audit disclosure  : {evidence['audit_disclosure']}")

    failures = 0
    for name, problem in evaluate_run(evidence):
        if problem is None:
            print(f"  PASS: {name}")
        else:
            failures += 1
            print(f"  FAIL: {name} — {problem}")

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

    _LAST_PROOF.clear()
    _LAST_PROOF.update(evidence)
    status_rc = cmd_status(_args)
    if failures or status_rc:
        print(f"RUN FAILED ({failures} obligation(s) not holding; status exit {status_rc})")
        return 1
    print("RUN OK — all binding scenarios executed and verified in the implementation environment; zero mutation;")
    print("         B5-BLK-4 remains OPEN; the Physical Multi-Database MVP remains mandatory and NOT complete.")
    return 0


# ------------------------------------------------------------------------------------------------
# status
# ------------------------------------------------------------------------------------------------
def cmd_status(_args: argparse.Namespace) -> int:
    _control_dsn, admin_dsn = _resolve_dsns()
    del _control_dsn
    secret_dir = _validated_secret_dir()
    print("Smoke C V2 integrated live proof — STATUS (read-only; fail-closed)")
    failures = 0

    for label, runner, evaluator in (
        ("B5-4 standing topology PASS", _b5_4_status, _b5_4_status_problem),
        ("B5-4A standing auth fixture PASS", _b5_4a_status, _b5_4a_status_problem),
    ):
        code, out = runner()
        problem = evaluator(code, out)
        if problem is None:
            print(f"  PASS: {label}")
        else:
            failures += 1
            print(f"  FAIL: {label} — {problem}")

    def spec_problem() -> Optional[str]:
        if not _SPEC_PATH.is_file():
            return f"missing: {_SPEC_PATH}"
        text = _SPEC_PATH.read_text(encoding="utf-8")
        needles = ("SMOKE-C-SPEC-01", "Gateway.handle", "tenant_access_denied", "tenant_not_ready", TENANT_ALPHA, TENANT_BETA)
        missing = [needle for needle in needles if needle not in text]
        return f"spec lost pinned needle(s): {missing}" if missing else None

    def fixture_problem() -> Optional[str]:
        if not _CRYPTO_FIXTURE_PATH.is_file():
            return f"missing: {_CRYPTO_FIXTURE_PATH}"
        text = _CRYPTO_FIXTURE_PATH.read_text(encoding="utf-8")
        needles = ("def generate_rs256_keypair", "def mint_rs256_token", "def issuer_env_json")
        missing = [needle for needle in needles if needle not in text]
        return f"fixture lost pinned surface: {missing}" if missing else None

    def standing_problem(tenant_id: str, target: str, *, expect_ready: bool) -> Optional[str]:
        patch = _EnvPatch()
        try:
            cp = _compose_snapshot_plane(patch)
            try:
                row = _tenant_row_snapshot(cp, tenant_id)
                memberships = cp.store.list_memberships(principal_ref=PRINCIPAL, tenant_id=tenant_id)
            finally:
                _close_plane(cp)
        finally:
            patch.restore()
        if row is None:
            return "registry row absent"
        expected_state = "Ready" if expect_ready else "Registered"
        if row["lifecycle_state"] != expected_state:
            return f"lifecycle is {row['lifecycle_state']!r}, expected {expected_state!r}"
        if not memberships:
            return f"{PRINCIPAL} membership absent"
        conn = _connect(admin_dsn)
        try:
            with conn.cursor() as cur:
                cur.execute(_SQL_PG_DATABASE_PRESENT, (target,))
                present = cur.fetchone() is not None
        finally:
            conn.close()
        if present is not expect_ready:
            return f"physical database presence is {present}, expected {expect_ready}"
        secret_file = secret_dir / "tenant" / tenant_id / f"dsn@{ASSOCIATION_VERSION}"
        if secret_file.is_file() is not expect_ready:
            return f"secret-file presence is {secret_file.is_file()}, expected {expect_ready}"
        return None

    def residue_problem() -> Optional[str]:
        count = _snapshot_state()["residue"]
        return f"{count} residue row(s) found" if count else None

    def listener_problem() -> Optional[str]:
        if _ACTIVE_SERVERS:
            return f"{len(_ACTIVE_SERVERS)} in-process server(s) still registered as live"
        return None

    from control_plane.provisioning import tenant_database_name

    checks: List[Tuple[str, Callable[[], Optional[str]]]] = [
        ("Smoke C specification found and pinned", spec_problem),
        ("RS256 fixture found and pinned", fixture_problem),
        ("standing alpha prerequisites PASS", lambda: standing_problem(TENANT_ALPHA, ALPHA_DB, expect_ready=True)),
        ("standing beta prerequisites PASS", lambda: standing_problem(TENANT_BETA, BETA_DB, expect_ready=True)),
        (
            "standing dormant prerequisites PASS",
            lambda: standing_problem(TENANT_DORMANT, tenant_database_name(TENANT_DORMANT), expect_ready=False),
        ),
        ("zero residue PASS", residue_problem),
        ("no leftover in-process service/listener PASS", listener_problem),
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

    if _LAST_PROOF:
        if proof_complete(_LAST_PROOF):
            scenario_count = len(_LAST_PROOF.get("scenarios", {}))
            print(f"  PASS: last in-process proof evidence complete ({scenario_count} scenarios; commit {_LAST_PROOF.get('commit')})")
        else:
            failures += 1
            print("  FAIL: last in-process proof evidence is INCOMPLETE — the proof may not be claimed")
    else:
        print("  INFO: no in-process proof evidence (run has not executed in this process); prerequisites alone")
        print("        NEVER constitute a Smoke C claim (fail closed)")

    if failures:
        print(f"STATUS FAILED ({failures} check(s) not holding)")
        return 1
    print("STATUS OK — prerequisites healthy; proof evidence only ever comes from an in-process run")
    return 0


# ------------------------------------------------------------------------------------------------
# entrypoint
# ------------------------------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="smoke_c_integrated_live_proof",
        description="Smoke C V2 integrated live proof over the standing B5-4/B5-4A fixture (plan/run/status; zero-mutation).",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("plan", help="read-only intent + standing-prerequisite delegation (no server, no request, no mutation)")
    sub.add_parser("run", help="the integrated zero-mutation proof (loopback ephemeral services; before==after required)")
    sub.add_parser("status", help="read-only fail-closed prerequisite + evidence verification (non-zero unless healthy)")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    handlers: dict = {"plan": cmd_plan, "run": cmd_run, "status": cmd_status}
    try:
        return int(handlers[args.command](args))
    except OpsConfigError as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
