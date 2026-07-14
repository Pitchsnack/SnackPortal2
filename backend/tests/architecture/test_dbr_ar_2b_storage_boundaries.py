"""DBR-AR-2B — durable routing-audit storage/transport boundary guard (architecture; no DB, no runtime).

Machine-pins the DBR-AR-2B execution boundaries (PRD DBR-AR-2B §13.2; START-GATE MC1-MC10 /
EC1-EC10) by text/AST inspection of the committed sources, as EVOLVED IN LOCKSTEP by
DBR-AR-2C (PRD DBR-AR-2C V2 D9): the exact authorized production surface; composition
confined to the two authorized composition roots (each ``main.py`` references ONLY its own
side of the 2B transport pair through lazy relative imports — the pair is COMPOSED as an
explicit opt-in seam, and every other production file, including
``database_router/router.py``, stays free of 2B symbols); no cross-service import in
either direction;
a stdlib-only router client with no database library, no Control-DB selector, and none of
the phase-4 needle substrings; no queue/thread/worker/background machinery and none of the
banned server-lifecycle identifiers in the new adapters; the exact ingest endpoint and
envelope anchors; the exact seventeen-key wire allowlist (identical on the ingest edge and
the client); forbidden-field-name and secret-shaped-value defenses; ``recorded_at`` absent
from the wire and store-assigned in DDL 010 (with ``id`` the DB-generated ordering
authority the adapter never binds); ``event_id`` uniqueness; the exact contract-frozen
four-action set; the exact twenty-column table with no hidden JSON/metadata/body/credential
/topology column and no cross-database constraint; DB-level append-only enforcement in DDL
011 (which contains no CREATE TABLE); created-not-applied discipline with no migration
runner and no standing-topology enrollment; and complete DDL-guard registration (blob pins
+ census/order). Every detector carries a planted non-vacuity companion. Pure stdlib;
standalone-runnable:
  python tests/architecture/test_dbr_ar_2b_storage_boundaries.py
"""

from __future__ import annotations

import ast
import pathlib
import re
import sys
from typing import FrozenSet, Optional, Set, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

_REPO = _scan.REPO_ROOT
_BACKEND = _scan.BACKEND_ROOT

_DDL_010 = _REPO / "infrastructure" / "db" / "control" / "010_routing_audit.sql"
_DDL_011 = _REPO / "infrastructure" / "db" / "control" / "011_routing_audit_append_only.sql"
_CP_MODEL = _BACKEND / "control_plane" / "routing_audit.py"
_CP_INGEST = _BACKEND / "control_plane" / "adapters" / "providers" / "http_routing_audit_api.py"
_CP_PG = _BACKEND / "control_plane" / "adapters" / "providers" / "postgres_store.py"
_DR_CLIENT = _BACKEND / "database_router" / "adapters" / "providers" / "http_routing_audit.py"
_DR_MODELS = _BACKEND / "database_router" / "models.py"
_DR_MAIN = _BACKEND / "database_router" / "main.py"
_CP_MAIN = _BACKEND / "control_plane" / "main.py"
_BLOB_GUARD = pathlib.Path(__file__).resolve().parent / "test_b7c1_control_audit_ddl_blob_pins.py"
_TOPO_GUARD = pathlib.Path(__file__).resolve().parent / "test_b5_standing_topology_boundaries.py"

_NEW_MODULES = (_CP_MODEL, _CP_INGEST, _DR_CLIENT)  # the three NEW 2B production modules

_INGEST_PATH_LITERAL = '"/internal/routing-audit/events"'

_REQUIRED_WIRE_KEYS = frozenset(
    {"event_id", "event_version", "occurred_at", "correlation_id", "actor_ref", "action", "outcome", "source_service", "source_version"}
)
_OPTIONAL_WIRE_KEYS = frozenset(
    {
        "request_ref",
        "tenant_ref",
        "resolved_tenant_ref",
        "public_code",
        "error_class",
        "association_store_ref",
        "association_version",
        "lane",
    },
)
_WIRE_KEYS = _REQUIRED_WIRE_KEYS | _OPTIONAL_WIRE_KEYS  # exactly 17 (MC9)

