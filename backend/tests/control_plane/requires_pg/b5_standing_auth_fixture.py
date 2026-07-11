"""B5-4A V2 standing authentication fixture extension — operator harness (standalone-only; PRD B5-4A V2).

An OPERATOR TOOL, not application runtime code and not a test: it extends the ESTABLISHED B5-4 standing
local topology with the PERMANENT standing authentication fixture rows that Smoke C V2 will read —

    membership: b5_standing_member -> b5_standing_alpha    (TENANT_AGENT)
    membership: b5_standing_member -> b5_standing_beta     (TENANT_AGENT)
    membership: b5_standing_member -> b5_standing_dormant  (TENANT_AGENT)
    tenant:     b5_standing_dormant                        (Registered / non-Ready; reference-only)

``b5_standing_member`` is a principal IDENTIFIER carried on the membership rows — it is not a separate
Control DB row. The dormant membership is load-bearing: the live Auth Router resolver checks membership
BEFORE readiness, so a non-member is denied ``tenant_access_denied`` regardless of lifecycle — only a
member of a known non-Ready tenant can observe ``tenant_not_ready``. The dormant tenant therefore makes
the membership-gated non-Ready denial reachable through the real standing Control DB, while the
unknown-tenant denial needs no row at all.

Commands (stdlib argparse; work happens ONLY after an explicit subcommand — import performs no I/O):

    plan      read-only: original B5-4 6/6 status + exact classification of each intended row
              (ABSENT / EXACT / CONFLICTING) + whether apply is additive or a no-op. No mutation.
    apply     idempotent, additive-only, fail-closed: requires original B5-4 status 6/6 first,
              exact-preflights all four rows, refuses on ANY conflict before writing, then creates only
              the ABSENT rows through the SUPPORTED APIs — ``cp.registry.register_tenant`` (the dormant
              tenant; exactly one permanent RegisterTenant audit row on first creation, zero on re-apply)
              and ``cp.membership.add_membership`` (the three memberships; unaudited by design). Runs
              status at the end. A second apply is a proven no-op (zero new rows, zero new audit rows).
    status    read-only, fail-closed: first re-verifies the ORIGINAL B5-4 topology 6/6 (subprocess,
              status-only argv), then proves the extension obligations independently. Non-zero unless
              everything holds.

There is deliberately NO removal command: the fixture is permanent, the ControlStore port has no row
deletion, and the audit history is append-only by database trigger. No direct SQL mutation exists here —
the ONLY raw SQL is the single read-only ``pg_database`` absence probe; every other read goes through the
ControlStore port and the real ``ControlPlaneReadService`` read edge.

COMPOSITION POSTURE (control-store-standalone; PRD 07D-2a RULE 2). The effectful/status commands set
``SP2_CP_CONTROL_STORE=postgres`` and FORCE the three live-side selectors to ``in_memory`` in-process, so
the composed plane is the durable registry/audit posture with a deny-guarded onboarding/recovery surface
(mixed effective posture) — this operator is physically incapable of provisioning a tenant database or
applying a tenant schema, and it refuses to proceed unless that guard is actually composed. The dormant
tenant's ``database_association_ref`` (``tenant/b5_standing_dormant/dsn`` @ ``1``) stays a DANGLING
canonical reference: no matching secret file, no matching secret env key, no physical database, no tenant
schema, and no federation row is ever created (the federation reference is a string on the tenant row).

DRIVER CONTAINMENT. No static database-driver import: psycopg is located via importlib at call time;
provider CLASSES are imported lazily inside commands. Module import is inert (no I/O, no env mutation, no
connection). The original B5-4 harness is NEVER imported — its status is invoked ONLY as a subprocess
with status-only argv. Runbook: ``infrastructure/runbooks/b5_standing_auth_fixture.md`` (invoked from
``backend/`` as ``python tests/control_plane/requires_pg/b5_standing_auth_fixture.py <command>``).

SECRET HYGIENE (D-14). DSNs are resolved in-memory by reference and NEVER printed, logged, or returned;
connection errors carry a redacted identity only (scheme+host+port+database). This tool writes no file.

NO OVERCLAIM. This tool extends a LOCAL PRECONDITION FIXTURE. It is not Smoke C, not a served-request
proof, and not physical-database proof. Smoke C has not been executed. B5-BLK-4 remains OPEN; the
Physical Multi-Database MVP remains mandatory and is NOT completed by this harness.
"""

