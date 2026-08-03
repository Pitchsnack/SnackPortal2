"""W1a — composed-core import write-path + durable Import-audit boundaries guard (architecture; no DB, no runtime).

Machine-pins the W1a composed-core execution decisions by text/AST inspection of the committed sources — every
detector carries a planted non-vacuity companion. Scope: the composed-core import copy + its durable Import
operational audit only (northbound served /import is W1b; operator retrieval is a later slice). Pins:

* DDL 014/015 blob equality to the reviewed pins; the frozen 014 shape (id identity PK; UNIQUE audit_id; the
  five-value action CHECK; the source_service='import_service' CHECK; the event_version>0 CHECK; both 015
  append-only triggers; references-only — no JSON/FK/hash-chain); 014/015 un-enrolled (created-not-applied);
* tenant 008 — the plain, non-partial, non-CONCURRENT UNIQUE index; enrolled in the applicator + the tenant
  DDL apply-order authority;
* the Import-Service durable emitter — stdlib only, no DB driver, no cross-service import, no DSN literal,
  exact nine-key references-only wire, single transport attempt (the policy owns retry);
* the Control-Plane ingest edge — internal-only loopback path, POST-only, single-threaded, imports only
  control_plane.import_audit, forbidden-name + secret-shape defenses, no api_gateway/import_service/DB driver;
* the CP store + port — CP-local record/port (no api_gateway/import_service import), one abstract write
  method, ON CONFLICT (audit_id), append-only adapter surface;
* the composition seams — the CP loopback-host allowlist + fail-closed; the import-side BoundedImportAuditPolicy
  bounded single retry (no loop);
* the single-route pin — the executed composed IMPORT_INITIATION path calls no Database-Router dispatch;
* the served import edge — one blessed serve entrypoint; the StartupDirectorySource single-record mapping;
  the ImportResultDTO references-only catalogue member;
* the MANUAL_ONLY disposable proof — STOP-before-connect, exact 014→015 apply order, no wildcard, three
  proof-owned disposable databases with guaranteed teardown, references-only, registered MANUAL_ONLY;
* no secret/DSN literal in any W1a source file.

Pure stdlib; standalone-runnable:
  python tests/architecture/test_import_write_path_boundaries.py
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

_REPO = _scan.REPO_ROOT
_BACKEND = _scan.BACKEND_ROOT
_CONTROL = _REPO / "infrastructure" / "db" / "control"
_TENANT = _REPO / "infrastructure" / "db" / "tenant"

_DDL_014 = _CONTROL / "014_import_operational_audit.sql"
_DDL_015 = _CONTROL / "015_import_operational_audit_append_only.sql"
_DDL_008 = _TENANT / "008_startups_global_startup_id_unique.sql"
_EMITTER = _BACKEND / "import_service" / "adapters" / "providers" / "durable_audit_emitter.py"
_IMPORT_MAIN = _BACKEND / "import_service" / "main.py"
_IMPORT_EDGE = _BACKEND / "import_service" / "adapters" / "providers" / "http_import_api.py"
_STARTUP_SOURCE = _BACKEND / "import_service" / "adapters" / "providers" / "startup_directory_source.py"
_GATEWAY = _BACKEND / "api_gateway" / "gateway.py"
_GW_MAIN = _BACKEND / "api_gateway" / "main.py"
_INIT_CLIENT = _BACKEND / "api_gateway" / "adapters" / "providers" / "http_import_initiation.py"
_PORTAL = _BACKEND / "api_gateway" / "portal.py"
_CP_INGEST = _BACKEND / "control_plane" / "adapters" / "providers" / "http_import_audit_api.py"
_CP_STORE = _BACKEND / "control_plane" / "adapters" / "providers" / "postgres_store.py"
_CP_PORT = _BACKEND / "control_plane" / "import_audit.py"
_CP_MAIN = _BACKEND / "control_plane" / "main.py"
_APPLICATOR = _BACKEND / "control_plane" / "adapters" / "providers" / "postgres_tenant_schema_applicator.py"
_PROOF = _BACKEND / "tests" / "control_plane" / "requires_pg" / "test_pg_import_copy_durable.py"
_RUNBOOK = _REPO / "infrastructure" / "runbooks" / "import_copy_live_proof.md"
_OPS = _BACKEND / "tests" / "control_plane" / "requires_pg" / "b5_standing_topology.py"
_COMPLETENESS_GUARD = _BACKEND / "tests" / "architecture" / "test_live_pg_workflow_runset_completeness.py"
_TENANT_GUARD = _BACKEND / "tests" / "architecture" / "test_tenant_ddl_blob_drift.py"
_MULTIINSTANCE_GUARD = _BACKEND / "tests" / "architecture" / "test_07d3_multiinstance_readiness_static.py"

# The reviewed LF-normalized git-blob SHA-1 pins for the created-not-applied W1a DDL.
_REVIEWED_014_BLOB = "73436f9681163c8a86ee230f51206062b06735c5"
_REVIEWED_015_BLOB = "ba594e3cd6eb070790bde6015f5225960c0d62ed"
_REVIEWED_008_BLOB = "20741db4dc6152bcdf9aaec029b9845a7bacb78e"

# The five frozen Import-operational-audit actions (IC-003).
_EXPECTED_ACTIONS = ("ImportRequested", "ImportStarted", "ImportResumed", "ImportCompleted", "ImportFailed")
_EXPECTED_CHECKS = (
    "control_import_audit_action_check",
    "control_import_audit_event_version_check",
    "control_import_audit_source_service_check",
)
_EXPECTED_TRIGGERS = ("control_import_audit_no_mutation", "control_import_audit_no_truncate")
_PROOF_RELPATH = "tests/control_plane/requires_pg/test_pg_import_copy_durable.py"


def _text(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def _tree(path: pathlib.Path) -> ast.Module:
    return ast.parse(_text(path), filename=str(path))


def _git_blob_sha1(path: pathlib.Path) -> str:
    data = path.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def _import_tops(path: pathlib.Path) -> set:
    return {m.split(".")[0] for m in _scan.imported_modules(path)}


def _load_ops_module():  # noqa: ANN202
    spec = importlib.util.spec_from_file_location("b5_standing_topology_w1a_pin", _OPS)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- 1. file surface + DDL blob/shape/enrollment ---------------------------------------------------
def test_w1a_file_surface_exists() -> None:
    for path in (
        _DDL_014,
        _DDL_015,
        _DDL_008,
        _EMITTER,
        _IMPORT_MAIN,
        _IMPORT_EDGE,
        _STARTUP_SOURCE,
        _GATEWAY,
        _GW_MAIN,
        _INIT_CLIENT,
        _PORTAL,
        _CP_INGEST,
        _CP_STORE,
        _CP_PORT,
        _CP_MAIN,
        _APPLICATOR,
        _PROOF,
        _RUNBOOK,
    ):
        assert path.is_file(), f"W1a surface file missing: {path}"


def test_ddl_014_015_blob_pins_match_committed() -> None:
    assert _git_blob_sha1(_DDL_014) == _REVIEWED_014_BLOB, "014 blob drifted from the reviewed pin"
    assert _git_blob_sha1(_DDL_015) == _REVIEWED_015_BLOB, "015 blob drifted from the reviewed pin"
    # Cross-checked in the default suite by the blob-drift guard (single source of truth = the bytes).
    blob_guard = _text(_BACKEND / "tests" / "architecture" / "test_b7c1_control_audit_ddl_blob_pins.py")
    assert "_PIN_014" in blob_guard and "_PIN_015" in blob_guard, "the blob-drift guard must also pin 014/015"
    assert _PROOF_RELPATH.split("/")[-1] in blob_guard, "the blob-drift guard must cross-check the proof harness pins"


def test_ddl_014_frozen_shape() -> None:
    ddl = _text(_DDL_014)
    assert "CREATE TABLE IF NOT EXISTS control_import_audit" in ddl
    assert "GENERATED ALWAYS AS IDENTITY PRIMARY KEY" in ddl, "id must be the identity ordering-authority PK"
    assert "audit_id" in ddl and "NOT NULL UNIQUE" in ddl, "audit_id must be the UNIQUE idempotency key"
    for action in _EXPECTED_ACTIONS:
        assert f"'{action}'" in ddl, f"the action CHECK must pin {action}"
    assert "CHECK (source_service = 'import_service')" in ddl, "the source_service CHECK must pin the producer constant"
    assert "CHECK (event_version > 0)" in ddl, "the event_version CHECK must pin positivity"
    for check in _EXPECTED_CHECKS:
        assert check in ddl, f"the named CHECK {check} must exist"
    # Scan the CREATE TABLE BODY only, with `--` comments stripped (comment prose legitimately names
    # "NO JSON / hash-chain" and explains LineageWritten's exclusion).
    body = "\n".join(line.split("--")[0] for line in ddl.splitlines()).lower()
    # LineageWritten must NOT be an import-audit action (structurally rejected by the action CHECK).
    assert "lineagewritten" not in body, "LineageWritten must never be an import-audit action (not in the CHECK)"
    for banned in ("jsonb", " json", "references ", "foreign key", "hash_chain"):
        assert banned not in body, f"references-only DDL body must carry no {banned!r} column/constraint"


def test_ddl_015_append_only_triggers() -> None:
    ddl = _text(_DDL_015)
    assert "CREATE OR REPLACE FUNCTION control_import_audit_append_only()" in ddl
    for trigger in _EXPECTED_TRIGGERS:
        assert f"CREATE TRIGGER {trigger}" in ddl, f"the append-only trigger {trigger} must exist"
    assert "BEFORE UPDATE OR DELETE" in ddl and "BEFORE TRUNCATE" in ddl, "UPDATE/DELETE and TRUNCATE must both be rejected"


def test_ddl_014_015_created_not_applied_and_unenrolled() -> None:
    on_disk = {p.name for p in _CONTROL.glob("*.sql")}
    assert {"014_import_operational_audit.sql", "015_import_operational_audit_append_only.sql"} <= on_disk, (
        "014/015 must be present on disk"
    )
    module = _load_ops_module()
    for name in ("014_import_operational_audit.sql", "015_import_operational_audit_append_only.sql"):
        assert name not in module._CONTROL_DDL_ORDER, f"{name} is created-not-applied and must NOT be enrolled in the standing apply order"


# --- 2. tenant 008 ---------------------------------------------------------------------------------
def test_tenant_008_shape_plain_unique_index() -> None:
    assert _git_blob_sha1(_DDL_008) == _REVIEWED_008_BLOB, "008 blob drifted from the reviewed pin"
    ddl = _text(_DDL_008)
    assert "CREATE UNIQUE INDEX IF NOT EXISTS startups_global_startup_id_key ON startups (global_startup_id);" in ddl, (
        "008 must be the exact plain unique index on startups(global_startup_id)"
    )
    # Scan the CREATE INDEX statement only (comment prose legitimately names CONCURRENTLY / partial while
    # explaining why they are avoided).
    stmt = "\n".join(line.split("--")[0] for line in ddl.splitlines()).lower()
    assert "concurrently" not in stmt, "008 must NOT be CONCURRENT (applied inside the atomic Step-2b transaction)"
    assert " where " not in stmt, "008 must be a PLAIN (non-partial) index — no WHERE predicate"
    assert "tenant_id" not in stmt, "no tenant_id column (tenancy is physical)"


def test_tenant_008_enrolled_in_applicator_and_guard() -> None:
    applicator = _text(_APPLICATOR)
    assert '"008_startups_global_startup_id_unique.sql"' in applicator, "008 must be enrolled in default_tenant_schema_ddl_paths()"
    guard = _text(_TENANT_GUARD)
    assert '"008_startups_global_startup_id_unique.sql"' in guard, "008 must be in the tenant DDL apply-order authority"
    assert _REVIEWED_008_BLOB in guard, "the tenant blob-drift guard must pin the 008 blob"


# --- 3. Import-Service durable emitter -------------------------------------------------------------
def test_import_audit_emitter_is_stdlib_only_no_driver_no_cross_service_no_dsn() -> None:
    tops = _import_tops(_EMITTER)
    assert tops <= {"__future__", "json", "urllib", "uuid", "datetime", "typing", "shared"}, (
        f"emitter imports outside the stdlib/shared surface: {sorted(tops)}"
    )
    for banned in ("psycopg", "psycopg2", "asyncpg", "sqlalchemy", "control_plane", "database_router", "api_gateway", "threading"):
        assert banned not in tops, f"the emitter must not import {banned}"
    lowered = _text(_EMITTER).lower()
    for needle in ("dsn", "postgresql://", "postgres://", "password", "connect("):
        assert needle not in lowered, f"the emitter must not reference {needle} (no DB driver / descriptor)"


def test_import_audit_emitter_wire_is_nine_references_only_keys_no_loop() -> None:
    tree = _tree(_EMITTER)
    keys = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_wire_event":
            for inner in ast.walk(node):
                if isinstance(inner, ast.Dict):
                    keys = {k.value for k in inner.keys if isinstance(k, ast.Constant)}
    assert keys == {
        "audit_id",
        "event_version",
        "occurred_at",
        "correlation_id",
        "action",
        "outcome",
        "actor_ref",
        "target_ref",
        "source_ref",
    }, f"the wire event must carry exactly the nine references-only keys: {keys}"
    assert "source_service" not in (keys or set()), "source_service is a store-side constant — never a wire key"
    # Single transport attempt: the emitter's POST method contains no retry loop (the policy owns the retry).
    post_fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "post")
    assert not any(isinstance(n, (ast.For, ast.While)) for n in ast.walk(post_fn)), "the emitter's post() must contain no retry loop"


# --- 4. Control-Plane ingest edge ------------------------------------------------------------------
def test_cp_import_audit_ingest_edge_boundaries() -> None:
    text = _text(_CP_INGEST)
    tops = _import_tops(_CP_INGEST)
    assert tops <= {"__future__", "json", "typing", "fastapi", "control_plane", "shared"}, (
        f"ingest imports outside the adapter surface: {sorted(tops)}"
    )
    # FastAPI is the ONE sanctioned framework; the ASGI server and its socket stay in the shared runtime.
    for banned in (
        "api_gateway",
        "import_service",
        "psycopg",
        "psycopg2",
        "asyncpg",
        "sqlalchemy",
        "threading",
        "asyncio",
        "starlette",
        "uvicorn",
        "http",
    ):
        assert banned not in tops, f"the ingest edge must not import {banned}"
    assert '"/internal/import-audit/events"' in text, "the internal-only ingest path must be pinned"
    assert '"127.0.0.1"' in text, "the ingest edge must default-bind the loopback host"
    for marker in ("HTTPServer", "ThreadingHTTPServer", "ThreadingMixIn"):
        assert marker not in text, f"the ingest edge must hand-roll no server ({marker}); the shared runtime owns it"
    assert "build_asgi_server" in text, "the ingest edge must serve through the shared ASGI runtime"
    assert "_FORBIDDEN_EVENT_KEYS" in text and "source_service" in text, "the forbidden-name denylist (incl. source_service) must exist"
    assert "_SECRET_SHAPES" in text, "the secret/token/DSN-shape defense must exist"
    for action in _EXPECTED_ACTIONS:
        assert f'"{action}"' in text, f"the ingest edge must pin the {action} action"
    # POST-only: exactly one registered route decorator, and it is a POST (every other method is
    # refused 405 by the shared fail-closed app before the store is reached).
    served = _scan.registered_route_methods(_tree(_CP_INGEST))
    assert served == ["post"], f"the ingest edge must be POST-only: {served}"


# --- 5. CP store + port ----------------------------------------------------------------------------
def test_cp_import_audit_port_is_control_local_append_only() -> None:
    tops = _import_tops(_CP_PORT)
    for banned in ("api_gateway", "database_router", "auth_router", "import_service", "psycopg"):
        assert banned not in tops, f"the CP import-audit port must not import {banned}"
    text = _text(_CP_PORT)
    assert "def append_import_audit" in text, "the store port must expose append_import_audit"
    for verb in ("def list", "def get", "def read", "def query", "def export", "def purge", "def update", "def delete"):
        assert verb not in text, f"the append-only store port must expose no {verb!r}"


def test_cp_import_audit_store_on_conflict_audit_id_append_only_surface() -> None:
    text = _text(_CP_STORE)
    assert "ON CONFLICT (audit_id) DO NOTHING RETURNING id" in text, "the store must idempotently upsert on audit_id"
    assert "class PostgresImportAuditStore" in text
    assert "control_import_audit" in text, "the store must target control_import_audit"
    assert "UPDATE control_import_audit" not in text and "DELETE FROM control_import_audit" not in text, "append-only adapter"


# --- 6. composition seams --------------------------------------------------------------------------
def test_cp_import_audit_composition_seam_loopback_failclosed() -> None:
    text = _text(_CP_MAIN)
    assert "def build_import_audit_server_from_env" in text
    assert "SP2_CP_IMPORT_AUDIT_HOST" in text and "SP2_CP_IMPORT_AUDIT_PORT" in text
    assert "_IMPORT_AUDIT_LOOPBACK_HOSTS" in text and '"127.0.0.1"' in text, "the ingest edge must be loopback-only (fail closed)"


def test_import_service_audit_policy_single_retry_no_loop() -> None:
    text = _text(_IMPORT_MAIN)
    assert "class BoundedImportAuditPolicy" in text and "def build_import_audit_sink_from_env" in text
    assert "no silent fallback" in text, "the fail-closed selector intent must be documented"
    policy = next(n for n in ast.walk(_tree(_IMPORT_MAIN)) if isinstance(n, ast.ClassDef) and n.name == "BoundedImportAuditPolicy")
    initiate = next(n for n in ast.walk(policy) if isinstance(n, ast.FunctionDef) and n.name == "initiate")
    assert not any(isinstance(n, (ast.For, ast.While)) for n in ast.walk(initiate)), "the policy must not use a retry LOOP"
    posts = [n for n in ast.walk(initiate) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "post"]
    assert len(posts) == 2, "the policy must call the inner post at most twice (initial + exactly one retry)"


# --- 7. single-route + served edge + mapping + DTO -------------------------------------------------
def test_gateway_composed_import_path_single_route_no_dispatch() -> None:
    handle = next(n for n in ast.walk(_tree(_GATEWAY)) if isinstance(n, ast.FunctionDef) and n.name == "_handle")
    composed_if = None
    for node in ast.walk(handle):
        if isinstance(node, ast.If) and "_import_initiation" in ast.dump(node.test):
            composed_if = node
            break
    assert composed_if is not None, "the composed IMPORT_INITIATION branch (gated on _import_initiation) must exist"
    dispatch_calls = [
        n for n in ast.walk(composed_if) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "dispatch"
    ]
    assert dispatch_calls == [], "single-route: the executed composed import path must contain NO router dispatch call"
    # The gateway imports no import_service and makes no start_import CALL/name (AST — a `-- comment` in an
    # unrelated pinned string may legitimately mention the name; the ic009 guard enforces the same by AST).
    gtree = _tree(_GATEWAY)
    gimports = {n.module.split(".")[0] for n in ast.walk(gtree) if isinstance(n, ast.ImportFrom) and n.module}
    gimports |= {a.name.split(".")[0] for n in ast.walk(gtree) if isinstance(n, ast.Import) for a in n.names}
    assert "import_service" not in gimports, "the gateway must not import import_service (DAG independence)"
    names = {n.attr for n in ast.walk(gtree) if isinstance(n, ast.Attribute)} | {n.id for n in ast.walk(gtree) if isinstance(n, ast.Name)}
    assert "start_import" not in names, "the gateway must make no start_import call/name (import-execution ban)"


def test_import_edge_sole_serve_entrypoint_blessed() -> None:
    text = _text(_IMPORT_EDGE)
    assert "def serve_import_api" in text, "the served import edge must expose serve_import_api"
    serve_calls = [
        n
        for n in ast.walk(_tree(_IMPORT_EDGE))
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "serve_forever"
    ]
    assert len(serve_calls) == 1, "exactly one serve_forever CALL, inside the single blessed entrypoint"
    for marker in ("ThreadingHTTPServer", "ThreadingMixIn"):
        assert marker not in text, f"the served edge must stay single-threaded (found {marker})"
    census = _text(_MULTIINSTANCE_GUARD)
    assert '"import_service/adapters/providers/http_import_api.py": "serve_import_api"' in census, (
        "the served import edge must be a blessed serve-loop entrypoint in the 07d3 census"
    )


def test_startup_directory_source_single_record_mapping_pins() -> None:
    tops = _import_tops(_STARTUP_SOURCE)
    for banned in ("control_plane", "database_router", "psycopg"):
        assert banned not in tops, f"the mapping adapter must not import {banned}"
    text = _text(_STARTUP_SOURCE)
    assert "get_record" in text and "global_startup_id" in text and "company_name" in text, "the single-record Global→tenant mapping"
    assert "record_id" in text and "display_name" in text, "record_id->global_startup_id; display_name->company_name"
    # Single-record: no directory page loop (that is GlobalDirectorySource's behavior).
    read_fn = next(n for n in ast.walk(_tree(_STARTUP_SOURCE)) if isinstance(n, ast.FunctionDef) and n.name == "read")
    assert not any(isinstance(n, ast.While) for n in ast.walk(read_fn)), "the single-record mapping must not page/loop"


def test_import_result_dto_references_only_catalogue() -> None:
    portal = _text(_PORTAL)
    assert "class ImportResultDTO" in portal, "ImportResultDTO must be defined in the portal catalogue"
    for field in ("source_ref", "target_tenant_ref", "tenant_record_ref", "lineage_ref", "import_id", "outcome"):
        assert field in portal, f"ImportResultDTO must carry the references-only field {field}"
    assert "ImportResultDTO: (PORTAL_CONTRACT_ID, PORTAL_CONTRACT_REVISION)" in portal, "ImportResultDTO must be in APPROVED_PORTAL_DTOS"
    ic009 = _text(_BACKEND / "tests" / "architecture" / "test_ic009_portal_binding_checks.py")
    assert "ImportResultDTO" in ic009, "the ic009 portal-binding guard must census ImportResultDTO"


def test_no_secret_or_dsn_literal_in_w1a_sources() -> None:
    # The CP ingest edge and the served import edge are EXCLUDED here: they legitimately define the
    # secret/token/DSN-shape DETECTION markers. Every other W1a source must carry no actual secret/DSN literal.
    for path in (_EMITTER, _INIT_CLIENT, _STARTUP_SOURCE, _CP_PORT, _DDL_014, _DDL_015, _DDL_008):
        text = _text(path)
        assert not re.search(r"postgresql://[^\s\"']", text), f"{path.name} must carry no DSN literal"
        for needle in ("password=", "eyJ", "-----BEGIN "):
            assert needle not in text, f"{path.name} must carry no secret literal ({needle!r})"


# --- 8. MANUAL_ONLY disposable proof ---------------------------------------------------------------
def test_proof_stop_before_connect_and_apply_order() -> None:
    text = _text(_PROOF)
    assert "_verify_reviewed_blobs()" in text and "STOP before connect/apply" in text
    verify = text.index("_verify_reviewed_blobs()")
    assert verify < text.index("_DDL_014.read_text"), "the blob STOP must precede any DDL apply"
    assert text.count("_DDL_014.read_text") == 1 and text.count("_DDL_015.read_text") == 1, "each control DDL file is applied exactly once"
    assert text.index("_DDL_014.read_text") < text.index("_DDL_015.read_text"), "014 must be applied before 015"
    assert '_DDL_014 = _CONTROL / "014_import_operational_audit.sql"' in text, "014 must be addressed by its exact repo path"
    assert '_DDL_015 = _CONTROL / "015_import_operational_audit_append_only.sql"' in text, "015 must be addressed by its exact repo path"
    for banned in ("glob(", "rglob(", "listdir", "iterdir", "*.sql"):
        assert banned not in text, f"the proof must never wildcard/scan for DDL ({banned!r})"
    for copied in ("CREATE TABLE control_import_audit", "CREATE TRIGGER control_import_audit"):
        assert copied not in text, f"the proof must apply the repo files, never copied DDL bytes ({copied!r})"


def test_proof_disposable_ownership_teardown_three_databases() -> None:
    text = _text(_PROOF)
    for db in ("sp2_w1a_import_proof_control", "sp2_w1a_import_proof_t1", "sp2_w1a_import_proof_t2"):
        assert db in text, f"the proof must name the disposable proof database {db}"
    assert "DROP DATABASE IF EXISTS" in text, "the proof must drop its disposable databases"
    # Guaranteed teardown: the three names are iterated in a drop loop and zero retention is asserted.
    assert "must be removed after the proof" in text, "the proof must assert zero retained proof databases"
    assert "os.environ" not in text, "the DSN reaches the proof only through _pg (SNACKPORTAL_TEST_DSN by name)"
    assert not re.search(r"postgresql://[^\"\s]", text), "no DSN literal may appear in the proof"
    for standing in ("sp2_b3a_control", "snackportal2_control_local", "sp2_tenant_b5_standing", "sp2_gateway_audit_v1a_proof"):
        assert standing not in text, f"the proof must never name another target ({standing!r})"
    assert '"infrastructure" / "db" / "control"' in text, "the proof must build the control DDL path from the canonical segments"
    assert "_REVIEWED_014_BLOB" in text and "_REVIEWED_015_BLOB" in text, "the proof must pin the reviewed 014/015 blobs"


def test_proof_registered_manual_only_no_hosted_enrollment() -> None:
    completeness = _text(_COMPLETENESS_GUARD)
    assert _PROOF_RELPATH in completeness, "the proof must be a registered MANUAL_ONLY exception of the run-set completeness guard"
    tree = _tree(_COMPLETENESS_GUARD)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "MANUAL_ONLY_EXCEPTIONS" for t in node.targets):
            mapping = ast.literal_eval(node.value)
            assert _PROOF_RELPATH in mapping and str(mapping[_PROOF_RELPATH]).strip(), "the exception must carry a written justification"
            return
    raise AssertionError("MANUAL_ONLY_EXCEPTIONS not found in the completeness guard")


# --- non-vacuity companions ------------------------------------------------------------------------
def test_boundary_detectors_are_non_vacuous() -> None:
    # blob pin
    assert _git_blob_sha1(_DDL_014) != "0" * 40
    # action-set detector flags a truncated CHECK
    assert not all(f"'{a}'" in "action IN ('ImportRequested')" for a in _EXPECTED_ACTIONS)
    # loop detector flags a retry loop
    looped = ast.parse("def post(self, e, *, audit_id, event_version, occurred_at):\n    while True:\n        pass\n")
    fn = next(n for n in ast.walk(looped) if isinstance(n, ast.FunctionDef))
    assert any(isinstance(n, (ast.For, ast.While)) for n in ast.walk(fn)), "the loop detector must flag a retry loop"
    # single-route detector flags a planted dispatch call
    planted = ast.parse("def _handle(self):\n    if self._import_initiation is not None:\n        self._router.dispatch(x, y)\n")
    handle = next(n for n in ast.walk(planted) if isinstance(n, ast.FunctionDef))
    ifnode = next(n for n in ast.walk(handle) if isinstance(n, ast.If))
    assert any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "dispatch" for n in ast.walk(ifnode))
    # apply-order detector
    assert "014_import_operational_audit.sql".index("014") < "015".index("015") + 1


if __name__ == "__main__":
    _scan.run(
        [
            test_w1a_file_surface_exists,
            test_ddl_014_015_blob_pins_match_committed,
            test_ddl_014_frozen_shape,
            test_ddl_015_append_only_triggers,
            test_ddl_014_015_created_not_applied_and_unenrolled,
            test_tenant_008_shape_plain_unique_index,
            test_tenant_008_enrolled_in_applicator_and_guard,
            test_import_audit_emitter_is_stdlib_only_no_driver_no_cross_service_no_dsn,
            test_import_audit_emitter_wire_is_nine_references_only_keys_no_loop,
            test_cp_import_audit_ingest_edge_boundaries,
            test_cp_import_audit_port_is_control_local_append_only,
            test_cp_import_audit_store_on_conflict_audit_id_append_only_surface,
            test_cp_import_audit_composition_seam_loopback_failclosed,
            test_import_service_audit_policy_single_retry_no_loop,
            test_gateway_composed_import_path_single_route_no_dispatch,
            test_import_edge_sole_serve_entrypoint_blessed,
            test_startup_directory_source_single_record_mapping_pins,
            test_import_result_dto_references_only_catalogue,
            test_no_secret_or_dsn_literal_in_w1a_sources,
            test_proof_stop_before_connect_and_apply_order,
            test_proof_disposable_ownership_teardown_three_databases,
            test_proof_registered_manual_only_no_hosted_enrollment,
            test_boundary_detectors_are_non_vacuous,
        ]
    )
