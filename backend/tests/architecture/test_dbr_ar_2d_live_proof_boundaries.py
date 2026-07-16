"""DBR-AR-2D — disposable live-proof / runbook boundaries guard (architecture; no DB, no runtime).

Machine-pins the PRD DBR-AR-2D V2 execution decisions by text/AST inspection of the committed
sources: the exact authorized file surface (exactly SIX backend ``dbr_ar_2d``/``dbr_ar_2e`` files
after PRD DBR-AR-2D V3 + PRD DBR-AR-2E V1 — the disposable live-PG proof harness, this guard, the
three V3 standing-witness files, and the single 2E activation-evidence guard); the harness's
reviewed 010/011 blob pins equal to the committed DDL blobs with the §7.1 STOP-before-connect
ordering; the exact 010→011 apply order (each exactly once, exact repo paths, no wildcard or
directory scan, no copied DDL bytes); disposable proof-database ownership with guaranteed
teardown and no standing/tenant/production target; the 14-entry hosted run loop with the 2D
harness enrolled exactly once, the ephemeral localhost DSN, no repository secret, no DSN echo,
and the bounded readiness wait; the live evidence set (all four event classes, INSERTED /
DUPLICATE_MATCH / 409 CONFLICT with no extra rows, fresh store + fresh server reconstruction,
UPDATE / DELETE / TRUNCATE rejection with rows unchanged, DB-assigned ``recorded_at`` /
caller-unbound ``id``, identity ordering, bounded failure with no in-memory fallback and no
leakage — everything over the real HTTP wire, never a direct store call); the non-destructive
operator runbook (blob verification before SQL, explicit 010→011, forbidden destructive
recovery, production enablement unauthorized before DBR-AR-2E); the OBS-2D-1 hardening (the exact
20-column sequence, the exact authored CHECK set, and the exact trigger set, cross-derived from the
committed DDL and pinned in both the V2 harness and the V3 standing operator); and the locked state
(the exact canonical DBR-AR-2 closure sentence — Dan-authorized governance decision, 2026-07-16 —
in the contract doc and the b7c2 doc; the V2 disposable proof + V3 standing witnesses delivered only
after evidence acceptance with the remained-OPEN-at-delivery historical tail; 2E production-activation
evidence consolidated with Outcome A — REMAIN NOT
READY / DO-NOT-ACTIVATE; ATR-2B-1 separate with its HTTP-hardening meaning).
Every detector carries a planted non-vacuity companion. Pure stdlib; standalone-runnable:
  python tests/architecture/test_dbr_ar_2d_live_proof_boundaries.py
"""

from __future__ import annotations

import ast
import hashlib
import pathlib
import re
import sys
from typing import List, Optional

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

_REPO = _scan.REPO_ROOT
_BACKEND = _scan.BACKEND_ROOT

_HARNESS = _BACKEND / "tests" / "control_plane" / "requires_pg" / "test_dbr_ar_2d_routing_audit_live_pg.py"
_HARNESS_RELPATH = "tests/control_plane/requires_pg/test_dbr_ar_2d_routing_audit_live_pg.py"
_GUARD = pathlib.Path(__file__).resolve()
_WORKFLOW = _REPO / ".github" / "workflows" / "live-pg-durable-path.yml"
_B7C2 = _REPO / "docs" / "runtime" / "b7c2_live_pg_durable_path_ci.md"
_CONTRACT_DOC = _REPO / "docs" / "runtime" / "dbr_ar_2_durable_routing_audit_contract.md"
_RUNBOOK = _REPO / "infrastructure" / "runbooks" / "dbr_ar_2_durable_routing_audit.md"
_CONTROL_README = _REPO / "infrastructure" / "db" / "control" / "README.md"
_CP_INGEST = _BACKEND / "control_plane" / "adapters" / "providers" / "http_routing_audit_api.py"
_2C_GUARD = pathlib.Path(__file__).resolve().parent / "test_dbr_ar_2c_composition_boundaries.py"
_BLOB_GUARD = pathlib.Path(__file__).resolve().parent / "test_b7c1_control_audit_ddl_blob_pins.py"
_DDL_010 = _REPO / "infrastructure" / "db" / "control" / "010_routing_audit.sql"
_DDL_011 = _REPO / "infrastructure" / "db" / "control" / "011_routing_audit_append_only.sql"

# The exact PRD DBR-AR-2D V2 §10 authorized surface (maximum eleven tracked files).
_AUTHORIZED_SURFACE = (
    "backend/tests/control_plane/requires_pg/test_dbr_ar_2d_routing_audit_live_pg.py",
    "backend/tests/architecture/test_dbr_ar_2d_live_proof_boundaries.py",
    "backend/tests/architecture/test_dbr_ar_2_readiness_contract.py",
    "backend/tests/architecture/test_dbr_ar_2c_composition_boundaries.py",
    "backend/tests/architecture/test_b7c1_control_audit_ddl_blob_pins.py",
    "backend/tests/architecture/test_live_pg_docs_workflow_consistency.py",
    "docs/runtime/b7c2_live_pg_durable_path_ci.md",
    "docs/runtime/dbr_ar_2_durable_routing_audit_contract.md",
    "infrastructure/runbooks/dbr_ar_2_durable_routing_audit.md",
    ".github/workflows/live-pg-durable-path.yml",
    "infrastructure/db/control/README.md",
)

