"""DBR-AR-2C — durable routing-audit composition/failure-semantics guard (architecture; no DB, no runtime).

Machine-pins the DBR-AR-2C execution decisions (PRD DBR-AR-2C V2 D1-D10) by text/AST
inspection of the committed sources: the exact four environment names (and no drifted
variants) split across the two composition roots; the C2 gate-first selector order (the
audit variables are consulted only past the outer routing gate, and only by the two
dedicated helpers); the pinned timeout contract (default 2.0, cap 30.0, bounds-checked
before client construction); the credential/query/fragment-free URL validation whose
error never echoes the configured value; the bounded per-event-class policy shape —
exactly ONE same-event retry gated on the ``unavailable`` transport kind, no loop, no
sleep, terminal re-raise for ``Route``/``RouteControl`` and swallow-and-count for
``RouteDenied``/``IsolationAnomaly``; the fixed two-key integer degradation snapshot;
no in-memory fallback reachable once durable mode is selected; the router's condition-1
shape (both ``_ok`` emission points fail closed with the bounded
``routing_audit_unavailable`` denial, the tenant path discards the acquired connection
first, and neither handler recursively audits); the loopback-only host allow-list and
ValueError-before-store/socket ordering of the Control-Plane ingest seam with its
reference-only store construction; created-not-applied DDL discipline unchanged;
ATR-2B-1 not silently implemented; and the 2C file census with no DBR-AR-2D/2E work
begun. Every detector carries a planted non-vacuity companion. Pure stdlib;
standalone-runnable:
  python tests/architecture/test_dbr_ar_2c_composition_boundaries.py
"""

from __future__ import annotations

import ast
import pathlib
import re
import sys
from typing import List, Optional, Set

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

_REPO = _scan.REPO_ROOT
_BACKEND = _scan.BACKEND_ROOT

_DR_MAIN = _BACKEND / "database_router" / "main.py"
_DR_ROUTER = _BACKEND / "database_router" / "router.py"
_CP_MAIN = _BACKEND / "control_plane" / "main.py"
_CP_INGEST = _BACKEND / "control_plane" / "adapters" / "providers" / "http_routing_audit_api.py"
_CONTRACT_DOC = _REPO / "docs" / "runtime" / "dbr_ar_2_durable_routing_audit_contract.md"
_DDL_010 = _REPO / "infrastructure" / "db" / "control" / "010_routing_audit.sql"
_DDL_011 = _REPO / "infrastructure" / "db" / "control" / "011_routing_audit_append_only.sql"

_TESTS = pathlib.Path(__file__).resolve().parent.parent
_2C_TEST_FILES = (
    _TESTS / "architecture" / "test_dbr_ar_2c_composition_boundaries.py",
    _TESTS / "control_plane" / "test_dbr_ar_2c_routing_audit_composition.py",
    _TESTS / "database_router" / "test_dbr_ar_2c_routing_audit_composition.py",
)

# D2/D3 — the exact, complete environment vocabulary of this slice (no drifted variants).
_DR_ENV_SUFFIXES = frozenset({"BASE_URL", "TIMEOUT_SECONDS"})
_CP_ENV_SUFFIXES = frozenset({"HOST", "PORT"})
_DR_ENV_RE = re.compile(r"SP2_DBR_ROUTING_AUDIT_([A-Z0-9_]+)")
_CP_ENV_RE = re.compile(r"SP2_CP_ROUTING_AUDIT_([A-Z0-9_]+)")

# D8 — the fixed degradation-counter vocabulary (integer counts only).
_COUNTER_KEYS = frozenset({"route_denied_audit_failures", "isolation_anomaly_audit_failures"})

_LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")


