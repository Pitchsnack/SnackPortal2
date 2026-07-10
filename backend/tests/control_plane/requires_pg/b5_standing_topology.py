"""B5-4 standing local physical topology — operator harness (standalone-only; PRD B5-4).

An OPERATOR TOOL, not application runtime code and not a test: it establishes, inspects, and tears
down the governed B5-4 standing local topology —

    one standing Control DB (control DDL 001-009 applied by THIS explicit ops command — never at
    runtime) + two deterministic B5-4 tenants (``b5_standing_alpha`` / ``b5_standing_beta``) driven
    through the REAL env-composed all-Postgres onboarding path (Register -> Provision -> Apply ->
    Verify -> Ready) onto two physically distinct tenant databases at DATABASE granularity on the
    admin DSN's cluster + canonical ``tenant/<id>/dsn`` secret references with matching DSN secret
    files materialized OUTSIDE the repository under ``$SNACKPORTAL_TENANT_SECRET_DIR``.

Commands (stdlib argparse; work happens ONLY after an explicit subcommand — import performs no I/O):

    plan      read-only: sanitized intent (redacted control identity, tenant ids/targets/refs,
              secret-dir path, DDL inventory counts). No connection, no mutation.
    apply     idempotent: control DDL 001-009 (read from infrastructure/db/control — never embedded;
              applied twice to prove re-apply safety), tenant DSN secret files (atomic write,
              owner-only where supported), then the real composed onboarding for both tenants.
    status    read-only, fail-closed: exits non-zero unless the COMPLETE topology holds (DDL census,
              both rows Ready, distinct physical DBs, full tenant schema census, canonical
              refs/versions, secret files present, BOTH sides' secret adapters resolve each tenant
              to its OWN database). Deliberately performs no sentinel/evidence write.
    teardown  explicit (requires ``--confirm-b5-teardown``), bounded, idempotent: supported registry
              lifecycle reconciliation ONLY (Ready -> Suspended -> Decommissioned via
              suspend_tenant/decommission_tenant + the disable_routing companion; rows are RETAINED
              — the ControlStore has no row deletion and none is invented), then drops EXACTLY the
              two recomputed B5-4 tenant databases through the existing identifier-guarded
              ``PostgresProvisioningOperator.deprovision`` (DROP IF EXISTS; no SQL literal here),
              then removes exactly the two canonical secret files. Never touches the Control DB,
              its DDL, cluster roles, or any other database/row/secret. DECOMMISSIONED is terminal:
              re-establishing the fixture afterwards requires the runbook's full-fixture reset.

Configuration (EXISTING conventions only — this tool introduces NO new environment variable):
control-store DSN by reference ``control/control-store-dsn`` and provisioning-admin DSN by reference
``control/provisioning-admin-dsn`` via the shared ``EnvReferenceSecretStore`` env/file convention;
``SNACKPORTAL_TENANT_SECRET_DIR`` must be an ABSOLUTE path OUTSIDE the repository worktree (refused
otherwise); the four ``SP2_CP_*`` selectors are set to ``postgres`` in-process by the effectful
commands (the sanctioned all-Postgres composition — ``create_app()``'s own coherence rules apply).

DRIVER CONTAINMENT. No static database-driver import: psycopg is located via importlib at call
time; provider CLASSES are imported lazily inside commands. Module import is inert (no I/O, no env
mutation, no connection). Runbook: ``infrastructure/runbooks/b5_standing_topology.md`` (invoked from
``backend/`` as ``python tests/control_plane/requires_pg/b5_standing_topology.py <command>``).

SECRET HYGIENE (D-14). DSNs are resolved in-memory by reference and NEVER printed, logged, or
returned: every emitted identity is redacted to scheme+host+port+database (no userinfo, no query).
Secret files live only under the operator-provided secret root outside the repo.

NO OVERCLAIM. This tool establishes a LOCAL PRECONDITION FIXTURE. It is not Smoke C, not a
served-request proof, not cluster-level distinctness, and not physical-DB proof. B5-BLK-4 remains
OPEN; the Physical Multi-Database MVP remains mandatory and is NOT completed by this harness.
"""