# The exact backend ``dbr_ar_2d``/``dbr_ar_2e`` census after PRD DBR-AR-2D V3 §11 (V2's two files
# + the three standing-witness files) and PRD DBR-AR-2E V1 §4 (exactly one activation-evidence
# guard). Any SEVENTH file, and any SECOND 2E file, remains forbidden until its own governed slice.
_AUTHORIZED_2D_BACKEND_V3 = (
    "backend/tests/architecture/test_dbr_ar_2d_live_proof_boundaries.py",
    "backend/tests/architecture/test_dbr_ar_2d_standing_witness_boundaries.py",
    "backend/tests/architecture/test_dbr_ar_2e_activation_evidence_boundaries.py",
    "backend/tests/control_plane/requires_pg/dbr_ar_2d_standing_witnesses.py",
    "backend/tests/control_plane/requires_pg/test_dbr_ar_2d_routing_audit_live_pg.py",
    "backend/tests/control_plane/requires_pg/test_pg_dbr_ar_2d_standing_witnesses.py",
)
_STANDING_OPS = _BACKEND / "tests" / "control_plane" / "requires_pg" / "dbr_ar_2d_standing_witnesses.py"

_EXPECTED_HARNESS_COUNT = 14  # 13 → 14 by PRD DBR-AR-2D V2 (the dedicated 2D disposable proof)
_EPHEMERAL_DSN = "postgresql://postgres@localhost:5432/postgres"  # the ONLY workflow DSN (localhost service)

_LOOP_RE = re.compile(r"for\s+h\s+in\s+(?P<loop>.+?);\s*do", re.DOTALL)
_ENTRY_RE = re.compile(r"\S+\.py")

# The ONLY sanctioned DBR-AR-2 closure claim (PRD DBR-AR-2 Closure Decision V2 START-GATE §7).
_CLOSURE_PIN = (
    "dbr-ar-2 — closed (dan-authorized governance decision, 2026-07-16); this closure closes zero b5"
    " activation blockers, the blocker census remains nine with 8 of 9 open, and production remains"
    " not ready / do-not-activate."
)

# The four frozen event classes, as the harness's emission-order assertion literal.
_FOUR_CLASSES = '["Route", "RouteControl", "RouteDenied", "IsolationAnomaly"]'

# Destructive-recovery vocabulary that may appear ONLY inside the runbook's Forbidden section
# (SQL-shaped/imperative forms so the sanctioned reject-expected canary probes never false-flag).
_DESTRUCTIVE_TOKENS = (
    "drop table",
    "truncate control_routing_audit",
    "delete from control_routing_audit",
    "update control_routing_audit set",
    "disable trigger",
    "drop trigger",
    "rewrite audit rows",
)


def _text(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def _norm(s: str) -> str:
    return " ".join(s.lower().replace("**", "").replace("`", "").split())


def _git_blob_sha1(path: pathlib.Path) -> str:
    data = path.read_bytes().replace(b"\r\n", b"\n")  # autocrlf normalization (the git blob is LF)
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def _loop_entries(workflow_text: str) -> Optional[List[str]]:
    m = _LOOP_RE.search(workflow_text)
    return _ENTRY_RE.findall(m.group("loop")) if m else None


def _exercise_segment(harness_text: str) -> str:
    """Source of the harness's single registered exercise function (AST-located)."""
    tree = ast.parse(harness_text)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "test_dbr_ar_2d_disposable_live_proof":
            seg = ast.get_source_segment(harness_text, node)
            assert seg is not None
            return seg
    raise AssertionError("test_dbr_ar_2d_disposable_live_proof must exist in the 2D harness")


def _pg_run_registered_names(source_text: str) -> List[str]:
    """Function names registered in ``_pg.run([...])`` (AST; the AT-07E1-2 idiom, replicated)."""
    names: List[str] = []
    for node in ast.walk(ast.parse(source_text)):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "run"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "_pg"
            and node.args
            and isinstance(node.args[0], ast.List)
        ):
            names.extend(elt.id for elt in node.args[0].elts if isinstance(elt, ast.Name))
    return names


def _md_section(text: str, header_fragment: str) -> str:
    """Body of the first ``## …<header_fragment>…`` markdown section (up to the next ``## ``)."""
    pat = re.compile(r"^##[^\n]*" + re.escape(header_fragment) + r"[^\n]*$(?P<body>.*?)(?=^##\s|\Z)", re.MULTILINE | re.DOTALL)
    m = pat.search(text)
    return m.group("body") if m else ""


# ---------------------------------------------------------------------------
# 1. Exact authorized surface: two backend 2D files, zero 2E files, all eleven paths exist
# ---------------------------------------------------------------------------
def test_2d_exact_file_surface() -> None:
    hits = sorted(
        str(p.relative_to(_REPO).as_posix())
        for pattern in ("*dbr_ar_2d*", "*dbr_ar_2e*")
        for p in _BACKEND.rglob(pattern)
        if not (_scan.SKIP_PARTS & set(p.parts))
    )
    assert hits == sorted(_AUTHORIZED_2D_BACKEND_V3), (
        f"exactly the six authorized backend 2D/2E files may exist (no seventh file; no second 2E file): {hits}"
    )
    for rel in _AUTHORIZED_SURFACE + _AUTHORIZED_2D_BACKEND_V3:
        assert (_REPO / rel).is_file(), f"authorized-surface file missing: {rel}"


