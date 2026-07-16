"""DBR-AR-2D V3 — standing-witness boundaries guard (architecture; no DB, no server, no runtime).

Machine-pins the PRD DBR-AR-2D V3 execution decisions by text/AST inspection of the committed
sources plus BEHAVIORAL probes over the operator's pure predicates (the module is loaded by file
location — import is inert by contract; no database, socket, subprocess, or thread is touched):
the exact operator/harness paths and the exact ``plan/apply/run/status`` command surface; the
exact standing allow-list (the retained local Control DB as the SOLE DDL target — alpha/beta/
dormant are never DDL targets and no other standing name exists); the exact 010→011 apply order
with the reviewed blob pins and each file applied exactly once from its exact repository path
(no wildcard, no directory scan, no copied DDL bytes); backup-before-apply with the backup argv
carrying NO DSN/credential (child-environment passing only) and the backup directory validated
OUTSIDE the repository; no destructive SQL surface of any kind (no wildcard/destructive rollback);
the exact S1–S5 scenario matrix with EXACTLY the predeclared four-row evidence set and the
Auth-edge zero-row rule (no fifth V3 row); the full before/after snapshot families and the exact
allowed delta; the one-request→one-tenant→one-database witnesses; the dormant
no-secret/no-database/no-schema probes; loopback-only ephemeral services with ``finally`` cleanup
and environment restoration; the durable cross-process rerun refusal; the no-overclaim status
posture; the hosted live-PG loop UNCHANGED at exactly 14 with the new standing harness a justified
MANUAL_ONLY exception; the subprocess census (status-only standing delegation + the read-only
commit witness + pg_dump/pg_restore only); the evolved locked-state record (DBR-AR-2D delivered
only after evidence acceptance; DBR-AR-2 remains OPEN; DBR-AR-2E production-activation evidence
consolidated with Outcome A — REMAIN NOT READY / DO-NOT-ACTIVATE; production NOT
READY; ATR-2B-1 separate); and the exact authorized backend 2D/2E file census. Every detector
carries a planted non-vacuity companion. Pure stdlib; standalone-runnable:
  python tests/architecture/test_dbr_ar_2d_standing_witness_boundaries.py
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import pathlib
import re
import sys
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

_REPO = _scan.REPO_ROOT
_BACKEND = _scan.BACKEND_ROOT

_OPS = _BACKEND / "tests" / "control_plane" / "requires_pg" / "dbr_ar_2d_standing_witnesses.py"
_WRAPPER = _BACKEND / "tests" / "control_plane" / "requires_pg" / "test_pg_dbr_ar_2d_standing_witnesses.py"
_WRAPPER_RELPATH = "tests/control_plane/requires_pg/test_pg_dbr_ar_2d_standing_witnesses.py"
_V2_HARNESS = _BACKEND / "tests" / "control_plane" / "requires_pg" / "test_dbr_ar_2d_routing_audit_live_pg.py"
_V2_GUARD = pathlib.Path(__file__).resolve().parent / "test_dbr_ar_2d_live_proof_boundaries.py"
_COMPLETENESS_GUARD = pathlib.Path(__file__).resolve().parent / "test_live_pg_workflow_runset_completeness.py"
_WORKFLOW = _REPO / ".github" / "workflows" / "live-pg-durable-path.yml"
_CONTRACT_DOC = _REPO / "docs" / "runtime" / "dbr_ar_2_durable_routing_audit_contract.md"
_RUNBOOK = _REPO / "infrastructure" / "runbooks" / "dbr_ar_2_durable_routing_audit.md"
_CONTROL_README = _REPO / "infrastructure" / "db" / "control" / "README.md"
_EVIDENCE_TEMPLATE = _REPO / "docs" / "runtime" / "dbr_ar_2d_standing_evidence_template.md"
_CP_INGEST = _BACKEND / "control_plane" / "adapters" / "providers" / "http_routing_audit_api.py"
_DDL_010 = _REPO / "infrastructure" / "db" / "control" / "010_routing_audit.sql"
_DDL_011 = _REPO / "infrastructure" / "db" / "control" / "011_routing_audit_append_only.sql"

# The exact authorized backend 2D/2E census after PRD DBR-AR-2D V3 (V2's two files + V3's three)
# and PRD DBR-AR-2E V1 (exactly one activation-evidence guard).
_AUTHORIZED_2D_BACKEND = (
    "backend/tests/architecture/test_dbr_ar_2d_live_proof_boundaries.py",
    "backend/tests/architecture/test_dbr_ar_2d_standing_witness_boundaries.py",
    "backend/tests/architecture/test_dbr_ar_2e_activation_evidence_boundaries.py",
    "backend/tests/control_plane/requires_pg/dbr_ar_2d_standing_witnesses.py",
    "backend/tests/control_plane/requires_pg/test_dbr_ar_2d_routing_audit_live_pg.py",
    "backend/tests/control_plane/requires_pg/test_pg_dbr_ar_2d_standing_witnesses.py",
)

_EXPECTED_HARNESS_COUNT = 14  # the hosted loop is UNCHANGED by this slice (manual-only standing harness)

_LOOP_RE = re.compile(r"for\s+h\s+in\s+(?P<loop>.+?);\s*do", re.DOTALL)
_ENTRY_RE = re.compile(r"\S+\.py")

# The V3 evidence contract: four predeclared rows; the Auth-edge S3 correlation adds ZERO rows.
_EXPECTED_ACTIONS = ["Route", "Route", "RouteDenied", "IsolationAnomaly"]
_EXPECTED_CORRELATIONS = ["dbr2dv3-s1-alpha", "dbr2dv3-s2-beta", "dbr2dv3-s4-dormant-router", "dbr2dv3-s5-anomaly"]
_S3_CORRELATION = "dbr2dv3-s3-dormant-auth"

# The exact snapshot families of the before/after witness (full families, never bare counts).
_SNAPSHOT_KEYS = {
    "control_identity",
    "tenant_ids",
    "tenants",
    "memberships",
    "audit_rows",
    "federation",
    "routing_schema_present",
    "routing_schema_census",
    "routing_rows",
    "pg_tenant_databases",
    "dormant_database_present",
    "proof_database_present",
    "tenant_db_state",
    "secret_root_files",
    "env",
}

# Destructive vocabulary that must NEVER appear in the operator/wrapper (no destructive rollback).
_DESTRUCTIVE_TOKENS = (
    "DROP TABLE",
    "DROP DATABASE",
    "DROP TRIGGER",
    "TRUNCATE control_routing_audit",
    "DELETE FROM",
    "UPDATE control_routing_audit",
    "ALTER TABLE",
    "pg_terminate_backend",
    "DISABLE TRIGGER",
)


def _text(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def _norm(s: str) -> str:
    return " ".join(s.lower().replace("**", "").replace("`", "").split())


def _git_blob_sha1(path: pathlib.Path) -> str:
    data = path.read_bytes().replace(b"\r\n", b"\n")  # autocrlf normalization (the git blob is LF)
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def _load_ops() -> Any:
    """Load the operator by FILE LOCATION (never a package import; module import is inert)."""
    name = "dbr_ar_2d_standing_witnesses_guard_view"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, _OPS)
    assert spec is not None and spec.loader is not None, "the standing operator module must be loadable"
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


def _func_segment(source: str, name: str) -> str:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            seg = ast.get_source_segment(source, node)
            assert seg is not None
            return seg
    raise AssertionError(f"function {name!r} must exist in the standing operator")


def _module_literal(source: str, name: str) -> Any:
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return ast.literal_eval(node.value)
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == name and node.value is not None:
            return ast.literal_eval(node.value)
    raise AssertionError(f"module literal {name!r} must exist in the standing operator")


def _loop_entries(workflow_text: str) -> Optional[List[str]]:
    m = _LOOP_RE.search(workflow_text)
    return _ENTRY_RE.findall(m.group("loop")) if m else None


def _example_census() -> Dict[str, Any]:
    """A minimal healthy schema census accepted by the operator's schema evaluator."""
    ops = _load_ops()
    columns = []
    for name in ops._EXPECTED_COLS:
        data_type = {
            "id": "bigint",
            "event_id": "uuid",
            "event_version": "integer",
            "occurred_at": "timestamp with time zone",
            "recorded_at": "timestamp with time zone",
        }.get(name, "text")
        is_nullable = "NO" if name in ops._NOT_NULL_COLS else "YES"
        is_identity = "YES" if name == "id" else "NO"
        identity_generation = "ALWAYS" if name == "id" else None
        default = "now()" if name == "recorded_at" else None
        columns.append((name, data_type, is_nullable, is_identity, identity_generation, default))
    return {
        "columns": columns,
        "column_names": list(ops._EXPECTED_COLS),
        "pk": ["id"],
        "unique": ["event_id"],
        "checks": list(ops._EXPECTED_CHECKS),
        "triggers": list(ops._EXPECTED_TRIGGERS),
        "function_present": True,
    }


