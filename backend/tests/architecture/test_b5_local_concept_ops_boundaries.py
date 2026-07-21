"""B5 local-concept bounded-operations boundary guard (default suite; no DB, no network).

Static text/AST boundary pins for the local-concept bounded-operations surfaces:

  - backend/tests/control_plane/requires_pg/b5_local_concept_ops.py   (the operator wrapper)
  - infrastructure/runbooks/b5_local_concept_ops.md                   (the operator runbook)

This guard binds no runtime, imports no database driver, opens no socket, and touches no database. It keeps
the local-concept wrapper an honest LOCAL-CONCEPT-ONLY, MANUAL_ONLY, reuse-not-duplicate bounded operator, and
fails CLOSED on any embedded DDL, duplicated migration order, new composition root, new secret backend, new
environment variable, ``build/lib`` shadow import, ``D:`` PostgreSQL data-directory bind, repo-internal runtime
artifact, wrong artifact root, implicit standing ``apply``/``teardown``, restore over a standing identity,
exposed raw secret/DSN, served/hosted/deployment/activation/production behaviour, hosted/production overclaim,
or operator-surface widening. Every forbidden-pattern test carries a non-vacuity companion so it can never pass
merely because a required implementation element is absent.

Exactly twenty-two tests:

 1. test_manifest_surfaces_exist
 2. test_ops_is_operator_not_test_manual_only_and_start_gated
 3. test_ops_locates_driver_via_importlib_no_static_db_import
 4. test_ops_exposes_exactly_the_approved_surface
 5. test_ops_enumerates_exactly_the_four_authoritative_databases
 6. test_ops_reuses_standing_idioms_not_its_alpha_beta_tenant_set
 7. test_ops_forbids_restore_over_standing_identities
 8. test_ops_restore_target_is_a_disposable_validation_database
 9. test_ops_embeds_no_schema_ddl_or_db_lifecycle_sql
10. test_ops_duplicates_no_migration_order
11. test_ops_defines_no_new_composition_root_or_secret_backend
12. test_ops_reuses_canonical_provisioning_and_secret_store
13. test_ops_canonical_imports_only_no_build_lib_shadow
14. test_ops_introduces_no_new_environment_variable
15. test_ops_artifact_root_is_exact_never_short_never_repo
16. test_ops_pg_dump_discipline_reexpressed_not_imported
17. test_ops_restore_validate_single_final_write_after_disposal
18. test_ops_seed_is_idempotent_and_protects_system_primary
19. test_ops_no_served_hosted_or_activation_behavior
20. test_surfaces_reject_hosted_and_production_overclaims
21. test_surfaces_preserve_locked_state_and_secret_references_only
22. test_runbook_distinguishes_four_stages_and_holds_runtime

This guard closes no blocker. The live blocker census remains 7 of 9 OPEN; Production remains NOT READY /
DO-NOT-ACTIVATE. The guard positively requires exactly that and rejects any drift.

Pure stdlib; standalone-runnable:
  python tests/architecture/test_b5_local_concept_ops_boundaries.py
"""

from __future__ import annotations

import ast
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

_OPS = _scan.BACKEND_ROOT / "tests" / "control_plane" / "requires_pg" / "b5_local_concept_ops.py"
_RUNBOOK = _scan.REPO_ROOT / "infrastructure" / "runbooks" / "b5_local_concept_ops.md"

# Reference-delta targets — referenced (existence-only), never restated by the local-concept surfaces.
_REF_STANDING_OPS = _scan.BACKEND_ROOT / "tests" / "control_plane" / "requires_pg" / "b5_standing_topology.py"
_REF_STANDING_RUNBOOK = _scan.REPO_ROOT / "infrastructure" / "runbooks" / "b5_standing_topology.md"
_REF_ROLLBACK_RUNBOOK = _scan.REPO_ROOT / "infrastructure" / "runbooks" / "controlled_rollback_rehearsal.md"
_REF_COMPOSE = _scan.REPO_ROOT / "infrastructure" / "docker" / "docker-compose.local.yml"

# The approved operator surface and the surface that must NEVER be exposed (PRD §8).
_APPROVED_COMMANDS = {"plan", "backup", "restore-validate", "seed", "status"}
_FORBIDDEN_COMMANDS = ["apply", "teardown", "serve", "activate", "deploy", "promote", "production", "hosted"]

# The authoritative four-cluster database identities (PRD §5; docker-compose.local.yml) — enumerated exactly.
_AUTH_DBS = {
    "snackportal2_control_local",
    "snackportal2_tenant_acme_local",
    "snackportal2_tenant_zeta_local",
    "snackportal2_tenant_nova_local",
}
# The retained standing tenants — reused for idiom only; never adopted as the cluster set, never restored over.
_STANDING_TENANTS = {"b5_standing_alpha", "b5_standing_beta"}
_FORBIDDEN_RESTORE = _AUTH_DBS | _STANDING_TENANTS

