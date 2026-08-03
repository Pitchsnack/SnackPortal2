"""CLM — 2-Day Accelerated Controlled Local MVP Stage B runtime boundary guard (default suite; no DB, no network).

Static + pure-executable boundary pins for the D-42 Stage B implementation slice (the CLM
controlled-local rehearsal runtime): the two served tenant Startup routes, the bounded
single-field update, the Gateway→Database-Router tenant Startup data seam, and the CLM
durable-audit partition. Companion to the Stage A contract guard
(test_clm_2day_stage_a_contract_boundaries.py — contract text) — THIS guard binds the code
the Stage A code-closure note required to be widened "in the same change".

It binds no live runtime, opens no socket, and touches no database: every check is AST/text
over the implementation modules or a call to a pure function (the update-body parser and
the two bounded route matchers are socket-free pure values).

This guard closes no blocker. B5-BLK-5 remains OPEN; the live blocker census remains 7 of 9
OPEN; production remains NOT READY / DO-NOT-ACTIVATE.

Pure stdlib + api_gateway imports; standalone-runnable:
  python tests/architecture/test_clm_2day_stage_b_runtime_boundaries.py
"""

from __future__ import annotations

import ast
import pathlib
import sys
from typing import Set

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

if str(_scan.BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_scan.BACKEND_ROOT))

from api_gateway.main import _CLM_DURABLE_ACTIONS  # noqa: E402
from api_gateway.models import AuditAction  # noqa: E402
from api_gateway.portal import (  # noqa: E402
    TENANT_STARTUP_SHORT_DESCRIPTION_MAX_CHARS,
    TenantStartupUpdateRequestDTO,
    parse_tenant_startup_update_request,
)

_GW = _scan.BACKEND_ROOT / "api_gateway"
_DBR = _scan.BACKEND_ROOT / "database_router"
_GATEWAY = _GW / "gateway.py"
_GW_CLIENT = _GW / "adapters" / "providers" / "http_tenant_startup.py"
_GW_MAIN = _GW / "main.py"
_DBR_OPS = _DBR / "tenant_startup_ops.py"
_DBR_EDGE = _DBR / "adapters" / "providers" / "http_tenant_startup_api.py"
_DBR_MAIN = _DBR / "main.py"

# DB drivers / vendor SDKs / crypto / concurrency banned from every CLM module (the modules
# reach tenant data ONLY through the injected routed-session port / internal transport).
_FORBIDDEN_TOPS = frozenset(
    {
        "psycopg",
        "psycopg2",
        "asyncpg",
        "sqlalchemy",
        "databases",
        "aiopg",
        "jwt",
        "cryptography",
        "supabase",
        "lovable",
        "threading",
        "asyncio",
        "concurrent",
        "multiprocessing",
        "logging",
        # FastAPI is the ONE sanctioned framework; a second one is never permitted, and the
        # edges must not reach past it to the ASGI server (the shared runtime owns that).
        "uvicorn",
        "flask",
        "django",
        "starlette",
        "requests",
    }
)


def _tree(path: pathlib.Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _import_tops(path: pathlib.Path) -> Set[str]:
    return {m.split(".")[0] for m in _scan.imported_modules(path)}


def _attr_call_count(tree: ast.AST, attr: str) -> int:
    return sum(1 for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == attr)


def _has_loop(node: ast.AST) -> bool:
    return any(isinstance(n, (ast.For, ast.While, ast.AsyncFor)) for n in ast.walk(node))


# ---------------------------------------------------------------------------
# 1. The bounded update parser: exactly the one allowlisted field, fail-closed
# ---------------------------------------------------------------------------
def test_update_parser_single_allowlisted_field_closure() -> None:
    assert TENANT_STARTUP_SHORT_DESCRIPTION_MAX_CHARS == 500, "IC-009/IC-010 CLM pin: at most 500 characters"
    # Green controls: exactly the one allowlisted field, string or null, at/under the bound.
    ok = parse_tenant_startup_update_request(b'{"short_description": "hello"}')
    assert ok == TenantStartupUpdateRequestDTO(short_description="hello")
    assert parse_tenant_startup_update_request(b'{"short_description": null}').short_description is None
    at_bound = '{"short_description": "' + "a" * 500 + '"}'
    assert parse_tenant_startup_update_request(at_bound.encode("utf-8")).short_description == "a" * 500
    # Fail-closed rejections: undecodable, non-object, unknown/extra/missing field,
    # non-string non-null value, over-bound value. Every one raises (NO partial parse).
    for bad in (
        b"not-json",
        b"[]",
        b"{}",
        b'{"long_description": "x"}',
        b'{"short_description": "x", "company_name": "y"}',
        b'{"short_description": 7}',
        b'{"short_description": ["x"]}',
        ('{"short_description": "' + "a" * 501 + '"}').encode("utf-8"),
    ):
        raised = False
        try:
            parse_tenant_startup_update_request(bad)
        except ValueError:
            raised = True
        assert raised, f"the bounded update parser must reject {bad[:40]!r} fail-closed"


# ---------------------------------------------------------------------------
# 2. Gateway single-route rule: the CLM path never reaches router.dispatch
# ---------------------------------------------------------------------------
def test_gateway_keeps_exactly_one_router_dispatch_call_site() -> None:
    tree = _tree(_GATEWAY)
    # The legacy TENANT_OPERATION handoff owns the ONE router.dispatch call; the CLM tenant
    # Startup branch executes through the tenant_startup port and adds no second call site
    # (single-route — the W1a import precedent).
    dispatch_calls = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "dispatch"
        and isinstance(n.func.value, ast.Attribute)
        and n.func.value.attr == "_router"
    ]
    assert len(dispatch_calls) == 1, f"gateway.py must keep exactly ONE self._router.dispatch call site, found {len(dispatch_calls)}"
    # The CLM branch exists and calls the port's read/update exactly once each.
    text = _GATEWAY.read_text(encoding="utf-8")
    assert "_tenant_startup_ref(request.path)" in text, "the gateway must own the bounded core-side ref extractor"
    for method_name in ("read", "update"):
        calls = [
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == method_name
            and isinstance(n.func.value, ast.Attribute)
            and n.func.value.attr == "_tenant_startup"
        ]
        assert len(calls) == 1, f"the gateway must call tenant_startup.{method_name} exactly once, found {len(calls)}"