def _text(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def _tree(path: pathlib.Path) -> ast.Module:
    return ast.parse(_text(path), filename=str(path))


def _func(tree: ast.AST, name: str) -> Optional[ast.FunctionDef]:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def _class(tree: ast.AST, name: str) -> Optional[ast.ClassDef]:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    return None


def _calls_named(node: ast.AST, attr: str) -> List[ast.Call]:
    """Call nodes whose callee is ``<something>.<attr>`` or the bare name ``<attr>``."""
    out: List[ast.Call] = []
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            if isinstance(n.func, ast.Attribute) and n.func.attr == attr:
                out.append(n)
            elif isinstance(n.func, ast.Name) and n.func.id == attr:
                out.append(n)
    return out


def _inner_initiate_calls(node: ast.AST) -> List[ast.Call]:
    """Call nodes of the exact shape ``self._inner.initiate(...)``."""
    out: List[ast.Call] = []
    for n in ast.walk(node):
        if (
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "initiate"
            and isinstance(n.func.value, ast.Attribute)
            and n.func.value.attr == "_inner"
        ):
            out.append(n)
    return out


def _names_used(node: ast.AST) -> Set[str]:
    out: Set[str] = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Name):
            out.add(n.id)
        elif isinstance(n, ast.Attribute):
            out.add(n.attr)
    return out


def _env_get_names(node: ast.AST) -> Set[str]:
    """The env-name constants read via ``os.environ.get(<Name>)`` within ``node``."""
    out: Set[str] = set()
    for call in _calls_named(node, "get"):
        if (
            isinstance(call.func, ast.Attribute)
            and isinstance(call.func.value, ast.Attribute)
            and call.func.value.attr == "environ"
            and call.args
            and isinstance(call.args[0], ast.Name)
        ):
            out.add(call.args[0].id)
    return out


def _module_constant(tree: ast.Module, name: str) -> object:
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            if isinstance(node.value, ast.Constant):
                return node.value.value
            if isinstance(node.value, ast.Tuple):
                return tuple(e.value for e in node.value.elts if isinstance(e, ast.Constant))
    return None


def _segment(path: pathlib.Path, node: ast.AST) -> str:
    seg = ast.get_source_segment(_text(path), node)
    assert seg is not None
    return seg


# ---------------------------------------------------------------------------
# D2/D3. Exact environment vocabulary, split across the two composition roots
# ---------------------------------------------------------------------------
def test_2c_exact_env_names() -> None:
    dr = _text(_DR_MAIN)
    cp = _text(_CP_MAIN)
    assert set(_DR_ENV_RE.findall(dr)) == _DR_ENV_SUFFIXES, "the DBR audit env vocabulary drifted"
    assert set(_CP_ENV_RE.findall(cp)) == _CP_ENV_SUFFIXES, "the CP audit env vocabulary drifted"
    # No cross-side environment names: the router never reads the CP bind knobs and the
    # Control Plane never reads the router selector/timeout.
    assert not _CP_ENV_RE.search(dr), "database_router/main.py must not reference the CP ingest bind knobs"
    assert not _DR_ENV_RE.search(cp), "control_plane/main.py must not reference the router audit selector/timeout"
    # The exact constant-name pins (the literals double as the module constants).
    for name in ("SP2_DBR_ROUTING_AUDIT_BASE_URL", "SP2_DBR_ROUTING_AUDIT_TIMEOUT_SECONDS"):
        assert f'{name} = "{name}"' in dr, f"missing exact env constant {name}"
    for name in ("SP2_CP_ROUTING_AUDIT_HOST", "SP2_CP_ROUTING_AUDIT_PORT"):
        assert f'{name} = "{name}"' in cp, f"missing exact env constant {name}"


def test_2c_env_names_nonvacuity() -> None:
    assert set(_DR_ENV_RE.findall("SP2_DBR_ROUTING_AUDIT_FALLBACK_URL")) == {"FALLBACK_URL"}, "a drifted DBR name must be detectable"
    assert set(_CP_ENV_RE.findall("SP2_CP_ROUTING_AUDIT_DSN")) == {"DSN"}, "a drifted CP name must be detectable"
    assert _CP_ENV_RE.search("os.environ.get(SP2_CP_ROUTING_AUDIT_HOST)"), "a cross-side reference must be detectable"