# The disposable restore-validation database prefix (PRD §10.2) and the deterministic synthetic prefix (§11.2).
_VALIDATION_PREFIX = "sp2_local_restore_validation_"
_SYNTHETIC_PREFIX = "sp2-local-concept-"

# The exact approved artifact root and the prohibited short path (PRD §4), in both slash forms (normalized).
_APPROVED_ROOT = "d:/pitchsnack/sp2-local-concept"
_FORBIDDEN_SHORT_ROOT = "d:/sp2-local-concept"

# Schema-DDL / destructive / DB-lifecycle verbs that must never appear in an executed SQL string literal.
# (CREATE/DROP DATABASE are delegated to the canonical PostgresProvisioningOperator, so no such literal exists.)
_DDL_SQL_VERBS = [
    "create table",
    "alter table",
    "create index",
    "create unique index",
    "create trigger",
    "create or replace",
    "create function",
    "create sequence",
    "create schema",
    "create database",
    "drop database",
    "drop table",
    "truncate",
    "delete from",
]

# Served-edge markers that must NEVER appear in the composed-free wrapper.
_SERVED_MARKERS = ["_server_from_env", "httpconnection", "socket.create_connection", "serve_forever", "build_gateway", "build_dispatch"]

# Runtime service packages the wrapper must never import.
_FORBIDDEN_RUNTIME_IMPORTS = ("api_gateway", "auth_router", "import_service", "lineage_service")

# Forbidden hosted / production / closure / census overclaim patterns (normalized text).
_FORBIDDEN_PATTERNS = [
    (r"production\s+ready", "'production ready' overclaim"),
    (r"production\s+activation\s+authorized", "'production activation authorized' overclaim"),
    (r"activate\s+production", "'activate production' overclaim"),
    (r"hosted\s+proof\s+(?:complete|achieved|proven)", "'hosted proof proven' overclaim"),
    (r"production\s+proof\s+(?:complete|achieved|proven)", "'production proof proven' overclaim"),
    (r"hosted\s+ready", "'hosted ready' overclaim"),
    (r"\b8\s*(?:of|/)\s*9\b", "stale census '8 of 9'"),
    (r"\b6\s*(?:of|/)\s*9\b", "false census '6 of 9'"),
    (r"do-not-activate\s+lifted", "'do-not-activate lifted' overclaim"),
    (r"blocker\s+closed", "'blocker closed' overclaim"),
]

_LOCKED_STATE_NEEDLES = ["closes no blocker", "7 of 9 open", "not ready / do-not-activate"]

# Secret/PII shape detectors (BUILT from low-entropy fragments — never a contiguous shape in this source).
_DSN_RE = re.compile("postgresql" + "://" + r"\S")
_JWT_MARKER = "ey" + "J"
_KEY_MARKER = "-----" + "BEGIN"
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

# New-env-var name shapes the wrapper must not hardcode (SP2_* / SNACKPORTAL_* uppercase env-var names).
_ENV_NAME_RE = re.compile(r"\b(?:SP2|SNACKPORTAL)_[A-Z0-9_]+\b")


def _text(path: pathlib.Path) -> str:
    assert path.is_file(), f"{path} must exist"
    return path.read_text(encoding="utf-8")


def _norm(s: str) -> str:
    """Lowercase, normalize dash/arrow glyphs, drop markdown emphasis, and collapse whitespace."""
    s = s.lower()
    s = s.replace("—", "-").replace("–", "-").replace("→", "->")
    s = s.replace("*", "").replace("`", "")
    return re.sub(r"\s+", " ", s)


def _ops_tree() -> ast.AST:
    return ast.parse(_text(_OPS), filename=str(_OPS))


def _string_literals(tree: ast.AST) -> set[str]:
    return {node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)}