# ---------------------------------------------------------------------------
# 3. Gateway-side transport client boundaries (the HttpControlPlaneRead idiom)
# ---------------------------------------------------------------------------
def test_gateway_client_adapter_boundaries() -> None:
    assert _GW_CLIENT.is_file(), "the gateway-side tenant Startup transport client must exist"
    tree = _tree(_GW_CLIENT)
    tops = _import_tops(_GW_CLIENT)
    assert tops <= {"__future__", "json", "urllib", "typing", "api_gateway"}, f"client import surface violated: {sorted(tops)}"
    assert not (tops & _FORBIDDEN_TOPS), f"client must import no driver/vendor/crypto/concurrency: {sorted(tops & _FORBIDDEN_TOPS)}"
    # Exactly ONE urlopen site; no retry loop around it; bounded timeout default.
    urlopen_calls = _attr_call_count(tree, "urlopen")
    assert urlopen_calls == 1, f"the client must own exactly one urlopen site, found {urlopen_calls}"
    call_fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_call")
    assert not _has_loop(call_fn), "the transport call must not be wrapped in a retry loop (single attempt)"
    init_fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "__init__")
    defaults = [d.value for d in init_fn.args.defaults if isinstance(d, ast.Constant) and isinstance(d.value, (int, float))]
    assert defaults and float(defaults[0]) <= 30.0, "the client timeout default must be bounded (<= 30s)"


# ---------------------------------------------------------------------------
# 4. Database-Router executor: driver-free; the sole CLM-mutable column
# ---------------------------------------------------------------------------
def test_dbr_executor_boundaries_and_sole_mutable_column() -> None:
    assert _DBR_OPS.is_file(), "the Database-Router tenant Startup executor must exist"
    tops = _import_tops(_DBR_OPS)
    assert tops <= {"__future__", "dataclasses", "typing", "shared"}, f"executor import surface violated: {sorted(tops)}"
    assert not (tops & _FORBIDDEN_TOPS), "the executor reaches tenant data ONLY through the injected routed-session port"
    tree = _tree(_DBR_OPS)
    # The bounded UPDATE assignment dict literal carries EXACTLY the one allowlisted column.
    update_calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "update"]
    assert len(update_calls) == 1, f"the executor must own exactly one bounded write site, found {len(update_calls)}"
    assignments_arg = update_calls[0].args[2]
    assert isinstance(assignments_arg, ast.Dict), "the bounded write must be a literal single-column assignment dict"
    keys = {k.value for k in assignments_arg.keys if isinstance(k, ast.Constant)}
    assert keys == {"short_description"}, f"short_description is the SOLE CLM-mutable column; found {sorted(keys)}"
    # No upsert/append/delete/execute write escape hatch exists in the executor — the bounded
    # single-column UPDATE is the only mutation path (a full-record upsert or a raw execute
    # would be able to touch a second column).
    for banned_call in ("upsert", "append", "execute", "executemany"):
        assert _attr_call_count(tree, banned_call) == 0, f"the executor must not call session.{banned_call}"