def test_2d_file_surface_nonvacuity() -> None:
    planted = sorted(list(_AUTHORIZED_2D_BACKEND_V3) + ["backend/tests/database_router/test_dbr_ar_2d_extra.py"])
    assert planted != sorted(_AUTHORIZED_2D_BACKEND_V3), "a sixth dbr_ar_2d backend file must be detectable"
    assert "backend/tests/x/test_dbr_ar_2e_probe.py" not in _AUTHORIZED_2D_BACKEND_V3, (
        "only the single PRD-DBR-AR-2E-V1 guard is authorized — any other 2E file stays unauthorized"
    )


# ---------------------------------------------------------------------------
# 2. Reviewed blob pins + STOP-before-connect ordering (§7.1)
# ---------------------------------------------------------------------------
def test_2d_harness_blob_pins_match_committed_ddl() -> None:
    text = _text(_HARNESS)
    m010 = re.search(r'_REVIEWED_010_BLOB\s*=\s*"([0-9a-f]{40})"', text)
    m011 = re.search(r'_REVIEWED_011_BLOB\s*=\s*"([0-9a-f]{40})"', text)
    assert m010 and m011, "the 2D harness must pin _REVIEWED_010_BLOB and _REVIEWED_011_BLOB"
    assert m010.group(1) == _git_blob_sha1(_DDL_010), "harness _REVIEWED_010_BLOB diverges from the committed 010 blob"
    assert m011.group(1) == _git_blob_sha1(_DDL_011), "harness _REVIEWED_011_BLOB diverges from the committed 011 blob"
    # The default-suite cross-check must stay a COLLECTED test — a renamed/disabled def keeps the
    # variable names in source (satisfying the meta-guard's textual INV-B) but never runs (mutation 9).
    assert "def test_dbr_ar_2d_harness_pins_match_current_ddl" in _text(_BLOB_GUARD), (
        "the blob-pins guard must keep the 2D harness cross-check defined as a collected test"
    )


def test_2d_stop_before_connect_ordering() -> None:
    seg = _exercise_segment(_text(_HARNESS))
    verify = seg.index("_verify_reviewed_blobs()")
    assert verify < seg.index("PostgresControlStore("), "the blob STOP must precede every connection construction (§7.1)"
    assert verify < seg.index("PostgresRoutingAuditStore("), "the blob STOP must precede the durable store construction"
    assert verify < seg.index("_DDL_010.read_text"), "the blob STOP must precede any DDL apply"
    helper = _text(_HARNESS)
    assert "STOP before connect/apply" in helper, "the STOP posture must be stated at both pin-assert sites"


def test_2d_blob_stop_nonvacuity() -> None:
    inverted = "store = PostgresControlStore(dsn)\n_verify_reviewed_blobs()\n"
    assert inverted.index("_verify_reviewed_blobs()") > inverted.index("PostgresControlStore("), (
        "a connect-before-verify rewrite must be detectable"
    )
    assert not re.search(r'_REVIEWED_010_BLOB\s*=\s*"([0-9a-f]{40})"', '_REVIEWED_010_BLOB = "drifted"'), "a non-hex pin must be detectable"
    assert "def test_dbr_ar_2d_harness_pins_match_current_ddl" not in "def _disabled_dbr_ar_2d_harness_pins_match_current_ddl", (
        "a renamed/disabled blob cross-check must be detectable"
    )


# ---------------------------------------------------------------------------
# 3. Exact apply order 010 → 011; no wildcard; no copied DDL bytes
# ---------------------------------------------------------------------------
def test_2d_apply_order_and_no_wildcard() -> None:
    text = _text(_HARNESS)
    assert text.count("_DDL_010.read_text") == 1 and text.count("_DDL_011.read_text") == 1, "each DDL file is applied exactly once"
    assert text.index("_DDL_010.read_text") < text.index("_DDL_011.read_text"), "010 must be applied before 011"
    assert '_DDL_010 = _CONTROL / "010_routing_audit.sql"' in text, "010 must be addressed by its exact repo path"
    assert '_DDL_011 = _CONTROL / "011_routing_audit_append_only.sql"' in text, "011 must be addressed by its exact repo path"
    for banned in ("glob(", "rglob(", "listdir", "iterdir", "*.sql"):
        assert banned not in text, f"the harness must never wildcard/scan for DDL ({banned!r})"
    for copied in ("CREATE TABLE", "CREATE OR REPLACE FUNCTION", "CREATE TRIGGER"):
        assert copied not in text, f"the harness must apply the repo files, never copied DDL bytes ({copied!r})"


def test_2d_apply_order_nonvacuity() -> None:
    swapped = "cur.execute(_DDL_011.read_text())\ncur.execute(_DDL_010.read_text())"
    assert swapped.index("_DDL_010.read_text") > swapped.index("_DDL_011.read_text"), "a swapped apply order must be detectable"
    assert "glob(" in 'for f in _CONTROL.glob("*.sql"): apply(f)', "a wildcard apply must be detectable"
    assert "iterdir" in "for f in sorted(_CONTROL.iterdir())", "an obfuscated directory scan must be detectable"
    assert "CREATE TABLE" in 'cur.execute("CREATE TABLE control_routing_audit (…)")', "copied DDL bytes must be detectable"