from __future__ import annotations

import argparse
import importlib
import os
import pathlib
import sys
from typing import Any, Callable, List, Optional, Sequence, Tuple
from urllib.parse import urlsplit, urlunsplit

_THIS = pathlib.Path(__file__).resolve()
_BACKEND_ROOT = _THIS.parents[3]
_REPO_ROOT = _THIS.parents[4]
sys.path.insert(0, str(_BACKEND_ROOT))  # backend on path (the requires_pg harness idiom); no package import happens at module scope

_CONTROL_DDL_DIR = _REPO_ROOT / "infrastructure" / "db" / "control"
# Canonical numeric apply order 001 -> 009 (union of the 07D harness order [001-007+009] and the
# ledger harness's 008). Dependencies satisfied numerically: 003<-002, 008<-001, 009<-004. Every
# file is idempotent by SQL text (IF NOT EXISTS / OR REPLACE / DROP TRIGGER IF EXISTS+recreate /
# ADD COLUMN IF NOT EXISTS); the files are READ here and never embedded or modified.
_CONTROL_DDL_ORDER: Tuple[str, ...] = (
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

# The deterministic B5-4 standing tenants (admission shape ^[a-z0-9_]+$; collision-free vs every
# scratch family and seeded record on this repo's harnesses). Targets/refs are RECOMPUTED from
# these ids everywhere — teardown never accepts a database name from the caller.
TENANT_IDS: Tuple[str, str] = ("b5_standing_alpha", "b5_standing_beta")
_ORG_REF = "b5_standing_org"
_FED_REF = "b5_standing_fed"
_ACTOR = "b5_standing_topology_ops"
_SECRET_DIR_ENV = "SNACKPORTAL_TENANT_SECRET_DIR"  # EXISTING shared-convention name (both secret-store twins read it)

# Expected control-DDL census (read-only status checks; names owned by the canonical DDL files).
_CONTROL_TABLES = (
    "control_distinctness_ledger",
    "control_audit",
    "control_tenants",
    "control_memberships",
    "control_federation",
    "control_directory",
)
_CONTROL_INDEXES = ("control_distinctness_fingerprint_unique", "ux_control_tenants_single_control_internal")
_CONTROL_TRIGGERS = ("control_audit_no_mutation", "control_audit_no_truncate")


class OpsConfigError(Exception):
    """Non-sensitive operator-configuration/refusal error (never carries a DSN or secret value)."""


def _psycopg() -> Any:
    """The database driver, located at call time (no static import — Driver Containment Standard)."""
    return importlib.import_module("psycopg")


def _swap_db(base_dsn: str, dbname: str) -> str:
    """``base_dsn`` with its database path replaced (the requires_pg ``_pg.swap_db`` idiom, replicated)."""
    parts = urlsplit(base_dsn)
    return urlunsplit((parts.scheme, parts.netloc, "/" + dbname, parts.query, parts.fragment))


def _redacted(dsn: str) -> str:
    """Non-sensitive connection identity: scheme + host + port + database. NEVER userinfo/query (D-14)."""
    parts = urlsplit(dsn)
    host = parts.hostname or ""
    port = f":{parts.port}" if parts.port else ""
    return f"{parts.scheme}://{host}{port}{parts.path}"


def _database_of(dsn: str) -> str:
    return urlsplit(dsn).path.lstrip("/")


def _connect(dsn: str, *, autocommit: bool = False) -> Any:
    """Open a short-lived connection; a failure is reported with the REDACTED identity only."""
    psycopg = _psycopg()
    try:
        return psycopg.connect(dsn, connect_timeout=10, autocommit=autocommit)
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
    """The infrastructure-owned tenant-secret root: absolute AND outside the repository worktree."""
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


def _tenant_ref(tenant_id: str) -> str:
    from control_plane.onboarding import tenant_dsn_ref

    return tenant_dsn_ref(tenant_id)


def _tenant_target(tenant_id: str) -> str:
    from control_plane.provisioning import tenant_database_name

    return tenant_database_name(tenant_id)


def _secret_file(secret_dir: pathlib.Path, tenant_id: str) -> pathlib.Path:
    """The EXACT resolver path ``$SNACKPORTAL_TENANT_SECRET_DIR/<store_ref>@1`` for a validated
    canonical B5-4 reference, containment-checked against the configured root."""
    if tenant_id not in TENANT_IDS:
        raise OpsConfigError("secret paths are constructed only for the two fixed B5-4 tenant ids — refused")
    ref = _tenant_ref(tenant_id)  # canonical tenant/<id>/dsn shape by construction
    # Root and candidate are resolved AT THE SAME MOMENT: a root resolved earlier can lawfully
    # differ from a later-resolved child once directories exist (symlinks / OS filesystem
    # virtualization) — containment must compare one consistent view.
    root = secret_dir.resolve()
    candidate = (root / f"{ref}@1").resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        raise OpsConfigError("secret file path escapes the configured secret root — refused") from None
    return candidate


def _compose_all_postgres_plane() -> Any:
    """Set the four EXISTING ``SP2_CP_*`` selectors to ``postgres`` (in-process) and compose the real
    plane via ``create_app()`` (its own selector-coherence rules keep this fail-closed)."""
    from control_plane import main as cp_main

    for name in (
        cp_main.CONTROL_STORE_ENV,
        cp_main.PROVISIONING_ADAPTER_ENV,
        cp_main.TENANT_SCHEMA_APPLICATOR_ENV,
        cp_main.DISTINCTNESS_LEDGER_ENV,
    ):
        os.environ[name] = "postgres"
    return cp_main.create_app()


def _close_plane(cp: Any) -> None:
    """Best-effort close of the durable store's cached connection (the 07D finally idiom)."""
    try:
        if getattr(cp.store, "_conn_cache", None) is not None:
            cp.store._conn_cache.close()
    except Exception:
        pass


def _one(cur: Any, sql: str, params: Tuple[Any, ...] = ()) -> Any:
    cur.execute(sql, params)
    row = cur.fetchone()
    return row[0] if row else None


# ----------------------------------------------------------------------------------------------
# plan
# ----------------------------------------------------------------------------------------------
def cmd_plan(_args: argparse.Namespace) -> int:
    control_dsn, admin_dsn = _resolve_dsns()
    secret_dir = _validated_secret_dir()
    missing = [name for name in _CONTROL_DDL_ORDER if not (_CONTROL_DDL_DIR / name).is_file()]
    if missing:
        raise OpsConfigError(f"canonical control DDL assets missing on disk: {missing}")
    from control_plane.adapters.providers.postgres_tenant_schema_applicator import default_tenant_schema_ddl_paths

    tenant_ddl = default_tenant_schema_ddl_paths()
    print("B5-4 standing topology — PLAN (read-only; no connection, no mutation)")
    print(f"  control DB target : {_redacted(control_dsn)}")
    print(f"  admin cluster     : {_redacted(admin_dsn)} (tenant DBs land here at DATABASE granularity)")
    for tid in TENANT_IDS:
        print(f"  tenant            : {tid} -> database {_tenant_target(tid)} ; secret ref {_tenant_ref(tid)}@1")
    print(f"  secret dir        : {secret_dir} (outside repo; file form <dir>/tenant/<id>/dsn@1)")
    print(f"  control DDL       : {len(_CONTROL_DDL_ORDER)} files from {_CONTROL_DDL_DIR}")
    print(f"  tenant DDL        : {len(tenant_ddl)} files applied by the existing Step-2b applicator during onboarding")
    print("PLAN OK")
    return 0


# ----------------------------------------------------------------------------------------------
# apply
# ----------------------------------------------------------------------------------------------
def _apply_control_ddl(control_dsn: str, *, label: str) -> None:
    """Apply the canonical control DDL set in one transaction (single commit; templates read-only)."""
    missing = [name for name in _CONTROL_DDL_ORDER if not (_CONTROL_DDL_DIR / name).is_file()]
    if missing:
        raise OpsConfigError(f"canonical control DDL assets missing on disk: {missing}")
    conn = _connect(control_dsn)
    try:
        with conn.cursor() as cur:
            for name in _CONTROL_DDL_ORDER:
                cur.execute((_CONTROL_DDL_DIR / name).read_text(encoding="utf-8"))
        conn.commit()
    except OpsConfigError:
        raise
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        # 008 is fail-closed by design over pre-existing duplicate fingerprints (isolation-anomaly
        # evidence) — surface a non-sensitive category, never driver/DSN internals.
        raise OpsConfigError(f"control DDL apply failed ({label}): {type(exc).__name__} — no partial pass committed") from None
    finally:
        conn.close()
    print(f"  control DDL 001-009 applied ({label}) to {_redacted(control_dsn)}")


def _materialize_secret_file(secret_dir: pathlib.Path, tenant_id: str, dsn: str) -> pathlib.Path:
    """Atomic (tmp + os.replace), owner-only where supported (0600 best-effort; Windows-limited)."""
    target_path = _secret_file(secret_dir, tenant_id)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = target_path.parent / (target_path.name + ".tmp")
    tmp.write_text(dsn + "\n", encoding="utf-8")
    os.replace(tmp, target_path)
    try:
        os.chmod(target_path, 0o600)
    except OSError:
        pass
    return target_path


def cmd_apply(_args: argparse.Namespace) -> int:
    control_dsn, admin_dsn = _resolve_dsns()
    secret_dir = _validated_secret_dir()
    control_db = _database_of(control_dsn)
    if not control_db:
        raise OpsConfigError("the control-store DSN names no database — refused")
    if control_db.startswith("sp2_tenant_") or control_db in {_tenant_target(t) for t in TENANT_IDS}:
        raise OpsConfigError("the control-store DSN targets the tenant namespace — refused (Control DB is never a tenant target)")

    print("B5-4 standing topology — APPLY (idempotent)")
    _apply_control_ddl(control_dsn, label="pass 1")
    _apply_control_ddl(control_dsn, label="pass 2 — idempotent re-apply proof")

    for tid in TENANT_IDS:
        path = _materialize_secret_file(secret_dir, tid, _swap_db(admin_dsn, _tenant_target(tid)))
        print(f"  secret file materialized: {path} (content: the tenant DSN — never printed)")

    from control_plane.distinctness import DistinctnessResult
    from control_plane.records import TenantLifecycleState

    cp = _compose_all_postgres_plane()
    failures: List[str] = []
    try:
        for tid in TENANT_IDS:
            outcome = cp.onboarding.onboard(
                tid, organization_ref=_ORG_REF, federation_config_ref=_FED_REF, actor=_ACTOR, correlation_id=f"b5-apply-{tid}"
            )
            if outcome.result is DistinctnessResult.VERIFIED:
                print(f"  onboarded {tid}: VERIFIED ({outcome.reason or 'fresh run'})")
            elif outcome.reason == "decommissioned":
                failures.append(f"{tid}: decommissioned (terminal) — re-establishing requires the runbook's full-fixture reset")
            else:
                failures.append(f"{tid}: {outcome.result.value} / {outcome.reason}")
        for tid in TENANT_IDS:
            rec = cp.store.get_tenant(tid)
            state = rec.lifecycle_state.value if rec is not None else "ABSENT"
            print(f"  registry: {tid} -> {state} (association {_tenant_ref(tid)}@1; target {_tenant_target(tid)})")
            if rec is None or rec.lifecycle_state is not TenantLifecycleState.READY:
                failures.append(f"{tid}: not Ready after apply")
    finally:
        _close_plane(cp)
    if failures:
        for line in failures:
            print(f"  FAIL: {line}")
        print("APPLY FAILED (fail closed; nothing was rolled forward past the failing step)")
        return 1
    print("APPLY OK — standing fixture established (run `status` to verify; teardown requires --confirm-b5-teardown)")
    return 0


# ----------------------------------------------------------------------------------------------
# status
# ----------------------------------------------------------------------------------------------
def cmd_status(_args: argparse.Namespace) -> int:
    control_dsn, admin_dsn = _resolve_dsns()
    secret_dir = _validated_secret_dir()
    checks: List[Tuple[str, Callable[[], Optional[str]]]] = []

    def check_control_ddl() -> Optional[str]:
        conn = _connect(control_dsn)
        try:
            with conn.cursor() as cur:
                for table in _CONTROL_TABLES:
                    if _one(cur, "SELECT to_regclass(%s)", (table,)) is None:
                        return f"control table missing: {table}"
                for index in _CONTROL_INDEXES:
                    if _one(cur, "SELECT 1 FROM pg_indexes WHERE indexname = %s", (index,)) is None:
                        return f"control index missing: {index}"
                for trigger in _CONTROL_TRIGGERS:
                    if _one(cur, "SELECT 1 FROM pg_trigger WHERE tgname = %s", (trigger,)) is None:
                        return f"control trigger missing: {trigger}"
                cas_sql = "SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = %s"
                if _one(cur, cas_sql, ("control_tenants", "version")) is None:
                    return "control_tenants.version (009) missing"
        finally:
            conn.close()
        return None

    def check_registry_ready() -> Optional[str]:
        from control_plane.read_api import ControlPlaneReadService
        from control_plane.records import TenantLifecycleState

        cp = _compose_all_postgres_plane()
        try:
            reader = ControlPlaneReadService(cp.store)
            for tid in TENANT_IDS:
                rec = cp.store.get_tenant(tid)
                if rec is None:
                    return f"registry row absent: {tid}"
                if rec.lifecycle_state is not TenantLifecycleState.READY:
                    return f"{tid} lifecycle is {rec.lifecycle_state.value}, not Ready"
                if rec.database_association_ref.store_ref != _tenant_ref(tid) or rec.database_association_ref.version != "1":
                    return f"{tid} association is not the canonical {_tenant_ref(tid)}@1"
                view = reader.routing_view(tid)
                if view is None or view.get("ready") is not True:
                    return f"{tid} routing view is not ready"
        finally:
            _close_plane(cp)
        return None

    def check_databases_exist_distinct() -> Optional[str]:
        targets = [_tenant_target(tid) for tid in TENANT_IDS]
        if len(set(targets)) != len(targets):
            return "tenant targets are not distinct"
        conn = _connect(admin_dsn)
        try:
            with conn.cursor() as cur:
                for target in targets:
                    if _one(cur, "SELECT 1 FROM pg_database WHERE datname = %s", (target,)) is None:
                        return f"physical database missing: {target}"
        finally:
            conn.close()
        return None

    def check_tenant_schemas() -> Optional[str]:
        from control_plane.recovery import BOOTSTRAP_TABLE_SET

        for tid in TENANT_IDS:
            conn = _connect(_swap_db(admin_dsn, _tenant_target(tid)))
            try:
                with conn.cursor() as cur:
                    for qualified in sorted(BOOTSTRAP_TABLE_SET):
                        if _one(cur, "SELECT to_regclass(%s)", (qualified,)) is None:
                            return f"{tid}: schema object missing: {qualified}"
                    if _one(cur, "SELECT count(*) FROM agents WHERE agent_kind = 'system_primary'") != 1:
                        return f"{tid}: System Primary seed is not a singleton"
                    if _one(cur, "SELECT count(*) FROM agents") != 1:
                        return f"{tid}: unexpected extra agents rows"
                    version = _one(cur, "SELECT version FROM schema_version ORDER BY applied_at DESC LIMIT 1")
                    if str(version) != "1":
                        return f"{tid}: schema_version is {version!r}, expected '1'"
            finally:
                conn.close()
        return None

    def check_secret_files() -> Optional[str]:
        for tid in TENANT_IDS:
            if not _secret_file(secret_dir, tid).is_file():
                return f"secret file missing: {_secret_file(secret_dir, tid)}"
        return None

    def check_adapters_resolve_own_database() -> Optional[str]:
        # BOTH sides' existing adapters (the replicated twins) must resolve each tenant's canonical
        # reference, and each resolved DSN must reach that tenant's OWN database (read-only probe).
        from control_plane.adapters.providers.env_tenant_dsn_secret_store import EnvTenantDsnSecretStore
        from database_router.adapters.providers.env_tenant_secret_store import EnvTenantSecretStore
        from shared.secrets import SecretRef

        observed: List[str] = []
        for tid in TENANT_IDS:
            ref = SecretRef(store_ref=_tenant_ref(tid), version="1")
            try:
                cp_side = EnvTenantDsnSecretStore().resolve(ref).material
                dbr_side = EnvTenantSecretStore().resolve(ref).material
            except (LookupError, PermissionError) as exc:
                return f"{tid}: secret resolution failed ({type(exc).__name__})"
            if cp_side != dbr_side:
                return f"{tid}: the two secret adapters resolved DIFFERENT material"
            conn = _connect(cp_side)
            try:
                with conn.cursor() as cur:
                    current = _one(cur, "SELECT current_database()")
            finally:
                conn.close()
            if current != _tenant_target(tid):
                return f"{tid}: secret resolves to database {current!r}, expected its own {_tenant_target(tid)!r}"
            observed.append(str(current))
        if len(set(observed)) != len(TENANT_IDS):
            return f"both tenant secrets resolve to ONE database ({observed[0]!r}) — distinctness violated"
        return None

    checks = [
        ("control DDL 001-009 complete", check_control_ddl),
        ("registry rows Ready + canonical refs", check_registry_ready),
        ("two distinct physical tenant databases exist", check_databases_exist_distinct),
        ("complete tenant schema in both databases", check_tenant_schemas),
        ("secret files present outside repo", check_secret_files),
        ("both secret adapters resolve each tenant to its OWN database", check_adapters_resolve_own_database),
    ]
    print("B5-4 standing topology — STATUS (read-only; fail-closed)")
    failures = 0
    for name, fn in checks:
        try:
            problem = fn()
        except OpsConfigError as exc:
            problem = str(exc)
        except Exception as exc:  # fail the CHECK, sanitized (type only — driver messages may carry connection detail)
            problem = f"{type(exc).__name__} (fail closed)"
        if problem is None:
            print(f"  PASS: {name}")
        else:
            failures += 1
            print(f"  FAIL: {name} — {problem}")
    if failures:
        print(f"STATUS FAILED ({failures} check(s) not holding)")
        return 1
    print("STATUS OK — complete standing topology")
    return 0


# ----------------------------------------------------------------------------------------------
# teardown
# ----------------------------------------------------------------------------------------------
def cmd_teardown(args: argparse.Namespace) -> int:
    # Confirmation is checked FIRST — before any configuration read, connection, or effect.
    if not getattr(args, "confirm", False):
        print("REFUSED: teardown requires the explicit --confirm-b5-teardown flag (no action was taken)")
        return 1
    control_dsn, admin_dsn = _resolve_dsns()
    del control_dsn  # config completeness is validated; teardown itself talks via the composed plane + operator
    secret_dir = _validated_secret_dir()

    from control_plane import main as cp_main
    from control_plane.records import TenantLifecycleState
    from control_plane.registry import RegistryError

    print("B5-4 standing topology — TEARDOWN (bounded to the two B5-4 tenants; idempotent)")
    cp = _compose_all_postgres_plane()
    failures: List[str] = []
    try:
        for tid in TENANT_IDS:
            rec = cp.store.get_tenant(tid)
            if rec is None:
                print(f"  {tid}: no registry row (no-op)")
                continue
            state = rec.lifecycle_state
            try:
                if state is TenantLifecycleState.VERIFYING:
                    failures.append(f"{tid}: mid-flight (Verifying) — no supported egress; retry teardown later")
                    continue
                if state is TenantLifecycleState.READY:
                    cp.registry.suspend_tenant(tid, actor=_ACTOR, correlation_id=f"b5-teardown-{tid}")
                    state = TenantLifecycleState.SUSPENDED
                if state is not TenantLifecycleState.DECOMMISSIONED:
                    cp.onboarding.disable_routing(tid, actor=_ACTOR, correlation_id=f"b5-teardown-{tid}")
                    cp.registry.decommission_tenant(tid, actor=_ACTOR, correlation_id=f"b5-teardown-{tid}")
                print(f"  {tid}: registry reconciled -> Decommissioned (row RETAINED — supported lifecycle semantics; audited)")
            except RegistryError as exc:
                failures.append(f"{tid}: registry reconciliation failed ({exc})")
    finally:
        _close_plane(cp)

    # Physical drops: EXACTLY the two recomputed targets, through the existing identifier-guarded
    # operator (drop-if-exists semantics — idempotent; no SQL literal in this module; never a list,
    # wildcard, or caller-supplied name). The Control DB and every other database are untouched.
    from shared.adapters.providers.env_reference_secret_store import DEFAULT_ALLOWED, EnvReferenceSecretStore
    from shared.secrets import SecretRef

    del admin_dsn  # the operator resolves the admin descriptor by reference itself (D-14)
    from control_plane.adapters.providers.postgres_provisioning_operator import PostgresProvisioningOperator

    admin_secrets = EnvReferenceSecretStore(allowed=frozenset({*DEFAULT_ALLOWED, cp_main.PROVISIONING_ADMIN_DSN_REF}))
    operator = PostgresProvisioningOperator(secrets=admin_secrets, ref=SecretRef(store_ref=cp_main.PROVISIONING_ADMIN_DSN_REF, version="1"))
    for tid in TENANT_IDS:
        target = _tenant_target(tid)
        try:
            operator.deprovision(target=target)
            print(f"  dropped (if present): {target}")
        except Exception as exc:
            failures.append(f"{tid}: database drop failed ({type(exc).__name__})")

    for tid in TENANT_IDS:
        path = _secret_file(secret_dir, tid)
        path.unlink(missing_ok=True)
        try:
            path.parent.rmdir()  # remove the now-empty tenant/<id> dir only; non-empty -> left alone
        except OSError:
            pass
        print(f"  secret file removed (if present): {path}")

    if failures:
        for line in failures:
            print(f"  FAIL: {line}")
        print("TEARDOWN INCOMPLETE (rerun is safe; every step is idempotent by outcome)")
        return 1
    print("TEARDOWN OK — rows Decommissioned (retained), databases dropped, secret files removed.")
    print("NOTE: Decommissioned is terminal; re-establishing the fixture requires the runbook's full-fixture reset.")
    return 0


# ----------------------------------------------------------------------------------------------
# entrypoint
# ----------------------------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="b5_standing_topology",
        description="B5-4 standing local physical topology operator harness (plan/apply/status/teardown).",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("plan", help="read-only sanitized intent (no connection, no mutation)")
    sub.add_parser("apply", help="idempotent: control DDL 001-009 + secret files + real composed onboarding of both tenants")
    sub.add_parser("status", help="read-only fail-closed topology verification (non-zero unless complete)")
    teardown = sub.add_parser("teardown", help="explicit bounded idempotent teardown of the two B5-4 tenants")
    teardown.add_argument("--confirm-b5-teardown", dest="confirm", action="store_true", help="required explicit confirmation")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    handlers: dict = {"plan": cmd_plan, "apply": cmd_apply, "status": cmd_status, "teardown": cmd_teardown}
    try:
        return int(handlers[args.command](args))
    except OpsConfigError as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