from __future__ import annotations

import argparse
import importlib
import os
import pathlib
import subprocess
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlsplit

_THIS = pathlib.Path(__file__).resolve()
_BACKEND_ROOT = _THIS.parents[3]
_REPO_ROOT = _THIS.parents[4]
sys.path.insert(0, str(_BACKEND_ROOT))  # backend on path (the requires_pg harness idiom); no package import happens at module scope

# The ORIGINAL B5-4 topology operator (same directory). Never imported — subprocess status-only.
_B5_4_OPS = _THIS.parent / "b5_standing_topology.py"
_B5_4_STATUS_COMMAND = "status"  # the ONLY B5-4 subcommand this operator may ever invoke
_B5_4_PASS_COUNT = 6

# The EXACT permanent standing record set (PRD B5-4A V2 §7.3). The principal is an identifier, not a row.
PRINCIPAL = "b5_standing_member"
READY_TENANT_IDS: Tuple[str, str] = ("b5_standing_alpha", "b5_standing_beta")
DORMANT_TENANT_ID = "b5_standing_dormant"
MEMBERSHIP_TENANT_IDS: Tuple[str, str, str] = ("b5_standing_alpha", "b5_standing_beta", "b5_standing_dormant")
_ROLE_VALUE = "TENANT_AGENT"
_ORG_REF = "b5_standing_org"
_FED_REF = "b5_standing_fed"
_SCHEMA_VERSION = "1"
_ACTOR = "b5_standing_auth_fixture_ops"
_CORRELATION_ID = "b5-4a-apply-b5_standing_dormant"
_SECRET_DIR_ENV = "SNACKPORTAL_TENANT_SECRET_DIR"  # EXISTING shared-convention name (no new env variable)

# The exact dormant registry row (field-level; preflight/status compare EXACTLY — drift fails closed
# because both supported write APIs would otherwise silently mask it). The association reference is the
# canonical convention value; commands re-derive it via onboarding.tenant_dsn_ref and REFUSE on drift.
_EXPECTED_DORMANT_ROW: Dict[str, str] = {
    "lifecycle_state": "Registered",
    "organization_ref": _ORG_REF,
    "expected_schema_version": _SCHEMA_VERSION,
    "federation_config_ref": _FED_REF,
    "assoc_store_ref": "tenant/b5_standing_dormant/dsn",
    "assoc_version": "1",
}

ABSENT = "ABSENT"
EXACT = "EXACT"
CONFLICTING = "CONFLICTING"

_SMOKE_PREFIX = "smoke" + "_c_"  # built dynamically so no temporary-row identifier literal exists here

# The ONLY raw SQL in this module: the read-only physical-database absence probe (no port exposes it).
_PG_DATABASE_SQL = "SELECT 1 FROM pg_database WHERE datname = %s"


class OpsConfigError(Exception):
    """Non-sensitive operator-configuration/refusal error (never carries a DSN or secret value)."""


def _psycopg() -> Any:
    """The database driver, located at call time (no static import — Driver Containment Standard)."""
    return importlib.import_module("psycopg")