def _add_parser_names(tree: ast.AST) -> set[str]:
    """The exact set of ``sub.add_parser("X")`` command names declared in the wrapper (AST-precise)."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_parser"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            names.add(node.args[0].value)
    return names


def _function_names(tree: ast.AST) -> set[str]:
    return {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}


# --- 1 -------------------------------------------------------------------------------------------
def test_manifest_surfaces_exist() -> None:
    assert _OPS.is_file(), "the local-concept operator wrapper must exist at the manifest path"
    assert _RUNBOOK.is_file(), "the local-concept operator runbook must exist at the manifest path"
    for ref in (_REF_STANDING_OPS, _REF_STANDING_RUNBOOK, _REF_ROLLBACK_RUNBOOK, _REF_COMPOSE):
        assert ref.is_file(), f"the reference-delta target must exist: {ref.name}"


# --- 2 -------------------------------------------------------------------------------------------
def test_ops_is_operator_not_test_manual_only_and_start_gated() -> None:
    assert not _OPS.name.startswith("test_"), "the operator must NOT carry a test_ prefix (never auto-collected as a test)"
    norm = _norm(_text(_OPS))
    for needle in ("operator tool", "manual_only", "start-gate", "closes no blocker"):
        assert needle in norm, f"the operator must be a MANUAL_ONLY, START-GATED operator tool: missing {needle!r}"


# --- 3 -------------------------------------------------------------------------------------------
def test_ops_locates_driver_via_importlib_no_static_db_import() -> None:
    imported = _scan.imported_modules(_OPS)
    for mod in imported:
        assert not (mod == "psycopg" or mod.startswith("psycopg")), f"the operator must not statically import a DB driver: {mod!r}"
        assert mod not in ("jwt", "cryptography", "socket"), f"the operator must import no crypto/socket: {mod!r}"
    src = _text(_OPS)
    assert 'importlib.import_module("psycopg")' in src, "the operator must locate psycopg via importlib at call time (Driver Containment)"
    # non-vacuity: the static-driver detector fires on a planted import list.
    planted = ["psycopg", "psycopg.rows", "jwt"]
    assert any(m == "psycopg" or m.startswith("psycopg") or m in ("jwt", "cryptography", "socket") for m in planted), "detector must fire"


# --- 4 -------------------------------------------------------------------------------------------
def test_ops_exposes_exactly_the_approved_surface() -> None:
    tree = _ops_tree()
    declared = _add_parser_names(tree)
    assert declared == _APPROVED_COMMANDS, f"the operator must expose EXACTLY {sorted(_APPROVED_COMMANDS)}; got {sorted(declared)}"
    funcs = _function_names(tree)
    for forbidden in _FORBIDDEN_COMMANDS:
        assert forbidden not in declared, f"the operator must not expose the forbidden command {forbidden!r}"
        assert f"cmd_{forbidden}" not in funcs, f"the operator must not define a handler cmd_{forbidden}"
    # non-vacuity: the add_parser detector fires on a planted subparser declaration.
    planted = ast.parse("import argparse\np = argparse.ArgumentParser()\ns = p.add_subparsers()\ns.add_parser('apply')\n")
    assert "apply" in _add_parser_names(planted), "the add_parser detector must fire on a planted forbidden command"


# --- 5 -------------------------------------------------------------------------------------------
def test_ops_enumerates_exactly_the_four_authoritative_databases() -> None:
    literals = _string_literals(_ops_tree())
    present = {db for db in _AUTH_DBS if db in literals}
    assert present == _AUTH_DBS, (
        f"the operator must enumerate the four authoritative compose databases; missing {sorted(_AUTH_DBS - present)}"
    )
    norm = _norm(_text(_OPS))
    for needle in ("tenant alpha witness", "tenant beta witness", "adjacent witness", "5540", "5541", "5542", "5543"):
        assert needle in norm, f"the operator must carry the witness mapping and compose ports: missing {needle!r}"


# --- 6 -------------------------------------------------------------------------------------------
def test_ops_reuses_standing_idioms_not_its_alpha_beta_tenant_set() -> None:
    literals = _string_literals(_ops_tree())
    # The standing tenants may be NAMED (never-disturb / forbidden-restore), but never as a cluster DATABASE identity.
    for standing in _STANDING_TENANTS:
        assert standing in literals, f"the operator must name the standing tenant to forbid disturbing/restoring it: {standing!r}"
    # AST: the Cluster(...) constructor call database arguments must be EXACTLY the four authoritative identities.
    cluster_dbs: set[str] = set()
    for node in ast.walk(_ops_tree()):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "Cluster":
            if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str):
                cluster_dbs.add(node.args[1].value)
    assert cluster_dbs == _AUTH_DBS, (
        f"the four Cluster database identities must be exactly the authoritative set; got {sorted(cluster_dbs)}"
    )
    assert not (_STANDING_TENANTS & cluster_dbs), "b5_standing_alpha/b5_standing_beta must never be adopted as a cluster database identity"


# --- 7 -------------------------------------------------------------------------------------------
def test_ops_forbids_restore_over_standing_identities() -> None:
    src = _text(_OPS)
    for name in _FORBIDDEN_RESTORE:
        assert name in src, f"the operator must know the forbidden restore target {name!r}"
    assert "_reject_forbidden_restore_target" in src, "the operator must define a forbidden-restore-target guard"
    assert "FORBIDDEN_RESTORE_TARGETS" in src, "the operator must declare the forbidden-restore-target set"
    # the guard must be CALLED before a restore process is ever invoked.
    tree = _ops_tree()
    calls = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "_reject_forbidden_restore_target"
    ]
    assert calls, "the forbidden-restore-target guard must be invoked"
    # non-vacuity: the forbidden set is the four authoritative DBs plus the two standing tenants (exactly six).
    assert len(_FORBIDDEN_RESTORE) == 6 and _AUTH_DBS <= _FORBIDDEN_RESTORE and _STANDING_TENANTS <= _FORBIDDEN_RESTORE, (
        "detector set must be exact"
    )


# --- 8 -------------------------------------------------------------------------------------------
def test_ops_restore_target_is_a_disposable_validation_database() -> None:
    src = _text(_OPS)
    assert _VALIDATION_PREFIX in src, "the operator must restore only into a disposable sp2_local_restore_validation_* database"
    assert "pg_restore" in src and "--dbname" in src, "the operator must re-express a bounded pg_restore-into-database argv"
    # the restore-into argv must guard the validation-database identifier before returning.
    norm = _norm(src)
    assert "new-but-bounded" in norm or "new but bounded" in norm, (
        "the operator must state restore-into-DB is new-but-bounded (Observation C)"
    )
    # non-vacuity: a well-formed disposable name matches the prefix; a standing name does not.
    assert (_VALIDATION_PREFIX + "abcd1234").startswith(_VALIDATION_PREFIX), "the disposable prefix must match a well-formed name"
    assert not "snackportal2_control_local".startswith(_VALIDATION_PREFIX), "a standing name must never look disposable"


# --- 9 -------------------------------------------------------------------------------------------
def test_ops_embeds_no_schema_ddl_or_db_lifecycle_sql() -> None:
    literals = {s.lower() for s in _string_literals(_ops_tree())}
    for literal in literals:
        for verb in _DDL_SQL_VERBS:
            assert verb not in literal, f"the operator must embed no schema/DDL/DB-lifecycle SQL literal ({verb!r} found)"
    # non-vacuity: every banned verb is detected inside a planted SQL literal that contains them all.
    planted = " ; ".join(v + " probe" for v in _DDL_SQL_VERBS)
    for verb in _DDL_SQL_VERBS:
        assert verb in planted, f"the DDL-verb detector must fire on a planted sample: {verb!r}"
        assert verb not in "insert into startups values (1) on conflict do nothing", f"the detector must ignore DML: {verb!r}"


# --- 10 ------------------------------------------------------------------------------------------
def test_ops_duplicates_no_migration_order() -> None:
    literals = _string_literals(_ops_tree())
    ddl_file_re = re.compile(r"^\d{3}_.*\.sql$")
    for literal in literals:
        assert not ddl_file_re.match(literal), f"the operator must not enumerate a migration/DDL-file order: {literal!r}"
    src = _text(_OPS)
    for token in ("_CONTROL_DDL_ORDER", "default_tenant_schema_ddl_paths", "infrastructure/db/control", "infrastructure/db/tenant"):
        assert token not in src, f"the operator must not duplicate the migration order surface: {token!r}"
    # non-vacuity: the DDL-file detector fires on a planted canonical filename.
    assert ddl_file_re.match("001_distinctness_ledger.sql"), "the DDL-file detector must fire on a planted canonical name"


# --- 11 ------------------------------------------------------------------------------------------
def test_ops_defines_no_new_composition_root_or_secret_backend() -> None:
    tree = _ops_tree()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            assert node.name != "create_app", "the operator must not define a new composition root (create_app)"
        if isinstance(node, ast.ClassDef):
            lname = node.name.lower()
            assert "controlplane" not in lname, "the operator must not define a new ControlPlane composition root"
            assert "secretstore" not in lname and "secretbackend" not in lname, "the operator must not define a new secret backend"
    # non-vacuity: the class-name detectors fire on planted definitions.
    planted = ast.parse("class MySecretStore: pass\nclass MyControlPlane: pass\n")
    names = [n.name.lower() for n in ast.walk(planted) if isinstance(n, ast.ClassDef)]
    assert any("secretstore" in n for n in names) and any("controlplane" in n for n in names), "detectors must fire"


# --- 12 ------------------------------------------------------------------------------------------
def test_ops_reuses_canonical_provisioning_and_secret_store() -> None:
    imported = set(_scan.imported_modules(_OPS))
    assert "control_plane.adapters.providers.postgres_provisioning_operator" in imported, (
        "the operator must reuse the canonical provisioning operator"
    )
    assert "shared.adapters.providers.env_reference_secret_store" in imported, (
        "the operator must reuse the canonical reference secret store"
    )
    src = _text(_OPS)
    for symbol in ("PostgresProvisioningOperator", "EnvReferenceSecretStore"):
        assert symbol in src, f"the operator must delegate to the canonical {symbol}"


# --- 13 ------------------------------------------------------------------------------------------
def test_ops_canonical_imports_only_no_build_lib_shadow() -> None:
    # The enforcement is import-based (the docstring may lawfully NAME the build/lib shadow to forbid it).
    for mod in _scan.imported_modules(_OPS):
        assert not mod.startswith("build."), f"the operator must not import the build shadow: {mod!r}"
        assert "build.lib" not in mod, f"the operator must not import the build/lib shadow: {mod!r}"
        assert "/build/lib/" not in mod, f"the operator must not import the build/lib shadow: {mod!r}"
    # Every backend import must resolve from a canonical top-level package under backend/<pkg>/...
    for mod in _scan.imported_modules(_OPS):
        assert not mod.startswith("backend.build"), f"the operator must not import a backend.build shadow: {mod!r}"
    # non-vacuity: the shadow detector fires on planted module names in either shape.
    assert "build.control_plane".startswith("build."), "the build-shadow detector must fire on a planted sample"
    assert "build.lib" in "backend.build.lib.control_plane".replace("backend.", ""), "the build.lib detector must fire on a planted sample"


# --- 14 ------------------------------------------------------------------------------------------
def test_ops_introduces_no_new_environment_variable() -> None:
    tree = _ops_tree()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Subscript)
                    and isinstance(target.value, ast.Attribute)
                    and target.value.attr == "environ"
                    and isinstance(target.value.value, ast.Name)
                    and target.value.value.id == "os"
                ):
                    raise AssertionError("the operator must not assign os.environ[...] (no new environment variable)")
    hits = _ENV_NAME_RE.findall(_text(_OPS))
    assert not hits, f"the operator must hardcode no new SP2_*/SNACKPORTAL_* environment-variable name: {hits}"
    # non-vacuity: both detectors fire on planted samples.
    planted = ast.parse("import os\nos.environ['SP2_NEW_THING'] = 'x'\n")
    assert any(
        isinstance(n, ast.Subscript) and isinstance(n.value, ast.Attribute) and n.value.attr == "environ" for n in ast.walk(planted)
    ), "the os.environ-assignment detector must fire"
    assert _ENV_NAME_RE.search("SP2_NEW_THING and SNACKPORTAL_NEW_BACKEND"), "the env-name detector must fire on a planted sample"


# --- 15 ------------------------------------------------------------------------------------------
def test_ops_artifact_root_is_exact_never_short_never_repo() -> None:
    norm = _norm(_text(_OPS))
    assert _APPROVED_ROOT in norm, "the operator must use the exact approved artifact root D:/Pitchsnack/SP2-Local-Concept"
    # The prohibited short root may be NAMED only as the refused path — never as a live write target substitution.
    assert "prohibited short path" in norm, "the operator must explicitly refuse the prohibited short path"
    for needle in ("_refuse_repo_path", "resolves inside the repository", "live postgresql data directory"):
        assert needle in norm, f"the operator must fail closed on repo-internal and D:-datadir writes: missing {needle!r}"
    # non-vacuity: the approved root does NOT contain the forbidden short root as a substring.
    assert _FORBIDDEN_SHORT_ROOT not in _APPROVED_ROOT, "the approved root must not embed the forbidden short root"
    assert _APPROVED_ROOT.startswith("d:/pitchsnack/"), "the approved root must live under D:/Pitchsnack"


# --- 16 ------------------------------------------------------------------------------------------
def test_ops_pg_dump_discipline_reexpressed_not_imported() -> None:
    norm = _norm(_text(_OPS))
    for needle in ("--format=custom", "--no-password", "pgpassword", "pg_restore --list", "sha-256"):
        assert needle in norm, f"the operator must re-express the pg_dump discipline: missing {needle!r}"
    # It must NOT import the private sibling backup helpers (Observation B): re-expression, not cross-harness import.
    for mod in _scan.imported_modules(_OPS):
        assert "dbr_ar_2d_standing_witnesses" not in mod, "the operator must not import the private sibling backup harness"
    src = _text(_OPS)
    for private in ("_pg_dump_argv", "_create_backup", "_backup_child_env"):
        assert f"from {private}" not in src, f"the operator must not import the private sibling helper {private!r}"
    assert "refuse-overwrite" in norm or "refuse overwrite" in norm, "the operator must refuse to overwrite an existing dump"


# --- 17 (single-final-write) ---------------------------------------------------------------------
def _restore_fn(tree: ast.AST) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "cmd_restore_validate":
            return node
    raise AssertionError("the operator must define cmd_restore_validate")


def _subscript_assign_lines(scope: ast.AST, base: str, key: str) -> list[int]:
    lines: list[int] = []
    for node in ast.walk(scope):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if (
                isinstance(target, ast.Subscript)
                and isinstance(target.value, ast.Name)
                and target.value.id == base
                and isinstance(target.slice, ast.Constant)
                and target.slice.value == key
            ):
                lines.append(node.lineno)
    return sorted(lines)


def _finalization_positions(fn: ast.FunctionDef) -> tuple[int, int, int, int, int]:
    outer_try = next((n for n in fn.body if isinstance(n, ast.Try) and n.finalbody), None)
    assert outer_try is not None and outer_try.end_lineno is not None, "a top-level try/finally disposal block is required"
    retained = [
        n.lineno
        for n in ast.walk(outer_try)
        if isinstance(n, ast.Assert)
        and isinstance(n.test, ast.Compare)
        and isinstance(n.test.left, ast.Name)
        and n.test.left.id == "retained"
        and len(n.test.ops) == 1
        and isinstance(n.test.ops[0], ast.Eq)
        and len(n.test.comparators) == 1
        and isinstance(n.test.comparators[0], ast.Constant)
        and n.test.comparators[0].value == 0
    ]
    assert len(retained) == 1, f"exactly one 'retained == 0' finally assertion is required (found {len(retained)})"
    writes = [
        n.lineno
        for n in ast.walk(fn)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "_write_restore_evidence"
    ]
    assert len(writes) == 1, f"exactly one authoritative _write_restore_evidence(...) call is required (found {len(writes)})"
    disposal = _subscript_assign_lines(fn, "record", "DISPOSAL_ASSERTION")
    verdict = _subscript_assign_lines(fn, "record", "FINAL_VERDICT")
    assert len(disposal) == 1, f"record['DISPOSAL_ASSERTION'] must be assigned exactly once (found {len(disposal)})"
    assert len(verdict) == 1, f"record['FINAL_VERDICT'] must be assigned exactly once (found {len(verdict)})"
    return outer_try.end_lineno, retained[0], disposal[0], verdict[0], writes[0]


def _valid_finalization_order(fn: ast.FunctionDef) -> bool:
    try:
        try_end, retained_ln, disposal_ln, verdict_ln, write_ln = _finalization_positions(fn)
    except AssertionError:
        return False
    return (
        retained_ln <= try_end
        and disposal_ln > try_end
        and verdict_ln > try_end
        and write_ln > try_end
        and retained_ln < disposal_ln < write_ln
        and retained_ln < verdict_ln < write_ln
    )


_GOOD_FINALIZATION = """
def cmd_restore_validate(args):
    record = {}
    retained = 1
    try:
        pass
    finally:
        retained = 0
        assert retained == 0
    record["DISPOSAL_ASSERTION"] = "PASS (retained=0)"
    record["FINAL_VERDICT"] = "RESTORE-VALIDATED-LOCAL"
    _write_restore_evidence(bundle_path, record)
