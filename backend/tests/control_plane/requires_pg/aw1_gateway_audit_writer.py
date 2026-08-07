"""AW-1 — least-privilege standing Gateway operational-audit writer: OPERATOR TOOL (standalone only).

Not application runtime code and not a test. This is the governed vehicle for AW-1's M2 step: it
observes, classifies and (only under Gate B) applies the byte-frozen §5.4 role/grant payload that
creates the least-privilege identity the Gateway-audit ingest edge writes as.

WHY IT EXISTS. `build_gateway_audit_store_from_env` is durable **by construction** and, with no
reference set, binds the DEFAULT ref `control/control-store-dsn` — which by standing convention
resolves to the `sp2_local` SUPERUSER DSN. Every durable Gateway audit row would therefore be written
by the most privileged identity in the cluster. AW-1 replaces that with a role that can do exactly
two things to exactly one table: `INSERT` and `SELECT` on `public.control_gateway_audit`.

    sp2_gateway_audit_writer   NOLOGIN grant role — holds the entire privilege surface
    sp2_gateway_audit_ingest   LOGIN identity — holds ONLY membership + a credential

COMMANDS (stdlib argparse; work happens ONLY after an explicit subcommand — import performs no I/O):

    plan    READ-ONLY. Connects, observes role/attribute/membership/ACL/comment state plus the
            Tier-B environment preconditions, classifies MATCHING / MISSING / CONFLICTING, and
            exits non-zero on CONFLICTING. NEVER binds a credential, NEVER writes secret material,
            NEVER executes the payload. Safe to run before Gate B — that is its purpose (§9 O-2).
            It evaluates V-12 through the SAME `v12_problems()` predicate `apply` uses, on the same
            observation, so it cannot report green where `apply` would refuse on V-12 (RB-1).
    apply   GATE-B ONLY, and refuses to run without `--confirm-gate-b-m2`. Asserts the database
            identity pin, executes the frozen payload in ONE transaction, performs the §5.6
            statement-logging observation, then takes exactly one §5.5 credential-convergence
            branch. Reports `M2 INITIAL CREATION`, `M2 RECOVERY`, `NO_CHANGES` or `CONFLICTING`.
            A MUTATING branch performs all four §5.5 steps in the governed order — mint, bind,
            write the material, RE-PROBE — and proves the sink writable BEFORE minting, so a
            password can never be bound and then become unreachable.
    status  READ-ONLY, fail-closed, fixed declared pass count (V-13). Exits non-zero unless the
            COMPLETE least-privilege state holds. This is the launcher's start gate (§9 O-6 → O-7):
            the ingest edge must not start if this command fails.

GATE BOUNDARY. Under Gate A this tool is BUILT, not run against standing state. No role, grant,
password or credential is created by merging it. `apply` is inert without its explicit confirmation
flag, and creating the writer credential is a Gate-B M2 act that must be named in the frozen
mutation inventory before it is authorized (AW-1 U-3).

DRIVER CONTAINMENT. No static database-driver import: psycopg is located via importlib at call time.

SECRET HYGIENE (D-14). No DSN, password or credential value is printed, logged, returned, or written
to any repository file. Every emitted identity is redacted to scheme+host+port+database. The writer
DSN material lives ONLY in the operator-local, untracked §7 mechanism: the env-var form named by
`WRITER_MATERIAL_ENV`, or the file form `$SNACKPORTAL_SECRET_DIR/<ref>@<version>`. `apply` persists
to the FILE form because a child process cannot write its parent shell's environment; the sink is
proven to resolve OUTSIDE every repository worktree before anything is written to it.

Invoked from ``backend/``:  python tests/control_plane/requires_pg/aw1_gateway_audit_writer.py <cmd>
Runbook: ``infrastructure/runbooks/aw1_gateway_audit_writer.md``
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.util
import ipaddress
import os
import pathlib
import secrets
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import parse_qsl, urlsplit

_THIS = pathlib.Path(__file__).resolve()
_BACKEND_ROOT = _THIS.parents[3]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

# --------------------------------------------------------------------------- pinned identities ---
WRITER_ROLE = "sp2_gateway_audit_writer"
INGEST_ROLE = "sp2_gateway_audit_ingest"

# §5.4.1 apply-connection database pin. The payload MIXES cluster-wide statements (role creation,
# attribute pins, membership, GRANT CONNECT ON DATABASE, COMMENT ON ROLE) with database-local ones
# (GRANT USAGE ON SCHEMA public, the table GRANT/REVOKE). Executed from the maintenance `postgres`
# database it would strand the schema grant in the wrong database — invisible to every later probe,
# which only ever looks inside the control database — and the table grants would fail outright.
CONTROL_DATABASE = "snackportal2_control_local"

AUDIT_TABLE = "public.control_gateway_audit"

# §7. A NEW reference. `control/control-store-dsn` — bound by standing convention to the sp2_local
# superuser DSN — is NEVER reused for the writer.
WRITER_SECRET_REF = "control/gateway-audit-writer-dsn"
WRITER_MATERIAL_ENV = "SNACKPORTAL_SECRET_CONTROL_GATEWAY_AUDIT_WRITER_DSN_V1"
WRITER_MATERIAL_VERSION = "1"

# §7 names TWO material forms, and `EnvReferenceSecretStore.resolve` reads both: the env var first,
# then `$SNACKPORTAL_SECRET_DIR/<store_ref>@<version>`. The FILE form is the one an `apply` PROCESS
# can actually persist — a child process cannot write its parent shell's environment — so it is the
# governed sink for the §5.5 material write. (§11 S-4(a2) governs adopting the file form for the
# INGEST process, which is a separate, launcher-side decision; this variable is read here only to
# locate the operator-local sink, and the ingest edge is still forbidden to carry it.)
SECRET_DIR_ENV = "SNACKPORTAL_SECRET_DIR"

MATERIAL_FORM_ENV = "env"
MATERIAL_FORM_FILE = "file"

# The scheme token of the composed material. Deliberately a constant rather than part of a DSN
# literal: no credential-bearing DSN literal may exist in this file, and the composer builds every
# other component from the pinned identities above.
_DSN_SCHEME = "postgresql"

# R-3: mandatory, non-secret, byte-pinned. It is the executable half of the V-8 connected-identity
# proof — without it, `pg_stat_activity` cannot distinguish the governed ingest session from any
# other, because the Docker userland port proxy makes client_addr/client_port useless here.
INGEST_APPLICATION_NAME = "sp2-gateway-audit-ingest"

# The plan/apply/status executor identity. `sp2_local` is the sole login identity on the standing
# control cluster and the only one that can CREATE ROLE. This provisioning use is Gate-B-governed
# bootstrap and is CATEGORICALLY DISTINCT from the runtime writer falling back to `sp2_local`, which
# is prohibited and made impossible by the AW-1 §11 S-4 launcher controls.
EXECUTOR_DSN_ENV = "SNACKPORTAL_SECRET_CONTROL_CONTROL_STORE_DSN_V1"

# Tier-A rehearsal executability: on PG < 15 the V-5 "CREATE TABLE in public" probe passes for the
# WRONG reason (the PUBLIC schema-CREATE default), which would make the rehearsal vacuous.
MIN_SERVER_VERSION_NUM = 150000
STANDING_SERVER_MAJOR = 17

# The six-attribute vectors, both roles (V-6 / R-1). Order:
# (rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls)
EXPECTED_ATTRIBUTES: Dict[str, Tuple[bool, bool, bool, bool, bool, bool]] = {
    WRITER_ROLE: (False, False, False, False, False, False),
    INGEST_ROLE: (True, False, False, False, False, False),
}
# rolinherit is load-bearing for the ingest role: without it, membership grants nothing.
EXPECTED_INHERIT: Dict[str, bool] = {WRITER_ROLE: True, INGEST_ROLE: True}

# V-7: the six sibling Control-DB tables the writer must be unable to read. Non-vacuous only when
# control DDL 001-009 has been applied (otherwise every probe raises undefined_table 42P01 — a
# wrong-reason pass).
UNRELATED_TABLES = (
    "control_memberships",
    "control_tenants",
    "control_audit",
    "control_federation",
    "control_directory",
    "control_distinctness_ledger",
)

# V-10: both 013 append-only triggers, present AND enabled.
EXPECTED_TRIGGERS = ("control_gateway_audit_no_mutation", "control_gateway_audit_no_truncate")

# V-17: no tenant-namespace database may live on the control cluster.
TENANT_DB_PATTERNS = ("sp2_tenant_%", "snackportal2_tenant_%")

# V-12 (RB-1). The client authentication methods under which a credential probe actually DECIDES
# the credential AW-1 binds, i.e. the password stored by `ALTER ROLE ... PASSWORD`. Everything else
# is non-discriminating for AW-1's purposes and therefore disqualifies BOTH the §5.5 branch-1
# decision and the mandatory post-bind re-probe:
#
#   trust                     accepts unconditionally — the probe proves nothing;
#   peer / ident / cert       authenticate the OS user or a client certificate, so the probe
#                             succeeds no matter what password is bound;
#   ldap / radius / pam / bsd verify a password held by an EXTERNAL directory, never the one this
#                             tool just bound;
#   gss / sspi                authenticate a Kerberos/Windows principal;
#   reject                    refuses unconditionally — the probe proves nothing in the other
#                             direction, and would make branch 1 permanently unreachable.
#
# An allow-list, not a deny-list: a method this tool has never heard of must block rather than pass,
# because "unknown" is precisely the state in which the probe's meaning is unknown. The predecessor
# checked only for the single string `trust` and did so across EVERY `type='host'` rule in the file,
# which is neither this connection's rule nor the whole hazard.
PASSWORD_DISCRIMINATING_AUTH_METHODS = frozenset({"scram-sha-256", "md5", "password"})

# `pg_hba_file_rules` gained the globally-ordered `rule_number` in PostgreSQL 16. Below that,
# `line_number` is the only ordering column available. Both are read ORDERED, because pg_hba is a
# FIRST-MATCH table and an unordered scan would pick an arbitrary rule.
_HBA_RULE_NUMBER_MIN_VERSION = 160000

# Database-column tokens that resolve definitively WITHOUT further information for a normal
# (non-replication) client connection such as this tool's.
_HBA_REPLICATION_TOKEN = "replication"

# Address tokens meaning "every client address" — matched without parsing.
_HBA_ANY_ADDRESS = frozenset({"all", "0.0.0.0/0", "::/0"})

# §5.6 statement-logging guard. A bind performed while any of these holds writes the full
# `ALTER ROLE ... PASSWORD` text to the server log — PostgreSQL performs no password redaction.
BLOCKING_LOG_STATEMENT = frozenset({"ddl", "mod", "all"})

# O-6: sampling GUCs that can also surface statement text. Observed and reported; a positive sample
# rate is treated as CONFLICTING for the same reason `log_min_duration_statement >= 0` is.
SAMPLING_GUCS = ("log_min_duration_sample", "log_statement_sample_rate", "log_transaction_sample_rate")

# V-11 / V-16: the pinned canonical row serialization. `extract(epoch from timestamptz)` is an
# absolute instant and is therefore independent of session TimeZone/DateStyle — text rendering is
# not, and would produce false drift or mask real drift under different GUCs. The microsecond bigint
# cast is exact for PostgreSQL timestamp precision. `quote_nullable` makes NULL and every text value
# unambiguously distinguishable, so no separator collision can alias two different row contents.
# `ORDER BY id` makes the aggregate order-stable. Both md5 and quote_nullable are core, portable
# PostgreSQL. This string is used BYTE-IDENTICALLY at V-11 and V-16.
ROW_FINGERPRINT_SQL = (
    "SELECT count(*), max(id), md5(string_agg(rowhash, ',' ORDER BY id)) FROM ("
    "SELECT id, md5(concat("
    "quote_nullable(id::text),'|',"
    "quote_nullable(audit_id),'|',"
    "quote_nullable(event_version::text),'|',"
    "quote_nullable(((extract(epoch from occurred_at)*1000000)::bigint)::text),'|',"
    "quote_nullable(((extract(epoch from recorded_at)*1000000)::bigint)::text),'|',"
    "quote_nullable(correlation_id),'|',"
    "quote_nullable(action),'|',"
    "quote_nullable(outcome),'|',"
    "quote_nullable(source_service),'|',"
    "quote_nullable(actor_ref),'|',"
    "quote_nullable(subject_ref),'|',"
    "quote_nullable(tenant_ref),'|',"
    "quote_nullable(carrier_ref),'|',"
    "quote_nullable(record_ref)"
    ")) AS rowhash FROM control_gateway_audit WHERE id <= %s) t"
)

# =================================================================================================
# THE BYTE-FROZEN §5.4 M2 PAYLOAD
#
# This block is frozen by AW-1 V2 §5.4 INCLUDING ITS COMMENTS. It is carried here VERBATIM and is
# pinned by `backend/tests/architecture/test_aw1_gateway_audit_writer_boundaries.py`, which compares
# its SHA-256 against a committed constant and anchors every statement individually. Changing one
# byte — even a comment — must be a governed AW-1 amendment plus a lockstep guard re-stamp, never an
# in-place edit.
#
# It deliberately does NOT ship as `infrastructure/db/**/*.sql`. Two things would break if it did:
# `test_b5_standing_topology_boundaries.py` asserts a CLOSED 15-file on-disk DDL inventory, and the
# PMA-AR-2 role-security meta-guard would force a `ROLE_SECURITY_COVERAGE` family registration whose
# INV-A is structurally bound to on-disk SQL. The embedded form plus a dedicated byte-pin guard
# satisfies the meta-guard's intent without widening the Gate-A surface.
#
# The credential bind is NOT part of this block — see §5.5 / `_converge_credential`.
# =================================================================================================
FROZEN_ROLE_GRANT_SQL = """\
-- AW-1: least-privilege standing Gateway operational-audit writer (Control DB cluster only).
-- Grant role (NOLOGIN) holds the surface; login role holds only membership + a credential.
-- The apply session MUST be connected to database snackportal2_control_local (see 5.4.1).
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'sp2_gateway_audit_writer') THEN
        CREATE ROLE sp2_gateway_audit_writer NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'sp2_gateway_audit_ingest') THEN
        CREATE ROLE sp2_gateway_audit_ingest LOGIN;
    END IF;