def _redacted(dsn: str) -> str:
    """Non-sensitive connection identity: scheme + host + port + database. NEVER userinfo/query (D-14)."""
    parts = urlsplit(dsn)
    host = parts.hostname or ""
    port = f":{parts.port}" if parts.port else ""
    return f"{parts.scheme}://{host}{port}{parts.path}"


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
    Needed READ-ONLY here (the no-dormant-secret-material probe); this tool never writes under it."""
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


def _dormant_ref() -> Any:
    """The canonical dangling dormant association reference, RE-DERIVED from the live convention and
    coherence-checked against the pinned expectation (fail closed on convention drift)."""
    from control_plane.onboarding import tenant_dsn_ref
    from shared.secrets import SecretRef

    store_ref = tenant_dsn_ref(DORMANT_TENANT_ID)
    if store_ref != _EXPECTED_DORMANT_ROW["assoc_store_ref"]:
        raise OpsConfigError("canonical tenant DSN reference convention drifted from the pinned expectation — refused")
    return SecretRef(store_ref=store_ref, version=_EXPECTED_DORMANT_ROW["assoc_version"])


def _dormant_target() -> str:
    """The WOULD-BE dormant database name (absence-asserted, never created)."""
    from control_plane.provisioning import tenant_database_name

    return tenant_database_name(DORMANT_TENANT_ID)


def _compose_control_store_standalone_plane() -> Any:
    """Compose the control-store-standalone plane (PRD 07D-2a RULE 2): durable ControlStore ONLY.

    The three live-side selectors are FORCED to ``in_memory`` in-process — an outer all-postgres shell
    can never smuggle a live provisioning side into this operator — so the effective posture is MIXED
    and ``create_app()`` wraps the onboarding/recovery surface in the fail-closed deny facades. Both
    facts are then ASSERTED (defense in depth): this operator refuses to run on a plane that could
    provision, apply schema, or lose its writes to a volatile store."""
    from control_plane import main as cp_main

    os.environ[cp_main.CONTROL_STORE_ENV] = "postgres"
    for name in (cp_main.PROVISIONING_ADAPTER_ENV, cp_main.TENANT_SCHEMA_APPLICATOR_ENV, cp_main.DISTINCTNESS_LEDGER_ENV):
        os.environ[name] = "in_memory"
    cp = cp_main.create_app()
    if type(cp.store).__name__ != "PostgresControlStore":
        raise OpsConfigError("composed plane is not backed by the durable ControlStore — refused (writes would be volatile)")
    if type(cp.onboarding).__name__ != "_MixedPostureOnboardingGuard":
        raise OpsConfigError("composed plane exposes a live onboarding surface — refused (control-store-standalone required)")
    return cp


def _close_plane(cp: Any) -> None:
    """Best-effort close of the durable store's cached connection (the 07D finally idiom)."""
    try:
        if getattr(cp.store, "_conn_cache", None) is not None:
            cp.store._conn_cache.close()
    except Exception:
        pass


# ----------------------------------------------------------------------------------------------
# original B5-4 topology status (subprocess-only; status-only argv)
# ----------------------------------------------------------------------------------------------
def _b5_4_status_argv() -> List[str]:
    """The EXACT original-B5-4 invocation: status-only argv. No other subcommand token is
    constructible from this operator (the B5-5 no-new-invocation census stays intact: subprocess,
    never an import)."""
    return [sys.executable, str(_B5_4_OPS), _B5_4_STATUS_COMMAND]