# ---------------------------------------------------------------------------
# 4. Disposable ownership: proof-owned database, guaranteed teardown, no standing target
# ---------------------------------------------------------------------------
def test_2d_disposable_ownership_and_teardown() -> None:
    text = _text(_HARNESS)
    assert '_PROOF_DB = "sp2_dbr_ar_2d_proof"' in text, "the proof database name must be the pinned proof-owned constant"
    assert text.count('DROP DATABASE IF EXISTS "{_PROOF_DB}"') == 2, "leftover-drop at start AND finally-teardown must both exist"
    assert "SELECT count(*) FROM pg_database WHERE datname = %s" in text, "teardown must verify the proof database is gone"
    assert "the disposable proof database must be removed after the proof" in text, "the removal assertion must exist"
    for standing in ("5540", "sp2_b3a_control", "snackportal2_control_local", "sp2_tenant_b5_standing"):
        assert standing not in text, f"the harness must never name a standing target ({standing!r})"
    assert "os.environ" not in text, "the DSN reaches the harness only through _pg (SNACKPORTAL_TEST_DSN by name)"
    # No DSN-shaped literal (host material after the scheme); the leak-scan tuple's bare
    # scheme prefix ("postgresql://",) is immediately closed by its quote and never matches.
    assert not re.search(r"postgresql://[^\"\s]", text), "no DSN literal may appear in the harness"


def test_2d_disposable_nonvacuity() -> None:
    assert re.search(r"postgresql://[^\"\s]", 'dsn = "postgresql://sp2_local@127.0.0.1:5540/x"'), "a DSN literal must be detectable"
    assert "5540" in "postgresql://sp2_local@127.0.0.1:5540/x", "a standing-port reference must be detectable"
    retained = 'admin.execute("CREATE DATABASE …")  # no drop'
    assert 'DROP DATABASE IF EXISTS "{_PROOF_DB}"' not in retained, "a retained proof database must be detectable"


# ---------------------------------------------------------------------------
# 5. Hosted CI: 14-entry loop, enrolled exactly once, ephemeral DSN, no secret, no echo, readiness wait
# ---------------------------------------------------------------------------
def test_2d_workflow_loop_and_safety() -> None:
    wf = _text(_WORKFLOW)
    entries = _loop_entries(wf)
    assert entries is not None, "the live-pg run loop must parse"
    assert len(entries) == _EXPECTED_HARNESS_COUNT, f"the hosted run set must be exactly {_EXPECTED_HARNESS_COUNT}, got {len(entries)}"
    assert _HARNESS_RELPATH in entries, "the 2D disposable proof must be an active loop entry"
    assert wf.count(_HARNESS_RELPATH) == 1, "the 2D harness must run through the governed loop exactly once (no bypass step)"
    assert f"SNACKPORTAL_TEST_DSN: {_EPHEMERAL_DSN}" in wf, "the workflow DSN must stay the ephemeral localhost service"
    assert "${{ secrets." not in wf, "the workflow must read no repository/organization/environment secret"
    assert "echo $SNACKPORTAL_TEST_DSN" not in wf and 'echo "$SNACKPORTAL_TEST_DSN"' not in wf, "the DSN must never be echoed"
    assert "Wait for PostgreSQL readiness" in wf and "pg_isready" in wf, "the bounded readiness wait must remain"
    assert "postgres:17" in wf, "the ephemeral postgres:17 service must remain the only database"


def test_2d_workflow_nonvacuity() -> None:
    thirteen = "for h in \\\n  " + " \\\n  ".join(f"tests/a/requires_pg/test_pg_{i}.py" for i in range(13)) + " ; do\n done"
    entries = _loop_entries(thirteen) or []
    assert len(entries) == 13 and _HARNESS_RELPATH not in entries, "a 13-entry loop without the 2D harness must be detectable"
    bypass = f"run: python {_HARNESS_RELPATH}\nfor h in \\\n  {_HARNESS_RELPATH} ; do\n done"
    assert bypass.count(_HARNESS_RELPATH) == 2, "a loop-bypassing second invocation must be detectable"
    assert "${{ secrets." in "env:\n  DSN: ${{ secrets.PROD_DSN }}", "a repository-secret read must be detectable"


# ---------------------------------------------------------------------------
# 6. b7c2 doc lockstep: 14-harness run set, the 2D entry, disposable-only scope
# ---------------------------------------------------------------------------
def test_2d_b7c2_doc_lockstep() -> None:
    doc = _text(_B7C2)
    assert "Run set (14 harnesses)" in doc, "the b7c2 doc must record the 14-harness run set"
    assert "test_dbr_ar_2d_routing_audit_live_pg.py" in _md_section(doc, "What it runs"), "the run-set prose must list the 2D harness"
    norm = _norm(doc)
    assert "no standing or production ddl application occurs" in norm, "the doc must record the disposable-only scope"
    assert _CLOSURE_PIN in norm, "the doc must carry the exact canonical DBR-AR-2 closure sentence"