def _example_rows() -> List[tuple]:
    """A synthetic evidence-row set that MUST satisfy the operator's row evaluator exactly."""
    import datetime

    ops = _load_ops()
    rows = []
    tz = datetime.timezone.utc
    for index, expected in enumerate(ops.EXPECTED_EVIDENCE_ROWS, start=1):
        rows.append(
            (
                index,  # id (identity order)
                f"00000000-0000-4000-8000-00000000000{index}",  # event_id (unique)
                expected["event_version"],
                datetime.datetime(2026, 7, 14, tzinfo=tz),  # occurred_at
                datetime.datetime(2026, 7, 14, tzinfo=tz),  # recorded_at (tz-aware)
                expected["correlation_id"],
                expected["actor_ref"],
                expected["action"],
                expected["outcome"],
                expected["source_service"],
                expected["source_version"],
                None,  # request_ref (gateway-owned for S1/S2)
                None,  # trace_ref (reserved; must stay NULL)
                expected["tenant_ref"],
                expected["resolved_tenant_ref"],
                expected["public_code"],
                expected["error_class"],
                expected["association_store_ref"],
                expected["association_version"],
                expected["lane"],
            )
        )
    return rows


# ---------------------------------------------------------------------------
# 1. Exact file census + command surface
# ---------------------------------------------------------------------------
def test_v3_exact_backend_2d_census() -> None:
    hits = sorted(
        str(p.relative_to(_REPO).as_posix())
        for pattern in ("*dbr_ar_2d*", "*dbr_ar_2e*")
        for p in _BACKEND.rglob(pattern)
        if not (_scan.SKIP_PARTS & set(p.parts))
    )
    assert hits == sorted(_AUTHORIZED_2D_BACKEND), (
        f"exactly the six authorized backend 2D/2E files may exist (no seventh file; no second 2E file): {hits}"
    )
    for rel in _AUTHORIZED_2D_BACKEND:
        assert (_REPO / rel).is_file(), f"authorized 2D file missing: {rel}"


def test_v3_census_nonvacuity() -> None:
    planted = sorted(list(_AUTHORIZED_2D_BACKEND) + ["backend/tests/database_router/test_dbr_ar_2d_extra.py"])
    assert planted != sorted(_AUTHORIZED_2D_BACKEND), "a sixth dbr_ar_2d backend file must be detectable"
    assert "backend/tests/x/test_dbr_ar_2e_probe.py" not in _AUTHORIZED_2D_BACKEND, (
        "only the single PRD-DBR-AR-2E-V1 guard is authorized — any other 2E file stays unauthorized"
    )


def test_v3_command_surface_exactly_plan_apply_run_status() -> None:
    source = _text(_OPS)
    added = re.findall(r'add_parser\(\s*"([a-z_]+)"', source)
    assert added == ["plan", "apply", "run", "status"], f"the operator command surface must be exactly plan/apply/run/status: {added}"
    for token in ("tear" + "down", "--confirm"):
        assert token not in source, f"no removal surface may exist in the standing operator ({token!r})"
    handlers = re.search(r"handlers: dict = \{(.+?)\}", source, re.DOTALL)
    assert handlers is not None and handlers.group(1).count("cmd_") == 4, "exactly four command handlers"


def test_v3_command_surface_nonvacuity() -> None:
    assert re.findall(r'add_parser\(\s*"([a-z_]+)"', 'sub.add_parser("teardown", help="x")') == ["teardown"], (
        "a planted extra subcommand must be detectable"
    )
    assert "teardown" in 'sub.add_parser("teardown")', "the removal-surface token must be detectable"