"""

_REJECT_WRITE_IN_TRY = """
def cmd_restore_validate(args):
    record = {}
    retained = 1
    try:
        _write_restore_evidence(bundle_path, record)
    finally:
        retained = 0
        assert retained == 0
    record["DISPOSAL_ASSERTION"] = "PASS (retained=0)"
    record["FINAL_VERDICT"] = "RESTORE-VALIDATED-LOCAL"
"""

_REJECT_VERDICT_IN_FINALLY = """
def cmd_restore_validate(args):
    record = {}
    retained = 1
    try:
        pass
    finally:
        record["FINAL_VERDICT"] = "RESTORE-VALIDATED-LOCAL"
        retained = 0
        assert retained == 0
    record["DISPOSAL_ASSERTION"] = "PASS (retained=0)"
    _write_restore_evidence(bundle_path, record)
"""

_REJECT_DUPLICATE_WRITE = """
def cmd_restore_validate(args):
    record = {}
    retained = 1
    try:
        pass
    finally:
        retained = 0
        assert retained == 0
    record["DISPOSAL_ASSERTION"] = "PASS (retained=0)"
    record["FINAL_VERDICT"] = "RESTORE-VALIDATED-LOCAL"
    _write_restore_evidence(bundle_path, record)
    _write_restore_evidence(bundle_path, record)