def test_2d_b7c2_nonvacuity() -> None:
    assert "Run set (14 harnesses)" not in "Run set (13 harnesses)", "a stale 13-count must be detectable"
    assert "no standing or production ddl application occurs" not in _norm("standing DDL application occurs here"), (
        "a scope widening must be detectable"
    )
    assert _CLOSURE_PIN not in _norm("dbr-ar-2 — closed."), "a bare closure claim must not satisfy the exact closure pin"
    assert _CLOSURE_PIN not in _norm(
        "dbr-ar-2 — closed (dan-authorized governance decision, 2026-07-16); production remains not ready / do-not-activate."
    ), "a count-free/zero-closure-free closure variant must not satisfy the exact closure pin"


# ---------------------------------------------------------------------------
# 7. Live evidence set: real wire, four classes, idempotency/conflict, reconstruction,
#    append-only, database authority, ordering, bounded failure, no fallback, no leakage
# ---------------------------------------------------------------------------
def test_2d_real_wire_never_direct_store() -> None:
    text = _text(_HARNESS)
    for required in ("HttpRoutingAudit(", "BoundedRoutingAuditPolicy(", "build_routing_audit_server(", "_post("):
        assert required in text, f"the proof must drive the REAL wire path ({required!r})"
    assert "append_routing_audit(" not in text, "the harness must never call the store directly — every event crosses the HTTP wire"
    assert "InMemoryAuditSink" not in text, "the live proof must never touch the in-memory sink (no fallback, mutation 20/43)"


def test_2d_four_event_classes_pinned() -> None:
    assert _FOUR_CLASSES in _text(_HARNESS), "the harness must assert all four event classes in durable emission order"


def test_2d_idempotency_conflict_pinned() -> None:
    text = _text(_HARNESS)
    assert '(200, {"version": 1, "result": "INSERTED"})' in text, "INSERTED must be asserted (mutation 26)"
    assert '(200, {"version": 1, "result": "DUPLICATE_MATCH"})' in text, "DUPLICATE_MATCH must be asserted (mutation 27)"
    assert '(409, {"version": 1, "result": "CONFLICT"})' in text, "the bounded CONFLICT must be asserted (mutation 29)"
    assert "an identical replay must add NO second row" in text, "the duplicate no-extra-row check must exist (mutation 28)"
    assert "a conflicting replay must add NO row" in text, "the conflict no-extra-row check must exist (mutation 30)"


def test_2d_reconstruction_pinned() -> None:
    text = _text(_HARNESS)
    assert "store_b = PostgresRoutingAuditStore(dsn=proof_dsn)" in text, "a FRESH store must be constructed (mutation 32)"
    assert 'server_b, base_b = build_routing_audit_server(store_b, host="127.0.0.1", port=0)' in text, (
        "a FRESH server must be constructed (mutation 33)"
    )
    assert "restart durability" in text, "the restart step must exist (mutation 31)"
    assert "rows persist; replay stays DUPLICATE_MATCH" in text, "the persist + fresh-instance replay evidence must exist"


def test_2d_append_only_pinned() -> None:
    text = _text(_HARNESS)
    assert "UPDATE control_routing_audit SET outcome" in text, "the UPDATE rejection probe must exist (mutation 34)"
    assert "DELETE FROM control_routing_audit WHERE id" in text, "the DELETE rejection probe must exist (mutation 35)"
    assert '"TRUNCATE control_routing_audit"' in text, "the TRUNCATE rejection probe must exist (mutation 36)"
    assert "rows must be byte-identical after the rejected UPDATE/DELETE/TRUNCATE" in text, "rows must be rechecked (mutation 37)"


def test_2d_database_authority_pinned() -> None:
    text = _text(_HARNESS)
    assert '("id", 999)' in text, "the caller-bound id probe must exist (mutation 39)"
    assert '("recorded_at"' in text, "the caller-bound recorded_at probe must exist (mutation 38)"
    assert "store-assigned, never caller-bound" in text and "now()" in text, "the DB-default recorded_at check must exist"
    assert "identity ordering must be strictly increasing" in text, "the ordering assertion must exist (mutation 40)"
    assert "ORDER BY id ASC" in text, "reads must use the identity total-order authority"
    assert "'Hacked'" in text, "the invalid-action rejection must exist (mutation 41)"
    assert "'api_gateway'" in text, "the invalid-source-service rejection must exist (mutation 42)"


def test_2d_bounded_failure_and_no_leakage_pinned() -> None:
    text = _text(_HARNESS)
    assert '(503, {"version": 1, "result": "UNAVAILABLE"})' in text, "the bounded UNAVAILABLE envelope must be asserted (mutation 43)"
    assert '"routing_audit_unavailable"' in text, "the condition-1 fail-closed denial must be asserted (mutation 44)"
    assert "must NOT be handed back" in text, "route success must never proceed after final audit failure (mutation 44)"
    assert "route_denied_audit_failures" in text, "the condition-3 lost-denial counter must be asserted"
    assert "no failure leg may write a fallback row" in text, "the no-fallback/no-buffer witness must exist"
    assert 'for leaked in ("postgresql://", "SELECT", "INSERT", "control_routing_audit", ":1/")' in text, (
        "the leak scan must exist (mutation 45)"
    )
    assert "stored cells must never contain the DSN/password" in text, "the stored-row secret scan must exist (mutation 45)"