# ---------------------------------------------------------------------------
# D1. C2 gate-first: audit env consulted only past the outer routing gate,
# and only by the two dedicated helpers
# ---------------------------------------------------------------------------
def test_2c_gate_first_selector_order() -> None:
    tree = _tree(_DR_MAIN)
    seam = _func(tree, "build_router_from_env")
    assert seam is not None, "build_router_from_env must exist"
    seg = _segment(_DR_MAIN, seam)
    assert "_routing_audit_from_env(" in seg, "the seam must consult the audit selector helper"
    assert seg.index("return None") < seg.index("_routing_audit_from_env("), (
        "gate-first: the outer routing gate's early return must precede the audit selector call"
    )
    # The audit env names are read ONLY inside the two dedicated helpers (never at import,
    # never in another function, never while the outer seam is inactive).
    for fn in ast.walk(tree):
        if isinstance(fn, ast.FunctionDef):
            reads = _env_get_names(fn) & {"SP2_DBR_ROUTING_AUDIT_BASE_URL", "SP2_DBR_ROUTING_AUDIT_TIMEOUT_SECONDS"}
            if reads:
                assert fn.name in ("_routing_audit_from_env", "_routing_audit_timeout_from_env"), (
                    f"{fn.name} reads the audit env — only the dedicated helpers may"
                )
    audit_kw = [kw for kw in ast.walk(seam) if isinstance(kw, ast.keyword) and kw.arg == "audit"]
    assert audit_kw, "the seam must pass audit= into build_router (selection reaches the composition)"


def test_2c_gate_first_nonvacuity() -> None:
    probe = "def build_router_from_env():\n    audit = _routing_audit_from_env()\n    raw = x\n    if not raw:\n        return None\n"
    assert probe.index("return None") > probe.index("_routing_audit_from_env("), "an inverted gate order must be detectable"
    fn = _func(ast.parse("def rogue():\n    import os\n    return os.environ.get(SP2_DBR_ROUTING_AUDIT_BASE_URL)\n"), "rogue")
    assert fn is not None and _env_get_names(fn) == {"SP2_DBR_ROUTING_AUDIT_BASE_URL"}, "a rogue env read must be detectable"


def test_2c_lazy_adapter_import_and_router_import_surface() -> None:
    # The transport-client import stays function-local in the DBR root (the merged lazy
    # seam shape): no module-top import — absolute or relative — of the 2B adapter.
    tree = _tree(_DR_MAIN)
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mod = (getattr(node, "module", "") or "") if isinstance(node, ast.ImportFrom) else ""
            names = [alias.name for alias in node.names]
            assert "http_routing_audit" not in mod, "the transport client import must stay function-local"
            assert "HttpRoutingAudit" not in names, "the transport client import must stay function-local"
    # router.py keeps its lean import surface: no importlib/dynamic-import machinery may
    # smuggle an obfuscated composition past the 2B symbol census.
    router_tops = {m.split(".")[0] for m in _scan.imported_modules(_DR_ROUTER)}
    assert router_tops <= {"__future__", "datetime", "typing", "uuid", "shared"}, f"router.py import surface widened: {sorted(router_tops)}"
    router_text = _text(_DR_ROUTER)
    for banned in ("importlib", "__import__"):
        assert banned not in router_text, f"router.py must not use dynamic imports ({banned})"


def test_2c_lazy_import_nonvacuity() -> None:
    hoisted = ast.parse("from database_router.adapters.providers.http_routing_audit import HttpRoutingAudit\n").body[0]
    assert isinstance(hoisted, ast.ImportFrom) and "http_routing_audit" in (hoisted.module or ""), (
        "a hoisted adapter import must be detectable"
    )
    assert "importlib" in 'mod = importlib.import_module("database_router.adapters.providers.http_" + "routing_audit")', (
        "a dynamic-import smuggle must be detectable"
    )
    assert not {"importlib"} <= {"__future__", "datetime", "typing", "uuid", "shared"}, "a widened import surface must be detectable"