# ---------------------------------------------------------------------------
# 2. Standing allow-list; Control DB the SOLE DDL target; blob pins; 010→011 order
# ---------------------------------------------------------------------------
def test_v3_standing_allow_list_and_sole_ddl_target() -> None:
    ops = _load_ops()
    assert ops.CONTROL_DB_NAME == "snackportal2_control_local", "the sole DDL target is the retained standing Control DB"
    assert (ops.ALPHA_DB, ops.BETA_DB) == ("sp2_tenant_b5_standing_alpha", "sp2_tenant_b5_standing_beta")
    assert (ops.TENANT_ALPHA, ops.TENANT_BETA, ops.TENANT_DORMANT) == ("b5_standing_alpha", "b5_standing_beta", "b5_standing_dormant")
    apply_seg = _func_segment(_text(_OPS), "cmd_apply")
    assert "_swap_db(" not in apply_seg, "apply must never swap the connection to another database (Control DB only)"
    assert "ALPHA_DB" not in apply_seg and "BETA_DB" not in apply_seg, "alpha/beta are FORBIDDEN DDL targets"
    assert "identity != CONTROL_DB_NAME" in apply_seg, "apply must verify current_database() IS the standing Control DB before DDL"
    assert apply_seg.index("identity != CONTROL_DB_NAME") < apply_seg.index("_DDL_010.read_text"), "identity check must precede DDL"
    source = _text(_OPS)
    for forbidden in ("sp2_tenant_acme", "sp2_tenant_zeta", "sp2_tenant_nova", "0.0.0.0"):
        assert forbidden not in source, f"a non-standing target name must never appear in the operator ({forbidden!r})"


def test_v3_blob_pins_and_apply_order() -> None:
    source = _text(_OPS)
    # Single pin authority (B7C1R2): the operator must declare NO second hand-copied hex pin —
    # it derives the reviewed pins from the merged V2 harness source by AST and fails closed.
    assert not re.search(r'_REVIEWED_[A-Z0-9]+_BLOB\s*=\s*"[0-9a-f]{40}"', source), (
        "the operator must never declare a second literal reviewed-pin (the V2 harness is the single pin authority)"
    )
    assert "def _reviewed_blob_pins" in source and "test_dbr_ar_2d_routing_audit_live_pg.py" in source, (
        "the operator must derive the reviewed pins from the merged V2 harness source"
    )
    ops = _load_ops()
    pins = ops._reviewed_blob_pins()
    assert pins == ("0c5eeecd5e20ef9fe4f11293b6c6561ae7cc897e", "cea40fc62c063e9f711fdb7ac90b00a8859586d4"), (
        f"the derived reviewed pins drifted from the PRD DBR-AR-2D V3 blob IDs: {pins}"
    )
    assert pins == (_git_blob_sha1(_DDL_010), _git_blob_sha1(_DDL_011)), "the reviewed pins diverge from the committed DDL blobs"
    ops._verify_reviewed_blobs()  # behavioral: the STOP rule holds clean on the committed tree
    assert '_DDL_010 = _CONTROL_DDL_DIR / "010_routing_audit.sql"' in source, "010 must be addressed by its exact repo path"
    assert '_DDL_011 = _CONTROL_DDL_DIR / "011_routing_audit_append_only.sql"' in source, "011 must be addressed by its exact repo path"
    assert source.count("_DDL_010.read_text") == 1 and source.count("_DDL_011.read_text") == 1, "each DDL file is applied exactly once"
    apply_seg = _func_segment(source, "cmd_apply")
    assert apply_seg.index("_create_backup(") < apply_seg.index("_verify_reviewed_blobs()"), "backup precedes the blob STOP (PRD §6.2)"
    assert apply_seg.index("_verify_reviewed_blobs()") < apply_seg.index("_DDL_010.read_text"), "the blob STOP precedes any DDL"
    assert apply_seg.index("_DDL_010.read_text") < apply_seg.index("_DDL_011.read_text"), "010 must be applied before 011"
    for banned in ("_CONTROL_DDL_DIR.glob", "_CONTROL_DDL_DIR.rglob", "iterdir", "listdir", "*.sql"):
        assert banned not in source, f"the operator must never wildcard/scan for DDL ({banned!r})"
    for copied in ("CREATE TABLE", "CREATE OR REPLACE FUNCTION", "CREATE TRIGGER"):
        assert copied not in source, f"the operator must apply the repo files, never copied DDL bytes ({copied!r})"


def test_v3_blob_and_order_nonvacuity() -> None:
    swapped = "cur.execute(_DDL_011.read_text())\ncur.execute(_DDL_010.read_text())"
    assert swapped.index("_DDL_010.read_text") > swapped.index("_DDL_011.read_text"), "a swapped apply order must be detectable"
    assert re.search(r'_REVIEWED_[A-Z0-9]+_BLOB\s*=\s*"[0-9a-f]{40}"', '_REVIEWED_010_BLOB = "' + "0" * 40 + '"'), (
        "a planted second literal pin must be detectable"
    )
    assert "_CONTROL_DDL_DIR.glob" in 'for f in _CONTROL_DDL_DIR.glob("*.sql"): apply(f)', "a wildcard apply must be detectable"
    late = "cur.execute(_DDL_010.read_text())\n_verify_reviewed_blobs()"
    assert late.index("_verify_reviewed_blobs()") > late.index("_DDL_010.read_text"), "a late blob check must be detectable"
    assert "_swap_db(" in "_connect(_swap_db(admin_dsn, ALPHA_DB))", "a DDL-target swap must be detectable"


# ---------------------------------------------------------------------------
# 3. Backup-before-apply; no DSN in child argv; backup dir outside the repository
# ---------------------------------------------------------------------------
def test_v3_backup_discipline() -> None:
    ops = _load_ops()
    argv = ops._pg_dump_argv(pathlib.Path("X") / "out.dump")
    assert argv[0] == "pg_dump" and "--format=custom" in argv and "--no-password" in argv, f"backup argv drifted: {argv}"
    assert not any("postgresql://" in part for part in argv), "the backup argv must NEVER carry a DSN (environment passing only)"
    listing = ops._pg_restore_list_argv(pathlib.Path("X") / "out.dump")
    assert listing[:2] == ["pg_restore", "--list"], f"the readability witness must be pg_restore --list: {listing}"
    source = _text(_OPS)
    assert "PGPASSWORD" in _func_segment(source, "_backup_child_env"), "credentials pass to the child by ENVIRONMENT only"
    try:
        ops._validated_backup_dir(str(_REPO / "inside"))
        raise AssertionError("a repository-contained backup dir must be refused")
    except ops.OpsConfigError:
        pass
    try:
        ops._validated_backup_dir("relative/dir")
        raise AssertionError("a relative backup dir must be refused")
    except ops.OpsConfigError:
        pass