END
$$;

ALTER ROLE sp2_gateway_audit_writer
    NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;

ALTER ROLE sp2_gateway_audit_ingest
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS INHERIT;

-- Credential binding is NOT part of this byte-frozen block. It executes as a separate
-- client-side-bound, safely-quoted ALTER ROLE ... PASSWORD statement in the same apply step
-- (psycopg.sql.Literal / ClientCursor -- ALTER ROLE is a utility statement and PostgreSQL
-- accepts no server-side bind parameters), ONLY under the section 5.5 convergence rule and
-- ONLY after the section 5.6 statement-logging observation. The value comes from the governed
-- local secret material (section 7); it appears in no repository file, no plan/apply/status
-- output, and no evidence. Server-side statement logging is an environment property, not an
-- AW-1 guarantee -- see section 5.6 and residual R-7.

GRANT CONNECT ON DATABASE snackportal2_control_local TO sp2_gateway_audit_writer;
GRANT USAGE  ON SCHEMA  public                       TO sp2_gateway_audit_writer;
GRANT SELECT, INSERT ON public.control_gateway_audit TO sp2_gateway_audit_writer;

-- Explicit even though never granted: documents intent; the 013 triggers are the backstop
-- even against a future mis-grant (the lineage 003 dual-enforcement precedent).
REVOKE UPDATE, DELETE, TRUNCATE ON public.control_gateway_audit FROM sp2_gateway_audit_writer;

GRANT sp2_gateway_audit_writer TO sp2_gateway_audit_ingest;

COMMENT ON ROLE sp2_gateway_audit_writer IS
    'AW-1 least-privilege Gateway operational-audit writer grant role (NOLOGIN; INSERT+SELECT '
    'on public.control_gateway_audit only; login credential via D-14 secret store; '
    'controlled non-production only).';
COMMENT ON ROLE sp2_gateway_audit_ingest IS
    'AW-1 Gateway operational-audit ingest LOGIN identity (member of sp2_gateway_audit_writer; '
    'no direct grants; controlled non-production only).';
