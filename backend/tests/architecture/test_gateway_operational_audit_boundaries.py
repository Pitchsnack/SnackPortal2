"""Gateway Audit V1a — durable-persistence boundaries guard (architecture; no DB, no runtime).

Machine-pins the Gateway Operational Audit Persistence V1a execution decisions by text/AST inspection
of the committed sources — every detector carries a planted non-vacuity companion. Scope: the durable
persistence slice only (V1b operator retrieval is out of scope). Pins:

* DDL 012/013 blob equality to the reviewed pins; the frozen shape (id identity PK; UNIQUE audit_id;
  the five-value action CHECK; the FROZEN source_service='api_gateway' CHECK (DDL, separately governed); the event_version>0 CHECK;
  both append-only triggers; references-only — no JSON/hash-chain/FK); and 012/013 un-enrolled in the
  standing apply order (created-not-applied);
* the gateway durable emitter — stdlib urllib only, no DB driver, no cross-service import, no DSN
  literal, exact ten-key references-only wire, single transport attempt (the composition owns retry);
* the Control-Plane ingest edge — internal-only loopback path, POST-only, single-threaded, imports
  only control_plane.gateway_audit, forbidden-name + secret-shape defenses, no sibling service/DB driver;
* the CP store + port — CP-local record/port (no sibling-service import), one abstract
  write method, ON CONFLICT (audit_id), append-only adapter surface;
* the composition seams — the CP loopback-host allowlist + fail-closed; the gateway
  SP2_GW_AUDIT_SINK_BASE_URL selector with NO loopback default and ValueError-before-socket; the
  BoundedGatewayAuditPolicy bounded single retry;
* the gateway fail-closed edit — the success emit is wrapped and a terminal failure returns 503;
* the MANUAL_ONLY disposable proof — STOP-before-connect, exact 012→013 apply order, no wildcard,
  proof-owned disposable database with guaranteed teardown, references-only, and registration as a
  justified MANUAL_ONLY exception (hosted run-set count unchanged);
* no secret/DSN literal in any V1a source file;
* the D-43 Post-10C.3 CarrierMismatch corrective closure — no new action string, no DDL change,
  no migration; the five-event runtime wiring stays a strict subset of the frozen store vocabulary.

Pure stdlib; standalone-runnable:
  python tests/architecture/test_gateway_operational_audit_boundaries.py
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

_DDL_012 = _CONTROL / "012_gateway_operational_audit.sql"
_DDL_013 = _CONTROL / "013_gateway_operational_audit_append_only.sql"
# The durable emitter and its selection moved from the Gateway
# (api_gateway/adapters/providers/durable_audit_emitter.py + api_gateway/main.py, both deleted) into
# the SHARED public-boundary audit library, where both route-owning edges link it in-process. The
# WIRE, the store, the DDL and the action vocabulary are unchanged — only the emitter's home moved.
_EMITTER = _BACKEND / "shared" / "adapters" / "providers" / "edge_audit.py"
_GW_MAIN = _BACKEND / "shared" / "adapters" / "providers" / "edge_audit.py"
_KERNEL = _BACKEND / "shared" / "public_edge.py"
_CP_INGEST = _BACKEND / "control_plane" / "adapters" / "providers" / "http_gateway_audit_api.py"
_CP_STORE = _BACKEND / "control_plane" / "adapters" / "providers" / "postgres_store.py"
_CP_PORT = _BACKEND / "control_plane" / "gateway_audit.py"
_CP_MAIN = _BACKEND / "control_plane" / "main.py"
_PROOF = _BACKEND / "tests" / "control_plane" / "requires_pg" / "test_pg_gateway_audit_durable.py"
# The emitter selector now lives in EACH route-owning service's composition root (one shared
# implementation, two call sites) instead of the single Gateway root.
_SELECTOR_ROOTS = (_BACKEND / "database_router" / "main.py", _BACKEND / "control_plane" / "main.py")
_RUNBOOK = _REPO / "infrastructure" / "runbooks" / "gateway_operational_audit_live_proof.md"
_OPS = _BACKEND / "tests" / "control_plane" / "requires_pg" / "b5_standing_topology.py"
_COMPLETENESS_GUARD = _BACKEND / "tests" / "architecture" / "test_live_pg_workflow_runset_completeness.py"

# The reviewed LF-normalized git-blob SHA-1 pins for the created-not-applied Gateway-audit DDL.
_REVIEWED_012_BLOB = "d2c70bab2a1c00d836b428d0c04a3bf61f4df1ae"
_REVIEWED_013_BLOB = "4377ec309cc7640cf36b35491c63168ef05d60f4"

# The five frozen AuditAction string values (IC-010 §J); V1a wires only the success action.
_EXPECTED_ACTIONS = ("CarrierMismatch", "CarrierOnControlAnomaly", "RouteDenied", "IsolationAnomaly", "workspace_memberships_read")
_EXPECTED_CHECKS = (
    "control_gateway_audit_action_check",
    "control_gateway_audit_event_version_check",
    "control_gateway_audit_source_service_check",
)
_EXPECTED_TRIGGERS = ("control_gateway_audit_no_mutation", "control_gateway_audit_no_truncate")
_PROOF_RELPATH = "tests/control_plane/requires_pg/test_pg_gateway_audit_durable.py"


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
    spec = importlib.util.spec_from_file_location("b5_standing_topology_gwa_pin", _OPS)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- 1. file surface + DDL blob/shape/enrollment ---------------------------------------------------
def test_v1a_file_surface_exists() -> None:
    for path in (_DDL_012, _DDL_013, _EMITTER, _KERNEL, _CP_INGEST, _CP_STORE, _CP_PORT, _CP_MAIN, _PROOF, _RUNBOOK, *_SELECTOR_ROOTS):
        assert path.is_file(), f"V1a surface file missing: {path}"


def test_ddl_blob_pins_match_committed() -> None:
    assert _git_blob_sha1(_DDL_012) == _REVIEWED_012_BLOB, "012 blob drifted from the reviewed pin"
    assert _git_blob_sha1(_DDL_013) == _REVIEWED_013_BLOB, "013 blob drifted from the reviewed pin"
    # Cross-checked in the default suite by the blob-drift guard (single source of truth = the bytes).
    blob_guard = _text(_BACKEND / "tests" / "architecture" / "test_b7c1_control_audit_ddl_blob_pins.py")
    assert "_PIN_012" in blob_guard and "_PIN_013" in blob_guard, "the blob-drift guard must also pin 012/013"
    assert _PROOF_RELPATH.split("/")[-1] in blob_guard, "the blob-drift guard must cross-check the proof harness pins"


def test_ddl_012_frozen_shape() -> None:
    ddl = _text(_DDL_012)
    assert "CREATE TABLE IF NOT EXISTS control_gateway_audit" in ddl
    assert "id             bigint       GENERATED ALWAYS AS IDENTITY PRIMARY KEY" in ddl, "id must be the identity ordering-authority PK"
    assert "audit_id       text         NOT NULL UNIQUE" in ddl, "audit_id must be the UNIQUE idempotency key"
    for action in _EXPECTED_ACTIONS:
        assert f"'{action}'" in ddl, f"the action CHECK must pin {action}"
    assert "CHECK (source_service = 'api_gateway')" in ddl, "the source_service CHECK must pin the producer constant"
    assert "CHECK (event_version > 0)" in ddl, "the event_version CHECK must pin positivity"
    # Scan the CREATE TABLE BODY only, with BOTH full-line and inline `--` comments stripped (comment
    # prose legitimately says "NO JSON / hash-chain / secret"; no `--` appears inside a DDL string literal):
    body = "\n".join(line.split("--")[0] for line in ddl.splitlines()).lower()
    for banned in ("jsonb", " json", "references ", "foreign key", "hash_chain"):
        assert banned not in body, f"references-only DDL body must carry no {banned!r} column/constraint (no JSON/FK/hash-chain)"


def test_ddl_013_append_only_triggers() -> None:
    ddl = _text(_DDL_013)
    assert "CREATE OR REPLACE FUNCTION control_gateway_audit_append_only()" in ddl
    for trigger in _EXPECTED_TRIGGERS:
        assert f"CREATE TRIGGER {trigger}" in ddl, f"the append-only trigger {trigger} must exist"
    assert "BEFORE UPDATE OR DELETE" in ddl and "BEFORE TRUNCATE" in ddl, "UPDATE/DELETE and TRUNCATE must both be rejected"


def test_ddl_012_013_created_not_applied_and_unenrolled() -> None:
    on_disk = {p.name for p in _CONTROL.glob("*.sql")}
    assert {"012_gateway_operational_audit.sql", "013_gateway_operational_audit_append_only.sql"} <= on_disk, (
        "012/013 must be present on disk"
    )
    module = _load_ops_module()
    for name in ("012_gateway_operational_audit.sql", "013_gateway_operational_audit_append_only.sql"):
        assert name not in module._CONTROL_DDL_ORDER, f"{name} is created-not-applied and must NOT be enrolled in the standing apply order"


_NOT_ENROLLED_SENTENCE = "-- It is deliberately NOT enrolled in the B5-4 standing-topology apply order."


def test_ddl_012_013_headers_state_a_window_invariant_posture() -> None:
    """The header posture must be true in EVERY window, and the NOT-enrolled rule must survive verbatim.

    Both files once opened their posture paragraph with "Created, NOT applied". That was true when it
    was written and is false now: 012/013 have since been applied to the retained LOCAL standing
    Control database by a separately governed, Dan-authorized run, and the table carries pre-existing
    rows. A header sentence that flips truth value as standing state moves is worse than no sentence —
    an operator reads it as current. The Gate-A correction restates the posture as *which apply acts
    are sanctioned*, which does not flip.

    What must NOT move: the enrollment rule. It is the load-bearing half, it is asserted structurally
    just above against `_CONTROL_DDL_ORDER`, and it is quoted verbatim across four other guards.
    """
    for ddl in (_DDL_012, _DDL_013):
        text = _text(ddl)
        header = []
        for line in text.splitlines():
            if not line.startswith("--"):
                break
            header.append(line)
        assert header, f"{ddl.name} must open with a contiguous leading comment block"
        assert "" not in [line.strip() for line in header], f"{ddl.name}: the header block must carry no interior blank line"
        joined = "\n".join(header)
        assert _NOT_ENROLLED_SENTENCE in joined, f"{ddl.name} must keep the enrollment rule verbatim: {_NOT_ENROLLED_SENTENCE!r}"
        assert "TRUE IN EVERY WINDOW" in joined, (
            f"{ddl.name}: the application-posture paragraph must declare that it is stated window-invariantly, so a future "
            "editor is told the constraint rather than discovering it"
        )
        # The bare claim, as a sentence opener, is what falsifies. It may only appear as the explicitly
        # quoted historical reference the correction added.
        for line in header:
            if "Created, NOT applied" in line:
                assert '"Created, NOT applied"' in line, (
                    f'{ddl.name}: "Created, NOT applied" may appear only as a quoted historical reference, never as a '
                    "current-state claim — 012/013 ARE applied to the retained local standing Control database"
                )


# --- 2. gateway durable emitter --------------------------------------------------------------------
def test_emitter_is_stdlib_only_no_driver_no_cross_service_no_dsn() -> None:
    tops = _import_tops(_EMITTER)
    assert tops <= {"__future__", "abc", "json", "urllib", "typing", "shared"}, (
        f"emitter imports outside the stdlib/shared surface: {sorted(tops)}"
    )
    for banned in ("psycopg", "psycopg2", "asyncpg", "sqlalchemy", "control_plane", "database_router", "auth_router", "threading"):
        assert banned not in tops, f"the emitter must not import {banned}"
    lowered = _text(_EMITTER).lower()
    for needle in ("dsn", "postgresql://", "postgres://", "password", "connect("):
        assert needle not in lowered, f"the emitter must not reference {needle} (no DB driver / descriptor)"


def test_emitter_wire_is_ten_references_only_keys_single_attempt() -> None:
    tree = _tree(_EMITTER)
    # The wire builder returns exactly the eleven references-only keys (D-42 CLM adds
    # record_ref — the tenant-resident record reference on the tenant Startup success
    # events; still a reference only, never field content).
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
        "subject_ref",
        "tenant_ref",
        "carrier_ref",
        "record_ref",
    }, f"the wire event must carry exactly the eleven references-only keys: {keys}"
    assert "source_service" not in (keys or set()), "source_service is a store-side constant — never a wire key"
    # Single transport attempt: the emitter contains no retry loop (the policy owns the single retry).
    emit_fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "emit")
    assert not any(isinstance(n, (ast.For, ast.While)) for n in ast.walk(emit_fn)), "the emitter's emit() must contain no retry loop"


# --- 3. Control-Plane ingest edge ------------------------------------------------------------------
def test_cp_ingest_edge_boundaries() -> None:
    text = _text(_CP_INGEST)
    tops = _import_tops(_CP_INGEST)
    assert tops <= {"__future__", "json", "typing", "fastapi", "control_plane", "shared"}, (
        f"ingest imports outside the adapter surface: {sorted(tops)}"
    )
    for sibling in ("database_router", "auth_router", "import_service", "lineage_service"):
        assert sibling not in tops, f"the ingest edge must not import {sibling} (DAG independence)"
    # FastAPI is the ONE sanctioned framework; the ASGI server and its socket stay in the shared runtime.
    for banned in ("psycopg", "psycopg2", "asyncpg", "sqlalchemy", "threading", "asyncio", "starlette", "uvicorn", "http"):
        assert banned not in tops, f"the ingest edge must not import {banned}"
    assert '"/internal/gateway-audit/events"' in text, "the internal-only ingest path must be pinned"
    assert '"127.0.0.1"' in text, "the ingest edge must default-bind the loopback host"
    for marker in ("HTTPServer", "ThreadingHTTPServer", "ThreadingMixIn"):
        assert marker not in text, f"the ingest edge must hand-roll no server ({marker}); the shared runtime owns it"
    assert "build_asgi_server" in text, "the ingest edge must serve through the shared ASGI runtime"
    # Fail-closed defenses present.
    assert "_FORBIDDEN_EVENT_KEYS" in text and "source_service" in text, "the forbidden-name denylist (incl. source_service) must exist"
    assert "_SECRET_SHAPES" in text, "the secret/token/DSN-shape defense must exist"
    assert '"workspace_memberships_read"' in text, "V1a must pin the success action"
    # POST-only: exactly one registered route decorator, and it is a POST (every other method is
    # refused 405 by the shared fail-closed app before the store is reached).
    served = _scan.registered_route_methods(_tree(_CP_INGEST))
    assert served == ["post"], f"the ingest edge must be POST-only: {served}"


# --- 4. CP store + port ----------------------------------------------------------------------------
def test_cp_port_is_control_local_append_only() -> None:
    tops = _import_tops(_CP_PORT)
    for banned in ("database_router", "auth_router", "psycopg"):
        assert banned not in tops, f"the CP operational-audit port must not import {banned}"
    text = _text(_CP_PORT)
    assert "def append_gateway_audit" in text, "the store port must expose append_gateway_audit"
    for verb in ("def list", "def get", "def read", "def query", "def export", "def purge", "def update", "def delete"):
        assert verb not in text, f"the append-only store port must expose no {verb!r}"


def test_cp_store_on_conflict_audit_id_append_only_surface() -> None:
    text = _text(_CP_STORE)
    assert "ON CONFLICT (audit_id) DO NOTHING RETURNING id" in text, "the store must idempotently upsert on audit_id"
    assert "class PostgresGatewayAuditStore" in text
    # No UPDATE/DELETE against the gateway-audit table in the adapter (append-only).
    assert "UPDATE control_gateway_audit" not in text and "DELETE FROM control_gateway_audit" not in text


# --- 5. composition seams --------------------------------------------------------------------------
def test_cp_composition_seam_loopback_failclosed() -> None:
    text = _text(_CP_MAIN)
    assert "def build_gateway_audit_server_from_env" in text
    assert "SP2_CP_GATEWAY_AUDIT_HOST" in text and "SP2_CP_GATEWAY_AUDIT_PORT" in text
    assert "_GATEWAY_AUDIT_LOOPBACK_HOSTS" in text and '"127.0.0.1"' in text, "the ingest edge must be loopback-only (fail closed)"


def test_edge_audit_selector_no_loopback_default_single_retry() -> None:
    # The selector lives in EACH route-owning composition root now (one shared implementation, two
    # call sites) instead of the single Gateway root. Both must select it fail-closed, and NEITHER
    # may carry a loopback default — a default would silently activate a durable transport.
    for root in _SELECTOR_ROOTS:
        root_text = _text(root)
        assert "SP2_EDGE_AUDIT_SINK_BASE_URL" in root_text, f"{root.name} must pin the durable audit-sink selector"
        assert "def build_public_boundary_from_env" in root_text, f"{root.name} must own the boundary composition seam"
        assert "loopback default" in root_text.lower(), f"{root.name} must document that the audit-sink selector has no loopback default"
        for host in ("127.0.0.1", "localhost"):
            assert f'SP2_EDGE_AUDIT_SINK_BASE_URL = "http://{host}' not in root_text, (
                f"{root.name} must not default the audit sink to a loopback URL"
            )
    text = _text(_GW_MAIN)
    assert "class BoundedEdgeAuditPolicy" in text
    # The policy performs exactly one retry: a single follow-up inner.emit after the retryable branch,
    # and no loop.
    policy = next(n for n in ast.walk(_tree(_GW_MAIN)) if isinstance(n, ast.ClassDef) and n.name == "BoundedEdgeAuditPolicy")
    emit_fn = next(n for n in ast.walk(policy) if isinstance(n, ast.FunctionDef) and n.name == "emit")
    assert not any(isinstance(n, (ast.For, ast.While)) for n in ast.walk(emit_fn)), (
        "the policy must not use a retry LOOP (bounded single retry only)"
    )
    inner_emits = [n for n in ast.walk(emit_fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "emit"]
    assert len(inner_emits) == 2, "the policy must call the inner emit at most twice (initial + exactly one retry)"


def test_edge_success_emit_is_fail_closed() -> None:
    """Audit-before-hand-back, migrated from the Gateway core to the shared boundary kernel.

    The Gateway wrapped its own success emit in a try/except returning 503. The kernel now owns
    that behaviour for BOTH edges: ``PublicBoundary.emit`` converts a terminal audit-transport
    failure into ``unavailable()``, which the edges map to a typed 503 with an empty body. One
    implementation instead of one per consumer, and no edge can opt out of it.
    """
    text = _text(_KERNEL)
    assert "ACTION_WORKSPACE_MEMBERSHIPS_READ" in text, "the workspace success class must exist in the kernel vocabulary"
    assert "def unavailable" in text, "the kernel must own the fail-closed unavailable() denial"
    # The kernel declares TWO `emit` functions: the abstract port method and PublicBoundary's.
    # Walk into the CLASS first — `next(...)` over the module would pick the abstract one and the
    # check would pass vacuously on a body that is `...`.
    boundary_cls = next(n for n in ast.walk(_tree(_KERNEL)) if isinstance(n, ast.ClassDef) and n.name == "PublicBoundary")
    emit_fn = next(n for n in ast.walk(boundary_cls) if isinstance(n, ast.FunctionDef) and n.name == "emit")
    assert len(emit_fn.body) > 1, "the detector must be looking at a real implementation, not an abstract stub"
    wrapped = False
    for node in ast.walk(emit_fn):
        if isinstance(node, ast.Try):
            raises_unavailable = "unavailable" in ast.dump(ast.Module(body=node.handlers, type_ignores=[]))
            if raises_unavailable:
                wrapped = True
    assert wrapped, "PublicBoundary.emit must convert a terminal audit failure into the fail-closed denial"
    # Both edges must map that denial to a 503 with an empty body — never serve the success anyway.
    for edge in (
        _BACKEND / "database_router" / "adapters" / "providers" / "http_public_startup_edge.py",
        _BACKEND / "control_plane" / "adapters" / "providers" / "http_public_workspace_edge.py",
    ):
        edge_text = _text(edge)
        assert "PublicBoundaryDenied" in edge_text, f"{edge.name} must map the kernel denial, not swallow it"
        assert "empty_response" in edge_text, f"{edge.name} must answer a denial with an EMPTY body"


# --- 6. MANUAL_ONLY disposable proof ---------------------------------------------------------------
def test_proof_stop_before_connect_and_apply_order() -> None:
    text = _text(_PROOF)
    assert "_verify_reviewed_blobs()" in text and "STOP before connect/apply" in text
    seg = text
    verify = seg.index("_verify_reviewed_blobs()")
    assert verify < seg.index("PostgresControlStore("), "the blob STOP must precede every connection construction"
    assert verify < seg.index("_DDL_012.read_text"), "the blob STOP must precede any DDL apply"
    assert text.count("_DDL_012.read_text") == 1 and text.count("_DDL_013.read_text") == 1, "each DDL file is applied exactly once"
    assert text.index("_DDL_012.read_text") < text.index("_DDL_013.read_text"), "012 must be applied before 013"
    assert '_DDL_012 = _CONTROL / "012_gateway_operational_audit.sql"' in text, "012 must be addressed by its exact repo path"
    assert '_DDL_013 = _CONTROL / "013_gateway_operational_audit_append_only.sql"' in text, "013 must be addressed by its exact repo path"
    for banned in ("glob(", "rglob(", "listdir", "iterdir", "*.sql"):
        assert banned not in text, f"the proof must never wildcard/scan for DDL ({banned!r})"
    for copied in ("CREATE TABLE control_gateway_audit", "CREATE TRIGGER control_gateway_audit"):
        assert copied not in text, f"the proof must apply the repo files, never copied DDL bytes ({copied!r})"


def test_proof_disposable_ownership_teardown_and_references_control_dir() -> None:
    text = _text(_PROOF)
    assert '_PROOF_DB = "sp2_gateway_audit_v1a_proof"' in text, "the proof database name must be the pinned proof-owned constant"
    assert text.count('DROP DATABASE IF EXISTS "{_PROOF_DB}"') == 2, "leftover-drop at start AND finally-teardown must both exist"
    assert "the disposable proof database must be removed after the proof" in text, "the removal assertion must exist"
    assert "datname count for {_PROOF_DB} = " in text, "teardown must report the datname count"
    assert "os.environ" not in text, "the DSN reaches the proof only through _pg (SNACKPORTAL_TEST_DSN by name)"
    assert not re.search(r"postgresql://[^\"\s]", text), "no DSN literal may appear in the proof"
    for standing in ("sp2_b3a_control", "snackportal2_control_local", "sp2_tenant_b5_standing"):
        assert standing not in text, f"the proof must never name a standing target ({standing!r})"
    # References the canonical control DDL dir (the INV-C control-association the completeness meta-guard requires).
    assert '"infrastructure" / "db" / "control"' in text, "the proof must build the DDL path from the canonical control segments"
    assert "_REVIEWED_012_BLOB" in text and "_REVIEWED_013_BLOB" in text, "the proof must pin the reviewed 012/013 blobs"


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


# --- 7. no secret literal anywhere in the V1a sources ----------------------------------------------
def test_no_secret_or_dsn_literal_in_v1a_sources() -> None:
    # The CP ingest edge is EXCLUDED here: it legitimately defines the secret/token/DSN-shape DETECTION
    # markers (_SECRET_SHAPES) as a denylist (pinned by test_cp_ingest_edge_boundaries). Every other V1a
    # source must carry no actual secret/DSN literal.
    for path in (_EMITTER, _CP_PORT, _DDL_012, _DDL_013):
        text = _text(path)
        assert not re.search(r"postgresql://[^\s\"']", text), f"{path.name} must carry no DSN literal"
        for needle in ("password=", "eyJ", "-----BEGIN "):
            assert needle not in text, f"{path.name} must carry no secret literal ({needle!r})"


# --- 8. D-43 Post-10C.3 CarrierMismatch corrective closure -----------------------------------------
def _module_constants(tree: ast.Module) -> dict:
    """Module-level ``Name = <literal>`` assignments (string constants and ``frozenset({...})``)."""
    out: dict = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name, value = node.targets[0].id, node.value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                out[name] = value.value
            elif (
                isinstance(value, ast.Call)
                and isinstance(value.func, ast.Name)
                and value.func.id == "frozenset"
                and len(value.args) == 1
                and isinstance(value.args[0], ast.Set)
                and all(isinstance(e, ast.Constant) for e in value.args[0].elts)
            ):
                out[name] = frozenset(e.value for e in value.args[0].elts if isinstance(e, ast.Constant))
    return out


def test_post10c_carriermismatch_durable_wiring_stays_inside_frozen_vocabulary() -> None:
    # D-43 (Post-10C.3 corrective) closure guard: NO new action string, NO DDL change, NO
    # migration; the five-event runtime wiring is a STRICT subset of the existing store
    # vocabulary. Everything here is text/AST over committed sources — no runtime import.
    frozen_seven = {
        "CarrierMismatch",
        "CarrierOnControlAnomaly",
        "RouteDenied",
        "IsolationAnomaly",
        "workspace_memberships_read",
        "tenant_startup_read",
        "tenant_startup_update",
    }
    five_wired = {"workspace_memberships_read", "tenant_startup_read", "tenant_startup_update", "RouteDenied", "CarrierMismatch"}
    # (1) NO DDL change: both blobs still equal the SAME reviewed pins (the corrective touched no DDL).
    assert _git_blob_sha1(_DDL_012) == _REVIEWED_012_BLOB and _git_blob_sha1(_DDL_013) == _REVIEWED_013_BLOB
    # (2) NO migration: 012/013 remain the only gateway-audit DDL files (no new sibling was added).
    gateway_ddl = sorted(p.name for p in _CONTROL.glob("*gateway_operational_audit*.sql"))
    assert gateway_ddl == ["012_gateway_operational_audit.sql", "013_gateway_operational_audit_append_only.sql"]
    # (3) NO new action string — the DDL CHECK vocabulary is exactly the frozen seven...
    check = re.search(r"CHECK \(action IN \(([^)]+)\)\)", _text(_DDL_012), re.S)
    assert check is not None, "the action CHECK must exist in DDL 012"
    assert set(re.findall(r"'([A-Za-z_]+)'", check.group(1))) == frozen_seven, "the DDL action CHECK must stay the frozen seven"
    # ...and the runtime AuditAction enum + the CP store vocabulary carry the SAME seven values.
    kernel_tree = _tree(_KERNEL)
    enum_values: dict = {}
    for node in ast.walk(kernel_tree):
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id.startswith("ACTION_")
            and isinstance(node.value, ast.Constant)
        ):
            enum_values[node.targets[0].id] = node.value.value
    assert set(enum_values.values()) == frozen_seven, (
        "the shared kernel's ACTION_* vocabulary must stay the frozen seven (no new action string). "
        "The emitter moved from the Gateway to the route-owning edges; not one action string changed, "
        "which is what keeps DDL 012's frozen CHECK satisfied without a schema migration."
    )
    port_constants = None
    for node in _tree(_CP_PORT).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "EDGE_AUDIT_STORE_ACTIONS" for t in node.targets):
            port_constants = set(ast.literal_eval(node.value))
    assert port_constants == frozen_seven, "the CP store vocabulary must stay the frozen seven (no new action string)"
    # (4) the gateway durable partition wires EXACTLY the five events — a strict subset of the store vocabulary.
    durable_assign = next(
        n
        for n in _tree(_GW_MAIN).body
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "DURABLE_EDGE_AUDIT_ACTIONS" for t in n.targets)
    )
    # The durable partition names the kernel's ACTION_* constants, so resolve through the same
    # `enum_values` map the frozen-seven census built (Name nodes now, Attribute nodes before).
    referenced = {n.id for n in ast.walk(durable_assign.value) if isinstance(n, ast.Name)}
    durable_values = {enum_values[name] for name in referenced if name in enum_values}
    assert durable_values == five_wired, f"the durable partition must wire EXACTLY the five CLM events: {sorted(durable_values)}"
    assert durable_values < frozen_seven, "the five-event runtime wiring must stay a STRICT subset of the store vocabulary"
    # (5) the CP ingest edge wires the SAME five and keeps the two anomaly classes refused.
    ingest_consts = _module_constants(_tree(_CP_INGEST))
    wired = {ingest_consts["_V1A_ACTION"], ingest_consts["_CLM_DENIAL_ACTION"], ingest_consts["_CARRIER_MISMATCH_ACTION"]} | set(
        ingest_consts["_CLM_TENANT_SUCCESS_ACTIONS"]
    )
    assert wired == five_wired, f"the ingest wired set must be EXACTLY the five CLM events: {sorted(wired)}"
    wired_line = next(line for line in _text(_CP_INGEST).splitlines() if line.startswith("_WIRED_ACTIONS ="))
    for part in ("_V1A_ACTION", "_CLM_DENIAL_ACTION", "_CARRIER_MISMATCH_ACTION", "_CLM_TENANT_SUCCESS_ACTIONS"):
        assert part in wired_line, f"_WIRED_ACTIONS must be composed of the five wired constants ({part})"
    for unwired in ("CarrierOnControlAnomaly", "IsolationAnomaly"):
        assert unwired not in wired, f"{unwired} must stay refused at the ingest edge (no wider audit expansion)"


# --- non-vacuity companions ------------------------------------------------------------------------
def test_boundary_detectors_are_non_vacuous() -> None:
    # blob pin
    assert _git_blob_sha1(_DDL_012) != "0" * 40
    # action-set detector
    assert not all(f"'{a}'" in "action IN ('Route')" for a in _EXPECTED_ACTIONS), "action-set detector must flag a truncated CHECK"
    # emit-loop detector
    looped = ast.parse("def emit(self, e):\n    while True:\n        self._inner.emit(e)\n")
    fn = next(n for n in ast.walk(looped) if isinstance(n, ast.FunctionDef))
    assert any(isinstance(n, (ast.For, ast.While)) for n in ast.walk(fn)), "the loop detector must flag a retry loop"
    # apply-order detector
    assert "012_gateway_operational_audit.sql".index("012") < "013".index("013") + 1
    # un-enrolled detector (planted enrollment is detectable)
    planted = ("001_distinctness_ledger.sql", "012_gateway_operational_audit.sql")
    assert "012_gateway_operational_audit.sql" in planted, "a planted enrollment must be detectable"


if __name__ == "__main__":
    _scan.run(
        [
            test_v1a_file_surface_exists,
            test_ddl_blob_pins_match_committed,
            test_ddl_012_frozen_shape,
            test_ddl_013_append_only_triggers,
            test_ddl_012_013_created_not_applied_and_unenrolled,
            test_ddl_012_013_headers_state_a_window_invariant_posture,
            test_emitter_is_stdlib_only_no_driver_no_cross_service_no_dsn,
            test_emitter_wire_is_ten_references_only_keys_single_attempt,
            test_cp_ingest_edge_boundaries,
            test_cp_port_is_control_local_append_only,
            test_cp_store_on_conflict_audit_id_append_only_surface,
            test_cp_composition_seam_loopback_failclosed,
            test_edge_audit_selector_no_loopback_default_single_retry,
            test_edge_success_emit_is_fail_closed,
            test_proof_stop_before_connect_and_apply_order,
            test_proof_disposable_ownership_teardown_and_references_control_dir,
            test_proof_registered_manual_only_no_hosted_enrollment,
            test_no_secret_or_dsn_literal_in_v1a_sources,
            test_post10c_carriermismatch_durable_wiring_stays_inside_frozen_vocabulary,
            test_boundary_detectors_are_non_vacuous,
        ]
    )