def test_2d_harness_registration() -> None:
    names = _pg_run_registered_names(_text(_HARNESS))
    assert names == ["test_dbr_ar_2d_disposable_live_proof"], f"the harness must register exactly its exercise in _pg.run: {names}"


def test_2d_evidence_nonvacuity() -> None:
    gutted = _text(_HARNESS).replace('(200, {"version": 1, "result": "INSERTED"})', "(200, ANYTHING)")
    assert '(200, {"version": 1, "result": "INSERTED"})' not in gutted, "a dropped INSERTED assertion must be detectable"
    assert "append_routing_audit(" in "result = store.append_routing_audit(record)", "a direct-store bypass must be detectable"
    assert "InMemoryAuditSink" in "audit = InMemoryAuditSink()", "an in-memory substitution must be detectable"
    assert _pg_run_registered_names("import _pg\n_pg.run([test_other])") == ["test_other"], "a deregistered exercise must be detectable"


# ---------------------------------------------------------------------------
# 8. Operator runbook: blob-verify before SQL, explicit order, non-destructive, 2E gate
# ---------------------------------------------------------------------------
def test_2d_runbook_required_shape() -> None:
    text = _text(_RUNBOOK)
    for header in ("Preconditions", "Apply", "Verify", "Canary", "Disable", "Forbidden"):
        assert re.search(r"^##[^\n]*" + header, text, re.MULTILINE), f"the runbook must carry the {header} section"
    assert _git_blob_sha1(_DDL_010) in text and _git_blob_sha1(_DDL_011) in text, "the runbook must carry the exact reviewed blob IDs"
    apply_section = _md_section(text, "Apply")
    assert "010_routing_audit.sql" in apply_section and "011_routing_audit_append_only.sql" in apply_section, "explicit files (mutation 47)"
    assert apply_section.index("010_routing_audit.sql") < apply_section.index("011_routing_audit_append_only.sql"), "010 before 011"
    assert "*.sql" not in text, "the runbook must never instruct a wildcard apply (mutation 47)"
    norm = _norm(text)
    assert "verify the blobs before any sql" in norm, "blob verification must precede SQL (mutation 46)"
    assert "production enablement remains unauthorized" in norm, "production must stay unauthorized before DBR-AR-2E (mutation 49)"
    # An affirmative enablement claim is red even while the remains-unauthorized sentence
    # survives elsewhere (a contradictory mutant must not hide behind the presence pin).
    assert not re.search(
        r"production enablement (?:is|was|becomes|now|hereby|has been) (?:now )?(?:authorized|approved|enabled|permitted)", norm
    ), "no affirmative production-enablement claim may appear (mutation 49)"
    assert "dbr-ar-2e" in norm, "the DBR-AR-2E gate must be named in the runbook"
    assert "no runtime service ever applies ddl" in norm, "the no-runtime-DDL rule must be restated"
    assert "separately governed, dan-authorized standing-environment run" in norm, "the standing run must stay separately governed"


def test_2d_runbook_non_destructive() -> None:
    text = _text(_RUNBOOK)
    forbidden_section = _md_section(text, "Forbidden")
    assert forbidden_section, "the Forbidden section must exist"
    for word in ("DROP", "TRUNCATE", "DELETE", "disable trigger", "rewrite audit rows", "silently fall back after durable mode selection"):
        assert word in forbidden_section, f"the Forbidden list must carry {word!r}"
    outside = _norm(text.replace(forbidden_section, " <forbidden-section> "))
    for token in _DESTRUCTIVE_TOKENS:
        assert token not in outside, f"destructive instruction outside the Forbidden section (mutation 48): {token!r}"


def test_2d_runbook_nonvacuity() -> None:
    assert "truncate control_routing_audit" in _norm("Recovery: TRUNCATE control_routing_audit and restart"), (
        "destructive wording must be detectable"
    )
    assert "drop table" in _norm("then DROP TABLE control_routing_audit"), "alternate destructive wording must be detectable"
    assert "*.sql" in "apply infrastructure/db/control/*.sql in order", "a wildcard apply instruction must be detectable"
    assert "production enablement remains unauthorized" not in _norm("production enablement is now authorized"), (
        "a 2E bypass must be detectable"
    )
    assert re.search(
        r"production enablement (?:is|was|becomes|now|hereby|has been) (?:now )?(?:authorized|approved|enabled|permitted)",
        _norm("Production enablement is now authorized for the canary."),
    ), "an affirmative enablement claim must be detectable even beside the surviving unauthorized sentence"