# ---------------------------------------------------------------------------
# D2. Timeout contract: default 2.0; finite; 0 < t <= 30.0; before construction
# ---------------------------------------------------------------------------
def test_2c_timeout_contract_pinned() -> None:
    tree = _tree(_DR_MAIN)
    assert _module_constant(tree, "_ROUTING_AUDIT_TIMEOUT_DEFAULT") == 2.0, "the pinned default must be exactly 2.0"
    assert _module_constant(tree, "_ROUTING_AUDIT_TIMEOUT_MAX") == 30.0, "the pinned cap must be exactly 30.0"
    helper = _func(tree, "_routing_audit_timeout_from_env")
    assert helper is not None, "the timeout helper must exist"
    seg = _segment(_DR_MAIN, helper)
    assert "return _ROUTING_AUDIT_TIMEOUT_DEFAULT" in seg, "unset/empty must return the pinned default"
    assert "0.0 < timeout <= _ROUTING_AUDIT_TIMEOUT_MAX" in seg, (
        "the exact bounds check must be present (NaN fails it; ±inf falls outside — finite by construction)"
    )
    seam = _func(tree, "_routing_audit_from_env")
    assert seam is not None
    sseg = _segment(_DR_MAIN, seam)
    assert sseg.index("_routing_audit_timeout_from_env(") < sseg.index("HttpRoutingAudit("), (
        "the timeout must be validated BEFORE client construction"
    )


def test_2c_timeout_nonvacuity() -> None:
    assert _module_constant(ast.parse("_ROUTING_AUDIT_TIMEOUT_DEFAULT = 5.0"), "_ROUTING_AUDIT_TIMEOUT_DEFAULT") != 2.0
    assert "0.0 < timeout <= _ROUTING_AUDIT_TIMEOUT_MAX" not in "if timeout > 0:", "a weakened bounds check must be detectable"


# ---------------------------------------------------------------------------
# D2. URL validation: http scheme, netloc, no credentials/query/fragment;
# the configured value is never echoed through the ValueError
# ---------------------------------------------------------------------------
def test_2c_url_validation_pinned() -> None:
    tree = _tree(_DR_MAIN)
    seam = _func(tree, "_routing_audit_from_env")
    assert seam is not None
    seg = _segment(_DR_MAIN, seam)
    for needle in (
        'parts.scheme != "http"',
        "not parts.netloc",
        '"@" in parts.netloc',  # userinfo rejection — no credential material may ride the URL
        "parts.query",
        "parts.fragment",
    ):
        assert needle in seg, f"URL validation weakened: missing {needle!r}"
    # The URL ValueError must NOT interpolate the configured value (a mis-pasted
    # credential could otherwise leak through the error text).
    url_error = re.search(r"raise ValueError\(\s*f?\"unsupported \{SP2_DBR_ROUTING_AUDIT_BASE_URL\}([^\"]*)\"", seg)
    assert url_error is not None, "the bounded URL ValueError must exist"
    assert "{raw" not in url_error.group(1), "the URL error must never echo the configured value"
    assert "not echoed" in seg, "the no-echo posture must be stated at the raise site"


def test_2c_url_validation_nonvacuity() -> None:
    weakened = 'if parts.scheme != "http" or not parts.netloc:'
    assert '"@" in parts.netloc' not in weakened, "a credentials-check removal must be detectable"
    leaky = 'raise ValueError(f"unsupported {SP2_DBR_ROUTING_AUDIT_BASE_URL}={raw!r}; bad")'
    match = re.search(r"raise ValueError\(\s*f?\"unsupported \{SP2_DBR_ROUTING_AUDIT_BASE_URL\}([^\"]*)\"", leaky)
    assert match is not None and "{raw" in match.group(1), "a value-echoing URL error must be detectable"