"""

# The COMMENT texts as PostgreSQL stores them (the SQL literals above are adjacent-concatenated).
EXPECTED_COMMENTS: Dict[str, str] = {
    WRITER_ROLE: (
        "AW-1 least-privilege Gateway operational-audit writer grant role (NOLOGIN; INSERT+SELECT "
        "on public.control_gateway_audit only; login credential via D-14 secret store; "
        "controlled non-production only)."
    ),
    INGEST_ROLE: (
        "AW-1 Gateway operational-audit ingest LOGIN identity (member of sp2_gateway_audit_writer; "
        "no direct grants; controlled non-production only)."
    ),
}

# Classification vocabulary. `NO_CHANGES` is computed from STATE COMPARISON, never inferred from the
# DO-guards in the payload (only the two CREATE ROLEs are guarded; everything else is unconditional
# and state-convergent).
MATCHING = "MATCHING"
MISSING = "MISSING"
CONFLICTING = "CONFLICTING"
NO_CHANGES = "NO_CHANGES"

# V2-C2. On the FIRST-EVER apply every branch-2 conjunct holds (material absent, role/grant state
# converged by the payload that just ran, bind not done), so an implementation with only three
# branches would record initial credential creation as "recovery from a crash that never occurred".
# Branch 0 exists to keep the evidence honest.
M2_INITIAL_CREATION = "M2 INITIAL CREATION"
M2_RECOVERY = "M2 RECOVERY"

# V-13: `status` declares its pass count up front so a silently-skipped check cannot read as success.
STATUS_DECLARED_CHECKS = 9

# O-6 password alphabet: RFC 3986 UNRESERVED characters only. A URI-special character would bind
# successfully and then fail to compose a parseable DSN — landing in branch 3 with the credential
# already changed and no material bound, which is the one unrecoverable ordering in the whole arc.
_PASSWORD_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
_PASSWORD_LENGTH = 48


# ------------------------------------------------------------------------------------ helpers ----
def _psycopg() -> Any:
    """Locate psycopg at CALL time (Driver Containment Standard: no static driver import)."""
    if importlib.util.find_spec("psycopg") is None:
        raise SystemExit("psycopg is not installed; this operator tool requires it.")
    return importlib.import_module("psycopg")


def redacted(dsn: str) -> str:
    """scheme+host+port+database only. No userinfo, no password, no query string."""
    try:
        parts = urlsplit(dsn)
    except ValueError:
        return "<unparseable>"
    host = parts.hostname or "?"
    port = f":{parts.port}" if parts.port else ""
    return f"{parts.scheme or '?'}://{host}{port}{parts.path or ''}"


def _executor_dsn() -> str:
    dsn = (os.environ.get(EXECUTOR_DSN_ENV) or "").strip()
    if not dsn:
        raise SystemExit(
            f"{EXECUTOR_DSN_ENV} is unset/blank. This tool connects as the governed plan identity by "
            "reference; it never carries a DSN literal."
        )
    return dsn


def _material_file_path() -> Optional[pathlib.Path]:
    """The governed §7 file form: `$SNACKPORTAL_SECRET_DIR/control/gateway-audit-writer-dsn@1`.

    Composed exactly as `EnvReferenceSecretStore.resolve` composes it, so what this tool persists is
    byte-for-byte what the runtime resolver will read. `None` when the directory is not declared.
    """
    root = (os.environ.get(SECRET_DIR_ENV) or "").strip()
    if not root:
        return None
    return pathlib.Path(root) / f"{WRITER_SECRET_REF}@{WRITER_MATERIAL_VERSION}"


def _resolve_writer_material() -> Tuple[Optional[str], Optional[str]]:
    """`(material, form)` — resolution order MIRRORS `EnvReferenceSecretStore.resolve` exactly.

    The env var wins by MEMBERSHIP, not by truthiness: the resolver returns `os.environ[key]` the
    moment the key exists, so a set-but-EMPTY variable SHADOWS the file form at runtime. A blank env
    var is therefore reported as form `env` with material `None` — not as "absent". Collapsing the
    two would let this tool write a file the runtime can never see.

    Presence semantics are §5.5's: blank after stripping is NOT present. S-3: `psycopg.connect("")`
    does not fail — it falls back to libpq defaults (PG* variables, localhost:5432, the OS user name,
    `~/.pgpass`), a silent alternate-source path that would connect somewhere nobody chose.
    """
    raw = os.environ.get(WRITER_MATERIAL_ENV)
    if raw is not None:
        return (raw.strip() or None), MATERIAL_FORM_ENV
    path = _material_file_path()
    if path is not None and path.is_file():
        return (path.read_text(encoding="utf-8").strip() or None), MATERIAL_FORM_FILE
    return None, None


def _writer_material() -> Optional[str]:
    """The writer DSN material, PRESENCE-checked only. Never printed, never hashed, never emitted."""
    return _resolve_writer_material()[0]


def material_sink_blockers() -> List[str]:
    """Declaration-level reasons the minted material could NOT be persisted. No filesystem write.

    Safe for `plan`: it reads the environment and one path, and creates nothing.
    """
    blockers: List[str] = []
    _material, form = _resolve_writer_material()
    if form == MATERIAL_FORM_ENV:
        blockers.append(
            f"{WRITER_MATERIAL_ENV} is set in THIS process's environment. A child process cannot replace its "
            "parent shell's variable in place, which is what §5.5 branch 2 requires — and the env form shadows the "
            "file form in the resolver even when blank, so writing the file would leave the runtime reading the old "
            "value. Unset it in this shell, re-run, then reload the material from the governed file."
        )
    path = _material_file_path()
    if path is None:
        blockers.append(
            f"{SECRET_DIR_ENV} is unset or blank, so the governed §7 file form has no location. `apply` will not "
            "mint a password it has no way to persist."
        )
        return blockers
    try:
        resolved = path.resolve()
    except OSError:  # pragma: no cover — an unresolvable path is reported as the sink itself
        resolved = path
    repo_root = _THIS.parents[4]
    if resolved == repo_root or repo_root in resolved.parents:
        blockers.append(
            "the governed material sink resolves INSIDE the repository worktree. The writer DSN is operator-local "
            "and untracked by construction; a sink inside a repository is one `git add -A` from a committed secret."
        )
    return blockers


def material_sink_problems() -> List[str]:
    """`material_sink_blockers()` plus a REAL writability probe. `apply` only.

    Evaluated BEFORE any mint or bind, and a non-empty result STOPS with zero mutation. §5.5 note 2
    describes a crash between the payload commit and the material write as the state to recover
    FROM; a tool that binds a password it cannot persist makes that state the GUARANTEED outcome of
    every successful apply, and no later run can converge out of it — `status` never goes green, the
    launcher's §9 O-6 start gate never opens, and escaping requires a superuser `ALTER ROLE` outside
    AW-1's governed procedure, which is the class of act AW-1 exists to eliminate.
    """
    problems = material_sink_blockers()
    if problems:
        return problems
    path = _material_file_path()
    assert path is not None, "material_sink_blockers() already established the sink location"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        probe = path.parent / ".aw1-sink-write-probe"
        probe.write_text("probe", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        problems.append(f"the governed material sink directory is not writable ({exc.__class__.__name__})")
    return problems


def compose_writer_dsn(executor_dsn: str, password: str) -> str:
    """The §7 material shape, composed IN MEMORY. Never printed, never logged, never returned to a
    caller that prints it.

    Host and port come from the executor connection, so the writer targets the same cluster the
    payload was applied to; the database, role and `application_name` are the pinned constants.
    `_PASSWORD_ALPHABET` is RFC 3986 UNRESERVED, so no percent-encoding is required and the composed
    DSN is guaranteed parseable — which is what keeps a successful bind out of the one unrecoverable
    ordering in the whole arc (credential changed, material unparseable).
    """
    parts = urlsplit(executor_dsn)
    host = parts.hostname or "127.0.0.1"
    port = f":{parts.port}" if parts.port else ""
    return f"{_DSN_SCHEME}://{INGEST_ROLE}:{password}@{host}{port}/{CONTROL_DATABASE}?application_name={INGEST_APPLICATION_NAME}"


def _write_material(path: pathlib.Path, material: str) -> None:
    """Persist the governed §7 material to the operator-local, untracked file form.

    The ONLY write this tool performs, and it happens only inside the §5.5 mutating branches under
    Gate B. Atomic (temp + `os.replace`) so an interrupted write cannot leave a truncated DSN that
    resolves to something unintended, and `0600` where the platform honours POSIX modes. The value is
    never printed, never logged, and never returned.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".partial")
    temporary.write_text(material, encoding="utf-8")
    try:
        os.chmod(temporary, 0o600)
    except OSError:  # pragma: no cover — Windows ACLs do not honour POSIX modes
        pass
    os.replace(temporary, path)


def dsn_shape_problems(dsn: str) -> List[str]:
    """§5.6 / R-9 DSN hygiene, checked WITHOUT looking at the credential.

    Both adapter statements use the BARE table name `control_gateway_audit`; resolution to `public`
    rests on the default `search_path`. A DSN-level `options=-c search_path=...` is a documented,
    test-exercised mechanism for this DSN class, so the prohibition is concrete rather than
    theoretical. `application_name` is mandatory and byte-pinned because it is the executable half
    of the V-8 connected-identity proof.
    """
    problems: List[str] = []
    try:
        parts = urlsplit(dsn)
    except ValueError:
        return ["the writer DSN is not parseable"]
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    if "options" in query:
        problems.append("the writer DSN carries a libpq `options` keyword; it must not (search_path hijack vector)")
    if query.get("application_name") != INGEST_APPLICATION_NAME:
        problems.append(f"the writer DSN must carry application_name={INGEST_APPLICATION_NAME} exactly")
    if (parts.path or "").lstrip("/") != CONTROL_DATABASE:
        problems.append(f"the writer DSN must target database {CONTROL_DATABASE}")
    if parts.username and parts.username != INGEST_ROLE:
        problems.append(f"the writer DSN must authenticate as {INGEST_ROLE}")
    return problems


def _mint_password() -> str:
    return "".join(secrets.choice(_PASSWORD_ALPHABET) for _ in range(_PASSWORD_LENGTH))


def frozen_payload_sha256() -> str:
    """The byte-pin the static guard compares against (LF-normalized)."""
    return hashlib.sha256(FROZEN_ROLE_GRANT_SQL.replace("\r\n", "\n").encode("utf-8")).hexdigest()