def test_v3_backup_nonvacuity() -> None:
    assert any("postgresql://" in part for part in ["pg_dump", "--dbname=postgresql://u:p@h/db"]), "an argv DSN must be detectable"
    assert "--format=custom" not in ["pg_dump", "--file", "x"], "a dropped custom-format flag must be detectable"


# ---------------------------------------------------------------------------
# 4. No destructive surface anywhere in the new files
# ---------------------------------------------------------------------------
def test_v3_no_destructive_surface() -> None:
    for path in (_OPS, _WRAPPER):
        text = _text(path)
        for token in _DESTRUCTIVE_TOKENS:
            assert token not in text, f"destructive vocabulary {token!r} must never appear in {path.name}"


def test_v3_no_destructive_nonvacuity() -> None:
    assert "TRUNCATE control_routing_audit" in "cur.execute('TRUNCATE control_routing_audit')", "destructive SQL must be detectable"
    assert "DROP DATABASE" in 'admin.execute("DROP DATABASE x")', "a database drop must be detectable"
    assert "DISABLE TRIGGER" in 'cur.execute("ALTER TABLE x DISABLE TRIGGER ALL")', "a trigger bypass must be detectable"


# ---------------------------------------------------------------------------
# 5. Subprocess census: status-only delegation + commit witness + backup tooling
# ---------------------------------------------------------------------------
def test_v3_subprocess_census() -> None:
    source = _text(_OPS)
    assert source.count("subprocess.run(") == 3, "exactly three subprocess.run sites (delegation runner + pg_dump + pg_restore)"
    assert '_STATUS_COMMAND = "status"' in source, "the ONLY standing-operator subcommand token is status"
    for builder in ("_b5_4_status_argv", "_b5_4a_status_argv", "_smoke_c_status_argv"):
        seg = _func_segment(source, builder)
        assert "_STATUS_COMMAND" in seg, f"{builder} must delegate status-only"
        assert '"apply"' not in seg and '"teardown"' not in seg and '"run"' not in seg, f"{builder} must never build an effectful argv"
    assert '"rev-parse"' in _func_segment(source, "_git_head_argv"), "the commit witness must be git rev-parse"
    for module in ("b5_standing_topology", "b5_standing_auth_fixture", "smoke_c_integrated_live_proof"):
        assert f"import {module}" not in source, f"the standing operators are subprocess-only (never imported): {module}"
    wrapper_mods = {m.split(".")[0] for m in _scan.imported_modules(_WRAPPER)}
    assert "subprocess" not in wrapper_mods, "the wrapper must not import subprocess (only the operator holds that seam)"


def test_v3_subprocess_nonvacuity() -> None:
    assert '"teardown"' in '[sys.executable, str(_B5_4_OPS), "teardown"]', "an effectful delegation argv must be detectable"
    synthetic = [a.name for n in ast.walk(ast.parse("import subprocess\n")) if isinstance(n, ast.Import) for a in n.names]
    assert "subprocess" in synthetic, "the wrapper subprocess census went vacuous"


# ---------------------------------------------------------------------------
# 6. The S1–S5 matrix; the exact four-row evidence set; the Auth-edge zero-row rule
# ---------------------------------------------------------------------------
def test_v3_expected_evidence_matrix_exact() -> None:
    rows = _module_literal(_text(_OPS), "EXPECTED_EVIDENCE_ROWS")
    assert len(rows) == 4, "the predeclared evidence matrix is exactly four rows (no fifth V3 row)"
    assert [r["action"] for r in rows] == _EXPECTED_ACTIONS, "the action sequence is Route/Route/RouteDenied/IsolationAnomaly"
    assert [r["correlation_id"] for r in rows] == _EXPECTED_CORRELATIONS, "the deterministic evidence correlations drifted"
    for index, tenant in ((0, "b5_standing_alpha"), (1, "b5_standing_beta")):
        success = rows[index]
        assert success["tenant_ref"] == tenant and success["resolved_tenant_ref"] == tenant, (
            f"S{index + 1} must record its OWN standing tenant (alpha routes only to alpha; beta only to beta)"
        )
        assert success["association_store_ref"] == f"tenant/{tenant}/dsn" and success["association_version"] == "1", (
            f"S{index + 1} must carry the canonical D-14 association REFERENCE"
        )
        assert success["actor_ref"] == "b5_standing_member" and success["lane"] == "interactive", (
            f"S{index + 1} must record the authenticated standing principal on the interactive lane"
        )
    denied = rows[2]
    assert denied["public_code"] == "not_ready" and denied["outcome"] == "denied:not_ready", "S4 is the dormant not_ready denial"
    assert denied["tenant_ref"] == "b5_standing_dormant", "S4 records the dormant tenant reference"
    anomaly = rows[3]
    assert (anomaly["tenant_ref"], anomaly["resolved_tenant_ref"]) == ("b5_standing_alpha", "b5_standing_beta"), (
        "S5 records both the authenticated and the actually-bound tenant references"
    )
    source = _text(_OPS)
    assert f'S3_CORRELATION = "{_S3_CORRELATION}"' in source, "the S3 auth-edge correlation must be pinned"
    assert "must add ZERO routing-audit rows" in source, "the Auth-edge zero-row rule must be asserted"