# ---------------------------------------------------------------------------
# 9. Locked state: DBR-AR-2 OPEN; standing witnesses not started; 2E not started;
#    DDL still un-enrolled; README truthful; ATR-2B-1 separate
# ---------------------------------------------------------------------------
def test_2d_locked_state_pinned() -> None:
    doc = _text(_CONTRACT_DOC).lower()
    assert _CLOSURE_PIN in doc, "the exact canonical DBR-AR-2 closure sentence must be recorded in the contract doc"
    assert (
        "dbr-ar-2d — disposable/hosted postgresql proof delivered (v2) and retained standing-environment witnesses"
        " delivered (v3, this pr); dbr-ar-2d is delivered only after this evidence is accepted;"
        " dbr-ar-2 remained open at 2d delivery." in doc
    ), "the truthful V3 2D status (V2 disposable proof + V3 standing witnesses; delivered only after acceptance) must be recorded"
    assert "dbr-ar-2e — production-activation evidence consolidated; outcome a is remain not ready / do-not-activate." in doc, (
        "the truthful 2E status (evidence consolidated; Outcome A — REMAIN NOT READY) must be recorded"
    )
    assert "production runtime activation remains not ready / do-not-activate" in doc, "the fail-closed gate posture must hold"
    readme = _norm(_text(_CONTROL_README))
    assert "reviewed and exercised by the dbr-ar-2d disposable live proof" in readme, "the README must record the 2D review truthfully"
    assert "not enrolled in the b5-4 standing apply order" in readme, "the README must keep 010/011 un-enrolled"
    assert "manually applied" in readme and "retained local standing control db" in readme, (
        "the README must record the V3 manual standing apply truthfully"
    )


def test_2d_atr_2b1_stays_separate() -> None:
    ingest = _text(_CP_INGEST)
    assert "do_GET = do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = _method_not_allowed" in ingest, (
        "the 2B non-POST refusal shape must stay unchanged (ATR-2B-1 not silently implemented)"
    )
    for token in ("server_version", "sys_version", "version_string"):
        assert token not in ingest, f"ATR-2B-1 hardening ({token}) must not be silently implemented or relabeled"
    assert "def test_2c_atr_2b1_not_silently_implemented" in _text(_2C_GUARD), "the 2C ATR-2B-1 stop rail must survive (mutation 52)"


def test_2d_locked_state_nonvacuity() -> None:
    evolved = (
        "dbr-ar-2d — disposable/hosted postgresql proof delivered (v2) and retained standing-environment witnesses"
        " delivered (v3, this pr); dbr-ar-2d is delivered only after this evidence is accepted;"
        " dbr-ar-2 remained open at 2d delivery."
    )
    assert evolved not in evolved.replace("delivered only after this evidence is accepted", "unconditionally delivered"), (
        "an unconditional 2D delivery mask must be detectable"
    )
    assert evolved not in (
        "dbr-ar-2d — disposable/hosted postgresql proof delivered by this slice;"
        " standing-environment witnesses not started and separately governed; dbr-ar-2d remains open."
    ), "the superseded V2-era status sentence must no longer satisfy"
    assert "dbr-ar-2e — production-activation evidence consolidated; outcome a is remain not ready / do-not-activate." not in (
        "dbr-ar-2e — production-activation evidence consolidated."
    ), "a shortened 2E status (without the Outcome A / not-ready posture) must not satisfy"
    assert _CLOSURE_PIN not in "dbr-ar-2 — closed.", "a bare closure claim must not satisfy the exact closure pin"
    assert _CLOSURE_PIN not in (
        "dbr-ar-2 — closed (dan-authorized governance decision); this closure closes zero b5 activation"
        " blockers, the blocker census remains nine with 8 of 9 open, and production remains not ready /"
        " do-not-activate."
    ), "a date-free closure variant must not satisfy the exact closure pin"
    assert "version_string" in "def version_string(self): return ''", "an ATR-2B-1 header override must be detectable"