# --------------------------------------------------------------- V-12: the EFFECTIVE host auth ---
# RB-1. `pg_hba.conf` is a FIRST-MATCH table: exactly one entry governs any given connection, and
# which one it is depends on the connection type, the SSL/GSS state, the database, the role and the
# client address. A census of every `type='host'` rule's method therefore answers a question nobody
# asked — an unrelated `host all all 127.0.0.1/32 trust` line blocks a connection that arrives from a
# container-network address and never touches that rule, while a permissive rule that DOES govern
# this connection can hide behind a stricter one that does not.
#
# These functions are PURE (rules in, verdict out): they take the rule table and the observed
# connection facts and return the entry PostgreSQL actually applied. Being pure is what lets the
# static guard EXECUTE them against synthetic rule tables instead of pattern-matching their source,
# and what lets `plan` and `apply` reach the identical verdict from the identical inputs.
#
# Three-valued throughout: True (matches), False (definitely does not), None (cannot be decided from
# what is observable). A first-match table cannot be evaluated past an undecidable entry — the entry
# might be the governing one — so the scan STOPS there and reports UNDETERMINABLE. Fail-closed: an
# unknown effective method is treated exactly like a non-discriminating one.
def _hba_type_matches(rule_type: Optional[str], *, local: bool, ssl: Optional[bool]) -> Optional[bool]:
    """`local` / `host` / `hostssl` / `hostnossl` against this connection's transport."""
    if rule_type == "local":
        return local
    if rule_type not in ("host", "hostssl", "hostnossl", "hostgssenc", "hostnogssenc"):
        return None  # an unrecognised connection type is not guessed at
    if local:
        return False  # every host-family rule is a TCP rule
    if rule_type == "host":
        return True  # `host` matches TCP whether or not SSL is in use
    if rule_type in ("hostssl", "hostnossl"):
        if ssl is None:
            return None
        return ssl if rule_type == "hostssl" else not ssl
    return None  # GSS-encryption rules: this tool does not observe the GSS state


def _hba_tokens_match(tokens: Optional[Sequence[str]], value: Optional[str]) -> Optional[bool]:
    """A `pg_hba_file_rules` database/user token array against one observed value.

    `all` and an exact name decide TRUE. `replication` decides FALSE for the normal client
    connection this tool makes — deciding it correctly matters, because the stock PostgreSQL
    `pg_hba.conf` carries replication lines ABOVE the rule that governs an ordinary connection, and
    treating them as undecidable would stall every scan on every default installation. `+group`,
    `@file`, `sameuser` and `samerole` need catalog or filesystem state this tool does not read, so
    they decide NOTHING.
    """
    if tokens is None or value is None:
        return None
    undecidable = False
    for token in tokens:
        if token == "all" or token == value:
            return True
        if token == _HBA_REPLICATION_TOKEN:
            continue  # a replication-only entry cannot govern this ordinary connection
        if token.startswith(("+", "@")) or token in ("sameuser", "samerole"):
            undecidable = True
    return None if undecidable else False


def _hba_network(address: Optional[str], netmask: Optional[str]) -> Optional[Any]:
    """The rule's address as an `ipaddress` network, or `None` when it is not an IP literal.

    `pg_hba_file_rules` renders a CIDR entry as an address plus a separate `netmask`, and a
    hostname entry as the hostname itself. A hostname would need resolution — an act with its own
    failure modes and its own answer-changing-over-time problem — so it is left undecided.
    """
    if not address:
        return None
    for candidate in (f"{address}/{netmask}" if netmask else None, address):
        if candidate is None:
            continue
        try:
            return ipaddress.ip_network(candidate, strict=False)
        except ValueError:
            continue
    return None


def _hba_address_matches(address: Optional[str], netmask: Optional[str], client_address: Optional[str]) -> Optional[bool]:
    if address is not None and address.strip() in _HBA_ANY_ADDRESS:
        return True
    if client_address is None:
        return None
    try:
        client = ipaddress.ip_address(client_address.split("/")[0])
    except ValueError:
        return None
    network = _hba_network(address, netmask)
    if network is None:
        return None
    if client.version != network.version:
        return False
    return client in network


def effective_host_auth(rules: Optional[Sequence[Dict[str, Any]]], connection: Dict[str, Any]) -> Dict[str, Any]:
    """The ONE `pg_hba` entry that governs THIS connection — the V-12 subject.

    Returns ``{"method", "order", "undeterminable"}``. `undeterminable` carries the reason when no
    single entry could be identified; `method` is then `None` and V-12 blocks. Nothing here decides
    whether the method is acceptable — that is `v12_problems()`, so the observation and the judgement
    stay separable and separately testable.
    """
    if rules is None:
        return {
            "method": None,
            "order": None,
            "undeterminable": (
                "pg_hba_file_rules is not readable by the executor identity (it needs superuser or pg_read_server_files "
                "membership, and PostgreSQL 10+), so the effective client authentication method cannot be established"
            ),
        }
    for rule in rules:
        order = rule.get("order")
        if rule.get("error"):
            return {
                "method": None,
                "order": order,
                "undeterminable": (
                    f"the pg_hba entry at #{order} did not parse, so no entry at or after it can be evaluated and the "
                    "governing rule is unknowable"
                ),
            }
        rule_type = rule.get("type")
        verdicts = [
            _hba_type_matches(rule_type, local=bool(connection.get("local")), ssl=connection.get("ssl")),
            _hba_tokens_match(rule.get("database"), connection.get("database")),
            _hba_tokens_match(rule.get("user_name"), connection.get("user")),
            (
                True
                if rule_type == "local"
                else _hba_address_matches(rule.get("address"), rule.get("netmask"), connection.get("client_address"))
            ),
        ]
        if any(verdict is False for verdict in verdicts):
            continue  # a definite non-match on ANY field, whatever the other fields do
        if any(verdict is None for verdict in verdicts):
            return {
                "method": None,
                "order": order,
                "undeterminable": (
                    f"the pg_hba entry at #{order} can neither be matched nor excluded from what is observable "
                    "(non-literal address, group/file token, or an unobserved transport state), and pg_hba is a "
                    "first-match table — so no later entry can be assumed to govern instead"
                ),
            }
        return {"method": rule.get("auth_method"), "order": order, "undeterminable": None}
    return {
        "method": None,
        "order": None,
        "undeterminable": (
            "no pg_hba entry matches the observed connection facts, yet this connection was accepted — the observation "
            "and the server disagree, so nothing may be concluded from it"
        ),
    }


def v12_problems(environment: Dict[str, Any]) -> List[str]:
    """V-12, evaluated ONCE and consumed by BOTH commands.

    `classify()` (and therefore `plan`) and `_converge_credential` (and therefore `apply`) call THIS
    function on the SAME observation, which is what makes "a green `plan` where `apply` would refuse
    on V-12" structurally impossible rather than merely unlikely. The predecessor split the two:
    `apply` tested `'trust' in <every host rule's method>` and `classify()` never read the key at
    all, so `plan` exited 0 `MISSING` on a cluster where `apply` was guaranteed to refuse — a false
    green on the §6.3 pre-grant condition.

    Blocking here is not a bind-time nicety. §5.5 note 6 makes V-12 a HARD PRECONDITION of the whole
    convergence: under a non-discriminating method the branch-1 "material already authenticates"
    decision is meaningless AND the mandatory post-bind re-probe cannot confirm anything, so there is
    no branch left that is safe to take.
    """
    effective = environment.get("effective_host_auth")
    if not isinstance(effective, dict):
        return [
            "V-12: the effective client authentication method was not observed at all, so no credential probe "
            "performed here can be given a meaning"
        ]
    reason = effective.get("undeterminable")
    if reason:
        return [f"V-12: the effective client authentication method for this connection is UNDETERMINABLE — {reason}"]
    method = effective.get("method")
    if method not in PASSWORD_DISCRIMINATING_AUTH_METHODS:
        return [
            f"V-12: the effective client authentication method for THIS connection is {method!r} (pg_hba entry "
            f"#{effective.get('order')}), which does not decide the password bound by ALTER ROLE ... PASSWORD. "
            f"Only {sorted(PASSWORD_DISCRIMINATING_AUTH_METHODS)} do, so neither the §5.5 branch-1 decision nor the "
            "mandatory post-bind re-probe would be conclusive."
        ]
    return []