def test_v3_evidence_evaluator_behavioral() -> None:
    ops = _load_ops()
    healthy = _example_rows()
    assert ops.evaluate_evidence_rows(healthy) is None, "the canonical four-row set must PASS the evaluator"
    assert ops.evaluate_evidence_rows(healthy[:3]) is not None, "a missing row must FAIL"
    fifth = healthy + [
        tuple([5, "00000000-0000-4000-8000-000000000005"] + list(healthy[0][2:5]) + ["dbr2dv3-extra"] + list(healthy[0][6:]))
    ]
    assert ops.evaluate_evidence_rows(fifth) is not None, "a FIFTH V3 row must FAIL"
    swapped = [healthy[1], healthy[0], healthy[2], healthy[3]]
    assert ops.evaluate_evidence_rows(swapped) is not None, "an out-of-order id sequence must FAIL"
    s3_leak = [list(r) for r in healthy]
    s3_leak[3][5] = _S3_CORRELATION
    assert ops.evaluate_evidence_rows([tuple(r) for r in s3_leak]) is not None, "an S3-correlated durable row must FAIL"
    mutated = [list(r) for r in healthy]
    mutated[2][15] = "not_found"
    assert ops.evaluate_evidence_rows([tuple(r) for r in mutated]) is not None, "a wrong S4 public_code must FAIL"
    traced = [list(r) for r in healthy]
    traced[0][12] = "trace-x"
    assert ops.evaluate_evidence_rows([tuple(r) for r in traced]) is not None, "a non-NULL trace_ref must FAIL"
    foreign = [list(r) for r in healthy]
    foreign[0][5] = "smokec-01-alpha"
    assert ops.evaluate_evidence_rows([tuple(r) for r in foreign]) is not None, "a foreign correlation must FAIL"
    hidden = healthy + [
        tuple([5, "00000000-0000-4000-8000-000000000005"] + list(healthy[0][2:5]) + ["smokec-01-foreign"] + list(healthy[0][6:]))
    ]
    assert ops.evaluate_evidence_rows(hidden) is not None, (
        "the exact four rows PLUS a hidden foreign fifth row must FAIL — no pre-filter may hide extra rows"
    )
    dup = [list(r) for r in healthy]
    dup[1][1] = dup[0][1]
    assert ops.evaluate_evidence_rows([tuple(r) for r in dup]) is not None, "duplicate event_ids must FAIL"


def test_v3_leak_scan_behavioral() -> None:
    ops = _load_ops()
    healthy = _example_rows()
    assert ops._leak_scan_rows(healthy, ["postgresql://u:pw@h:1/db", "pw"]) is None, "the healthy set must pass the leak scan"
    leaked = [list(r) for r in healthy]
    leaked[0][6] = "postgresql://u:pw@h:1/db"
    assert ops._leak_scan_rows([tuple(r) for r in leaked], []) is not None, "a stored DSN must FAIL the leak scan"
    tokened = [list(r) for r in healthy]
    tokened[1][6] = "eyJhbGciOi"
    assert ops._leak_scan_rows([tuple(r) for r in tokened], []) is not None, "a stored token-shaped value must FAIL the leak scan"


# ---------------------------------------------------------------------------
# 7. Schema evaluator: exact 20 columns, exact CHECK set, exact trigger set (OBS-2D-1 posture)
# ---------------------------------------------------------------------------
def test_v3_schema_evaluator_behavioral() -> None:
    ops = _load_ops()
    healthy = _example_census()
    assert ops._routing_schema_problem(healthy) is None, "the canonical census must PASS"
    assert ops._routing_schema_problem(None) is not None, "an absent table must FAIL"
    fewer = dict(healthy)
    fewer["column_names"] = healthy["column_names"][:-1]
    assert ops._routing_schema_problem(fewer) is not None, "a dropped 20th column must FAIL"
    extra_check = dict(healthy)
    extra_check["checks"] = list(healthy["checks"]) + ["control_routing_audit_rogue_check"]
    assert ops._routing_schema_problem(extra_check) is not None, "an EXTRA check constraint must FAIL (exact set)"
    missing_check = dict(healthy)
    missing_check["checks"] = [c for c in healthy["checks"] if c != "control_routing_audit_source_service_check"]
    assert ops._routing_schema_problem(missing_check) is not None, "a missing frozen CHECK must FAIL"
    one_trigger = dict(healthy)
    one_trigger["triggers"] = ["control_routing_audit_no_mutation"]
    assert ops._routing_schema_problem(one_trigger) is not None, "a missing append-only trigger must FAIL (exact set)"
    no_fn = dict(healthy)
    no_fn["function_present"] = False
    assert ops._routing_schema_problem(no_fn) is not None, "a missing append-only function must FAIL"
    assert list(_load_ops()._EXPECTED_CHECKS) == [
        "control_routing_audit_action_check",
        "control_routing_audit_event_version_check",
        "control_routing_audit_source_service_check",
    ], "the exact CHECK set drifted"
    assert list(_load_ops()._EXPECTED_TRIGGERS) == ["control_routing_audit_no_mutation", "control_routing_audit_no_truncate"], (
        "the exact trigger set drifted"
    )


# ---------------------------------------------------------------------------
# 8. Stage machine + allowed delta: rerun refusal is durable and cross-process
# ---------------------------------------------------------------------------
def test_v3_stage_machine_behavioral() -> None:
    ops = _load_ops()
    census, rows = _example_census(), _example_rows()
    assert ops.classify_stage(None, []) == ops.STAGE_PRE_APPLY
    assert ops.classify_stage(census, []) == ops.STAGE_APPLIED_NO_EVIDENCE
    assert ops.classify_stage(census, rows) == ops.STAGE_COMPLETE
    assert ops.classify_stage(None, rows) == ops.STAGE_ANOMALOUS, "rows without schema are anomalous"
    assert ops.classify_stage(census, rows[:2]) == ops.STAGE_ANOMALOUS, "a partial evidence set is anomalous"
    broken = dict(census)
    broken["triggers"] = []
    assert ops.classify_stage(broken, []) == ops.STAGE_PARTIAL_SCHEMA
    assert ops.classify_stage(broken, rows) == ops.STAGE_ANOMALOUS


def test_v3_rerun_refusal_pinned() -> None:
    source = _text(_OPS)
    run_seg = _func_segment(source, "cmd_run")
    assert "stage != STAGE_APPLIED_NO_EVIDENCE" in run_seg, "run must refuse every stage except APPLIED_NO_EVIDENCE"
    assert "a second evidence-generating run is REFUSED" in run_seg, "the rerun refusal must be explicit"
    assert run_seg.index("RUN REFUSED") < run_seg.index("_snapshot_state()"), "the refusal precedes the snapshot/composition"
    apply_seg = _func_segment(source, "cmd_apply")
    assert "the V3 evidence is exactly-once" in apply_seg, "apply must refuse when any evidence row exists"
    assert "apply is exactly-once" in apply_seg, "apply must refuse when the complete schema already exists"
    wrapper = _text(_WRAPPER)
    assert '_run(["run"])' in wrapper and "a second evidence-generating run must be REFUSED" in wrapper, (
        "the wrapper must prove the live run refusal"
    )
    assert '_run(["apply", "--backup-dir", tmp])' in wrapper, "the wrapper must prove the live apply refusal"