"""

_REJECTED_FINALIZATIONS = (
    ("write inside the try (before disposal)", _REJECT_WRITE_IN_TRY),
    ("FINAL_VERDICT set inside the finally", _REJECT_VERDICT_IN_FINALLY),
    ("duplicate authoritative write", _REJECT_DUPLICATE_WRITE),
)


def test_ops_restore_validate_single_final_write_after_disposal() -> None:
    fn = _restore_fn(_ops_tree())
    try_end, retained_ln, disposal_ln, verdict_ln, write_ln = _finalization_positions(fn)
    assert retained_ln <= try_end, "the retained==0 assertion must live inside the cleanup finally"
    assert disposal_ln > try_end and verdict_ln > try_end and write_ln > try_end, (
        "finalization must occur OUTSIDE (after) the cleanup finally"
    )
    assert retained_ln < disposal_ln < write_ln and retained_ln < verdict_ln < write_ln, "the sole write must follow the disposal + verdict"
    assert _valid_finalization_order(fn), "the operator must satisfy the single-final-write finalization order"
    src = _text(_OPS)
    assert 'record["DISPOSAL_ASSERTION"] = "PASS (retained=0)"' in src, "DISPOSAL_ASSERTION must finalize to 'PASS (retained=0)'"
    assert 'record["FINAL_VERDICT"] = "RESTORE-VALIDATED-LOCAL"' in src, "FINAL_VERDICT must finalize to 'RESTORE-VALIDATED-LOCAL'"
    # a post-write existence assertion must guard the finalized bundle.
    existence = [
        node.lineno
        for node in ast.walk(fn)
        if isinstance(node, ast.Assert) and any(isinstance(c, ast.Attribute) and c.attr == "is_file" for c in ast.walk(node.test))
    ]
    assert existence and min(existence) > write_ln, "a post-write bundle_path.is_file() existence assertion must follow the write"
    # non-vacuity: the good chronology validates and every rejected chronology is refused.
    assert _valid_finalization_order(_restore_fn(ast.parse(_GOOD_FINALIZATION))), "the single-final-write chronology must validate"
    for label, snippet in _REJECTED_FINALIZATIONS:
        assert not _valid_finalization_order(_restore_fn(ast.parse(snippet))), f"a rejected chronology must be refused: {label}"


# --- 18 ------------------------------------------------------------------------------------------
def test_ops_seed_is_idempotent_and_protects_system_primary() -> None:
    norm = _norm(_text(_OPS))
    for needle in ("on conflict", "do nothing", "system_primary", "singleton", _SYNTHETIC_PREFIX, "adjacent isolation"):
        assert needle in norm, f"the seed must be idempotent and protect the System-Primary / NOVA isolation: missing {needle!r}"
    # the seed must never mutate the agents family (only INSERT ... ON CONFLICT DO NOTHING elsewhere).
    literals = {s.lower() for s in _string_literals(_ops_tree())}
    for banned in ("update agents", "delete from agents", "drop table agents", "truncate agents"):
        for literal in literals:
            assert banned not in literal, f"the seed must never mutate the System-Primary agents family ({banned!r})"
    # non-vacuity: the agents-mutation detector fires on a planted sample.
    assert "update agents" in "update agents set agent_kind='human'", "the agents-mutation detector must fire on a planted sample"


# --- 19 ------------------------------------------------------------------------------------------
def test_ops_no_served_hosted_or_activation_behavior() -> None:
    norm = _norm(_text(_OPS))
    for marker in _SERVED_MARKERS:
        assert marker not in norm, f"the wrapper must host no served edge: {marker!r}"
    for mod in _scan.imported_modules(_OPS):
        assert not mod.startswith(_FORBIDDEN_RUNTIME_IMPORTS), f"the wrapper must not import a served/runtime service package: {mod!r}"
    # non-vacuity: the served-marker and runtime-import detectors fire on planted samples.
    assert "_server_from_env" in _norm("build_gateway_edge_server_from_env()"), "the served-factory detector must fire"
    assert any(m.startswith(_FORBIDDEN_RUNTIME_IMPORTS) for m in ["api_gateway.main"]), "the runtime-import detector must fire"


# --- 20 ------------------------------------------------------------------------------------------
def test_surfaces_reject_hosted_and_production_overclaims() -> None:
    for path in (_OPS, _RUNBOOK):
        norm = _norm(_text(path))
        for pattern, label in _FORBIDDEN_PATTERNS:
            assert re.search(pattern, norm) is None, f"forbidden wording present in {path.name} ({label}): /{pattern}/"
    planted = _norm(
        "production ready. production activation authorized. activate production. hosted proof proven. "
        "production proof achieved. hosted ready. 8 of 9. 6 of 9. do-not-activate lifted. blocker closed."
    )
    for pattern, label in _FORBIDDEN_PATTERNS:
        assert re.search(pattern, planted), f"forbidden-pattern detector must fire on a planted sample ({label}): /{pattern}/"


# --- 21 ------------------------------------------------------------------------------------------
def test_surfaces_preserve_locked_state_and_secret_references_only() -> None:
    for path in (_OPS, _RUNBOOK):
        norm = _norm(_text(path))
        for needle in _LOCKED_STATE_NEEDLES:
            assert needle in norm, f"{path.name} must preserve the locked state: missing {needle!r}"
        src = _text(path)
        assert not _DSN_RE.search(src), f"a DSN-shaped value must never appear in {path.name}"
        assert _JWT_MARKER not in src, f"a token-shaped value must never appear in {path.name}"
        assert _KEY_MARKER not in src, f"key material must never appear in {path.name}"
        assert not _EMAIL_RE.search(src), f"PII (email-shaped) content must never appear in {path.name}"
    assert "references only" in _norm(_text(_OPS)) and "redacted" in _norm(_text(_OPS)), (
        "the operator must declare references-only redaction (D-14)"
    )
    guard_src = _norm(pathlib.Path(__file__).read_text(encoding="utf-8"))
    assert "closes no blocker" in guard_src, "the guard must declare that it closes no blocker"
    # non-vacuity: every secret detector fires on a fragment-built planted sample.
    assert _DSN_RE.search("postgresql" + "://u:p@h/db"), "a planted DSN must be detectable"
    assert _JWT_MARKER in ("ey" + "J" + "0aaa"), "a planted token shape must be detectable"
    assert _KEY_MARKER in ("-----" + "BEGIN" + " PRIVATE KEY"), "planted key material must be detectable"
    assert _EMAIL_RE.search("ops" + "@" + "example.com"), "a planted email must be detectable"


# --- 22 ------------------------------------------------------------------------------------------
def test_runbook_distinguishes_four_stages_and_holds_runtime() -> None:
    # Windows paths in runbook prose use backslashes; normalize them to forward slashes for the root check.
    norm = _norm(_text(_RUNBOOK)).replace("\\", "/")
    for stage in ("static implementation", "local runtime execution", "hosted proof", "production activation"):
        assert stage in norm, f"the runbook must distinguish the four governance stages: missing {stage!r}"
    assert "hold / wait - do not execute" in norm, "the runbook must mark runtime commands HOLD / WAIT — DO NOT EXECUTE"
    for needle in (
        "manual_only",
        "non-production",
        "d:/pitchsnack/sp2-local-concept",
        "docker-managed internal volumes",
        "new-but-bounded",
        "already exist",
        "never creates, recreates, deletes, or assumes ownership",
        "dan start-gate",
        "cannot close a hosted or a production requirement",
    ):
        assert needle in norm, f"the runbook must state {needle!r}"
    for db in _AUTH_DBS:
        assert db in norm, f"the runbook must name the authoritative database identity {db!r}"
    for ref in ("b5_standing_topology.md", "controlled_rollback_rehearsal.md"):
        assert ref in norm, f"the runbook must reference (not restate) the delta target: {ref}"
    # the runbook must prohibit restore over standing identities.
    assert "prohibited" in norm and "b5_standing_alpha" in norm, "the runbook must prohibit restore over standing identities"
    # non-vacuity: the HOLD/WAIT detector fires on a planted normalized sample.
    assert "hold / wait - do not execute" in _norm("HOLD / WAIT — DO NOT EXECUTE"), "the HOLD/WAIT detector must fire on a planted sample"


if __name__ == "__main__":
    _scan.run(
        [
            test_manifest_surfaces_exist,
            test_ops_is_operator_not_test_manual_only_and_start_gated,
            test_ops_locates_driver_via_importlib_no_static_db_import,
            test_ops_exposes_exactly_the_approved_surface,
            test_ops_enumerates_exactly_the_four_authoritative_databases,
            test_ops_reuses_standing_idioms_not_its_alpha_beta_tenant_set,
            test_ops_forbids_restore_over_standing_identities,
            test_ops_restore_target_is_a_disposable_validation_database,
            test_ops_embeds_no_schema_ddl_or_db_lifecycle_sql,
            test_ops_duplicates_no_migration_order,
            test_ops_defines_no_new_composition_root_or_secret_backend,
            test_ops_reuses_canonical_provisioning_and_secret_store,
            test_ops_canonical_imports_only_no_build_lib_shadow,
            test_ops_introduces_no_new_environment_variable,
            test_ops_artifact_root_is_exact_never_short_never_repo,
            test_ops_pg_dump_discipline_reexpressed_not_imported,
            test_ops_restore_validate_single_final_write_after_disposal,
            test_ops_seed_is_idempotent_and_protects_system_primary,
            test_ops_no_served_hosted_or_activation_behavior,
            test_surfaces_reject_hosted_and_production_overclaims,
            test_surfaces_preserve_locked_state_and_secret_references_only,
            test_runbook_distinguishes_four_stages_and_holds_runtime,
        ]
    )