# ------------------------------------------------------------------------- state observation -----
def observe_role_state(conn: Any) -> Dict[str, Any]:
    """The complete V-6 role-state census. Read-only; no statement is executed as the writer."""
    state: Dict[str, Any] = {"roles": {}, "memberships": [], "comments": {}, "owned_objects": {}}
    with conn.cursor() as cur:
        cur.execute(
            "SELECT rolname, rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolreplication, "
            "rolbypassrls, rolinherit FROM pg_roles WHERE rolname = ANY(%s) ORDER BY rolname",
            ([WRITER_ROLE, INGEST_ROLE],),
        )
        for row in cur.fetchall():
            state["roles"][row[0]] = {"attributes": tuple(bool(v) for v in row[1:7]), "inherit": bool(row[7])}

        # (b)(c)(d)(e): the membership roster and its options, in both directions.
        cur.execute(
            "SELECT r.rolname AS role, m.rolname AS member, a.admin_option "
            "FROM pg_auth_members a JOIN pg_roles r ON r.oid = a.roleid JOIN pg_roles m ON m.oid = a.member "
            "WHERE r.rolname = ANY(%s) OR m.rolname = ANY(%s) ORDER BY 1, 2",
            ([WRITER_ROLE, INGEST_ROLE], [WRITER_ROLE, INGEST_ROLE]),
        )
        state["memberships"] = [(row[0], row[1], bool(row[2])) for row in cur.fetchall()]

        cur.execute(
            "SELECT rolname, shobj_description(oid, 'pg_authid') FROM pg_roles WHERE rolname = ANY(%s)",
            ([WRITER_ROLE, INGEST_ROLE],),
        )
        state["comments"] = {row[0]: row[1] for row in cur.fetchall()}

        # (f): both roles must own nothing.
        for role in (WRITER_ROLE, INGEST_ROLE):
            cur.execute(
                "SELECT count(*) FROM pg_class c JOIN pg_roles r ON r.oid = c.relowner WHERE r.rolname = %s",
                (role,),
            )
            state["owned_objects"][role] = int(cur.fetchone()[0])
    return state


def observe_privileges(conn: Any) -> Dict[str, Any]:
    """V-5b / V-6b / V-7b: catalog privilege probes for the LOGIN role (inheritance-aware).

    `has_*_privilege` negatives replace the SQLSTATE-42501 assertions used in the Tier-A rehearsal,
    because nothing is executed as the writer here — this is a read-only standing proof.
    """
    out: Dict[str, Any] = {"positive": {}, "negative": {}, "unrelated": {}}
    with conn.cursor() as cur:
        cur.execute("SELECT has_database_privilege(%s, %s, 'CONNECT')", (INGEST_ROLE, CONTROL_DATABASE))
        out["positive"]["connect"] = bool(cur.fetchone()[0])
        cur.execute("SELECT has_schema_privilege(%s, 'public', 'USAGE')", (INGEST_ROLE,))
        out["positive"]["usage"] = bool(cur.fetchone()[0])
        for privilege in ("SELECT", "INSERT"):
            cur.execute("SELECT has_table_privilege(%s, %s, %s)", (INGEST_ROLE, AUDIT_TABLE, privilege))
            out["positive"][privilege.lower()] = bool(cur.fetchone()[0])
        for privilege in ("UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"):
            cur.execute("SELECT has_table_privilege(%s, %s, %s)", (INGEST_ROLE, AUDIT_TABLE, privilege))
            out["negative"][privilege.lower()] = bool(cur.fetchone()[0])
        cur.execute("SELECT has_schema_privilege(%s, 'public', 'CREATE')", (INGEST_ROLE,))
        out["negative"]["schema_create"] = bool(cur.fetchone()[0])
        for table in UNRELATED_TABLES:
            cur.execute("SELECT to_regclass(%s) IS NOT NULL", (f"public.{table}",))
            if not cur.fetchone()[0]:
                out["unrelated"][table] = "ABSENT"
                continue
            cur.execute("SELECT has_table_privilege(%s, %s, 'SELECT')", (INGEST_ROLE, f"public.{table}"))
            out["unrelated"][table] = "READABLE" if cur.fetchone()[0] else "denied"
    return out


def observe_environment(conn: Any) -> Dict[str, Any]:
    """Tier-B environment preconditions: triggers (V-10), tenant-DB census (V-17), version, GUCs."""
    env: Dict[str, Any] = {}
    with conn.cursor() as cur:
        cur.execute("SELECT current_database(), current_user, session_user")
        env["database"], env["current_user"], env["session_user"] = cur.fetchone()
        cur.execute("SELECT current_setting('server_version_num')::int")
        env["server_version_num"] = int(cur.fetchone()[0])

        cur.execute(
            "SELECT tgname, tgenabled FROM pg_trigger WHERE tgrelid = to_regclass(%s) AND NOT tgisinternal ORDER BY tgname",
            (AUDIT_TABLE,),
        )
        env["triggers"] = {row[0]: row[1] for row in cur.fetchall()}

        # V-17: the §4 no-tenant-DB derivation is otherwise an UNPROBED assumption.
        cur.execute(
            "SELECT datname FROM pg_database WHERE NOT datistemplate AND (datname LIKE %s OR datname LIKE %s) ORDER BY datname",
            TENANT_DB_PATTERNS,
        )
        env["tenant_databases_on_control_cluster"] = [row[0] for row in cur.fetchall()]

        # V-12b + O-1 sampling GUCs. Non-secret names and values.
        env["log_gucs"] = {}
        for guc in ("log_statement", "log_min_duration_statement", "log_min_error_statement", *SAMPLING_GUCS):
            try:
                cur.execute("SELECT current_setting(%s)", (guc,))
                env["log_gucs"][guc] = cur.fetchone()[0]
            except Exception:  # noqa: BLE001 — a GUC absent on this major version is not an error
                conn.rollback()
                env["log_gucs"][guc] = "<unavailable>"

        # V-12 (RB-1): the EFFECTIVE client authentication method for THIS connection. Under a
        # non-discriminating method the §5.5 branch-1 probe cannot decide credentials at all, so the
        # convergence decision must NOT be taken on probe success alone. Requires PG 10+ and
        # superuser (or pg_read_server_files); recorded as undeterminable — and therefore BLOCKING —
        # otherwise. The three observations below are the rule table, this connection's own facts,
        # and the derived governing entry.
        env["connection"] = _observe_connection_facts(conn, cur, env.get("database"), env.get("session_user"))
        env["host_auth_rules"] = _observe_hba_rules(conn, cur, int(env.get("server_version_num") or 0))
        env["effective_host_auth"] = effective_host_auth(env["host_auth_rules"], env["connection"])
        # REPORTED ONLY, and deliberately named so: this census is the predecessor's whole-file
        # membership test. It is useful context for an operator reading a CONFLICTING plan and it is
        # NEVER a decision input — `v12_problems()` reads `effective_host_auth` and nothing else.
        env["host_auth_method_census"] = (
            sorted({str(rule.get("auth_method")) for rule in env["host_auth_rules"] if rule.get("auth_method")})
            if env["host_auth_rules"] is not None
            else None
        )
    return env


def _observe_connection_facts(conn: Any, cur: Any, database: Optional[str], user: Optional[str]) -> Dict[str, Any]:
    """The four properties `pg_hba.conf` matches a connection against, for THIS connection.

    `local` is decided by `inet_client_addr()` being NULL — a Unix-socket connection has no client
    address. `ssl` decides `hostssl` / `hostnossl`; when it cannot be observed it stays `None`, and
    the matcher then treats those rule types as undecidable rather than assuming either way. The
    database and the role are the ones the connection was ESTABLISHED with, which is what pg_hba was
    evaluated against — `session_user`, never `current_user` (a `SET ROLE` does not re-authenticate).
    """
    facts: Dict[str, Any] = {"database": database, "user": user, "client_address": None, "local": None, "ssl": None}
    try:
        cur.execute("SELECT inet_client_addr()::text")
        address = cur.fetchone()[0]
        facts["client_address"] = address
        facts["local"] = address is None
    except Exception:  # noqa: BLE001 — an unobservable client address leaves the transport undecided
        conn.rollback()
    try:
        cur.execute("SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid()")
        row = cur.fetchone()
        facts["ssl"] = None if row is None or row[0] is None else bool(row[0])
    except Exception:  # noqa: BLE001 — pg_stat_ssl absent/unreadable: `hostssl`/`hostnossl` stay undecidable
        conn.rollback()
    return facts


def _observe_hba_rules(conn: Any, cur: Any, server_version_num: int) -> Optional[List[Dict[str, Any]]]:
    """The `pg_hba.conf` rule table IN FILE ORDER, or `None` when it cannot be read.

    Order is load-bearing: pg_hba is a first-match table, so an unordered read would let the matcher
    pick an arbitrary entry. PostgreSQL 16 added `rule_number`, which stays globally monotonic across
    `include` directives; below 16 `line_number` is the only ordering column there is.
    """
    order_column = "rule_number" if server_version_num >= _HBA_RULE_NUMBER_MIN_VERSION else "line_number"
    try:
        cur.execute(
            f"SELECT {order_column}, type, database, user_name, address, netmask, auth_method, error FROM pg_hba_file_rules ORDER BY 1"
        )
        rows = cur.fetchall()
    except Exception:  # noqa: BLE001 — not readable is reported as such, and V-12 then blocks
        conn.rollback()
        return None
    return [
        {
            "order": row[0],
            "type": row[1],
            "database": list(row[2]) if row[2] is not None else None,
            "user_name": list(row[3]) if row[3] is not None else None,
            "address": row[4],
            "netmask": row[5],
            "auth_method": row[6],
            "error": row[7],
        }
        for row in rows
    ]