def test_v3_allowed_delta_behavioral() -> None:
    ops = _load_ops()
    rows = _example_rows()
    before = {"tenant_ids": ["a"], "routing_rows": [], "memberships": [("p", "t", "r")]}
    after_good = {"tenant_ids": ["a"], "routing_rows": rows, "memberships": [("p", "t", "r")]}
    assert ops.snapshot_delta_problem(before, after_good) is None, "the exact allowed delta must PASS"
    drifted = {"tenant_ids": ["a", "b"], "routing_rows": rows, "memberships": [("p", "t", "r")]}
    assert ops.snapshot_delta_problem(before, drifted) is not None, "a tenant-registry drift must FAIL"
    membership_drift = {"tenant_ids": ["a"], "routing_rows": rows, "memberships": []}
    assert ops.snapshot_delta_problem(before, membership_drift) is not None, "a membership drift must FAIL"
    pre_polluted = dict(before)
    pre_polluted["routing_rows"] = rows
    assert ops.snapshot_delta_problem(pre_polluted, after_good) is not None, "a non-empty pre-run evidence table must FAIL"
    after_bad_rows = {"tenant_ids": ["a"], "routing_rows": rows[:2], "memberships": [("p", "t", "r")]}
    assert ops.snapshot_delta_problem(before, after_bad_rows) is not None, "a wrong post-run row set must FAIL"


def test_v3_snapshot_families_complete() -> None:
    source = _func_segment(_text(_OPS), "_snapshot_state")
    keys = set(re.findall(r'^\s+"([a-z_]+)":', source, re.MULTILINE))
    assert keys == _SNAPSHOT_KEYS, f"the before/after snapshot families drifted: {sorted(keys ^ _SNAPSHOT_KEYS)}"
    assert "md5(string_agg" in _text(_OPS), "tenant-DB tables must carry FULL-content digests, not bare counts"


def test_v3_snapshot_families_nonvacuity() -> None:
    hollow = '    return {\n        "tenant_ids": tenant_ids,\n    }'
    assert set(re.findall(r'^\s+"([a-z_]+)":', hollow, re.MULTILINE)) != _SNAPSHOT_KEYS, "a hollowed snapshot must be detectable"


# ---------------------------------------------------------------------------
# 9. One request → one tenant → one DB; dormant absences; loopback/finally discipline
# ---------------------------------------------------------------------------
def test_v3_isolation_witnesses_pinned() -> None:
    run_seg = _func_segment(_text(_OPS), "cmd_run")
    assert "routed_database_identity(" in run_seg, "the pooled-connection identity readback must exist"
    assert "one request/one tenant/one DB" in run_seg, "the one-request→one-tenant→one-DB witness must be asserted"
    assert "other_pool_delta" in run_seg, "the other-tenant non-touch witness must exist"
    assert "durable row(s) for" in run_seg, "the exactly-one-durable-Route-row witness must exist (S1/S2)"
    assert "expected exactly one durable RouteDenied(not_ready) row" in run_seg, "the S4 exactly-one-row witness must exist"
    assert "expected exactly one durable IsolationAnomaly row" in run_seg, "the S5 exactly-one-row witness must exist"
    assert "added routing-audit row(s) — must be ZERO" in run_seg, "the RUN-scoped S3 zero-delta witness must exist"
    assert "the OTHER tenant's pool changed during a success row" in run_seg, "the enforcing other-pool witness must exist"
    assert "a tenant-binding fault must be denied" in run_seg, "S5 must refuse a route success outright"
    assert "the misbound connection must be discarded and closed" in run_seg, "the S5 discard witness must exist"
    assert '"routing_isolation_fault"' in run_seg, "the S5 denial code must be asserted"
    assert "_dormant_absence_problem(" in run_seg, "the dormant no-secret/no-DB/no-schema probe must run inside the witness"
    ops_source = _text(_OPS)
    dormant_seg = _func_segment(ops_source, "_dormant_absence_problem")
    for needle in ("secret file exists", "resolves the dormant reference", "dormant database EXISTS"):
        assert needle in dormant_seg, f"the dormant probe must check {needle!r}"


def test_v3_loopback_and_finally_discipline() -> None:
    source = _text(_OPS)
    assert 'LOOPBACK_HOST = "127.0.0.1"' in source, "the loopback host is pinned"
    unset = _module_literal(source, "_ENV_UNSET_KEYS")
    for key in ("SP2_CP_READ_PORT", "SP2_CP_ROUTING_AUDIT_PORT", "SP2_AR_AUTHENTICATE_PORT", "SP2_DBR_DISPATCH_PORT"):
        assert key in unset, f"{key} must be explicitly UNSET for the run (ephemeral ports only)"
    run_seg = _func_segment(source, "cmd_run")
    assert re.search(r'patch\.set\("SP2_CP_READ_HOST", LOOPBACK_HOST\)', run_seg), "the read edge binds the loopback host"
    assert re.search(r'patch\.set\("SP2_CP_ROUTING_AUDIT_HOST", LOOPBACK_HOST\)', run_seg), "the ingest edge binds the loopback host"
    assert "    finally:\n        problems = _stop_all()" in run_seg and "patch.restore()" in run_seg, (
        "run must stop every server and restore the environment in ITS OWN finally block (not an else/except)"
    )
    ops = _load_ops()
    patch = ops._EnvPatch()
    try:
        patch.set("SP2_ROGUE_KEY", "x")
        raise AssertionError("an out-of-census env write must be refused")
    except ops.OpsConfigError:
        pass
    assert ops._port_refused("http://127.0.0.1:1"), "the port-release probe must report a refused port"


def test_v3_durable_composition_pinned() -> None:
    run_seg = _func_segment(_text(_OPS), "cmd_run")
    assert "build_routing_audit_server_from_env" in run_seg, "the REAL CP ingest seam must be composed"
    assert "build_dispatch_server_from_env" in run_seg, "the REAL DBR dispatch seam must be composed"
    assert "build_authenticate_server_from_env" in run_seg, "the REAL Auth Router seam must be composed"
    assert "build_read_server_from_env" in run_seg, "the REAL CP read seam must be composed"
    assert "build_gateway(" in run_seg, "the REAL gateway must be composed in-process"
    assert 'patch.set("SP2_DBR_ROUTING_AUDIT_BASE_URL", ingest_url)' in run_seg, "the durable audit opt-in must target the ingest edge"
    assert '"BoundedRoutingAuditPolicy"' in run_seg, "the composed router must hold the DURABLE routing-audit policy (proof 8)"
    assert "InMemoryAuditSink" not in _text(_OPS), "the standing witness must never touch the in-memory routing sink"