# ---------------------------------------------------------------------------
# D4. The bounded retry: exactly one same-event retry, unavailable-kind only,
# no loop, no sleep, no queue/outbox
# ---------------------------------------------------------------------------
def test_2c_policy_retry_shape() -> None:
    tree = _tree(_DR_MAIN)
    policy = _class(tree, "BoundedRoutingAuditPolicy")
    assert policy is not None, "BoundedRoutingAuditPolicy must exist in database_router/main.py"
    initiate = _func(policy, "initiate")
    assert initiate is not None
    assert len(_inner_initiate_calls(initiate)) == 2, (
        "initiate must contain EXACTLY two self._inner.initiate call sites (first attempt + the single retry)"
    )
    assert len(_inner_initiate_calls(policy)) == 2, "no additional transport call site may exist anywhere in the policy"
    for n in ast.walk(policy):
        assert not isinstance(n, (ast.For, ast.While, ast.AsyncFor)), "the policy must contain no retry loop"
    assert "sleep" not in _names_used(policy), "the policy must never sleep"
    retryable = _func(policy, "_retryable")
    assert retryable is not None
    rseg = _segment(_DR_MAIN, retryable)
    assert '== "unavailable"' in rseg, "the retry gate must test the exact transient kind"
    assert "isinstance(failure, self._transport_error)" in rseg, "the retry gate must test the bounded transport error type"
    iseg = _segment(_DR_MAIN, initiate)
    assert "if not self._retryable(first):" in iseg, "invalid/conflict (and non-transport failures) must take the no-retry path"
    # No queue/outbox machinery at the composition root (AST-level; docstrings may
    # legitimately SAY 'no queue, no outbox').
    tops = {m.split(".")[0] for m in _scan.imported_modules(_DR_MAIN)}
    assert not (tops & {"queue", "collections", "threading", "asyncio", "time"}), "no queue/buffer/sleep machinery may be imported"


def test_2c_policy_retry_nonvacuity() -> None:
    doubled = ast.parse(
        "class P:\n"
        "    def initiate(self, e):\n"
        "        self._inner.initiate(e)\n"
        "        self._inner.initiate(e)\n"
        "        self._inner.initiate(e)\n"
    )
    assert len(_inner_initiate_calls(doubled)) == 3, "a second retry must be detectable"
    looped = ast.parse("class P:\n    def initiate(self, e):\n        for _ in range(3):\n            self._inner.initiate(e)\n")
    assert any(isinstance(n, ast.For) for n in ast.walk(looped)), "a retry loop must be detectable"
    assert '== "unavailable"' not in 'kind in ("unavailable", "invalid")', "a widened retry gate must be detectable"


# ---------------------------------------------------------------------------
# D5/D6/D7. Per-event-class terminal posture: re-raise for Route/RouteControl;
# swallow-and-count for RouteDenied/IsolationAnomaly; never an upgrade
# ---------------------------------------------------------------------------
def test_2c_policy_terminal_posture() -> None:
    tree = _tree(_DR_MAIN)
    policy = _class(tree, "BoundedRoutingAuditPolicy")
    assert policy is not None
    terminal = _func(policy, "_terminal")
    assert terminal is not None
    seg = _segment(_DR_MAIN, terminal)
    assert 'event.action == "RouteDenied"' in seg and 'event.action == "IsolationAnomaly"' in seg, (
        "the two swallow-and-count event classes must be dispatched by exact action"
    )
    assert "self._route_denied_audit_failures += 1" in seg, "a lost denial record must increment its fixed counter"
    assert "self._isolation_anomaly_audit_failures += 1" in seg, "a lost anomaly record must increment its fixed counter"
    assert "raise failure" in seg, "Route/RouteControl terminal failure must re-raise (the router fails the route closed)"
    # The swallow branches return; only the success/route classes reach the raise.
    raises = [n for n in ast.walk(terminal) if isinstance(n, ast.Raise)]
    assert len(raises) == 1, "exactly one terminal raise (the fail-closed route path)"


def test_2c_policy_terminal_nonvacuity() -> None:
    assert 'event.action == "RouteDenied"' not in 'event.action in ("RouteDenied", "Route")', "a class-dispatch rewrite must be detectable"
    upgraded = "def _terminal(self, event, failure):\n    return None\n"
    assert "raise failure" not in upgraded, "a silently-fail-open terminal must be detectable"


# ---------------------------------------------------------------------------
# D8. The fixed two-key integer degradation snapshot
# ---------------------------------------------------------------------------
def test_2c_fixed_counter_keys() -> None:
    tree = _tree(_DR_MAIN)
    policy = _class(tree, "BoundedRoutingAuditPolicy")
    assert policy is not None
    snapshot = _func(policy, "degradation_snapshot")
    assert snapshot is not None, "the degradation snapshot must exist"
    dicts = [n for n in ast.walk(snapshot) if isinstance(n, ast.Dict)]
    assert len(dicts) == 1, "the snapshot must be a single dict literal"
    keys = {k.value for k in dicts[0].keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}
    assert keys == _COUNTER_KEYS, f"the snapshot keys must be EXACTLY the two fixed counters, got {sorted(keys)}"
    for value in dicts[0].values:
        assert isinstance(value, ast.Attribute), "snapshot values must be the bare integer counters — no payload structures"
    # No payload/identity material may enter the degradation state.
    pseg = _segment(_DR_MAIN, policy)
    for banned in ("correlation_id", "tenant_ref", "target_ref", "append(", "list("):
        assert banned not in pseg, f"the policy must hold no payload/identity degradation state ({banned!r})"