def observe_row_baseline(conn: Any) -> Dict[str, Any]:
    """V-11: the deterministic historical-row baseline. Reads nothing but aggregates."""
    with conn.cursor() as cur:
        cur.execute("SELECT count(*), coalesce(max(id), 0) FROM control_gateway_audit")
        total, high_water = cur.fetchone()
        cur.execute(ROW_FINGERPRINT_SQL, (high_water,))
        bounded_count, bounded_max, fingerprint = cur.fetchone()
    return {
        "total_rows": int(total),
        "high_water_mark": int(high_water),
        "bounded_count": int(bounded_count or 0),
        "bounded_max": int(bounded_max or 0),
        "fingerprint": fingerprint,
    }


# ------------------------------------------------------------------------------ classification ---
def classify(state: Dict[str, Any], privileges: Dict[str, Any], environment: Dict[str, Any]) -> Tuple[str, List[str]]:
    """MATCHING / MISSING / CONFLICTING, with every deviation named.

    MISSING means "not yet applied, and nothing observed contradicts the target state" — the normal
    pre-Gate-B classification. CONFLICTING means a pre-existing role deviates from the pinned target,
    and it BLOCKS Gate B: AW-1 does not authorize repairing a conflicting pre-existing role, because
    the unconditional ALTER ROLEs in the payload would silently "fix" it mid-apply.

    RB-1: the V-12 host-authentication precondition is evaluated HERE, through the same
    `v12_problems()` the `apply` convergence path calls. It is not a bind-time detail that `plan` may
    skip — `apply` cannot converge a credential under a non-discriminating method, so a `plan` that
    did not report it would exit 0 on a cluster where `apply` is guaranteed to refuse.
    """
    findings: List[str] = []
    present = [role for role in (WRITER_ROLE, INGEST_ROLE) if role in state["roles"]]

    findings.extend(v12_problems(environment))
    if environment.get("database") != CONTROL_DATABASE:
        findings.append(f"connected to database {environment.get('database')!r}, expected {CONTROL_DATABASE!r}")
    if int(environment.get("server_version_num") or 0) < MIN_SERVER_VERSION_NUM:
        findings.append(
            f"server_version_num {environment.get('server_version_num')} is below the AW-1 floor "
            f"{MIN_SERVER_VERSION_NUM}: on PG < 15 the schema-CREATE probe passes for the wrong reason"
        )
    missing_triggers = [t for t in EXPECTED_TRIGGERS if environment.get("triggers", {}).get(t) != "O"]
    if missing_triggers:
        findings.append(f"013 append-only trigger(s) absent or disabled: {missing_triggers}")
    if environment.get("tenant_databases_on_control_cluster"):
        findings.append(
            "tenant-namespace database(s) present on the control cluster: "
            f"{environment['tenant_databases_on_control_cluster']} — the no-tenant-DB derivation must be re-done"
        )

    if not present:
        return (CONFLICTING if findings else MISSING), findings

    if len(present) == 1:
        findings.append(f"exactly one of the two roles exists ({present[0]}) — a half-applied M2 state")

    for role in present:
        observed = state["roles"][role]
        if observed["attributes"] != EXPECTED_ATTRIBUTES[role]:
            findings.append(
                f"{role} attribute vector {observed['attributes']} != pinned {EXPECTED_ATTRIBUTES[role]} "
                "(rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls)"
            )
        if observed["inherit"] != EXPECTED_INHERIT[role]:
            findings.append(f"{role} rolinherit={observed['inherit']} != pinned {EXPECTED_INHERIT[role]}")
        if state["owned_objects"].get(role):
            findings.append(f"{role} owns {state['owned_objects'][role]} object(s); it must own none")
        expected_comment = EXPECTED_COMMENTS[role]
        if state["comments"].get(role) != expected_comment:
            findings.append(f"{role} COMMENT ON ROLE does not match the frozen text")

    if len(present) == 2:
        expected_membership = [(WRITER_ROLE, INGEST_ROLE, False)]
        if state["memberships"] != expected_membership:
            findings.append(
                f"membership roster {state['memberships']} != pinned {expected_membership} — the ONLY permitted "
                "row is a plain (no ADMIN OPTION) grant of the writer to the ingest role"
            )
        for name, granted in privileges["positive"].items():
            if not granted:
                findings.append(f"{INGEST_ROLE} lacks the required privilege: {name}")
        for name, granted in privileges["negative"].items():
            if granted:
                findings.append(f"{INGEST_ROLE} holds a FORBIDDEN privilege: {name}")
        readable = [t for t, verdict in privileges["unrelated"].items() if verdict == "READABLE"]
        if readable:
            findings.append(f"{INGEST_ROLE} can read unrelated Control-DB table(s): {readable}")
        absent = [t for t, verdict in privileges["unrelated"].items() if verdict == "ABSENT"]
        if absent:
            findings.append(
                f"unrelated-table probe is VACUOUS — table(s) absent: {absent}. Apply control DDL 001-009 first, "
                "or every negative passes for the wrong reason (undefined_table, not permission denied)"
            )

    return (CONFLICTING if findings else MATCHING), findings


def logging_observation_problems(environment: Dict[str, Any]) -> List[str]:
    """§5.6 / V-12b. Returns the reasons a credential bind must NOT be performed."""
    problems: List[str] = []
    gucs = environment.get("log_gucs", {})
    statement = str(gucs.get("log_statement", "")).lower()
    if statement in BLOCKING_LOG_STATEMENT:
        problems.append(f"log_statement={statement!r} would write the full ALTER ROLE ... PASSWORD text to the server log")
    try:
        duration = int(gucs.get("log_min_duration_statement", "-1"))
    except (TypeError, ValueError):
        duration = -1
    if duration >= 0:
        problems.append(f"log_min_duration_statement={duration} can write the full statement text to the server log")
    for guc in SAMPLING_GUCS:
        raw = gucs.get(guc, "0")
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if guc == "log_min_duration_sample":
            if value >= 0:
                problems.append(f"{guc}={raw} can sample full statement text")
        elif value > 0:
            problems.append(f"{guc}={raw} can sample full statement text")
    return problems


# ------------------------------------------------------------------------------------ reporting --
def _print_state(state: Dict[str, Any], privileges: Dict[str, Any], environment: Dict[str, Any]) -> None:
    print(f"  target database     : {environment.get('database')}")
    print(f"  executor identity   : {environment.get('current_user')} (session_user {environment.get('session_user')})")
    version = environment.get("server_version_num")
    print(f"  server_version_num  : {version} (standing major {STANDING_SERVER_MAJOR}, floor {MIN_SERVER_VERSION_NUM})")
    print(f"  013 triggers        : {environment.get('triggers')}")
    print(f"  tenant DBs on ctrl  : {environment.get('tenant_databases_on_control_cluster') or 'none (V-17 clean)'}")
    connection = environment.get("connection") or {}
    print(
        f"  connection facts    : local={connection.get('local')} ssl={connection.get('ssl')} "
        f"client_address={connection.get('client_address') or '<none/unobservable>'}"
    )
    effective = environment.get("effective_host_auth") or {}
    if effective.get("undeterminable"):
        print(f"  effective host auth : UNDETERMINABLE (V-12 BLOCKS) — {effective['undeterminable']}")
    else:
        print(f"  effective host auth : {effective.get('method')!r} at pg_hba entry #{effective.get('order')} — THE V-12 SUBJECT")
    census = environment.get("host_auth_method_census")
    print(f"  host auth census    : {census if census is not None else '<unobservable>'} (reported only; NOT the V-12 decision)")
    print(f"  logging GUCs        : {environment.get('log_gucs')}")
    for role in (WRITER_ROLE, INGEST_ROLE):
        observed = state["roles"].get(role)
        if observed is None:
            print(f"  {role:26s}: ABSENT")
        else:
            print(f"  {role:26s}: attrs={observed['attributes']} inherit={observed['inherit']} owns={state['owned_objects'].get(role)}")
    print(f"  memberships         : {state['memberships'] or 'none'}")
    if privileges["positive"] or privileges["negative"]:
        print(f"  required privileges : {privileges['positive']}")
        print(f"  forbidden privileges: {privileges['negative']}")
        print(f"  unrelated tables    : {privileges['unrelated']}")