def _b5_4_status() -> Tuple[int, str]:
    proc = subprocess.run(
        _b5_4_status_argv(),
        cwd=str(_BACKEND_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def _b5_4_status_problem(exit_code: int, output: str) -> Optional[str]:
    """None iff the original B5-4 standing topology reports the complete 6/6 PASS set."""
    if exit_code != 0:
        return f"original B5-4 status exited {exit_code}"
    if output.count("PASS:") != _B5_4_PASS_COUNT or "STATUS OK" not in output:
        return "original B5-4 status output does not show the complete 6/6 PASS set"
    return None


# ----------------------------------------------------------------------------------------------
# pure classification / evaluation predicates (exercised by the default-suite boundary guard)
# ----------------------------------------------------------------------------------------------
def intended_rows() -> Tuple[str, ...]:
    """The EXACT four intended permanent rows, as identity keys. There is no fifth row."""
    return tuple(f"membership:{tid}" for tid in MEMBERSHIP_TENANT_IDS) + (f"tenant:{DORMANT_TENANT_ID}",)


def _membership_classification(existing_role_value: Optional[str]) -> str:
    if existing_role_value is None:
        return ABSENT
    return EXACT if existing_role_value == _ROLE_VALUE else CONFLICTING


def _tenant_classification(snapshot: Optional[Dict[str, str]]) -> str:
    if snapshot is None:
        return ABSENT
    return EXACT if snapshot == _EXPECTED_DORMANT_ROW else CONFLICTING


def _evaluate(facts: Dict[str, Any]) -> List[Tuple[str, Optional[str]]]:
    """The independent extension status obligations, evaluated over a gathered facts snapshot.

    Pure (no I/O): the boundary guard feeds mutant snapshots and requires each named check to fail."""

    def membership_problem(tid: str) -> Optional[str]:
        role = facts["membership_roles"].get(tid)
        if role is None:
            return "membership row absent"
        if role != _ROLE_VALUE:
            return f"membership role is {role!r}, expected {_ROLE_VALUE!r}"
        return None

    def tenant_problem() -> Optional[str]:
        classification = _tenant_classification(facts["dormant_row"])
        if classification == EXACT:
            return None
        return f"dormant registry row is {classification}"

    def ready_false_problem() -> Optional[str]:
        state = facts["dormant_read_state"]
        if state is None:
            return "dormant tenant not visible at the read edge"
        if state.get("lifecycle_state") != "Registered":
            return f"lifecycle is {state.get('lifecycle_state')!r}, expected 'Registered'"
        if state.get("ready") is not False:
            return "read edge does not serve ready=false"
        return None

    def precondition_problem() -> Optional[str]:
        # The EXACT resolver precondition triple (membership-before-readiness): tenant row visible
        # AND the principal is a member AND ready is false — only then is the auth-boundary
        # non-Ready denial reachable instead of the non-member denial.
        if facts["dormant_read_state"] is None:
            return "tenant row not visible (resolver would deny as unknown/non-member)"
        if not facts["dormant_member"]:
            return "principal is NOT a member (resolver would deny tenant_access_denied)"
        if facts["dormant_read_state"].get("ready") is not False:
            return "tenant is not non-Ready at the read edge"
        return None

    def canonical_ref_problem() -> Optional[str]:
        row = facts["dormant_row"]
        if row is None:
            return "dormant registry row absent"
        expected = (_EXPECTED_DORMANT_ROW["assoc_store_ref"], _EXPECTED_DORMANT_ROW["assoc_version"])
        actual = (row.get("assoc_store_ref"), row.get("assoc_version"))
        if actual != expected:
            return f"association is {actual!r}, expected {expected!r}"
        return None

    def secret_material_problem() -> Optional[str]:
        present = []
        if facts["dormant_secret_file"]:
            present.append("secret file exists under the tenant-secret root")
        if facts["dormant_secret_env"]:
            present.append("secret env key is set")
        if facts["cp_adapter_resolves"]:
            present.append("control-plane secret adapter resolves the dormant reference")
        if facts["dbr_adapter_resolves"]:
            present.append("database-router secret adapter resolves the dormant reference")
        return "; ".join(present) if present else None

    def database_problem() -> Optional[str]:
        if facts["dormant_database_present"]:
            return "the would-be dormant database EXISTS (must remain absent; schema implied)"
        return None

    def audit_problem() -> Optional[str]:
        rows = facts["register_audit"]
        if len(rows) != 1:
            return f"{len(rows)} RegisterTenant audit row(s) for the dormant tenant, expected exactly 1"
        row = rows[0]
        expected = {"actor": _ACTOR, "from_state": None, "to_state": "Registered"}
        if row != expected:
            return f"audit provenance is {row!r}, expected {expected!r}"
        return None

    def smoke_problem() -> Optional[str]:
        count = facts["smoke_residue_count"]
        return f"{count} {_SMOKE_PREFIX}* residue row(s) found" if count else None

    def unrelated_problem() -> Optional[str]:
        if facts["membership_count"] != len(MEMBERSHIP_TENANT_IDS):
            return f"{facts['membership_count']} membership row(s), expected exactly {len(MEMBERSHIP_TENANT_IDS)}"
        expected_tenants = sorted((*READY_TENANT_IDS, DORMANT_TENANT_ID))
        if sorted(facts["tenant_ids"]) != expected_tenants:
            return f"tenant registry is {sorted(facts['tenant_ids'])!r}, expected exactly {expected_tenants!r}"
        return None

    return [
        ("alpha membership exact", membership_problem(READY_TENANT_IDS[0])),
        ("beta membership exact", membership_problem(READY_TENANT_IDS[1])),
        ("dormant membership exact", membership_problem(DORMANT_TENANT_ID)),
        ("dormant tenant exact", tenant_problem()),
        ("dormant ready=false through real read service", ready_false_problem()),
        ("dormant tenant produces the membership-gated non-Ready precondition", precondition_problem()),
        ("dormant canonical reference exact", canonical_ref_problem()),
        ("no dormant secret material", secret_material_problem()),
        ("no dormant physical database or tenant schema", database_problem()),
        ("exactly one permanent RegisterTenant audit row", audit_problem()),
        (f"zero {_SMOKE_PREFIX} residue", smoke_problem()),
        ("no unrelated standing rows (exactly three memberships; exactly the three standing tenants)", unrelated_problem()),
    ]


# ----------------------------------------------------------------------------------------------
# live snapshot gathering (ControlStore port + read edge; the single pg_database probe)
# ----------------------------------------------------------------------------------------------
def _membership_role(cp: Any, tenant_id: str) -> Optional[str]:
    rows = cp.store.list_memberships(principal_ref=PRINCIPAL, tenant_id=tenant_id)
    if not rows:
        return None
    return str(rows[0].role.value)


def _tenant_snapshot(cp: Any) -> Optional[Dict[str, str]]:
    rec = cp.store.get_tenant(DORMANT_TENANT_ID)
    if rec is None:
        return None
    return {
        "lifecycle_state": rec.lifecycle_state.value,
        "organization_ref": rec.organization_ref,
        "expected_schema_version": rec.expected_schema_version,
        "federation_config_ref": rec.federation_config_ref,
        "assoc_store_ref": rec.database_association_ref.store_ref,
        "assoc_version": rec.database_association_ref.version,
    }


def _preflight(cp: Any) -> Dict[str, str]:
    """Read-only exact classification of each of the FOUR intended rows."""
    result: Dict[str, str] = {}
    for tid in MEMBERSHIP_TENANT_IDS:
        result[f"membership:{tid}"] = _membership_classification(_membership_role(cp, tid))
    result[f"tenant:{DORMANT_TENANT_ID}"] = _tenant_classification(_tenant_snapshot(cp))
    return result


def _adapter_resolves(store: Any, ref: Any) -> bool:
    try:
        store.resolve(ref)
    except (LookupError, PermissionError):
        return False
    return True


def _gather_facts(cp: Any, admin_dsn: str, secret_dir: pathlib.Path) -> Dict[str, Any]:
    from control_plane.adapters.providers.env_tenant_dsn_secret_store import EnvTenantDsnSecretStore
    from control_plane.read_api import ControlPlaneReadService
    from database_router.adapters.providers.env_tenant_secret_store import EnvTenantSecretStore

    ref = _dormant_ref()
    reader = ControlPlaneReadService(cp.store)
    all_memberships = cp.store.list_memberships()
    tenant_ids = [str(t) for t in cp.store.list_tenant_ids()]
    audit_rows = cp.store.list_audit()
    register_audit = [
        {"actor": rec.actor, "from_state": rec.from_state, "to_state": rec.to_state}
        for rec in audit_rows
        if rec.tenant_id == DORMANT_TENANT_ID and rec.action == "RegisterTenant"
    ]
    smoke_residue = (
        sum(1 for t in tenant_ids if t.startswith(_SMOKE_PREFIX))
        + sum(1 for m in all_memberships if m.principal_ref.startswith(_SMOKE_PREFIX) or m.tenant_id.startswith(_SMOKE_PREFIX))
        + sum(1 for rec in audit_rows if (rec.tenant_id or "").startswith(_SMOKE_PREFIX) or rec.actor.startswith(_SMOKE_PREFIX))
    )
    secret_file = secret_dir / f"{ref.store_ref}@{ref.version}"
    env_key = EnvTenantDsnSecretStore._env_key(ref.store_ref, ref.version)
    conn = _connect(admin_dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(_PG_DATABASE_SQL, (_dormant_target(),))
            dormant_database_present = cur.fetchone() is not None
    finally:
        conn.close()
    return {
        "membership_roles": {tid: _membership_role(cp, tid) for tid in MEMBERSHIP_TENANT_IDS},
        "membership_count": len(all_memberships),
        "tenant_ids": tenant_ids,
        "dormant_row": _tenant_snapshot(cp),
        "dormant_read_state": reader.tenant_state(DORMANT_TENANT_ID),
        "dormant_member": bool(reader.is_member(PRINCIPAL, DORMANT_TENANT_ID)["member"]),
        "register_audit": register_audit,
        "dormant_secret_file": secret_file.is_file(),
        "dormant_secret_env": env_key in os.environ,
        "cp_adapter_resolves": _adapter_resolves(EnvTenantDsnSecretStore(), ref),
        "dbr_adapter_resolves": _adapter_resolves(EnvTenantSecretStore(), ref),
        "dormant_database_present": dormant_database_present,
        "smoke_residue_count": smoke_residue,
    }


# ----------------------------------------------------------------------------------------------
# plan
# ----------------------------------------------------------------------------------------------
def cmd_plan(_args: argparse.Namespace) -> int:
    _resolve_dsns()  # config completeness (fail closed before reporting intent)
    _validated_secret_dir()
    print("B5-4A V2 standing auth fixture — PLAN (read-only; no mutation)")
    failures = 0
    code, out = _b5_4_status()
    problem = _b5_4_status_problem(code, out)
    if problem is None:
        print("  B5-4 STATUS = 6/6 PASS")
    else:
        failures += 1
        print(f"  FAIL: original B5-4 standing topology — {problem}")
    cp = _compose_control_store_standalone_plane()
    try:
        pre = _preflight(cp)
    finally:
        _close_plane(cp)
    print(f"  principal : {PRINCIPAL} (identifier only — not a separate Control DB row)")
    for key in intended_rows():
        print(f"  row {key} -> {pre[key]}")
    ref = _dormant_ref()
    print(f"  dormant canonical reference : {ref.store_ref}@{ref.version} (dangling by design — reference only)")
    print(f"  dormant would-be database   : {_dormant_target()} (must remain ABSENT; never created)")
    if any(v == CONFLICTING for v in pre.values()):
        failures += 1
        print("  apply intent : FAIL CLOSED — conflicting standing row(s); apply will refuse before writing")
    elif all(v == EXACT for v in pre.values()):
        print("  apply intent : no-op (all four rows already exact)")
    else:
        print(f"  apply intent : additive ({sum(1 for v in pre.values() if v == ABSENT)} absent row(s) to create)")
    print("  no physical database, no secret material, no tenant schema, and no federation row will be created")
    if failures:
        print(f"PLAN FAILED ({failures} problem(s))")
        return 1
    print("PLAN OK")
    return 0


# ----------------------------------------------------------------------------------------------
# apply
# ----------------------------------------------------------------------------------------------
def cmd_apply(_args: argparse.Namespace) -> int:
    _resolve_dsns()
    _validated_secret_dir()
    print("B5-4A V2 standing auth fixture — APPLY (idempotent, additive-only, fail-closed)")
    code, out = _b5_4_status()
    problem = _b5_4_status_problem(code, out)
    if problem is not None:
        print(f"  FAIL: original B5-4 standing topology — {problem}")
        for line in out.splitlines():
            print(f"    | {line}")
        print("APPLY REFUSED — the established B5-4 standing topology is a hard precondition (zero writes)")
        return 1
    print("  B5-4 STATUS = 6/6 PASS")

    from control_plane.records import Role, TenantLifecycleState

    cp = _compose_control_store_standalone_plane()
    try:
        pre = _preflight(cp)
        for key in intended_rows():
            print(f"  preflight {key} -> {pre[key]}")
        if any(v == CONFLICTING for v in pre.values()):
            print("APPLY REFUSED — conflicting standing row(s); fail closed, zero writes")
            return 1
        if pre[f"tenant:{DORMANT_TENANT_ID}"] == ABSENT:
            rec = cp.registry.register_tenant(
                tenant_id=DORMANT_TENANT_ID,
                organization_ref=_ORG_REF,
                expected_schema_version=_SCHEMA_VERSION,
                database_association_ref=_dormant_ref(),
                federation_config_ref=_FED_REF,
                actor=_ACTOR,
                correlation_id=_CORRELATION_ID,
            )
            if rec.lifecycle_state is not TenantLifecycleState.REGISTERED:
                raise OpsConfigError(f"registered dormant tenant landed in {rec.lifecycle_state.value!r}, not Registered — fail closed")
            print(f"  created tenant {DORMANT_TENANT_ID} -> Registered (association {_EXPECTED_DORMANT_ROW['assoc_store_ref']}@1)")
        else:
            print(f"  tenant {DORMANT_TENANT_ID} already exact — no write, no new audit row")
        for tid in MEMBERSHIP_TENANT_IDS:
            if pre[f"membership:{tid}"] == ABSENT:
                cp.membership.add_membership(principal_ref=PRINCIPAL, tenant_id=tid, role=Role.TENANT_AGENT)
                print(f"  created membership {PRINCIPAL} -> {tid} ({_ROLE_VALUE})")
            else:
                print(f"  membership {PRINCIPAL} -> {tid} already exact — no write")
    finally:
        _close_plane(cp)
    print("APPLY OK — standing auth fixture rows converged (no database, schema, secret, or federation side effect)")
    return cmd_status(_args)


# ----------------------------------------------------------------------------------------------
# status
# ----------------------------------------------------------------------------------------------
def cmd_status(_args: argparse.Namespace) -> int:
    _control_dsn, admin_dsn = _resolve_dsns()
    del _control_dsn  # the plane resolves its own store DSN by reference; only the admin probe needs a DSN here
    secret_dir = _validated_secret_dir()
    print("B5-4A V2 standing auth fixture — STATUS (read-only; fail-closed)")
    failures = 0
    code, out = _b5_4_status()
    problem = _b5_4_status_problem(code, out)
    if problem is None:
        print("  B5-4 STATUS = 6/6 PASS")
    else:
        failures += 1
        print(f"  FAIL: original B5-4 standing topology — {problem}")
        for line in out.splitlines():
            print(f"    | {line}")
    cp = _compose_control_store_standalone_plane()
    try:
        facts = _gather_facts(cp, admin_dsn, secret_dir)
    finally:
        _close_plane(cp)
    for name, check_problem in _evaluate(facts):
        if check_problem is None:
            print(f"  PASS: {name}")
        else:
            failures += 1
            print(f"  FAIL: {name} — {check_problem}")
    if failures:
        print(f"STATUS FAILED ({failures} check(s) not holding)")
        return 1
    print("STATUS OK — standing auth fixture complete (original B5-4 topology preserved)")
    return 0


# ----------------------------------------------------------------------------------------------
# entrypoint
# ----------------------------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="b5_standing_auth_fixture",
        description="B5-4A V2 standing authentication fixture extension (plan/apply/status; permanent, additive-only).",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("plan", help="read-only intended-row classification + original B5-4 status (no mutation)")
    sub.add_parser("apply", help="idempotent additive-only convergence of the four permanent rows (fail-closed preflight)")
    sub.add_parser("status", help="read-only fail-closed verification (non-zero unless everything holds)")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    handlers: dict = {"plan": cmd_plan, "apply": cmd_apply, "status": cmd_status}
    try:
        return int(handlers[args.command](args))
    except OpsConfigError as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
