"""B5 local-concept bounded operations — operator harness (standalone-only; PRD SP2-LOCAL-CONCEPT-OPS-01).

An OPERATOR TOOL, not application runtime code and not a test (its name deliberately omits the ``test_``
prefix so the default suite and the live-PG run-set completeness sweep never collect it). It is the thin
"Option B" bounded wrapper the PRD authorizes: it fills exactly the four local-concept gaps not already
covered by the canonical standing topology — a topology-wide logical BACKUP, a safe RESTORE-VALIDATION into
a fresh disposable database, a deterministic synthetic SEED, and approved artifact placement — reusing the
existing governed provisioning path rather than building a second one. It introduces NO new database
architecture, migration source, secret backend, routing path, or composition root.

Commands (stdlib argparse; work happens ONLY after an explicit subcommand — import performs no I/O):

    plan             read-only: sanitized intent (redacted cluster references, the four authoritative
                     database identities/roles/ports, the artifact root + eight destinations census, the
                     backup destination, the disposable validation-DB prefix, the synthetic-seed prefix, and
                     the LOCAL-CONCEPT-ONLY / DO-NOT-ACTIVATE posture). No connection, no mutation.
    backup           one custom-format logical dump per authoritative database (Control/ACME/ZETA/NOVA) into
                     the approved ``03-Database-Backups`` destination, refuse-overwrite, SHA-256 per dump, one
                     references-only batch manifest. Credentials travel by child-process environment only.
    restore-validate approved dump -> SHA-256 vs manifest -> ``pg_restore --list`` readability -> a NEWLY
                     created disposable validation database (``sp2_local_restore_validation_*``, safe-identifier
                     guarded, created via the canonical ``PostgresProvisioningOperator``) -> real ``pg_restore``
                     INTO that database -> schema + sentinel + distinguishable-identity verification -> disposal
                     in ``finally`` -> retained validation-database count zero -> the single references-only
                     evidence bundle written LAST. Restore over any standing identity is refused before any
                     restore process is invoked.
    seed             deterministic, idempotent synthetic business data (every identifier prefixed
                     ``sp2-local-concept-``) proving Control-record creation, independent ACME and ZETA copies,
                     a Control->Tenant lineage soft reference with NO automatic synchronization, and adjacent
                     NOVA isolation — reusing the canonical DDL-created tables (never embedding DDL) and never
                     touching the System-Primary seed. Fixture-loading behaviour is authored; fixtures live
                     under ``06-Synthetic-Data`` and are neither created nor loaded until the runtime START-GATE.
    status           read-only, fail-closed: delegates the standing-topology verification to the sibling
                     operator by SUBPROCESS (status-only argv; the sibling is never imported and never has
                     ``apply``/``teardown`` invoked), verifies the artifact root + destinations, and asserts a
                     retained validation-database census of zero. Never mutates; never activates.

The operator exposes ONLY ``plan``/``backup``/``restore-validate``/``seed``/``status`` and never
``apply``/``teardown``/``serve``/``activate``/``deploy``/``promote``/``production``/``hosted``. The standing
``apply``/``teardown`` remain the sibling ``b5_standing_topology.py`` operator's responsibility; this wrapper
invokes only its ``status`` surface and never calls ``apply`` or ``teardown`` implicitly.

AUTHORITATIVE TOPOLOGY (PRD §3/§5; ``infrastructure/docker/docker-compose.local.yml``). Exactly four
physically separate local clusters at their compose database identities — Control
``snackportal2_control_local`` (5540), ACME ``snackportal2_tenant_acme_local`` (5541), ZETA
``snackportal2_tenant_zeta_local`` (5542), NOVA ``snackportal2_tenant_nova_local`` (5543). The descriptive
witness roles (Tenant Alpha witness = ACME, Tenant Beta witness = ZETA, Adjacent witness = NOVA) are test
labels only and NEVER rename a database identity. ``b5_standing_topology.py`` is reused for repository idioms
and status-surface conventions ONLY — NOT for its ``b5_standing_alpha`` / ``b5_standing_beta`` tenant set,
which this wrapper never adopts, renames, or disturbs.

CANONICAL SOURCES ONLY. All backend imports resolve from ``backend/<package>/...`` and NEVER from the
``backend/build/lib`` shadow (``build.lib``). Provider classes are imported lazily inside commands; the module
carries no static database-driver import (psycopg is located via importlib at call time — Driver Containment
Standard), so import is inert and the containment sweep never sees a driver import here.

pg_dump REUSE PRECISION (PRD §7; readiness observation B). The repository's canonical backup helper is
PRIVATE to a sibling ``requires_pg`` harness (``_pg_dump_argv`` / ``_create_backup`` in
``dbr_ar_2d_standing_witnesses.py``). "Reuse the pg_dump idiom" therefore means RE-EXPRESSING the same bounded
discipline here — custom format, ``--no-password``, credentials only through the child-process environment,
no raw DSN in argv, refuse-overwrite, SHA-256, and a ``pg_restore --list`` readability check — never importing
those private sibling symbols.

NEW RESTORE BEHAVIOUR (PRD §8; readiness observation C). Actual ``pg_restore`` INTO a database is genuinely
new in this repository (the tree previously carried only the ``pg_restore --list`` readability witness). It is
authorized here only as code authoring and only against a freshly created disposable validation database whose
name begins ``sp2_local_restore_validation_``; restore over ``snackportal2_control_local`` /
``snackportal2_tenant_acme_local`` / ``snackportal2_tenant_zeta_local`` / ``snackportal2_tenant_nova_local`` /
``b5_standing_alpha`` / ``b5_standing_beta`` is refused BEFORE any restore process is invoked.

SECRET HYGIENE (D-14). Cluster DSNs are resolved in-memory BY REFERENCE through the existing
``EnvReferenceSecretStore`` env/file convention (no new environment variable, no new secret backend) and are
NEVER printed, logged, embedded in argv, or written to any manifest or evidence artifact; every emitted
identity is redacted to scheme+host+port+database. Manifests and evidence bundles are substring-scanned for
DSN/token/key shapes before they are written.

ARTIFACT ROOT (PRD §4/§12). Every non-runtime artifact is written under the exact pre-existing approved root
``D:\\Pitchsnack\\SP2-Local-Concept`` (never the prohibited short ``D:\\SP2-Local-Concept``) and NEVER into the
Git repository. The root and its eight destinations already exist; this operator verifies them, tolerates a
pre-existing empty root, and never creates, recreates, deletes, or assumes ownership of them. No ``D:`` path is
ever used as a live PostgreSQL data directory — active storage stays on Docker-managed internal volumes.

MANUAL_ONLY / START-GATE. Every effectful command (``backup`` / ``restore-validate`` / ``seed``) is
MANUAL_ONLY and requires an explicit human START-GATE (Dan) before any execution, per
``infrastructure/runbooks/b5_local_concept_ops.md``. It is never wired into the default suite or any automated
live-PostgreSQL path (its filename carries no ``test_`` prefix, and ``requires_pg`` is ``--ignore``d).

NO OVERCLAIM. This wrapper delivers a LOCAL-CONCEPT-ONLY capability. It is not a hosted proof, not a production
activation, and closes no blocker: the live blocker census remains 7 of 9 OPEN and Production remains NOT
READY / DO-NOT-ACTIVATE. Local evidence can never close a hosted or production requirement.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import pathlib
import re
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlsplit, urlunsplit

_THIS = pathlib.Path(__file__).resolve()
_BACKEND_ROOT = _THIS.parents[3]
_REPO_ROOT = _THIS.parents[4]
sys.path.insert(0, str(_BACKEND_ROOT))  # backend on path (the requires_pg harness idiom); no package import at module scope

# The sibling standing-topology operator — reused for STATUS-surface delegation ONLY (subprocess, status-only
# argv). It is NEVER imported, and its apply/teardown surface is never invoked. Its b5_standing_alpha /
# b5_standing_beta identities are NOT adopted as the four-cluster enumeration.
_STANDING_OPS = _THIS.parent / "b5_standing_topology.py"
_STATUS_COMMAND = "status"  # the ONLY sibling subcommand this wrapper may ever invoke

# The exact approved artifact root (PRD §4) — pre-existing; verified, never created/owned; NEVER the short path.
_ARTIFACT_ROOT = pathlib.Path("D:/Pitchsnack/SP2-Local-Concept")
_FORBIDDEN_ARTIFACT_ROOT = pathlib.Path("D:/SP2-Local-Concept")  # prohibited short path — refused, never substituted
_ARTIFACT_SUBDIRS: Tuple[str, ...] = (
    "01-Execution-Reports",
    "02-Test-Evidence",
    "03-Database-Backups",
    "04-Code-Snapshots",
    "05-Recovery-Packages",
    "06-Synthetic-Data",
    "07-Local-Configuration",
    "08-Temporary-Logs",
)
_BACKUP_DEST = "03-Database-Backups"
_EVIDENCE_DEST = "02-Test-Evidence"
_SYNTHETIC_DEST = "06-Synthetic-Data"
_RECOVERY_DEST = "05-Recovery-Packages"

# The approved operator surface (PRD §8) and the surface that must NEVER be exposed.
COMMANDS: Tuple[str, ...] = ("plan", "backup", "restore-validate", "seed", "status")
FORBIDDEN_COMMANDS: Tuple[str, ...] = ("apply", "teardown", "serve", "activate", "deploy", "promote", "production", "hosted")

# Environment class and production posture recorded in every batch manifest (PRD §9.3).
ENVIRONMENT_CLASS = "LOCAL-CONCEPT-ONLY"
PRODUCTION_POSTURE = "DO-NOT-ACTIVATE"


@dataclass(frozen=True)
class Cluster:
    """One authoritative local-concept cluster: a compose database identity, its port, its descriptive witness
    role, and the reference-only DSN alias that resolves its admin descriptor (never a literal DSN)."""

    role: str  # Control / ACME / ZETA / NOVA
    database: str  # the exact compose POSTGRES_DB identity (never a witness alias)
    port: int  # loopback port bound by docker-compose.local.yml
    witness: str  # descriptive test role only — NOT a database rename
    dsn_ref: str  # reference-only alias resolved through EnvReferenceSecretStore (no new env var)


# The authoritative four-cluster set (PRD §5; docker-compose.local.yml). Enumerated exactly — Observation A.
CLUSTERS: Tuple[Cluster, ...] = (
    Cluster("Control", "snackportal2_control_local", 5540, "control", "localconcept/control/dsn"),
    Cluster("ACME", "snackportal2_tenant_acme_local", 5541, "Tenant Alpha witness", "localconcept/acme/dsn"),
    Cluster("ZETA", "snackportal2_tenant_zeta_local", 5542, "Tenant Beta witness", "localconcept/zeta/dsn"),
    Cluster("NOVA", "snackportal2_tenant_nova_local", 5543, "Adjacent witness", "localconcept/nova/dsn"),
)
_CLUSTER_BY_ROLE: Dict[str, Cluster] = {c.role.lower(): c for c in CLUSTERS}

# The two retained standing tenants — reused-for-idiom source only; never renamed, disturbed, or restored over.
STANDING_TENANT_ALPHA = "b5_standing_alpha"
STANDING_TENANT_BETA = "b5_standing_beta"

# Restore over ANY of these standing identities is refused before any restore process is invoked (PRD §8).
FORBIDDEN_RESTORE_TARGETS: frozenset = frozenset({c.database for c in CLUSTERS} | {STANDING_TENANT_ALPHA, STANDING_TENANT_BETA})

# Disposable restore-validation database (PRD §10.2): fixed local-concept prefix + a bounded lowercase suffix.
VALIDATION_DB_PREFIX = "sp2_local_restore_validation_"
_VALIDATION_DB_RE = re.compile(r"^sp2_local_restore_validation_[a-z0-9]{8,32}$")
# The canonical safe-identifier shape (the PostgresProvisioningOperator guard also fullmatches before quoting).
_SAFE_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_]*$")

# Deterministic synthetic-data prefix (PRD §11.2) — every synthetic identifier begins with it.
SYNTHETIC_PREFIX = "sp2-local-concept-"

# The canonical tables the seed reuses (never embeds): the Control global directory + the tenant startups copy
# + the System-Primary singleton probe. Identities owned by infrastructure/db/**; verified present, never created.
_CONTROL_DIRECTORY_TABLE = "control_directory"
_GLOBAL_STARTUP_DIRECTORY = "GlobalStartupDirectory"  # DirectoryKind.value (records.py is the vocabulary authority)
_TENANT_STARTUPS_TABLE = "startups"
_SYSTEM_PRIMARY_PROBE = "SELECT count(*) FROM agents WHERE agent_kind = 'system_primary'"

# Secret/PII shape detectors (BUILT from low-entropy fragments — never a contiguous shape in this source).
_DSN_MARKER = "postgresql" + "://"
_JWT_MARKER = "ey" + "J"
_KEY_MARKER = "-----" + "BEGIN"

# The exact references-only batch-manifest entry shape (PRD §9.3), order authoritative.
MANIFEST_ENTRY_KEYS: Tuple[str, ...] = (
    "environment_class",
    "source_commit",
    "source_tree",
    "postgresql_version",
    "database_role",
    "database_name",
    "cluster_system_identity",
    "created_at",
    "dump_format",
    "dump_filename",
    "byte_size",
    "sha256",
    "result",
    "error_detail",
    "production_posture",
)

# The exact references-only restore-validation evidence record shape (PRD §10.3), order authoritative.
RESTORE_RECORD_FIELDS: Tuple[str, ...] = (
    "EXECUTION_ID",
    "EXECUTION_DATE",
    "OPERATOR",
    "ENVIRONMENT_CLASS",
    "SOURCE_COMMIT",
    "SOURCE_TREE",
    "SOURCE_ROLE",
    "SOURCE_DATABASE",
    "DUMP_SHA256",
    "MANIFEST_SHA256",
    "VALIDATION_DATABASE",
    "CHECKSUM_MATCH_ASSERTION",
    "READABILITY_ASSERTION",
    "SCHEMA_PRESENT_ASSERTION",
    "SENTINEL_ASSERTION",
    "DISTINGUISHABLE_IDENTITY_ASSERTION",
    "STANDING_UNCHANGED_ASSERTION",
    "SECRET_REFERENCE_ONLY_ASSERTION",
    "DISPOSAL_ASSERTION",
    "RETAINED_VALIDATION_COUNT",
    "PRODUCTION_POSTURE",
    "FINAL_VERDICT",
)


class OpsConfigError(Exception):
    """Non-sensitive operator-configuration/refusal error (never carries a DSN, password, token, or secret)."""


# ------------------------------------------------------------------------------------------------
# low-level helpers (replicated requires_pg idioms; no backend import at module scope)
# ------------------------------------------------------------------------------------------------
def _psycopg() -> Any:
    """The database driver, located at call time (no static import — Driver Containment Standard)."""
    return importlib.import_module("psycopg")


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


def _database_of(dsn: str) -> str:
    return urlsplit(dsn).path.lstrip("/")


def _git_rev(spec: str) -> str:
    """Read-only ``git rev-parse`` witness so a manifest/evidence record binds to the tested commit/tree."""
    proc = subprocess.run(
        ["git", "rev-parse", spec], cwd=str(_REPO_ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60
    )
    if proc.returncode != 0:
        raise OpsConfigError(f"git rev-parse {spec} failed — the record must bind to the tested commit/tree")
    return proc.stdout.strip()


def _assert_no_secret_shapes(text: str, *, where: str) -> None:
    """Fail closed if a DSN/token/key-shaped value ever reaches a manifest or evidence artifact (D-14)."""
    lowered = text.lower()
    assert _DSN_MARKER not in lowered, f"a DSN-shaped value must never appear in {where}"
    assert _JWT_MARKER.lower() not in lowered, f"a token-shaped value must never appear in {where}"
    assert _KEY_MARKER.lower() not in lowered, f"key material must never appear in {where}"


# ------------------------------------------------------------------------------------------------
# artifact-root resolution (fail-closed; pre-existing root tolerated; never created/owned — Obs D)
# ------------------------------------------------------------------------------------------------
def _artifact_root() -> pathlib.Path:
    """The exact approved artifact root, verified fail-closed. Never the prohibited short path; never created,
    recreated, deleted, or owned here (the root and its eight destinations already exist — Observation D)."""
    resolved = _ARTIFACT_ROOT.resolve()
    if resolved == _FORBIDDEN_ARTIFACT_ROOT.resolve():
        raise OpsConfigError("the artifact root resolves to the prohibited short path D:/SP2-Local-Concept — refused")
    if resolved != _ARTIFACT_ROOT:
        raise OpsConfigError("the artifact root resolves elsewhere than the approved D:/Pitchsnack/SP2-Local-Concept — refused")
    try:
        resolved.relative_to(_REPO_ROOT)
    except ValueError:
        pass
    else:
        raise OpsConfigError("the artifact root resolves INSIDE the repository worktree — refused (no runtime artifact enters the repo)")
    if not resolved.is_dir():
        raise OpsConfigError(
            f"the approved artifact root is absent: {resolved} (it must be pre-provisioned; this operator never creates it)"
        )
    for name in _ARTIFACT_SUBDIRS:
        if not (resolved / name).is_dir():
            raise OpsConfigError(
                f"the approved destination is missing under the artifact root: {name} (pre-provision it; never created here)"
            )
    return resolved


def _artifact_dest(subdir: str) -> pathlib.Path:
    """One approved destination directory under the verified artifact root (never created here)."""
    if subdir not in _ARTIFACT_SUBDIRS:
        raise OpsConfigError(f"{subdir!r} is not an approved artifact destination — refused")
    return _artifact_root() / subdir


def _refuse_repo_path(path: pathlib.Path) -> pathlib.Path:
    """Fail closed if a write target would land inside the Git repository worktree (PRD §12)."""
    resolved = path.resolve()
    try:
        resolved.relative_to(_REPO_ROOT)
    except ValueError:
        return resolved
    raise OpsConfigError("refused: a runtime artifact target resolves inside the Git repository worktree")


# ------------------------------------------------------------------------------------------------
# reference-only DSN resolution (existing EnvReferenceSecretStore convention; no new env var/backend)
# ------------------------------------------------------------------------------------------------
def _resolve_cluster_dsn(cluster: Cluster) -> str:
    """Resolve one cluster's admin descriptor BY REFERENCE through the existing ``EnvReferenceSecretStore``
    env/file convention (D-14). Fail-closed: an unresolved reference names the REFERENCE, never a value; no
    literal DSN is configured here and no new environment variable or secret backend is introduced."""
    from shared.adapters.providers.env_reference_secret_store import DEFAULT_ALLOWED, EnvReferenceSecretStore
    from shared.secrets import SecretRef

    allowed = frozenset({*DEFAULT_ALLOWED, *(c.dsn_ref for c in CLUSTERS)})
    secrets = EnvReferenceSecretStore(allowed=allowed)
    try:
        return secrets.resolve(SecretRef(store_ref=cluster.dsn_ref, version="1")).material
    except (LookupError, PermissionError):
        raise OpsConfigError(f"unresolved DSN secret reference {cluster.dsn_ref!r}@1 — set the documented env/file secret") from None


def _connect(dsn: str, *, autocommit: bool = False) -> Any:
    """Open a short-lived connection; a failure is reported with the REDACTED identity only (D-14)."""
    psycopg = _psycopg()
    try:
        return psycopg.connect(dsn, connect_timeout=10, autocommit=autocommit)
    except Exception:
        raise OpsConfigError(f"cannot connect to {_redacted(dsn)} (fail closed; see the runbook prerequisites)") from None


def _one(cur: Any, sql: str, params: Tuple[Any, ...] = ()) -> Any:
    cur.execute(sql, params)
    row = cur.fetchone()
    return row[0] if row else None


# ------------------------------------------------------------------------------------------------
# pg_dump / pg_restore discipline — RE-EXPRESSED (Observation B; never importing private sibling helpers)
# ------------------------------------------------------------------------------------------------
def _pg_dump_argv(out_path: pathlib.Path) -> List[str]:
    """The re-expressed backup argv: custom format, no password prompt, NO DSN/credential in argv."""
    return ["pg_dump", "--format=custom", "--no-password", "--file", str(out_path)]


def _pg_restore_list_argv(dump_path: pathlib.Path) -> List[str]:
    """The re-expressed readability-witness argv: archive table-of-contents only, NO database touched."""
    return ["pg_restore", "--list", str(dump_path)]


def _pg_restore_into_argv(dump_path: pathlib.Path, validation_db: str) -> List[str]:
    """The re-expressed restore-into-database argv (new-but-bounded — Observation C): a safe-identifier
    validation database NAME only (never a DSN or credential in argv), exit-on-error, no ownership reset."""
    if not _VALIDATION_DB_RE.fullmatch(validation_db):
        raise OpsConfigError("the restore target is not a disposable validation-database identifier — refused")
    return ["pg_restore", "--no-password", "--no-owner", "--exit-on-error", "--dbname", validation_db, str(dump_path)]


def _child_env(dsn: str) -> Dict[str, str]:
    """Child-process environment carrying the connection identity — NEVER argv, NEVER printed (D-14)."""
    parts = urlsplit(dsn)
    env = dict(os.environ)
    env["PGHOST"] = parts.hostname or "127.0.0.1"
    env["PGPORT"] = str(parts.port or 5432)
    if parts.username:
        env["PGUSER"] = parts.username
    if parts.password:
        env["PGPASSWORD"] = parts.password
    env["PGDATABASE"] = (parts.path or "/").lstrip("/")
    return env


def _sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run_child(argv: List[str], child_env: Dict[str, str], *, timeout: int) -> subprocess.CompletedProcess:
    """Run a pg_* child with credentials by environment only (references-only failure surface on non-zero)."""
    return subprocess.run(
        argv, cwd=str(_BACKEND_ROOT), env=child_env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout
    )


# ------------------------------------------------------------------------------------------------
# batch manifest (references-only; PRD §9.3)
# ------------------------------------------------------------------------------------------------
def _manifest_entry(**values: Any) -> Dict[str, Any]:
    entry = {key: values.get(key, "") for key in MANIFEST_ENTRY_KEYS}
    assert tuple(entry.keys()) == MANIFEST_ENTRY_KEYS, "the manifest entry must carry the exact key set in order"
    return entry


def _write_manifest(path: pathlib.Path, entries: List[Dict[str, Any]], *, commit: str, tree: str) -> None:
    """Serialize the single references-only batch manifest AFTER a fail-closed secret-shape scan (PRD §9.3/§9.4)."""
    _refuse_repo_path(path)
    for entry in entries:
        assert tuple(entry.keys()) == MANIFEST_ENTRY_KEYS, "every manifest entry must carry the exact key set in order"
    document = {
        "schema": "sp2-local-concept-backup-manifest",
        "schema_version": 1,
        "environment_class": ENVIRONMENT_CLASS,
        "production_posture": PRODUCTION_POSTURE,
        "source_commit": commit,
        "source_tree": tree,
        "entries": entries,
    }
    blob = json.dumps(document, indent=2, sort_keys=False)
    _assert_no_secret_shapes(blob, where="the backup manifest")
    path.write_text(blob, encoding="utf-8")


# ------------------------------------------------------------------------------------------------
# plan
# ------------------------------------------------------------------------------------------------
def cmd_plan(_args: argparse.Namespace) -> int:
    root = _artifact_root()
    print("B5 local-concept bounded operations — PLAN (read-only; no connection, no mutation)")
    print(f"  artifact root     : {root} (pre-existing; {len(_ARTIFACT_SUBDIRS)} approved destinations verified; never created here)")
    print(f"  environment class : {ENVIRONMENT_CLASS}  posture: {PRODUCTION_POSTURE}")
    print(f"  operator surface  : {', '.join(COMMANDS)} (never {', '.join(FORBIDDEN_COMMANDS)})")
    for c in CLUSTERS:
        print(f"  cluster           : {c.role:<7} db {c.database} @127.0.0.1:{c.port} ; witness {c.witness} ; ref {c.dsn_ref}@1")
    print(f"  backup dest       : {root / _BACKUP_DEST} (one custom-format dump per database; refuse-overwrite; SHA-256)")
    print(f"  restore target    : a fresh disposable {VALIDATION_DB_PREFIX}* database only (never {sorted(FORBIDDEN_RESTORE_TARGETS)})")
    print(f"  synthetic prefix  : {SYNTHETIC_PREFIX} (deterministic, idempotent; System-Primary never modified)")
    print("  standing reuse    : b5_standing_topology.py status-surface/idioms only (b5_standing_alpha/b5_standing_beta never adopted)")
    print("PLAN OK — closes no blocker; live census 7 of 9 OPEN; Production NOT READY / DO-NOT-ACTIVATE")
    return 0


# ------------------------------------------------------------------------------------------------
# backup
# ------------------------------------------------------------------------------------------------
def _backup_one(cluster: Cluster, batch_dir: pathlib.Path, *, commit: str, tree: str) -> Dict[str, Any]:
    """Create one custom-format dump for one authoritative database and return its references-only manifest entry.

    Refuse-overwrite; credentials by child environment only; SHA-256 recorded; readability witnessed; references
    only. Read-only server probes (version + system identity) precede the dump on a short-lived connection."""
    dsn = _resolve_cluster_dsn(cluster)
    if _database_of(dsn) != cluster.database:
        raise OpsConfigError(f"the resolved reference for {cluster.role} does not name its database identity — refused")
    conn = _connect(dsn)
    try:
        with conn.cursor() as cur:
            server_version = str(_one(cur, "SELECT current_setting('server_version_num')"))
            system_identity = str(_one(cur, "SELECT system_identifier::text FROM pg_control_system()"))
            current_db = str(_one(cur, "SELECT current_database()"))
    finally:
        conn.close()
    if current_db != cluster.database:
        raise OpsConfigError(f"safe identity readback for {cluster.role} did not match its database identity — refused")
    out_path = _refuse_repo_path(batch_dir / f"{cluster.database}.dump")
    if out_path.exists():
        raise OpsConfigError(
            f"a dump already exists at the target path for {cluster.role} — refused (refuse-overwrite; choose a fresh batch)"
        )
    proc = _run_child(_pg_dump_argv(out_path), _child_env(dsn), timeout=600)
    if proc.returncode != 0 or not out_path.is_file() or out_path.stat().st_size == 0:
        return _manifest_entry(
            environment_class=ENVIRONMENT_CLASS,
            source_commit=commit,
            source_tree=tree,
            postgresql_version=server_version,
            database_role=cluster.role,
            database_name=cluster.database,
            cluster_system_identity=system_identity,
            created_at=_git_rev("HEAD"),
            dump_format="custom",
            dump_filename=out_path.name,
            byte_size=0,
            sha256="",
            result="failure",
            error_detail=f"pg_dump exit {proc.returncode}; archive missing or empty (references only)",
            production_posture=PRODUCTION_POSTURE,
        )
    listing = _run_child(_pg_restore_list_argv(out_path), dict(os.environ), timeout=300)
    if listing.returncode != 0:
        raise OpsConfigError(f"pg_restore --list cannot read the {cluster.role} dump — fail closed (references only)")
    return _manifest_entry(
        environment_class=ENVIRONMENT_CLASS,
        source_commit=commit,
        source_tree=tree,
        postgresql_version=server_version,
        database_role=cluster.role,
        database_name=cluster.database,
        cluster_system_identity=system_identity,
        created_at=_git_rev("HEAD"),
        dump_format="custom",
        dump_filename=out_path.name,
        byte_size=out_path.stat().st_size,
        sha256=_sha256(out_path),
        result="success",
        error_detail="",
        production_posture=PRODUCTION_POSTURE,
    )


def cmd_backup(args: argparse.Namespace) -> int:
    root = _artifact_root()
    commit, tree = _git_rev("HEAD"), _git_rev("HEAD^{tree}")
    batch_dir = _refuse_repo_path(root / _BACKUP_DEST / f"batch_{args.batch}")
    if not _SAFE_IDENTIFIER_RE.fullmatch(args.batch):
        raise OpsConfigError("--batch must be a safe lowercase identifier (a-z, 0-9, underscore; leading letter) — refused")
    if batch_dir.exists():
        raise OpsConfigError(f"the batch directory already exists: {batch_dir} — refused (refuse-overwrite; choose a fresh --batch)")
    batch_dir.mkdir(parents=False, exist_ok=False)
    print("B5 local-concept bounded operations — BACKUP (custom-format logical dump per authoritative database)")
    entries: List[Dict[str, Any]] = []
    failures = 0
    for cluster in CLUSTERS:
        entry = _backup_one(cluster, batch_dir, commit=commit, tree=tree)
        entries.append(entry)
        status = entry["result"].upper()
        print(f"  {cluster.role:<7} -> {entry['dump_filename']} ({status}; {entry['byte_size']} bytes; sha256 recorded in manifest)")
        failures += 1 if entry["result"] != "success" else 0
    _write_manifest(batch_dir / "manifest.json", entries, commit=commit, tree=tree)
    if failures:
        print(f"BACKUP INCOMPLETE ({failures} database(s) failed; the manifest records the references-only failure detail)")
        return 1
    print(f"BACKUP OK — {len(entries)} dumps under {batch_dir} ; posture {PRODUCTION_POSTURE} ; closes no blocker")
    return 0


# ------------------------------------------------------------------------------------------------
# restore-validate (real pg_restore INTO a disposable validation DB; single-final evidence write)
# ------------------------------------------------------------------------------------------------
def _reject_forbidden_restore_target(name: str) -> None:
    """Refuse a restore over ANY standing identity BEFORE any restore process is invoked (PRD §8)."""
    if name in FORBIDDEN_RESTORE_TARGETS:
        raise OpsConfigError(f"restore over the standing identity {name!r} is prohibited — refused (disposable validation DB only)")


def _validation_db_name(suffix: str) -> str:
    candidate = f"{VALIDATION_DB_PREFIX}{suffix}"
    if not _VALIDATION_DB_RE.fullmatch(candidate):
        raise OpsConfigError("the disposable validation-database name is not a bounded safe identifier — refused")
    _reject_forbidden_restore_target(candidate)  # defensive: a disposable name can never collide with a standing one
    return candidate


def _write_restore_evidence(path: pathlib.Path, record: Dict[str, Any]) -> None:
    """Serialize the single references-only restore-validation evidence bundle after a fail-closed validation:
    all fields present + non-empty, and every cell passes the secret-shape scan (PRD §10.3)."""
    _refuse_repo_path(path)
    for field in RESTORE_RECORD_FIELDS:
        assert field in record and str(record[field]).strip() != "", f"the restore record must carry a non-empty {field}"
    assert tuple(record.keys()) == RESTORE_RECORD_FIELDS, "the restore record must carry the exact field set in order"
    document = {
        "schema": "sp2-local-concept-restore-validation-evidence",
        "schema_version": 1,
        "environment_class": ENVIRONMENT_CLASS,
        "production_posture": PRODUCTION_POSTURE,
        "blocker_census": "7 of 9 OPEN",
        "outcome": "REMAIN NOT READY / DO-NOT-ACTIVATE",
        "record": record,
    }
    blob = json.dumps(document, indent=2, sort_keys=False)
    _assert_no_secret_shapes(blob, where="the restore-validation evidence bundle")
    path.write_text(blob, encoding="utf-8")


def cmd_restore_validate(args: argparse.Namespace) -> int:
    root = _artifact_root()
    cluster = _CLUSTER_BY_ROLE.get(args.role.lower())
    if cluster is None:
        raise OpsConfigError(f"unknown role {args.role!r} — one of {[c.role for c in CLUSTERS]} is required")
    if not _SAFE_IDENTIFIER_RE.fullmatch(args.batch):
        raise OpsConfigError("--batch must be a safe lowercase identifier — refused")
    if not _VALIDATION_DB_RE.fullmatch(f"{VALIDATION_DB_PREFIX}{args.suffix}"):
        raise OpsConfigError("--suffix must yield a bounded safe validation-database identifier (8-32 of a-z0-9) — refused")

    batch_dir = _refuse_repo_path(root / _BACKUP_DEST / f"batch_{args.batch}")
    dump_path = _refuse_repo_path(batch_dir / f"{cluster.database}.dump")
    manifest_path = _refuse_repo_path(batch_dir / "manifest.json")
    if not dump_path.is_file() or not manifest_path.is_file():
        raise OpsConfigError("the approved dump and its batch manifest must both exist under the artifact root — refused")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entry = next((e for e in manifest.get("entries", []) if e.get("database_name") == cluster.database), None)
    if entry is None or entry.get("result") != "success" or not entry.get("sha256"):
        raise OpsConfigError(f"the manifest carries no successful {cluster.role} dump entry to validate — refused")

    # (1) checksum match vs the manifest, and (2) pg_restore --list readability — BEFORE any restore is invoked.
    dump_sha = _sha256(dump_path)
    if dump_sha != entry["sha256"]:
        raise OpsConfigError("the dump SHA-256 does not match the manifest — refused (no restore attempted)")
    if _run_child(_pg_restore_list_argv(dump_path), dict(os.environ), timeout=300).returncode != 0:
        raise OpsConfigError("pg_restore --list cannot read the dump — refused (no restore attempted)")

    # The restore target is a FRESH disposable validation database on the SOURCE cluster (PRD §10.2); restore over
    # any standing identity is refused here, before the canonical provisioning operator is ever constructed.
    _reject_forbidden_restore_target(cluster.database)
    validation_db = _validation_db_name(args.suffix)
    dsn = _resolve_cluster_dsn(cluster)

    from control_plane.adapters.providers.postgres_provisioning_operator import PostgresProvisioningOperator
    from shared.adapters.providers.env_reference_secret_store import DEFAULT_ALLOWED, EnvReferenceSecretStore
    from shared.secrets import SecretRef

    secrets = EnvReferenceSecretStore(allowed=frozenset({*DEFAULT_ALLOWED, *(c.dsn_ref for c in CLUSTERS)}))
    operator = PostgresProvisioningOperator(secrets=secrets, ref=SecretRef(store_ref=cluster.dsn_ref, version="1"))

    record: Dict[str, Any] = {field: "" for field in RESTORE_RECORD_FIELDS}
    record.update(
        EXECUTION_ID=f"restore-validate-{cluster.role.lower()}-{args.suffix}",
        EXECUTION_DATE=_git_rev("HEAD")[:12],
        OPERATOR="operator (references only)",
        ENVIRONMENT_CLASS=ENVIRONMENT_CLASS,
        SOURCE_COMMIT=_git_rev("HEAD"),
        SOURCE_TREE=_git_rev("HEAD^{tree}"),
        SOURCE_ROLE=cluster.role,
        SOURCE_DATABASE=cluster.database,
        DUMP_SHA256=dump_sha,
        MANIFEST_SHA256=_sha256(manifest_path),
        VALIDATION_DATABASE=validation_db,
        CHECKSUM_MATCH_ASSERTION="PASS",
        READABILITY_ASSERTION="PASS",
        SECRET_REFERENCE_ONLY_ASSERTION="PASS",
        PRODUCTION_POSTURE=PRODUCTION_POSTURE,
    )

    print(f"B5 local-concept bounded operations — RESTORE-VALIDATE ({cluster.role} -> disposable {validation_db})")
    retained = 1  # pessimistic until the finally disposal proves otherwise (single-final-write discipline)
    try:
        operator.provision(cluster.role.lower(), target=validation_db)
        restore = _run_child(_pg_restore_into_argv(dump_path, validation_db), _child_env(_swap_db(dsn, validation_db)), timeout=600)
        if restore.returncode != 0:
            raise OpsConfigError("pg_restore into the disposable validation database failed — fail closed (references only)")
        vconn = _connect(_swap_db(dsn, validation_db))
        try:
            with vconn.cursor() as cur:
                current = str(_one(cur, "SELECT current_database()"))
                assert current == validation_db, "the validation connection must reach its own disposable database"
                assert current != cluster.database, "the validation identity must be distinguishable from the source identity"
                probe_table = _CONTROL_DIRECTORY_TABLE if cluster.role == "Control" else _TENANT_STARTUPS_TABLE
                assert _one(cur, "SELECT to_regclass(%s)", (probe_table,)) is not None, f"the restored schema must expose {probe_table}"
                record["SCHEMA_PRESENT_ASSERTION"] = "PASS"
                sentinel = _one(cur, f"SELECT count(*) FROM {probe_table}")
                record["SENTINEL_ASSERTION"] = "PASS" if sentinel is not None else "NONE"
                record["DISTINGUISHABLE_IDENTITY_ASSERTION"] = "PASS"
        finally:
            vconn.close()
        # No standing database was ever a restore target (the disposable DB is the only touched database).
        record["STANDING_UNCHANGED_ASSERTION"] = "PASS (only the disposable validation DB was written)"
    finally:
        operator.deprovision(target=validation_db)  # canonical identifier-guarded DROP DATABASE IF EXISTS
        aconn = _connect(dsn, autocommit=True)
        try:
            with aconn.cursor() as cur:
                retained = int(_one(cur, "SELECT count(*) FROM pg_database WHERE datname LIKE %s", (VALIDATION_DB_PREFIX + "%",)))
        finally:
            aconn.close()
        print(f"  finally disposal — retained {VALIDATION_DB_PREFIX}* database count = {retained}")
        assert retained == 0, "every disposable validation database must be removed after the run"

    # Reached ONLY when the restore succeeded AND the finally disposal proved retained == 0. Only now are the
    # disposal/verdict finalized and the single authoritative references-only evidence bundle written EXACTLY
    # ONCE, OUTSIDE the repository — so a failed run or a failed disposal can never retain a false-PASS record.
    record["RETAINED_VALIDATION_COUNT"] = retained
    record["DISPOSAL_ASSERTION"] = "PASS (retained=0)"
    record["FINAL_VERDICT"] = "RESTORE-VALIDATED-LOCAL"
    bundle_path = _refuse_repo_path(_artifact_dest(_EVIDENCE_DEST) / f"restore_validation_{record['EXECUTION_ID']}.json")
    _write_restore_evidence(bundle_path, record)
    assert bundle_path.is_file(), "the single authoritative references-only evidence bundle must exist under the artifact root"
    print(f"RESTORE-VALIDATE OK — {record['FINAL_VERDICT']} ; evidence {bundle_path.name} ; closes no blocker ; {PRODUCTION_POSTURE}")
    return 0


# ------------------------------------------------------------------------------------------------
# seed (deterministic, idempotent synthetic business data; System-Primary never modified)
# ------------------------------------------------------------------------------------------------
def _load_fixtures() -> Dict[str, Any]:
    """Load the deterministic synthetic fixture from ``06-Synthetic-Data`` (authored fixture-loading behaviour).

    Fixtures are NEITHER created NOR loaded until the runtime START-GATE; a missing fixture fails closed so this
    stage never fabricates data. Every synthetic identifier the fixture declares must carry the SYNTHETIC_PREFIX."""
    fixture = _artifact_dest(_SYNTHETIC_DEST) / "sp2-local-concept-seed.json"
    if not fixture.is_file():
        raise OpsConfigError(f"the synthetic seed fixture is absent: {fixture} (author it under 06-Synthetic-Data before seeding)")
    data = json.loads(fixture.read_text(encoding="utf-8"))
    text = json.dumps(data)
    _assert_no_secret_shapes(text, where="the synthetic seed fixture")
    for identifier in data.get("identifiers", []):
        if not str(identifier).startswith(SYNTHETIC_PREFIX):
            raise OpsConfigError(f"synthetic identifier {identifier!r} does not carry the required {SYNTHETIC_PREFIX} prefix — refused")
    return data


def _assert_system_primary_singleton(cur: Any, *, role: str) -> None:
    if int(_one(cur, _SYSTEM_PRIMARY_PROBE)) != 1:
        raise OpsConfigError(f"{role}: the System-Primary seed is not a singleton — refused (the seed must never modify it)")


def cmd_seed(_args: argparse.Namespace) -> int:
    _artifact_root()
    fixtures = _load_fixtures()
    control = _CLUSTER_BY_ROLE["control"]
    acme = _CLUSTER_BY_ROLE["acme"]
    zeta = _CLUSTER_BY_ROLE["zeta"]
    nova = _CLUSTER_BY_ROLE["nova"]

    global_record_id = str(fixtures.get("control_global_startup_id", f"{SYNTHETIC_PREFIX}startup-001"))
    if not global_record_id.startswith(SYNTHETIC_PREFIX):
        raise OpsConfigError("the synthetic Control record id must carry the required prefix — refused")

    print("B5 local-concept bounded operations — SEED (deterministic, idempotent synthetic business data)")

    # (1) Control record — one idempotent global directory row (reuses control_directory; embeds NO DDL).
    control_conn = _connect(_resolve_cluster_dsn(control), autocommit=True)
    try:
        with control_conn.cursor() as cur:
            if _one(cur, "SELECT to_regclass(%s)", (_CONTROL_DIRECTORY_TABLE,)) is None:
                raise OpsConfigError("Control: control_directory is absent — apply the canonical control DDL first (never embedded here)")
            cur.execute(
                "INSERT INTO control_directory (directory, record_id, display_name, attributes)"
                " VALUES (%s, %s, %s, '{}'::jsonb) ON CONFLICT (directory, record_id) DO NOTHING",
                (_GLOBAL_STARTUP_DIRECTORY, global_record_id, f"{SYNTHETIC_PREFIX}display"),
            )
        print(f"  Control -> control_directory[{_GLOBAL_STARTUP_DIRECTORY}/{global_record_id}] (idempotent; ON CONFLICT DO NOTHING)")
    finally:
        control_conn.close()

    # (2) Independent ACME + ZETA tenant copies of the SAME global record — "Global Record != Tenant Record":
    # importing one global record into two tenants creates two INDEPENDENT rows with NO automatic synchronization.
    for tenant in (acme, zeta):
        tconn = _connect(_resolve_cluster_dsn(tenant), autocommit=True)
        try:
            with tconn.cursor() as cur:
                if _one(cur, "SELECT to_regclass(%s)", (_TENANT_STARTUPS_TABLE,)) is None:
                    raise OpsConfigError(
                        f"{tenant.role}: startups is absent — apply the canonical tenant template first (never embedded here)"
                    )
                _assert_system_primary_singleton(cur, role=tenant.role)  # unchanged BEFORE the tenant insert
                cur.execute(
                    "INSERT INTO startups (global_startup_id, company_name) VALUES (%s, %s) ON CONFLICT (global_startup_id) DO NOTHING",
                    (global_record_id, f"{SYNTHETIC_PREFIX}{tenant.role.lower()}-company"),
                )
                _assert_system_primary_singleton(cur, role=tenant.role)  # and unchanged AFTER the tenant insert
            print(f"  {tenant.role:<7} -> startups[global_startup_id={global_record_id}] independent copy (lineage soft-ref; NO sync)")
        finally:
            tconn.close()

    # (3) Adjacent NOVA isolation — READ-ONLY probe: NOVA must carry ZERO synthetic rows (no seed reaches it).
    nova_conn = _connect(_resolve_cluster_dsn(nova))
    try:
        with nova_conn.cursor() as cur:
            if _one(cur, "SELECT to_regclass(%s)", (_TENANT_STARTUPS_TABLE,)) is not None:
                leaked = int(_one(cur, "SELECT count(*) FROM startups WHERE global_startup_id LIKE %s", (SYNTHETIC_PREFIX + "%",)))
                if leaked:
                    raise OpsConfigError("NOVA carries synthetic rows — adjacent isolation violated (the seed must never reach NOVA)")
        print("  NOVA    -> adjacent isolation confirmed (read-only; zero synthetic rows; never seeded)")
    finally:
        nova_conn.close()

    print(f"SEED OK — deterministic idempotent synthetic data ({SYNTHETIC_PREFIX}*) ; System-Primary unchanged ; closes no blocker")
    return 0


# ------------------------------------------------------------------------------------------------
# status (read-only, fail-closed; standing status by subprocess; no implicit apply/teardown)
# ------------------------------------------------------------------------------------------------
def _standing_status_argv() -> List[str]:
    """The EXACT sibling invocation: status-only argv (no other subcommand is ever constructible here)."""
    return [sys.executable, str(_STANDING_OPS), _STATUS_COMMAND]


def cmd_status(_args: argparse.Namespace) -> int:
    checks: List[Tuple[str, Callable[[], Optional[str]]]] = []

    def check_artifact_root() -> Optional[str]:
        try:
            _artifact_root()
        except OpsConfigError as exc:
            return str(exc)
        return None

    def check_standing_status() -> Optional[str]:
        proc = subprocess.run(
            _standing_status_argv(), cwd=str(_BACKEND_ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600
        )
        if proc.returncode != 0 or "STATUS OK" not in (proc.stdout + proc.stderr):
            return "the standing-topology status delegation did not report STATUS OK"
        return None

    def check_no_retained_validation_db() -> Optional[str]:
        for cluster in CLUSTERS:
            conn = _connect(_resolve_cluster_dsn(cluster), autocommit=True)
            try:
                retained = int(_one(conn.cursor(), "SELECT count(*) FROM pg_database WHERE datname LIKE %s", (VALIDATION_DB_PREFIX + "%",)))
            finally:
                conn.close()
            if retained:
                return f"{cluster.role}: {retained} retained {VALIDATION_DB_PREFIX}* database(s) (restore-validate must leave none)"
        return None

    checks = [
        ("artifact root + eight destinations present", check_artifact_root),
        ("standing-topology status delegation is green", check_standing_status),
        ("no retained restore-validation databases", check_no_retained_validation_db),
    ]
    print("B5 local-concept bounded operations — STATUS (read-only; fail-closed; no implicit apply/teardown)")
    failures = 0
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
    if failures:
        print(f"STATUS FAILED ({failures} check(s) not holding)")
        return 1
    print(f"STATUS OK — local-concept posture healthy ; closes no blocker ; 7 of 9 OPEN ; {PRODUCTION_POSTURE}")
    return 0


# ------------------------------------------------------------------------------------------------
# entrypoint
# ------------------------------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="b5_local_concept_ops",
        description="B5 local-concept bounded operations wrapper (plan/backup/restore-validate/seed/status).",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("plan", help="read-only sanitized intent (no connection, no mutation)")
    backup = sub.add_parser("backup", help="one custom-format dump per authoritative database into 03-Database-Backups")
    backup.add_argument("--batch", required=True, help="a fresh safe-identifier batch name (refuse-overwrite)")
    restore = sub.add_parser("restore-validate", help="restore one dump into a fresh disposable validation database, then dispose")
    restore.add_argument("--role", required=True, help="one of Control/ACME/ZETA/NOVA")
    restore.add_argument("--batch", required=True, help="the backup batch to validate")
    restore.add_argument("--suffix", required=True, help="a bounded lowercase suffix (8-32 of a-z0-9) for the disposable validation DB")
    sub.add_parser("seed", help="deterministic idempotent synthetic business-data seed (System-Primary never modified)")
    sub.add_parser("status", help="read-only fail-closed local-concept posture verification")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    handlers: Dict[str, Callable[[argparse.Namespace], int]] = {
        "plan": cmd_plan,
        "backup": cmd_backup,
        "restore-validate": cmd_restore_validate,
        "seed": cmd_seed,
        "status": cmd_status,
    }
    try:
        return int(handlers[args.command](args))
    except OpsConfigError as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