# ------------------------------------------------------------------------------------- commands --
def cmd_plan(args: argparse.Namespace) -> int:
    """READ-ONLY. Never binds, never writes material, never executes the payload."""
    psycopg = _psycopg()
    dsn = _executor_dsn()
    print("AW-1 least-privilege Gateway audit writer — PLAN (read-only; no mutation, no bind)")
    print(f"  connection          : {redacted(dsn)}")
    with psycopg.connect(dsn) as conn:
        conn.read_only = True
        environment = observe_environment(conn)
        state = observe_role_state(conn)
        privileges = observe_privileges(conn) if len(state["roles"]) == 2 else {"positive": {}, "negative": {}, "unrelated": {}}
        verdict, findings = classify(state, privileges, environment)
        baseline = observe_row_baseline(conn) if environment.get("triggers") else None
    _print_state(state, privileges, environment)

    if baseline:
        # V-11. Printed as counts and a hash only — the fingerprint is derived from references-only
        # columns, and the recipe is pinned so V-16 recomputes it byte-identically.
        print(f"  row baseline        : total={baseline['total_rows']} high_water_mark(B)={baseline['high_water_mark']}")
        print(f"  fingerprint(id<=B)  : count={baseline['bounded_count']} md5={baseline['fingerprint']}")

    resolved_material, resolved_form = _resolve_writer_material()
    material_present = resolved_material is not None
    print(
        f"  writer material     : {'PRESENT' if material_present else 'ABSENT'}"
        f" ({resolved_form or 'no form'} form; presence only; never read out, never hashed)"
    )
    if material_present:
        # Shape only. The credential is not inspected and no connection is attempted: plan never
        # probes authentication — that is reserved to `apply` under the §5.5 branches.
        for problem in dsn_shape_problems(resolved_material or ""):
            findings.append(problem)
            verdict = CONFLICTING

    # Declaration-level sink readiness (§5.5 step 0), reported so an operator learns BEFORE Gate B
    # that `apply` would refuse. Advisory only: it does not move the role/grant verdict, and it
    # creates nothing — `plan` performs no filesystem write.
    sink_blockers = material_sink_blockers()
    if sink_blockers:
        print("  material sink       : NOT READY — `apply` would refuse before minting anything:")
        for blocker in sink_blockers:
            print(f"      - {blocker}")
    else:
        print(f"  material sink       : declared ({SECRET_DIR_ENV} set; {WRITER_SECRET_REF}@{WRITER_MATERIAL_VERSION}, path not printed)")

    logging_problems = logging_observation_problems(environment)
    if logging_problems:
        print("  statement logging   : WOULD BLOCK A BIND —")
        for problem in logging_problems:
            print(f"      - {problem}")
    else:
        print("  statement logging   : clear for a bind (log_min_error_statement still logs a FAILING bind — residual R-7)")

    print(f"\n  VERDICT: {verdict}")
    for finding in findings:
        print(f"    - {finding}")
    if verdict == CONFLICTING:
        print("\n  CONFLICTING blocks Gate B. AW-1 does NOT authorize repairing a conflicting pre-existing role:")
        print("  the payload's unconditional ALTER ROLEs would silently converge it mid-apply. Escalate.")
        return 2
    if verdict == MISSING:
        print("\n  MISSING is the expected pre-Gate-B state. Nothing has been applied and nothing conflicts.")
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    """GATE-B ONLY. Refuses without --confirm-gate-b-m2."""
    if not args.confirm_gate_b_m2:
        print("REFUSED: `apply` performs the Gate-B M2 mutation (role creation, grants, and a credential bind).")
        print("It requires --confirm-gate-b-m2, and Gate B must be granted with the three credential actions")
        print("named explicitly in the frozen mutation inventory (AW-1 U-3): writer password creation, local")
        print("writer DSN material creation/replacement, and credential binding to sp2_gateway_audit_ingest.")
        print("If any is unnamed, those actions are NOT authorized and this command must not be run.")
        return 3

    psycopg = _psycopg()
    dsn = _executor_dsn()
    print("AW-1 least-privilege Gateway audit writer — APPLY (Gate-B M2)")
    print(f"  connection          : {redacted(dsn)}")

    with psycopg.connect(dsn) as conn:
        environment = observe_environment(conn)
        # §5.4.1 — asserted BEFORE the first statement, not after.
        if environment.get("database") != CONTROL_DATABASE:
            print(f"ABORT: connected to {environment.get('database')!r}; the payload pins {CONTROL_DATABASE!r}.")
            print("Executed elsewhere it would strand GRANT USAGE ON SCHEMA public in the wrong database.")
            return 2

        pre_state = observe_role_state(conn)
        pre_privileges = observe_privileges(conn) if len(pre_state["roles"]) == 2 else {"positive": {}, "negative": {}, "unrelated": {}}
        pre_verdict, pre_findings = classify(pre_state, pre_privileges, environment)
        if pre_verdict == CONFLICTING:
            print("ABORT: pre-apply classification is CONFLICTING. Zero statements executed.")
            for finding in pre_findings:
                print(f"    - {finding}")
            return 2
        roles_were_absent = not pre_state["roles"]

        # If the roles are absent this apply WILL take §5.5 branch 0 and MUST be able to persist the
        # minted material. Proving the sink now costs ZERO statements; discovering it after the
        # payload commits costs a committed mutation followed by a refusal.
        if roles_were_absent:
            sink_problems = material_sink_problems()
            if sink_problems:
                print("ABORT: this apply would take §5.5 branch 0, and the governed §7 material sink is unusable.")
                for problem in sink_problems:
                    print(f"    - {problem}")
                print("Zero statements executed; no role, grant or credential was touched.")
                return 2

        # One transaction: PostgreSQL executes CREATE ROLE / ALTER ROLE / GRANT / COMMENT
        # transactionally, so a mid-payload failure leaves no partial role/grant state.
        with conn.cursor() as cur:
            cur.execute(FROZEN_ROLE_GRANT_SQL)
        conn.commit()
        print("  payload             : committed (single transaction; zero table rows written)")

        post_state = observe_role_state(conn)
        post_privileges = observe_privileges(conn)
        post_verdict, post_findings = classify(post_state, post_privileges, environment)
        if post_verdict != MATCHING:
            print(f"ABORT after payload: post-apply classification is {post_verdict}. No credential action taken.")
            for finding in post_findings:
                print(f"    - {finding}")
            return 2

        outcome = _converge_credential(conn, psycopg, environment, executor_dsn=dsn, roles_were_absent=roles_were_absent)

    print(f"\n  ROLE/GRANT STATE: {MATCHING}")
    print(f"  CREDENTIAL      : {outcome}")
    if outcome == CONFLICTING:
        return 2
    return 0