# ---------------------------------------------------------------------------
# 10. No status overclaim; hosted loop unchanged at 14; the manual-only exception
# ---------------------------------------------------------------------------
def test_v3_no_status_overclaim() -> None:
    source = _text(_OPS)
    status_seg = _func_segment(source, "cmd_status")
    assert "NEVER constitute the witness" in status_seg, "status must state the fail-closed no-overclaim rule"
    assert "evaluate_evidence_rows" in _func_segment(source, "cmd_status"), "status must verify the DURABLE evidence directly"
    assert "DBR-AR-2 remains OPEN" in status_seg, "status must keep DBR-AR-2 OPEN in its verdict line"


def test_v3_hosted_loop_unchanged_and_manual_only() -> None:
    wf = _text(_WORKFLOW)
    entries = _loop_entries(wf)
    assert entries is not None and len(entries) == _EXPECTED_HARNESS_COUNT, "the hosted run set must remain exactly 14"
    assert _WRAPPER_RELPATH not in entries, "the standing harness must NOT be enrolled in the hosted loop"
    assert "dbr_ar_2d_standing_witnesses" not in wf, "the workflow must stay untouched by this slice"
    tree = ast.parse(_text(_COMPLETENESS_GUARD))
    mapping: Optional[Dict[str, str]] = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "MANUAL_ONLY_EXCEPTIONS" for t in node.targets):
            mapping = ast.literal_eval(node.value)
    assert isinstance(mapping, dict), "MANUAL_ONLY_EXCEPTIONS must stay a plain literal dict"
    assert _WRAPPER_RELPATH in mapping, "the V3 standing harness must be a registered MANUAL_ONLY exception"
    assert isinstance(mapping[_WRAPPER_RELPATH], str) and mapping[_WRAPPER_RELPATH].strip(), "the exception needs a written justification"
    for preserved in (
        "tests/control_plane/requires_pg/test_b3a_multi_database_topology.py",
        "tests/control_plane/requires_pg/test_pg_b5_standing_topology.py",
        "tests/control_plane/requires_pg/test_pg_b5_standing_auth_fixture.py",
        "tests/control_plane/requires_pg/test_pg_smoke_c_integrated_live_proof.py",
    ):
        assert preserved in mapping, f"a pre-existing MANUAL_ONLY exception was dropped: {preserved}"


def test_v3_hosted_loop_nonvacuity() -> None:
    fifteen = "for h in \\\n  " + " \\\n  ".join(f"tests/a/requires_pg/test_pg_{i}.py" for i in range(15)) + " ; do\n done"
    assert len(_loop_entries(fifteen) or []) == 15, "a widened 15-entry loop must be detectable"
    enrolled = f"for h in \\\n  {_WRAPPER_RELPATH} ; do\n done"
    assert _WRAPPER_RELPATH in (_loop_entries(enrolled) or []), "a hosted enrollment must be detectable"


# ---------------------------------------------------------------------------
# 11. The automatic apply order stays 001-009 (never an enrollment)
# ---------------------------------------------------------------------------
def test_v3_no_automatic_enrollment() -> None:
    ops = _load_ops()
    order = ops._auto_apply_order_from_b5_source()
    assert order == ops._EXPECTED_AUTO_APPLY_ORDER, f"the automatic standing apply order drifted: {order}"
    assert "010_routing_audit.sql" not in order and "011_routing_audit_append_only.sql" not in order, (
        "010/011 must NEVER be enrolled in the automatic standing apply order"
    )
    ops._assert_auto_apply_order_unchanged()


def test_v3_no_automatic_enrollment_nonvacuity() -> None:
    ops = _load_ops()
    planted = ops._EXPECTED_AUTO_APPLY_ORDER + ("010_routing_audit.sql",)
    assert planted != ops._EXPECTED_AUTO_APPLY_ORDER, "a planted enrollment must be detectable"


# ---------------------------------------------------------------------------
# 12. Locked state: contract/README/runbook/evidence-template lockstep
# ---------------------------------------------------------------------------
def test_v3_locked_state_lockstep() -> None:
    doc = _norm(_text(_CONTRACT_DOC))
    assert "dbr-ar-2 — remains open." in doc, "DBR-AR-2 must remain OPEN"
    assert (
        "dbr-ar-2d — disposable/hosted postgresql proof delivered (v2) and retained standing-environment witnesses"
        " delivered (v3, this pr); dbr-ar-2d is delivered only after this evidence is accepted; dbr-ar-2 remains open." in doc
    ), "the truthful evolved 2D status sentence must be recorded"
    assert "dbr-ar-2e — production-activation evidence consolidated; outcome a is remain not ready / do-not-activate." in doc, (
        "the truthful 2E status (evidence consolidated; Outcome A — REMAIN NOT READY) must be recorded"
    )
    assert "production runtime activation remains not ready / do-not-activate" in doc, "the fail-closed gate posture must hold"
    assert (
        "the ddl is applied only to the retained local standing control database" in doc
        and "not enrolled in the automatic standing apply order (001–009)" in doc
    ), "the truthful standing-apply record must be in the contract doc"
    readme = _norm(_text(_CONTROL_README))
    assert "manually applied" in readme and "retained local standing control db" in readme, (
        "the README must record the V3 manual standing apply truthfully"
    )
    assert "not enrolled in the b5-4 standing apply order" in readme, "the README must keep 010/011 un-enrolled"
    assert "created, not applied for every tenant, staging, and production database" in readme, (
        "the README must scope the apply to the retained local Control DB only"
    )
    runbook = _norm(_text(_RUNBOOK))
    assert "standing execution record (dbr-ar-2d v3)" in runbook, "the runbook must carry the V3 standing execution record"
    assert "production enablement remains unauthorized" in runbook, "production enablement must stay unauthorized"
    template = _norm(_text(_EVIDENCE_TEMPLATE))
    for needle in (
        "references only",
        "backup sha256",
        "exactly four evidence rows",
        "dbr-ar-2 remains open",
        "production activation remains not ready / do-not-activate",
    ):
        assert needle in template, f"the standing evidence template must carry {needle!r}"
    for banned in ("eyj", "-----begin", "postgresql://"):
        assert banned not in template, f"the evidence template must never carry secret-shaped material ({banned!r})"