def test_2c_counter_keys_nonvacuity() -> None:
    widened = ast.parse('def s(self):\n    return {"route_denied_audit_failures": 1, "events": [1]}\n')
    d = [n for n in ast.walk(widened) if isinstance(n, ast.Dict)][0]
    keys = {k.value for k in d.keys if isinstance(k, ast.Constant)}
    assert keys != _COUNTER_KEYS, "a widened snapshot vocabulary must be detectable"
    assert not isinstance(d.values[1], ast.Attribute), "a payload-bearing snapshot value must be detectable"


# ---------------------------------------------------------------------------
# D1. No fallback after durable selection
# ---------------------------------------------------------------------------
def test_2c_no_durable_fallback() -> None:
    tree = _tree(_DR_MAIN)
    for name in ("_routing_audit_from_env", "_routing_audit_timeout_from_env"):
        fn = _func(tree, name)
        assert fn is not None
        assert "InMemoryAuditSink" not in _names_used(fn), f"{name} must never reference the in-memory sink (no fallback)"
    policy = _class(tree, "BoundedRoutingAuditPolicy")
    assert policy is not None
    assert "InMemoryAuditSink" not in _names_used(policy), "the policy must never fall back to the in-memory sink"
    # The selector-unset path stays byte-compatible: build_router keeps its defaulted
    # in-memory composition for a None audit (this is selection-never-happened, not fallback).
    br = _func(tree, "build_router")
    assert br is not None
    assert "audit or InMemoryAuditSink()" in _segment(_DR_MAIN, br), "the unset-selector default must remain build_router's None path"


def test_2c_no_durable_fallback_nonvacuity() -> None:
    planted = "def _routing_audit_from_env():\n    try:\n        return P()\n    except Exception:\n        return InMemoryAuditSink()\n"
    fallback = _func(ast.parse(planted), "_routing_audit_from_env")
    assert fallback is not None and "InMemoryAuditSink" in _names_used(fallback), "a planted fallback must be detectable"


# ---------------------------------------------------------------------------
# D5. Router condition-1 shape: discard + bounded denial; never recursive audit
# ---------------------------------------------------------------------------
def test_2c_router_condition1_shape() -> None:
    text = _text(_DR_ROUTER)
    assert text.count('unavailable("routing_audit_unavailable") from None') == 2, (
        "both _ok emission points (RouteControl + Route) must raise the bounded context-suppressed denial exactly once each"
    )
    tree = _tree(_DR_ROUTER)
    route = _func(tree, "route")
    assert route is not None
    handlers = []
    for n in ast.walk(route):
        if isinstance(n, ast.ExceptHandler):
            seg = _segment(_DR_ROUTER, n)
            if "routing_audit_unavailable" in seg:
                handlers.append((n, seg))
    assert len(handlers) == 2, "exactly the two audit-failure handlers must exist in route()"
    discards = [seg for _, seg in handlers if ".discard(conn)" in seg]
    assert len(discards) == 1, "exactly the tenant-route handler must discard the acquired connection"
    tenant_seg = discards[0]
    assert tenant_seg.index(".discard(conn)") < tenant_seg.index('unavailable("routing_audit_unavailable")'), (
        "the connection must be discarded BEFORE the denial is raised"
    )
    for node, _seg in handlers:
        for recursive in ("_denied", "_anomaly", "initiate"):
            assert not _calls_named(node, recursive), f"the audit-failure handler must never call {recursive} (no recursive audit)"
    # The denial constructor is the router's own bounded 503 bucket (no new disclosure).
    assert "def unavailable(" in _text(_BACKEND / "database_router" / "models.py"), "the bounded denial constructor must be the models one"