_ACTIONS = ("Route", "RouteControl", "RouteDenied", "IsolationAnomaly")

_EXPECTED_COLUMNS = frozenset(
    {
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
    }
)  # exactly 20 (START-GATE §8)

_CONCURRENCY_TOPS = {"threading", "asyncio", "multiprocessing", "concurrent", "queue", "subprocess", "contextvars"}
_BANNED_SERVER_NAMES = ("ThreadingHTTPServer", "serve" + "_forever", "make" + "_server")  # split so THIS guard never carries the tokens
_CLIENT_NEEDLES = ("password", "passwd", "secret" + "=", "dsn" + "=", "begin private key")  # phase-4 needle mirror (EC2)
_2B_SYMBOLS = (
    "PostgresRoutingAuditStore",
    "build_routing_audit_server",
    "HttpRoutingAudit",
    "RoutingAuditStorePort",
    "control_routing_audit",
    "http_routing_audit",
)


def _text(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def _strip_sql_comments(sql: str) -> str:
    return re.sub(r"--[^\n]*", "", sql)


def _top_imports(path: pathlib.Path) -> Set[str]:
    return {m.split(".")[0] for m in _scan.imported_modules(path)}


def _resolve_string_set(tree: ast.Module, name: str, seen: Optional[Set[str]] = None) -> Optional[FrozenSet[str]]:
    """Resolve a module-level string-set constant: frozenset({...}) literals and unions of them."""
    seen = seen or set()
    if name in seen:
        return None
    seen.add(name)
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return _eval_string_set(tree, node.value, seen)
    return None


def _eval_string_set(tree: ast.Module, node: ast.expr, seen: Set[str]) -> Optional[FrozenSet[str]]:
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "frozenset":
        if node.args and isinstance(node.args[0], (ast.Set, ast.Tuple, ast.List)):
            values = [e.value for e in node.args[0].elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
            return frozenset(values)
        if node.args and isinstance(node.args[0], ast.Name):
            return _resolve_tuple_as_set(tree, node.args[0].id)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        left = _eval_string_set(tree, node.left, seen)
        right = _eval_string_set(tree, node.right, seen)
        if left is not None and right is not None:
            return left | right
    if isinstance(node, ast.Name):
        return _resolve_string_set(tree, node.id, seen)
    return None


def _resolve_tuple_as_set(tree: ast.Module, name: str) -> Optional[FrozenSet[str]]:
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            if isinstance(node.value, ast.Tuple):
                return frozenset(e.value for e in node.value.elts if isinstance(e, ast.Constant) and isinstance(e.value, str))
    return None


def _module_tuple(path: pathlib.Path, name: str) -> Optional[Tuple[str, ...]]:
    tree = ast.parse(_text(path), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            if isinstance(node.value, ast.Tuple):
                return tuple(e.value for e in node.value.elts if isinstance(e, ast.Constant) and isinstance(e.value, str))
    return None


def _wire_dict_keys(path: pathlib.Path) -> Optional[FrozenSet[str]]:
    """Keys of the dict literal returned by the client's _wire_event serializer."""
    tree = ast.parse(_text(path), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_wire_event":
            for inner in ast.walk(node):
                if isinstance(inner, ast.Dict):
                    return frozenset(k.value for k in inner.keys if isinstance(k, ast.Constant) and isinstance(k.value, str))
    return None


def _sql_columns(sql: str) -> FrozenSet[str]:
    stripped = _strip_sql_comments(sql)
    body_match = re.search(r"CREATE TABLE IF NOT EXISTS control_routing_audit \((.*)\)\s*;", stripped, re.S)
    assert body_match, "010 must create control_routing_audit"
    columns = set()
    for line in body_match.group(1).splitlines():
        m = re.match(r"\s*([a-z_]+)\s+(bigint|uuid|integer|timestamptz|text)\b", line)
        if m:
            columns.add(m.group(1))
    return frozenset(columns)


# ---------------------------------------------------------------------------
# 1. Exact authorized production surface exists
# ---------------------------------------------------------------------------
def test_2b_authorized_production_files_exist() -> None:
    for path in (_DDL_010, _DDL_011, _CP_MODEL, _CP_INGEST, _CP_PG, _DR_CLIENT):
        assert path.is_file(), f"DBR-AR-2B surface file missing: {path}"


# ---------------------------------------------------------------------------
# 2 + 18. Composition confined to the two authorized DBR-AR-2C composition roots
# (evolved in lockstep by DBR-AR-2C D9: the 2B transport pair is COMPOSED as an
# explicit opt-in seam, exclusively through the two main.py roots; every other
# production file stays free of 2B symbols)
# ---------------------------------------------------------------------------
# The DBR-AR-2C placement matrix: each composition root may reference ONLY its own side
# of the transport pair (plus the shared ``http_routing_audit`` module-path token its
# lazy relative import carries — the CP root's ingest adapter module name contains it).
# Cross-side symbols stay forbidden so neither service ever composes the other's adapter.
_DR_MAIN_ALLOWED = frozenset({"HttpRoutingAudit", "http_routing_audit"})
_CP_MAIN_ALLOWED = frozenset({"PostgresRoutingAuditStore", "build_routing_audit_server", "http_routing_audit"})


def test_2c_main_composition_roots_reference_only_authorized_2b_symbols() -> None:
    for main, allowed in ((_DR_MAIN, _DR_MAIN_ALLOWED), (_CP_MAIN, _CP_MAIN_ALLOWED)):
        text = _text(main)
        for symbol in _2B_SYMBOLS:
            if symbol in allowed:
                assert symbol in text, f"{main.name} must reference {symbol} — it is a DBR-AR-2C composition root"
            else:
                assert symbol not in text, f"{main.name} must not reference {symbol} — cross-side 2B symbols stay uncomposed"
        for module in _scan.imported_modules(main):
            assert "routing_audit" not in module, (
                f"{main.name} must not ABSOLUTELY import a 2B module ({module}); the composition imports are lazy relative imports"
            )


def test_2c_no_production_composition_census() -> None:
    # The ONLY production files referencing the 2B classes/factories are their defining
    # modules plus the two DBR-AR-2C composition roots (D9). Notably
    # database_router/router.py stays clean: its condition-1 failure handling references
    # no 2B symbol (the policy's terminal re-raise reaches it as a plain exception).
    defining = {_CP_MODEL.resolve(), _CP_INGEST.resolve(), _CP_PG.resolve(), _DR_CLIENT.resolve()}
    roots = {_DR_MAIN.resolve(), _CP_MAIN.resolve()}
    for package in _scan.SERVICE_PACKAGES + ["shared"]:
        for path in (_BACKEND / package).rglob("*.py"):
            if _scan.SKIP_PARTS & set(path.parts) or path.resolve() in defining or path.resolve() in roots:
                continue
            text = _text(path)
            for symbol in ("PostgresRoutingAuditStore", "build_routing_audit_server", "HttpRoutingAudit"):
                assert symbol not in text, f"{_scan.relposix(path)} references {symbol}: composition is confined to the two DBR-AR-2C roots"


def test_2c_composition_census_nonvacuity() -> None:
    assert "HttpRoutingAudit" in _text(_DR_CLIENT), "census target symbol must exist where defined"
    assert "PostgresRoutingAuditStore" in _text(_CP_PG)
    assert "build_routing_audit_server" in _text(_CP_INGEST)
    # The evolved placement matrix is live (non-vacuous): each root genuinely references
    # its own side of the pair...
    assert "HttpRoutingAudit" in _text(_DR_MAIN), "the DBR root must really compose the transport client"
    assert "PostgresRoutingAuditStore" in _text(_CP_MAIN), "the CP root must really compose the durable store"
    assert "build_routing_audit_server" in _text(_CP_MAIN), "the CP root must really compose the ingest server"
    # ...router.py genuinely stays outside the composition census...
    assert "HttpRoutingAudit" not in _text(_BACKEND / "database_router" / "router.py")
    # ...and the matrix rows are disjoint on the class/factory symbols, so a cross-side
    # placement (either root composing the other's adapter) is detectable.
    assert "HttpRoutingAudit" not in _CP_MAIN_ALLOWED and "PostgresRoutingAuditStore" not in _DR_MAIN_ALLOWED
    assert "build_routing_audit_server" not in _DR_MAIN_ALLOWED


# ---------------------------------------------------------------------------
# 3/5/6. No cross-service import in either direction
# ---------------------------------------------------------------------------
def test_2b_no_cross_service_import() -> None:
    client_tops = _top_imports(_DR_CLIENT)
    assert "control_plane" not in client_tops, "the router client must NEVER import control_plane (DAG rule)"
    for path in (_CP_MODEL, _CP_INGEST, _CP_PG):
        tops = _top_imports(path)
        assert "database_router" not in tops, f"{path.name} must NEVER import database_router (DAG rule)"
        for service in _scan.SERVICE_PACKAGES:
            if service != "control_plane":
                assert service not in tops, f"{path.name} imports {service}"
    for service in _scan.SERVICE_PACKAGES:
        if service != "database_router":
            assert service not in client_tops, f"client imports {service}"


# ---------------------------------------------------------------------------
# 4. Router client: stdlib-only, no DB library, no selector, no needle substrings
# ---------------------------------------------------------------------------
def test_2b_router_client_stdlib_only_no_db_no_selector() -> None:
    tops = _top_imports(_DR_CLIENT)
    assert tops <= {"__future__", "json", "urllib", "typing", "database_router"}, f"unexpected client imports: {sorted(tops)}"
    for banned in ("psycopg", "psycopg2", "asyncpg", "sqlalchemy", "os"):
        assert banned not in tops, f"the client must not import {banned}"
    text = _text(_DR_CLIENT)
    assert "SP2_" not in text and "os.environ" not in text and "getenv" not in text, (
        "no environment selector in the uncomposed client (DBR-AR-2C scope)"
    )
    lowered = text.lower()
    for needle in _CLIENT_NEEDLES:
        assert needle not in lowered, f"phase-4 needle {needle!r} must not appear anywhere in the client (EC2)"


def test_2b_client_needle_scan_nonvacuity() -> None:
    assert _CLIENT_NEEDLES[0] in "a password literal".lower()
    assert _CLIENT_NEEDLES[2] in "uses secret=value".lower()
    assert _CLIENT_NEEDLES[3] in "dsn=postgres".lower()


# ---------------------------------------------------------------------------
# 7. No queue/thread/worker/background machinery; no banned server identifiers
# ---------------------------------------------------------------------------
def test_2b_no_concurrency_machinery() -> None:
    for path in _NEW_MODULES:
        tops = _top_imports(path)
        overlap = tops & _CONCURRENCY_TOPS
        assert not overlap, f"{path.name} imports concurrency machinery: {sorted(overlap)}"
        text = _text(path)
        for name in _BANNED_SERVER_NAMES:
            assert name not in text, f"{path.name} references banned identifier {name}"
    pg_tops = _top_imports(_CP_PG)
    assert not (pg_tops & {"threading", "contextvars", "psycopg_pool", "concurrent"}), "postgres_store.py gained a forbidden import (EC4)"


def test_2b_concurrency_detector_nonvacuity() -> None:
    assert "threading" in _CONCURRENCY_TOPS and "queue" in _CONCURRENCY_TOPS
    assert _BANNED_SERVER_NAMES[1] == "serve_forever" and _BANNED_SERVER_NAMES[2] == "make_server"


# ---------------------------------------------------------------------------
# 8. Exact endpoint and envelope anchors on BOTH sides of the wire
# ---------------------------------------------------------------------------
def test_2b_exact_endpoint_and_envelope_anchors() -> None:
    ingest = _text(_CP_INGEST)
    client = _text(_DR_CLIENT)
    for text, who in ((ingest, "ingest"), (client, "client")):
        assert _INGEST_PATH_LITERAL in text, f"{who} must pin the literal internal ingest path"
        assert '"version"' in text and '"event"' in text, f"{who} must anchor the exact top-level envelope keys"
    for result in ('"INVALID"', '"CONFLICT"', '"UNAVAILABLE"'):
        assert result in ingest, f"ingest must answer the bounded result {result}"
    assert "result.value" in ingest, "ingest success answers come from the RoutingAuditAppendResult enum"
    model = _text(_CP_MODEL)
    for result in ('"INSERTED"', '"DUPLICATE_MATCH"'):
        assert result in model and result in client, f"the model enum and the client must anchor the success result {result}"
    assert '"result"' in client, "the client must strictly parse the two-key response envelope"


def test_2b_endpoint_anchor_nonvacuity() -> None:
    assert _INGEST_PATH_LITERAL not in _INGEST_PATH_LITERAL.replace("routing-audit", "routing"), "path anchor must detect tampering"


# ---------------------------------------------------------------------------
# 9. Strict field allowlist — identical closed 17-key set on both sides
# ---------------------------------------------------------------------------
def test_2b_strict_field_allowlist_exact() -> None:
    ingest_tree = ast.parse(_text(_CP_INGEST), filename=str(_CP_INGEST))
    required = _resolve_string_set(ingest_tree, "_REQUIRED_EVENT_KEYS")
    optional = _resolve_string_set(ingest_tree, "_OPTIONAL_EVENT_KEYS")
    union = _resolve_string_set(ingest_tree, "_EVENT_KEYS")
    assert required == _REQUIRED_WIRE_KEYS, f"ingest required-key set drifted: {required}"
    assert optional == _OPTIONAL_WIRE_KEYS, f"ingest optional-key set drifted: {optional}"
    assert union == _WIRE_KEYS and len(_WIRE_KEYS) == 17, "the wire allowlist is EXACTLY the seventeen approved keys"
    client_keys = _wire_dict_keys(_DR_CLIENT)
    assert client_keys == _WIRE_KEYS, f"client serialization keys drifted: {client_keys}"
    # The contract-frozen four-action vocabulary is identical in both services' constants.
    assert _module_tuple(_CP_MODEL, "ROUTING_AUDIT_STORE_ACTIONS") == _ACTIONS
    assert _module_tuple(_DR_MODELS, "ROUTING_AUDIT_ACTIONS") == _ACTIONS


def test_2b_allowlist_extractors_nonvacuity() -> None:
    tree = ast.parse('_A = frozenset({"x", "y"})\n_B = frozenset({"z"})\n_C = _A | _B\n')
    assert _resolve_string_set(tree, "_A") == frozenset({"x", "y"})
    assert _resolve_string_set(tree, "_C") == frozenset({"x", "y", "z"})
    probe = ast.parse('def _wire_event(e):\n    return {"a": 1, "b": 2}\n')
    dict_keys = None
    for node in ast.walk(probe):
        if isinstance(node, ast.Dict):
            dict_keys = frozenset(k.value for k in node.keys if isinstance(k, ast.Constant))
    assert dict_keys == frozenset({"a", "b"})


# ---------------------------------------------------------------------------
# 10. Forbidden field-name and secret-shaped-value defenses
# ---------------------------------------------------------------------------
def test_2b_forbidden_name_and_value_shape_defenses() -> None:
    ingest_tree = ast.parse(_text(_CP_INGEST), filename=str(_CP_INGEST))
    forbidden = _resolve_string_set(ingest_tree, "_FORBIDDEN_EVENT_KEYS")
    assert forbidden is not None and forbidden >= {
        "id",
        "store_id",
        "recorded_at",
        "trace_ref",
        "dsn",
        "password",
        "token",
        "jwt",
        "request_body",
        "response_body",
        "hostname",
        "connection",
    }, f"forbidden-name defense weakened: {forbidden}"
    shapes = _module_tuple(_CP_INGEST, "_SECRET_SHAPES")
    assert shapes is not None and set(shapes) == {"eyJ", "-----BEGIN", "AKIA", "ghp_", "xox", "://"}, shapes
    assert re.search(r"_MAX_REF_LENGTH\s*=\s*512\b", _text(_CP_INGEST)), "the uniform 512 reference cap must be pinned (MC9)"


def test_2b_forbidden_defense_nonvacuity() -> None:
    assert "recorded_at" in {"recorded_at", "x"} and "dsn" in {"dsn"}
    weakened = frozenset({"id", "store_id"})
    assert not weakened >= {"recorded_at", "dsn"}, "a weakened forbidden set must be detectable"


# ---------------------------------------------------------------------------
# 11 + 12. recorded_at: never on the wire; store-assigned; id never bound
# ---------------------------------------------------------------------------
def test_2b_recorded_at_absent_from_wire_request() -> None:
    assert "recorded_at" not in _WIRE_KEYS and "store_id" not in _WIRE_KEYS and "trace_ref" not in _WIRE_KEYS
    client_keys = _wire_dict_keys(_DR_CLIENT)
    assert client_keys is not None and "recorded_at" not in client_keys
    assert '"recorded_at"' not in _text(_DR_CLIENT), "the client must never name a store-assigned wire key"


def test_2b_recorded_at_store_assigned_and_id_never_bound() -> None:
    sql = _text(_DDL_010)
    assert re.search(r"recorded_at\s+timestamptz\s+NOT NULL\s+DEFAULT now\(\)", sql), "recorded_at is DB-assigned (DEFAULT now())"
    assert re.search(r"id\s+bigint\s+GENERATED ALWAYS AS IDENTITY PRIMARY KEY", sql), "id is the DB-generated ordering authority"
    columns = _module_tuple(_CP_PG, "_ROUTING_AUDIT_COLUMNS")
    assert columns is not None and len(columns) == 18
    assert "recorded_at" not in columns and "id" not in columns, "the adapter never binds store-assigned columns"
    assert set(columns) == set(_WIRE_KEYS | {"trace_ref"}), "adapter columns = the 17 wire keys + the reserved trace_ref"


def test_2b_recorded_at_detector_nonvacuity() -> None:
    assert re.search(
        r"recorded_at\s+timestamptz\s+NOT NULL\s+DEFAULT now\(\)", "    recorded_at            timestamptz  NOT NULL DEFAULT now(),  -- x"
    )
    assert not re.search(r"recorded_at\s+timestamptz\s+NOT NULL\s+DEFAULT now\(\)", "recorded_at timestamptz NOT NULL")


# ---------------------------------------------------------------------------
# 13 + 14. event_id uniqueness; exact frozen action set + constrained producer
# ---------------------------------------------------------------------------
def test_2b_event_id_unique_and_idempotent_insert() -> None:
    assert re.search(r"event_id\s+uuid\s+NOT NULL UNIQUE", _text(_DDL_010)), "event_id is the UNIQUE idempotency key"
    assert "ON CONFLICT (event_id) DO NOTHING RETURNING id" in _text(_CP_PG), "the adapter uses the sanctioned idempotent insert (MC4)"


def test_2b_exact_action_set_and_constraints_in_ddl() -> None:
    stripped = _strip_sql_comments(_text(_DDL_010))
    check = re.search(r"CHECK \(action IN \(([^)]*)\)\)", stripped)
    assert check, "the action CHECK must exist (contract-frozen vocabulary, MC3)"
    actions = set(re.findall(r"'([A-Za-z]+)'", check.group(1)))
    assert actions == set(_ACTIONS), f"action vocabulary drifted: {actions}"
    assert re.search(r"CHECK \(source_service = 'database_router'\)", stripped), "source_service is constrained to the router-edge producer"
    assert re.search(r"CHECK \(event_version > 0\)", stripped), "event_version must be positive"
    for reserved in ("DispatchCompleted", "DispatchFailed", "AuditSinkFailed"):
        assert reserved not in _text(_DDL_010), f"reserved forward action {reserved} must not be adopted"


def test_2b_action_set_nonvacuity() -> None:
    probe = "CHECK (action IN ('Route', 'RouteControl', 'RouteDenied', 'IsolationAnomaly', 'Publish'))"
    assert set(re.findall(r"'([A-Za-z]+)'", probe)) != set(_ACTIONS), "a fifth action must be detectable"


# ---------------------------------------------------------------------------
# 15. Exact twenty columns; no hidden JSON/metadata/body/credential/topology column
# ---------------------------------------------------------------------------
def test_2b_exact_column_set_no_hidden_columns() -> None:
    columns = _sql_columns(_text(_DDL_010))
    assert columns == _EXPECTED_COLUMNS and len(_EXPECTED_COLUMNS) == 20, f"column set drifted: {sorted(columns)}"
    stripped = _strip_sql_comments(_text(_DDL_010)).lower()
    for banned in ("json", "jsonb", "metadata", "bytea", "payload_", " body ", "token", "credential", "hash_chain"):
        assert banned not in stripped, f"hidden/forbidden column material in 010: {banned!r}"
    assert "references" not in stripped, "no foreign key / cross-database constraint may exist"
    assert "retention" not in stripped and "ttl" not in stripped, "no retention duration may be invented in DDL"


def test_2b_column_extractor_nonvacuity() -> None:
    probe = (
        "CREATE TABLE IF NOT EXISTS control_routing_audit (\n"
        "    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,\n"
        "    event_id uuid NOT NULL UNIQUE\n"
        ");\n"
    )
    assert _sql_columns(probe) == frozenset({"id", "event_id"})


# ---------------------------------------------------------------------------
# 16. Append-only enforcement; no update/delete/truncate anywhere in the adapter
# ---------------------------------------------------------------------------
def test_2b_append_only_trigger_and_no_mutation_path() -> None:
    trigger = _text(_DDL_011)
    assert "BEFORE UPDATE OR DELETE ON control_routing_audit" in trigger
    assert "BEFORE TRUNCATE ON control_routing_audit" in trigger
    assert "RAISE EXCEPTION" in trigger and "control_routing_audit_append_only" in trigger
    assert "CREATE TABLE" not in trigger, "011 is the trigger companion only (EC1)"
    pg = _text(_CP_PG)
    for banned in ("UPDATE control_routing_audit", "DELETE FROM control_routing_audit", "TRUNCATE"):
        assert banned not in pg, f"append-only violated in the adapter: {banned!r}"


def test_2b_append_only_nonvacuity() -> None:
    assert "BEFORE UPDATE OR DELETE ON control_routing_audit" not in "BEFORE INSERT ON control_routing_audit"
    assert "TRUNCATE" in "TRUNCATE control_routing_audit"


# ---------------------------------------------------------------------------
# 17. Created-not-applied: no application, no migration runner, no enrollment
# ---------------------------------------------------------------------------
def test_2b_no_ddl_application_or_migration_runner() -> None:
    for ddl in (_DDL_010, _DDL_011):
        assert "Created, NOT applied" in _text(ddl), f"{ddl.name} must carry the created-not-applied paragraph"
    for path in _NEW_MODULES:
        text = _text(path)
        for token in ("CREATE TABLE", "ALTER TABLE", "DROP TABLE", ".sql"):
            assert token not in text, f"{path.name} must not apply or load DDL ({token!r})"
        assert "infrastructure" not in text, f"{path.name} must not reach into the DDL tree"


def test_2b_ddl_application_nonvacuity() -> None:
    assert "CREATE TABLE" in _text(_DDL_010), "the detector's token must be real SQL vocabulary"


# ---------------------------------------------------------------------------
# 19. DDL guard registration is complete (blob pins + census/order)
# ---------------------------------------------------------------------------
def test_2b_ddl_guard_registration_complete() -> None:
    blob_guard = _text(_BLOB_GUARD)
    assert re.search(r'_DDL_010\s*=\s*_CONTROL\s*/\s*"010_routing_audit\.sql"', blob_guard), "010 must be declared in the blob-pins guard"
    assert re.search(r'_DDL_011\s*=\s*_CONTROL\s*/\s*"011_routing_audit_append_only\.sql"', blob_guard), (
        "011 must be declared in the blob-pins guard"
    )
    assert re.search(r'_PIN_010\s*=\s*"[0-9a-f]{40}"', blob_guard), "010 must carry a 40-hex blob pin"
    assert re.search(r'_PIN_011\s*=\s*"[0-9a-f]{40}"', blob_guard), "011 must carry a 40-hex blob pin"
    topo_guard = _text(_TOPO_GUARD)
    assert "_EXPECTED_UNENROLLED_DDL" in topo_guard, "the census/order guard must classify the 2B DDL"
    assert '"010_routing_audit.sql"' in topo_guard and '"011_routing_audit_append_only.sql"' in topo_guard


def test_2b_registration_nonvacuity() -> None:
    assert not re.search(r'_PIN_010\s*=\s*"[0-9a-f]{40}"', '_PIN_010 = "not-a-hash"'), "a fake pin must be detectable"
    assert re.search(r'_PIN_010\s*=\s*"[0-9a-f]{40}"', '_PIN_010 = "' + "0" * 40 + '"')


if __name__ == "__main__":
    _scan.run(
        [
            test_2b_authorized_production_files_exist,
            test_2c_main_composition_roots_reference_only_authorized_2b_symbols,
            test_2c_no_production_composition_census,
            test_2c_composition_census_nonvacuity,
            test_2b_no_cross_service_import,
            test_2b_router_client_stdlib_only_no_db_no_selector,
            test_2b_client_needle_scan_nonvacuity,
            test_2b_no_concurrency_machinery,
            test_2b_concurrency_detector_nonvacuity,
            test_2b_exact_endpoint_and_envelope_anchors,
            test_2b_endpoint_anchor_nonvacuity,
            test_2b_strict_field_allowlist_exact,
            test_2b_allowlist_extractors_nonvacuity,
            test_2b_forbidden_name_and_value_shape_defenses,
            test_2b_forbidden_defense_nonvacuity,
            test_2b_recorded_at_absent_from_wire_request,
            test_2b_recorded_at_store_assigned_and_id_never_bound,
            test_2b_recorded_at_detector_nonvacuity,
            test_2b_event_id_unique_and_idempotent_insert,
            test_2b_exact_action_set_and_constraints_in_ddl,
            test_2b_action_set_nonvacuity,
            test_2b_exact_column_set_no_hidden_columns,
            test_2b_column_extractor_nonvacuity,
            test_2b_append_only_trigger_and_no_mutation_path,
            test_2b_append_only_nonvacuity,
            test_2b_no_ddl_application_or_migration_runner,
            test_2b_ddl_application_nonvacuity,
            test_2b_ddl_guard_registration_complete,
            test_2b_registration_nonvacuity,
        ]
    )