def test_v3_locked_state_nonvacuity() -> None:
    evolved = (
        "dbr-ar-2d — disposable/hosted postgresql proof delivered (v2) and retained standing-environment witnesses"
        " delivered (v3, this pr); dbr-ar-2d is delivered only after this evidence is accepted; dbr-ar-2 remains open."
    )
    assert evolved not in evolved.replace("only after this evidence is accepted", "unconditionally"), (
        "an unconditional 2D delivery claim must be detectable"
    )
    assert "dbr-ar-2 — remains open." not in "dbr-ar-2 — closed.", "a closed-2 claim must be detectable"
    assert "dbr-ar-2e — production-activation evidence consolidated; outcome a is remain not ready / do-not-activate." not in (
        "dbr-ar-2e — production-activation evidence consolidated."
    ), "a shortened 2E status (without the Outcome A / not-ready posture) must not satisfy"
    assert "not enrolled in the automatic standing apply order (001–009)" not in _norm(
        "010/011 are now enrolled in the automatic standing apply order"
    ), "an enrollment claim must be detectable"


def test_v3_no_durable_fallback_in_composition() -> None:
    # Once durable mode is selected there is NEVER a fallback to the in-memory sink (contract §11).
    # The composed selector must return the bounded durable policy DIRECTLY — no try/except may
    # wrap it into a silent None (which would let build_router compose the in-memory default).
    dr_main = _BACKEND / "database_router" / "main.py"
    source = _text(dr_main)
    tree = ast.parse(source)
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_routing_audit_from_env")
    assert not any(isinstance(n, ast.Try) for n in ast.walk(fn)), (
        "_routing_audit_from_env must carry NO try/except — a wrapped fallback to None would silently re-enable the in-memory sink"
    )
    last = fn.body[-1]
    assert isinstance(last, ast.Return) and isinstance(last.value, ast.Call), "the selected branch must RETURN the composed policy"
    func = last.value.func
    assert isinstance(func, ast.Name) and func.id == "BoundedRoutingAuditPolicy", (
        "the selected branch must return BoundedRoutingAuditPolicy directly"
    )


def test_v3_no_durable_fallback_nonvacuity() -> None:
    mutant = ast.parse(
        "def _routing_audit_from_env():\n"
        "    try:\n"
        "        return BoundedRoutingAuditPolicy(x)\n"
        "    except Exception:\n"
        "        return None\n"
    )
    fn = mutant.body[0]
    assert any(isinstance(n, ast.Try) for n in ast.walk(fn)), "a try-wrapped fallback must be detectable"
    assert not isinstance(fn.body[-1], ast.Return), "the mutant's last statement is the Try, not the direct Return"


def test_v3_no_secret_shaped_literals_in_new_files() -> None:
    # D-14 hygiene: no token/key/DSN-shaped literal may exist in the operator or the wrapper
    # (the operator builds its leak-scan markers dynamically for exactly this reason).
    for path in (_OPS, _WRAPPER):
        text = _text(path)
        for marker in ("ey" + "J", "-----" + "BEGIN"):
            assert marker not in text, f"secret-shaped literal {marker!r} in {path.name}"
        assert not re.search(r"postgresql://[^\"\s]", text), f"a DSN-shaped literal must never appear in {path.name}"


def test_v3_no_secret_shaped_literals_nonvacuity() -> None:
    # The planted samples are BUILT dynamically (low-entropy fragments) so this guard itself never
    # carries a contiguous secret-shaped literal (the CI gitleaks diff scan would rightly flag one).
    planted_token = "cred = '" + "ey" + "J" + "0aaa.b1bb.c2cc'"
    assert ("ey" + "J") in planted_token, "a planted JWT-shaped value must be detectable"
    planted_dsn = 'dsn = "postgresql' + '://u:p@h/db"'
    assert re.search(r"postgresql://[^\"\s]", planted_dsn), "a planted DSN literal must be detectable"


def test_v3_atr_2b1_stays_separate() -> None:
    ingest = _text(_CP_INGEST)
    assert "do_GET = do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = _method_not_allowed" in ingest, (
        "the 2B non-POST refusal shape must stay unchanged (ATR-2B-1 not silently implemented or relabeled)"
    )
    for token in ("server_version", "sys_version", "version_string"):
        assert token not in ingest, f"ATR-2B-1 hardening ({token}) must not be silently implemented"


def test_v3_atr_2b1_nonvacuity() -> None:
    assert "version_string" in "def version_string(self): return ''", "an ATR-2B-1 header override must be detectable"


if __name__ == "__main__":
    _scan.run(
        [
            test_v3_exact_backend_2d_census,
            test_v3_census_nonvacuity,
            test_v3_command_surface_exactly_plan_apply_run_status,
            test_v3_command_surface_nonvacuity,
            test_v3_standing_allow_list_and_sole_ddl_target,
            test_v3_blob_pins_and_apply_order,
            test_v3_blob_and_order_nonvacuity,
            test_v3_backup_discipline,
            test_v3_backup_nonvacuity,
            test_v3_no_destructive_surface,
            test_v3_no_destructive_nonvacuity,
            test_v3_subprocess_census,
            test_v3_subprocess_nonvacuity,
            test_v3_expected_evidence_matrix_exact,
            test_v3_evidence_evaluator_behavioral,
            test_v3_leak_scan_behavioral,
            test_v3_schema_evaluator_behavioral,
            test_v3_stage_machine_behavioral,
            test_v3_rerun_refusal_pinned,
            test_v3_allowed_delta_behavioral,
            test_v3_snapshot_families_complete,
            test_v3_snapshot_families_nonvacuity,
            test_v3_isolation_witnesses_pinned,
            test_v3_loopback_and_finally_discipline,
            test_v3_durable_composition_pinned,
            test_v3_no_status_overclaim,
            test_v3_hosted_loop_unchanged_and_manual_only,
            test_v3_hosted_loop_nonvacuity,
            test_v3_no_automatic_enrollment,
            test_v3_no_automatic_enrollment_nonvacuity,
            test_v3_locked_state_lockstep,
            test_v3_locked_state_nonvacuity,
            test_v3_no_durable_fallback_in_composition,
            test_v3_no_durable_fallback_nonvacuity,
            test_v3_no_secret_shaped_literals_in_new_files,
            test_v3_no_secret_shaped_literals_nonvacuity,
            test_v3_atr_2b1_stays_separate,
            test_v3_atr_2b1_nonvacuity,
        ]
    )