# ---------------------------------------------------------------------------
# 10. OBS-2D-1 hardening (PRD DBR-AR-2D V3 §9): the live schema evidence is pinned EXACTLY —
#     the 20-column sequence, the catalog-equality assertion, both frozen CHECK names, the exact
#     authored CHECK set, and the exact trigger set — in the V2 harness AND the V3 standing
#     operator, cross-derived from the committed DDL 010/011 sources of truth (never modified).
# ---------------------------------------------------------------------------
_OBS1_EXPECTED_COLS = [
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
_OBS1_EXPECTED_CHECKS = [
    "control_routing_audit_action_check",
    "control_routing_audit_event_version_check",
    "control_routing_audit_source_service_check",
]
_OBS1_EXPECTED_TRIGGERS = ["control_routing_audit_no_mutation", "control_routing_audit_no_truncate"]

_DDL_COLUMN_RE = re.compile(r"^ {4}([a-z_]+)\b", re.MULTILINE)
_DDL_CONSTRAINT_RE = re.compile(r"CONSTRAINT (control_routing_audit_[a-z_]+)")
_DDL_TRIGGER_RE = re.compile(r"^CREATE TRIGGER (control_routing_audit_[a-z_]+)", re.MULTILINE)


def _module_literal(source: str, name: str) -> object:
    """The module-level literal ``name`` (AST; Assign or AnnAssign) of ``source``."""
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return ast.literal_eval(node.value)
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == name and node.value is not None:
            return ast.literal_eval(node.value)
    raise AssertionError(f"module literal {name!r} not found")


def test_2d_obs1_twenty_column_sequence_pinned() -> None:
    ddl_columns = _DDL_COLUMN_RE.findall(_text(_DDL_010))
    assert ddl_columns == _OBS1_EXPECTED_COLS, f"the DDL 010 column sequence drifted: {ddl_columns}"
    assert _module_literal(_text(_HARNESS), "_EXPECTED_COLS") == _OBS1_EXPECTED_COLS, (
        "the V2 harness _EXPECTED_COLS must pin the exact 20-column sequence"
    )
    assert _module_literal(_text(_STANDING_OPS), "_EXPECTED_COLS") == _OBS1_EXPECTED_COLS, (
        "the V3 standing operator _EXPECTED_COLS must pin the exact 20-column sequence"
    )
    assert "names == _EXPECTED_COLS" in _text(_HARNESS), "the harness must assert catalog columns EQUAL _EXPECTED_COLS"
    assert 'census["column_names"] != _EXPECTED_COLS' in _text(_STANDING_OPS), (
        "the standing operator must fail closed unless catalog columns EQUAL _EXPECTED_COLS"
    )


def test_2d_obs1_check_and_trigger_sets_pinned() -> None:
    ddl_checks = sorted(set(_DDL_CONSTRAINT_RE.findall(_text(_DDL_010))))
    assert ddl_checks == _OBS1_EXPECTED_CHECKS, f"the DDL 010 named CHECK set drifted: {ddl_checks}"
    ddl_triggers = sorted(_DDL_TRIGGER_RE.findall(_text(_DDL_011)))
    assert ddl_triggers == _OBS1_EXPECTED_TRIGGERS, f"the DDL 011 trigger set drifted: {ddl_triggers}"
    assert "CREATE OR REPLACE FUNCTION control_routing_audit_append_only()" in _text(_DDL_011), (
        "the append-only trigger function must remain the authored one"
    )
    harness = _text(_HARNESS)
    assert '"control_routing_audit_action_check" in checks' in harness, "the harness must pin the frozen action CHECK by name"
    assert '"control_routing_audit_source_service_check" in checks' in harness, (
        "the harness must pin the frozen source_service CHECK by name"
    )
    assert 'triggers == ["control_routing_audit_no_mutation", "control_routing_audit_no_truncate"]' in harness, (
        "the harness must assert the EXACT trigger set"
    )
    ops_source = _text(_STANDING_OPS)
    assert _module_literal(ops_source, "_EXPECTED_CHECKS") == _OBS1_EXPECTED_CHECKS, (
        "the standing operator must pin the EXACT authored CHECK set"
    )
    assert _module_literal(ops_source, "_EXPECTED_TRIGGERS") == _OBS1_EXPECTED_TRIGGERS, (
        "the standing operator must pin the EXACT trigger set"
    )
    assert 'census["checks"] != _EXPECTED_CHECKS' in ops_source, "the standing operator must fail closed on an inexact CHECK set"
    assert 'census["triggers"] != _EXPECTED_TRIGGERS' in ops_source, "the standing operator must fail closed on an inexact trigger set"


def test_2d_obs1_nonvacuity() -> None:
    assert _OBS1_EXPECTED_COLS[:19] != _OBS1_EXPECTED_COLS, "a dropped 20th column must be detectable"
    assert sorted(set(_OBS1_EXPECTED_CHECKS + ["control_routing_audit_rogue_check"])) != _OBS1_EXPECTED_CHECKS, (
        "an extra CHECK constraint must be detectable"
    )
    assert ["control_routing_audit_no_mutation"] != _OBS1_EXPECTED_TRIGGERS, "a dropped trigger must be detectable"
    assert _DDL_COLUMN_RE.findall("    rogue_col     text,\n") == ["rogue_col"], "the DDL column extractor went vacuous"
    assert _DDL_TRIGGER_RE.findall("CREATE TRIGGER control_routing_audit_extra\n") == ["control_routing_audit_extra"], (
        "the DDL trigger extractor went vacuous"
    )
    assert '"control_routing_audit_action_check" in checks' not in 'checks_probe = ["something_else"]', (
        "a dropped harness CHECK pin must be detectable"
    )


if __name__ == "__main__":
    _scan.run(
        [
            test_2d_exact_file_surface,
            test_2d_file_surface_nonvacuity,
            test_2d_harness_blob_pins_match_committed_ddl,
            test_2d_stop_before_connect_ordering,
            test_2d_blob_stop_nonvacuity,
            test_2d_apply_order_and_no_wildcard,
            test_2d_apply_order_nonvacuity,
            test_2d_disposable_ownership_and_teardown,
            test_2d_disposable_nonvacuity,
            test_2d_workflow_loop_and_safety,
            test_2d_workflow_nonvacuity,
            test_2d_b7c2_doc_lockstep,
            test_2d_b7c2_nonvacuity,
            test_2d_real_wire_never_direct_store,
            test_2d_four_event_classes_pinned,
            test_2d_idempotency_conflict_pinned,
            test_2d_reconstruction_pinned,
            test_2d_append_only_pinned,
            test_2d_database_authority_pinned,
            test_2d_bounded_failure_and_no_leakage_pinned,
            test_2d_harness_registration,
            test_2d_evidence_nonvacuity,
            test_2d_runbook_required_shape,
            test_2d_runbook_non_destructive,
            test_2d_runbook_nonvacuity,
            test_2d_locked_state_pinned,
            test_2d_atr_2b1_stays_separate,
            test_2d_locked_state_nonvacuity,
            test_2d_obs1_twenty_column_sequence_pinned,
            test_2d_obs1_check_and_trigger_sets_pinned,
            test_2d_obs1_nonvacuity,
        ]
    )