def test_2c_router_condition1_nonvacuity() -> None:
    recursive = ast.parse(
        "def route():\n"
        "    try:\n"
        "        ok()\n"
        "    except Exception:\n"
        "        self._denied(ctx, tid, 'routing_audit_unavailable')\n"
        "        raise\n"
    )
    handler = [n for n in ast.walk(recursive) if isinstance(n, ast.ExceptHandler)][0]
    assert _calls_named(handler, "_denied"), "a recursive audit call inside the handler must be detectable"
    unordered = 'raise unavailable("routing_audit_unavailable")\npool.discard(conn)'
    assert unordered.index(".discard(conn)") > unordered.index('unavailable("routing_audit_unavailable")'), (
        "a raise-before-discard rewrite must be detectable"
    )
    assert 'unavailable("routing_audit_unavailable") from None' not in 'raise unavailable("routing_audit_unavailable")', (
        "dropped context suppression must be detectable"
    )


# ---------------------------------------------------------------------------
# D3. Control-Plane ingest seam: loopback-only, ValueError before store/socket,
# reference-only store construction, function-local provider imports
# ---------------------------------------------------------------------------
def test_2c_cp_seam_shape() -> None:
    tree = _tree(_CP_MAIN)
    assert _module_constant(tree, "_ROUTING_AUDIT_LOOPBACK_HOSTS") == _LOOPBACK_HOSTS, (
        "the ingest bind host allow-list must be exactly the three loopback hosts"
    )
    seam = _func(tree, "build_routing_audit_server_from_env")
    assert seam is not None, "build_routing_audit_server_from_env must exist"
    seg = _segment(_CP_MAIN, seam)
    # Host-gate-first, then host allow-list, then port, then secret ref — all BEFORE the
    # store construction and the socket-binding server construction.
    order = (
        "return None",
        "host not in _ROUTING_AUDIT_LOOPBACK_HOSTS",
        "_routing_audit_port_from_env(",
        "CONTROL_STORE_DSN_REF_ENV",
        "PostgresRoutingAuditStore(secrets=secrets, ref=ref)",
        "build_routing_audit_server(store, host=host, port=port)",
    )
    positions = [seg.index(needle) for needle in order]
    assert positions == sorted(positions), "the fail-closed validation order (gate→host→port→ref→store→server) must hold"
    # Reference-only: the seam handles the secret REFERENCE, never a resolved value.
    assert "SecretRef(store_ref=store_ref, version=" in seg, "the store must be constructed from the reference"
    assert ".resolve(" not in seg and ".material" not in seg, "the seam must never resolve the secret itself (lazy first-use)"
    assert "SNACKPORTAL_TEST_DSN" not in seg, "the test DSN env must never be reused as runtime config"
    assert "not echoed" in seg, "the host ValueError must state the no-echo posture"
    # Provider imports are function-local (driver/transport containment).
    body_imports = [n for n in ast.walk(seam) if isinstance(n, ast.ImportFrom)]
    imported = {n.module for n in body_imports if n.module}
    assert any(m and m.endswith("postgres_store") for m in imported), "the store provider import must be function-local"
    assert any(m and m.endswith("http_routing_audit_api") for m in imported), "the ingest adapter import must be function-local"


def test_2c_cp_seam_nonvacuity() -> None:
    inverted = "store = PostgresRoutingAuditStore(secrets=secrets, ref=ref)\nport = _routing_audit_port_from_env(\nreturn None"
    needles = ("return None", "_routing_audit_port_from_env(", "PostgresRoutingAuditStore(secrets=secrets, ref=ref)")
    positions = [inverted.index(n) for n in needles]
    assert positions != sorted(positions), "an inverted validation order must be detectable"
    widened = _module_constant(ast.parse('_ROUTING_AUDIT_LOOPBACK_HOSTS = ("0.0.0.0",)'), "_ROUTING_AUDIT_LOOPBACK_HOSTS")
    assert widened != _LOOPBACK_HOSTS, "a widened host allow-list must be detectable"
    resolved = "descriptor = secrets.resolve(ref).material"
    assert ".resolve(" in resolved and ".material" in resolved, "an in-seam secret resolution must be detectable"