# ---------------------------------------------------------------------------
# 5. Database-Router internal edge: loopback, POST-only, fail-closed, silent
# ---------------------------------------------------------------------------
def test_dbr_internal_edge_boundaries() -> None:
    assert _DBR_EDGE.is_file(), "the internal tenant Startup operations edge must exist"
    text = _DBR_EDGE.read_text(encoding="utf-8")
    tree = _tree(_DBR_EDGE)
    tops = _import_tops(_DBR_EDGE)
    assert tops <= {"__future__", "json", "typing", "fastapi", "database_router", "shared"}, f"edge import surface violated: {sorted(tops)}"
    assert not (tops & _FORBIDDEN_TOPS), "the internal edge must import no driver/vendor/crypto/concurrency"
    served = _scan.registered_route_methods(tree)
    # The two internal surfaces (read + update) are POST-only; every other method is refused 405
    # by the shared fail-closed app before the executor is reached.
    assert served == ["post", "post"], f"the internal edge must expose exactly two POST routes (served: {served})"
    assert 'host: str = "127.0.0.1"' in text, "the internal edge must default to the loopback bind (IC-010 §R)"
    assert '"/internal/tenant/startups/read"' in text and '"/internal/tenant/startups/update"' in text, (
        "the two literal internal paths must be pinned"
    )
    used = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)} | {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert "send_error" not in used, "the internal edge must never call stdlib send_error"
    for marker in ("HTTPServer", "ThreadingHTTPServer", "ThreadingMixIn"):
        assert marker not in used, f"the internal edge must hand-roll no server ({marker}); the shared runtime owns it"
    assert "build_asgi_server" in used, "the internal edge must serve through the shared ASGI runtime"
    # Request logging is silenced at the shared runtime now (the migrated home of log_message).
    runtime = (_scan.BACKEND_ROOT / "shared" / "adapters" / "providers" / "asgi_runtime.py").read_text(encoding="utf-8")
    assert "access_log=False" in runtime and "log_config=None" in runtime, "request logging must stay silenced"


# ---------------------------------------------------------------------------
# 6. The CLM durable-audit partition homes EXACTLY the five ratified classes
# ---------------------------------------------------------------------------
def test_clm_durable_audit_partition_is_exactly_the_five_events() -> None:
    # D-43 (Post-10C.3 corrective): the durable set widened from four to exactly five —
    # adding the CarrierMismatch denial record and NO other audit class.
    assert _CLM_DURABLE_ACTIONS == frozenset(
        {
            AuditAction.WORKSPACE_MEMBERSHIPS_READ,
            AuditAction.TENANT_STARTUP_READ,
            AuditAction.TENANT_STARTUP_UPDATE,
            AuditAction.ROUTE_DENIED,
            AuditAction.CARRIER_MISMATCH,
        }
    ), "the durably homed set is EXACTLY the IC-010 CLM audit evidence set (no wider audit expansion)"
    # The two remaining anomaly classes stay OUTSIDE the durable partition.
    for unhomed in (AuditAction.CARRIER_ON_CONTROL_ANOMALY, AuditAction.ISOLATION_ANOMALY):
        assert unhomed not in _CLM_DURABLE_ACTIONS, f"{unhomed.value} must stay on the in-memory no-sink emitter"
    # The durably homed actions carry EXACTLY the contract action strings.
    assert AuditAction.TENANT_STARTUP_READ.value == "tenant_startup_read"
    assert AuditAction.TENANT_STARTUP_UPDATE.value == "tenant_startup_update"
    assert AuditAction.CARRIER_MISMATCH.value == "CarrierMismatch"


# ---------------------------------------------------------------------------
# 7. Composition selectors exist and stay fail-closed (no silent fallback)
# ---------------------------------------------------------------------------
def test_composition_selectors_pinned() -> None:
    gw_main = _GW_MAIN.read_text(encoding="utf-8")
    assert 'GW_TENANT_STARTUP_BASE_URL_ENV = "SP2_GW_TENANT_STARTUP_BASE_URL"' in gw_main
    assert "def build_tenant_startup_from_env" in gw_main
    assert gw_main.count("no silent fallback") >= 6, "every gateway selector keeps the fail-closed no-silent-fallback posture"
    dbr_main = _DBR_MAIN.read_text(encoding="utf-8")
    assert 'SP2_DBR_TENANT_STARTUP_HOST = "SP2_DBR_TENANT_STARTUP_HOST"' in dbr_main
    assert 'SP2_DBR_TENANT_STARTUP_PORT = "SP2_DBR_TENANT_STARTUP_PORT"' in dbr_main
    assert "def build_tenant_startup_server_from_env" in dbr_main


# ---------------------------------------------------------------------------
# 8. Governance: this slice closes no blocker
# ---------------------------------------------------------------------------
def test_stage_b_closes_no_blocker() -> None:
    guard_src = pathlib.Path(__file__).read_text(encoding="utf-8").lower()
    assert "closes no blocker" in guard_src, "the guard must declare that it closes no blocker"
    for module in (_GATEWAY, _GW_CLIENT, _DBR_OPS, _DBR_EDGE):
        text = module.read_text(encoding="utf-8").lower()
        for overclaim in ("production ready", "production-ready", "activates production", "blocker closed"):
            assert overclaim not in text, f"{module.name} must not overclaim ({overclaim})"


if __name__ == "__main__":
    _scan.run(
        [
            test_update_parser_single_allowlisted_field_closure,
            test_gateway_keeps_exactly_one_router_dispatch_call_site,
            test_gateway_client_adapter_boundaries,
            test_dbr_executor_boundaries_and_sole_mutable_column,
            test_dbr_internal_edge_boundaries,
            test_clm_durable_audit_partition_is_exactly_the_five_events,
            test_stage_b_closes_no_blocker,
            test_composition_selectors_pinned,
        ]
    )