def _converge_credential(conn: Any, psycopg: Any, environment: Dict[str, Any], *, executor_dsn: str, roles_were_absent: bool) -> str:
    """§5.5 credential convergence — exactly one branch, never a blind re-bind, and never a bind
    whose material cannot be reached afterwards.

    Branch 0 (`M2 INITIAL CREATION`) is the correction carried into Gate A. AW-1 V2 as written has
    only three branches, and on the first-ever apply every branch-2 conjunct holds: material absent,
    role/grant state converged (by the payload that just ran), bind not done. A three-branch
    implementation therefore records the very first credential creation as "recovery" from a crash
    that never occurred, and the evidence pack inherits that falsehood.

    Branch 1 must SKIP, not re-bind: re-binding even an identical password re-salts the SCRAM
    verifier and mutates `pg_authid.rolpassword`, which is a delta under the zero-unintended-deltas
    rule and a de-facto rotation — separately governed.

    Both MUTATING branches perform §5.5's four steps in the governed order and all four are
    mandatory: **mint → bind (client-side, after the §5.6 observation) → write the material →
    re-probe** and require authentication exactly as `sp2_gateway_audit_ingest`. Dropping the last
    two is not a partial implementation, it is an unrecoverable one: the role ends up holding a
    password that existed only in a process that has exited, branch 1 becomes permanently
    unreachable, `status` can never go green, and the launcher's §9 O-6 start gate can never open.
    That is why the sink is proven writable BEFORE anything is minted.
    """
    material, form = _resolve_writer_material()

    # V-12 is a HARD PRECONDITION of the decision, not context (§5.5 note 6). Under a
    # non-discriminating effective method no credential probe can decide anything — which
    # disqualifies the branch-1 decision AND the mandatory post-bind re-probe, so it blocks the whole
    # convergence rather than one branch. RB-1: this is the SAME `v12_problems()` `classify()` and
    # therefore `plan` consume, on the same observation, so the two can never disagree. Reaching it
    # via `apply` additionally requires the pre-apply `classify()` to have passed, which means this
    # is now defence in depth rather than the first line of it.
    v12 = v12_problems(environment)
    if v12:
        print("  V-12                : CONFLICTING — the effective host authentication method for this connection")
        print("                        makes neither the converged decision nor the required re-probe decisive:")
        for problem in v12:
            print(f"      - {problem}")
        return CONFLICTING

    authenticates = False
    if material is not None:
        problems = dsn_shape_problems(material)
        if problems:
            for problem in problems:
                print(f"  DSN shape           : {problem}")
            return CONFLICTING
        authenticates = _probe_authenticates(psycopg, material)

    if material is not None and authenticates:
        # Branch 1 — converged. This is the branch a successful mutating run must be able to reach
        # on its NEXT invocation; if it cannot, the arc has no steady state.
        print(f"  branch              : 1 (converged) — material present ({form} form) and authenticating; bind and rewrite SKIPPED")
        return NO_CHANGES

    if roles_were_absent and material is None:
        label = M2_INITIAL_CREATION
        branch = "0 (initial creation) — the roles did not exist before this apply"
    elif material is None or not authenticates:
        label = M2_RECOVERY
        branch = "2 (bounded M2 recovery) — role/grant state was already MATCHING before this apply"
    else:  # pragma: no cover — defensive; the combinations above are exhaustive
        return CONFLICTING

    # §5.5 step 0 — can the minted material be persisted AT ALL? Before the mint, before the bind.
    sink_problems = material_sink_problems()
    if sink_problems:
        print("  MATERIAL SINK       : CONFLICTING — nothing minted, nothing bound, credential UNCHANGED:")
        for problem in sink_problems:
            print(f"      - {problem}")
        return CONFLICTING

    print(f"  branch              : {branch}")

    problems = logging_observation_problems(environment)
    if problems:
        print("  V-12b               : CONFLICTING — bind NOT performed:")
        for problem in problems:
            print(f"      - {problem}")
        print("  Remediation (server logging configuration) is outside AW-1's bounded scope.")
        return CONFLICTING
    print(f"  V-12b               : observed and clear ({environment.get('log_gucs')})")

    # ---- §5.5 in the governed order: mint -> bind -> write the material -> re-probe -------------
    password = _mint_password()
    writer_dsn = compose_writer_dsn(executor_dsn, password)
    shape_problems = dsn_shape_problems(writer_dsn)
    if shape_problems:  # pragma: no cover — the pinned parts and the UNRESERVED alphabet exclude this
        print("  COMPOSED DSN        : CONFLICTING — nothing bound, credential UNCHANGED:")
        for problem in shape_problems:
            print(f"      - {problem}")
        return CONFLICTING

    sql = importlib.import_module("psycopg.sql")
    with conn.cursor() as cur:
        # Client-side bound: ALTER ROLE is a utility statement and PostgreSQL accepts no server-side
        # bind parameters for it. psycopg.sql.Literal performs the safe quoting.
        cur.execute(sql.SQL("ALTER ROLE {} PASSWORD {}").format(sql.Identifier(INGEST_ROLE), sql.Literal(password)))
    conn.commit()
    print("  bind                : executed (client-side bound; the value appears in no output and in no repository file)")

    path = _material_file_path()
    assert path is not None, "material_sink_problems() already established the sink location"
    try:
        _write_material(path, writer_dsn)
    except OSError as exc:
        print(f"  MATERIAL WRITE      : FAILED ({exc.__class__.__name__}) AFTER the bind committed.")
        print("  The role's credential HAS been changed and the material was not persisted. Re-run `apply`:")
        print("  §5.5 branch 2 is exactly this recovery and it mints one fresh password in place.")
        return CONFLICTING
    print(f"  material            : written to the governed §7 file form {WRITER_SECRET_REF}@{WRITER_MATERIAL_VERSION}")
    print(f"                        under {SECRET_DIR_ENV} — operator-local, untracked, outside every repository.")
    print(f"                        Same ref, same version, in place. It carries application_name={INGEST_APPLICATION_NAME}")
    print("                        and no libpq options keyword. The value is not printed here and enters no evidence.")

    # §5.5 REQUIRED re-probe — re-RESOLVED through the same mechanism the runtime uses, so what is
    # proven is that the PERSISTED material authenticates, not that an in-memory string would have.
    reprobed, reprobed_form = _resolve_writer_material()
    if reprobed is None or not _probe_authenticates(psycopg, reprobed):
        print(f"  RE-PROBE            : FAILED — the persisted material does not authenticate as {INGEST_ROLE}.")
        print("  The role's credential HAS been changed. Re-run `apply` to take the bounded §5.5 branch-2")
        print("  recovery path, which mints one fresh password and replaces the material in place.")
        return CONFLICTING
    print(f"  re-probe            : authenticated exactly as {INGEST_ROLE} using the PERSISTED material ({reprobed_form} form)")
    return label


def _probe_authenticates(psycopg: Any, material: str) -> bool:
    """Bounded connection attempt: does the material authenticate EXACTLY as the ingest role?

    Connection establishment, not secret inspection. Nothing is printed or persisted.
    """
    try:
        with psycopg.connect(material, connect_timeout=5) as probe:
            with probe.cursor() as cur:
                cur.execute("SELECT current_user, session_user, current_database()")
                current_user, session_user, database = cur.fetchone()
        return current_user == INGEST_ROLE and session_user == INGEST_ROLE and database == CONTROL_DATABASE
    except Exception:  # noqa: BLE001 — any failure is "does not authenticate"; the reason is not emitted
        return False


def cmd_status(args: argparse.Namespace) -> int:
    """READ-ONLY, fail-closed, fixed declared pass count (V-13). The launcher's start gate."""
    psycopg = _psycopg()
    dsn = _executor_dsn()
    print(f"AW-1 least-privilege Gateway audit writer — STATUS ({STATUS_DECLARED_CHECKS} declared checks)")
    with psycopg.connect(dsn) as conn:
        conn.read_only = True
        environment = observe_environment(conn)
        state = observe_role_state(conn)
        privileges = observe_privileges(conn) if len(state["roles"]) == 2 else {"positive": {}, "negative": {}, "unrelated": {}}
        material, material_form = _resolve_writer_material()

    checks: List[Tuple[str, bool, str]] = [
        ("S1 connected to the pinned control database", environment.get("database") == CONTROL_DATABASE, str(environment.get("database"))),
        ("S2 both AW-1 roles exist", len(state["roles"]) == 2, ", ".join(sorted(state["roles"])) or "none"),
        (
            "S3 attribute vectors match the pinned six-attribute census",
            all(state["roles"].get(r, {}).get("attributes") == EXPECTED_ATTRIBUTES[r] for r in (WRITER_ROLE, INGEST_ROLE)),
            str({r: state["roles"].get(r, {}).get("attributes") for r in (WRITER_ROLE, INGEST_ROLE)}),
        ),
        (
            "S4 membership roster is exactly one plain grant",
            state["memberships"] == [(WRITER_ROLE, INGEST_ROLE, False)],
            str(state["memberships"]),
        ),
        (
            "S5 required privileges granted",
            all(privileges["positive"].values()) and bool(privileges["positive"]),
            str(privileges["positive"]),
        ),
        ("S6 forbidden privileges absent", not any(privileges["negative"].values()), str(privileges["negative"])),
        (
            "S7 unrelated Control-DB tables unreadable and probe non-vacuous",
            bool(privileges["unrelated"]) and all(v == "denied" for v in privileges["unrelated"].values()),
            str(privileges["unrelated"]),
        ),
        (
            "S8 both 013 append-only triggers present and enabled",
            all(environment.get("triggers", {}).get(t) == "O" for t in EXPECTED_TRIGGERS),
            str(environment.get("triggers")),
        ),
        (
            "S9 V-17 no tenant-namespace database on the control cluster",
            not environment.get("tenant_databases_on_control_cluster"),
            str(environment.get("tenant_databases_on_control_cluster") or "none"),
        ),
    ]
    assert len(checks) == STATUS_DECLARED_CHECKS, "the declared and executed check counts must agree"

    failed = 0
    for label, ok, detail in checks:
        print(f"  {'PASS' if ok else 'FAIL'}: {label} — {detail}")
        if not ok:
            failed += 1

    print(f"  INFO: writer material {'PRESENT' if material else 'ABSENT'} ({material_form or 'no form'}; presence only)")
    if failed:
        print(f"\nSTATUS FAILED ({failed} of {STATUS_DECLARED_CHECKS}). The Gateway-audit ingest edge MUST NOT start:")
        print("with the writer state incomplete it would fall back to the DEFAULT control-store reference, which")
        print("by standing convention resolves to the sp2_local SUPERUSER DSN — the exact condition AW-1 exists to")
        print("eliminate. AW-1 §9 O-6 -> O-7.")
        return 1
    print(f"\nSTATUS OK ({STATUS_DECLARED_CHECKS} of {STATUS_DECLARED_CHECKS})")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="AW-1 least-privilege Gateway operational-audit writer (operator tool)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("plan", help="read-only: observe and classify; never binds, never mutates")
    apply_parser = sub.add_parser("apply", help="GATE-B ONLY: execute the frozen M2 payload and converge the credential")
    apply_parser.add_argument(
        "--confirm-gate-b-m2",
        action="store_true",
        help="required. Confirms Gate B is granted and the three credential actions are named in the frozen inventory.",
    )
    sub.add_parser("status", help="read-only, fail-closed start gate (fixed declared pass count)")
    args = parser.parse_args(list(argv) if argv is not None else None)
    return {"plan": cmd_plan, "apply": cmd_apply, "status": cmd_status}[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