# ---------------------------------------------------------------------------
# Stop rails: DDL discipline unchanged; ATR-2B-1 not silently implemented;
# no DBR-AR-2D/2E work; locked state pinned in the contract doc
# ---------------------------------------------------------------------------
def test_2c_ddl_discipline_and_locked_state() -> None:
    for ddl in (_DDL_010, _DDL_011):
        assert "Created, NOT applied" in _text(ddl), f"{ddl.name} must keep the created-not-applied paragraph"
    for path in (_DR_MAIN, _DR_ROUTER, _CP_MAIN):
        text = _text(path)
        for token in ("CREATE TABLE", "ALTER TABLE", "DROP TABLE", ".sql"):
            assert token not in text, f"{path.name} must not apply or load DDL ({token!r})"
    doc = _text(_CONTRACT_DOC).lower()
    assert "dbr-ar-2 — remains open." in doc, "DBR-AR-2 must remain OPEN in the contract doc"
    assert "dbr-ar-2d through dbr-ar-2e — not started." in doc, "2D/2E must remain not started"
    assert "production runtime activation remains not ready / do-not-activate" in doc, "the fail-closed gate posture must hold"


def test_2c_no_2d_2e_files() -> None:
    hits = [p for pattern in ("*dbr_ar_2d*", "*dbr_ar_2e*") for p in _BACKEND.rglob(pattern) if not (_scan.SKIP_PARTS & set(p.parts))]
    assert hits == [], f"DBR-AR-2D/2E work must not begin in this slice: {hits}"
    for path in _2C_TEST_FILES:
        assert path.is_file(), f"2C surface test file missing: {path}"


def test_2c_atr_2b1_not_silently_implemented() -> None:
    # ATR-2B-1 (unsupported-method / default-HTML / Server:-header hardening) is carried
    # separately: the 2B ingest adapter must keep its merged refusal shape and gain no
    # header-suppression override.
    ingest = _text(_CP_INGEST)
    assert "do_GET = do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = _method_not_allowed" in ingest, (
        "the merged 2B non-POST refusal shape must be unchanged"
    )
    for token in ("server_version", "sys_version", "version_string"):
        assert token not in ingest, f"ATR-2B-1 hardening ({token}) must not be silently implemented"


def test_2c_stop_rails_nonvacuity() -> None:
    assert "CREATE TABLE" in _text(_DDL_010), "the DDL-apply detector token must be real SQL vocabulary"
    assert "dbr-ar-2d through dbr-ar-2e — not started." not in "dbr-ar-2d through dbr-ar-2e — started.", (
        "a started-2D claim must be detectable"
    )
    assert "version_string" in "def version_string(self): return ''", "an ATR-2B-1 header override must be detectable"


if __name__ == "__main__":
    _scan.run(
        [
            test_2c_exact_env_names,
            test_2c_env_names_nonvacuity,
            test_2c_gate_first_selector_order,
            test_2c_gate_first_nonvacuity,
            test_2c_lazy_adapter_import_and_router_import_surface,
            test_2c_lazy_import_nonvacuity,
            test_2c_timeout_contract_pinned,
            test_2c_timeout_nonvacuity,
            test_2c_url_validation_pinned,
            test_2c_url_validation_nonvacuity,
            test_2c_policy_retry_shape,
            test_2c_policy_retry_nonvacuity,
            test_2c_policy_terminal_posture,
            test_2c_policy_terminal_nonvacuity,
            test_2c_fixed_counter_keys,
            test_2c_counter_keys_nonvacuity,
            test_2c_no_durable_fallback,
            test_2c_no_durable_fallback_nonvacuity,
            test_2c_router_condition1_shape,
            test_2c_router_condition1_nonvacuity,
            test_2c_cp_seam_shape,
            test_2c_cp_seam_nonvacuity,
            test_2c_ddl_discipline_and_locked_state,
            test_2c_no_2d_2e_files,
            test_2c_atr_2b1_not_silently_implemented,
            test_2c_stop_rails_nonvacuity,
        ]
    )
