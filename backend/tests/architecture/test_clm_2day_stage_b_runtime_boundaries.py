"""CLM — 2-Day Accelerated Controlled Local MVP Stage B runtime boundary guard (default suite; no DB, no network).

Static + pure-executable boundary pins for the D-42 Stage B implementation slice (the CLM
controlled-local rehearsal runtime): the two served tenant Startup routes, the bounded
single-field update, the tenant Startup data path, and the CLM durable-audit partition.
Companion to the Stage A contract guard (test_clm_2day_stage_a_contract_boundaries.py —
contract text) — THIS guard binds the code the Stage A code-closure note required to be
widened "in the same change".

**Migrated when the API Gateway was deleted.** Stage B's data path used to be
Gateway → [HTTP] → internal tenant-Startup envelope edge → executor. The Gateway and that
internal edge are both gone; the PUBLIC tenant Startup edge holds the executor in-process. Three
checks moved and two were withdrawn with their subject:

| Was | Now |
|---|---|
| the update parser lives in ``api_gateway/portal.py`` | ``database_router/portal.py`` — owner-resident |
| the gateway keeps exactly ONE ``router.dispatch`` call site | WITHDRAWN — nothing dispatches;
  ``test_public_edge_boundaries`` pins one ``boundary.admit`` site per edge instead |
| the Gateway-side transport client's bounds | WITHDRAWN — the executor is in-process, so there
  is no client; the surviving internal clients are bounded by
  ``test_ic010_control_read_adapter_boundaries`` |
| the internal envelope edge's boundaries | the PUBLIC Startup edge's boundaries (below), which additionally AUTHENTICATE |
| ``_CLM_DURABLE_ACTIONS`` in the Gateway root | ``DURABLE_EDGE_AUDIT_ACTIONS`` in
  ``shared/adapters/providers/edge_audit.py`` — the same five values |

It binds no live runtime, opens no socket, and touches no database: every check is AST/text
over the implementation modules or a call to a pure function (the update-body parser and
the two bounded route matchers are socket-free pure values).

This guard closes no blocker. B5-BLK-5 remains OPEN; the live blocker census remains 7 of 9
OPEN; production remains NOT READY / DO-NOT-ACTIVATE.

Pure stdlib + repository imports; standalone-runnable:
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

from database_router.portal import (  # noqa: E402
    TENANT_STARTUP_SHORT_DESCRIPTION_MAX_CHARS,
    TenantStartupUpdateRequestDTO,
    parse_tenant_startup_update_request,
)
from shared.adapters.providers.edge_audit import DURABLE_EDGE_AUDIT_ACTIONS  # noqa: E402
from shared.public_edge import (  # noqa: E402
    ACTION_CARRIER_MISMATCH,
    ACTION_CARRIER_ON_CONTROL_ANOMALY,
    ACTION_ISOLATION_ANOMALY,
    ACTION_ROUTE_DENIED,
    ACTION_TENANT_STARTUP_READ,
    ACTION_TENANT_STARTUP_UPDATE,
    ACTION_WORKSPACE_MEMBERSHIPS_READ,
)

_DBR = _scan.BACKEND_ROOT / "database_router"
_DBR_OPS = _DBR / "tenant_startup_ops.py"
_PUBLIC_EDGE = _DBR / "adapters" / "providers" / "http_public_startup_edge.py"
_DBR_MAIN = _DBR / "main.py"
_EDGE_AUDIT = _scan.BACKEND_ROOT / "shared" / "adapters" / "providers" / "edge_audit.py"

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
# 2/3. WITHDRAWN with their subject: the dispatch call-site rule and the
#      Gateway-side transport client. Recorded, not silently dropped.
# ---------------------------------------------------------------------------
def test_the_withdrawn_gateway_side_subjects_are_really_absent() -> None:
    """Stage B's Gateway-side halves had two checks; both subjects were deleted.

    Asserting the absence keeps "withdrawn deliberately" distinguishable from "forgotten", and
    names where each property lives now so a reader is never left wondering whether it was lost.
    """
    import importlib.util

    for gone in (
        "api_gateway",
        "api_gateway.gateway",
        "api_gateway.adapters.providers.http_tenant_startup",
        "database_router.adapters.providers.http_tenant_startup_api",
    ):
        try:
            found = importlib.util.find_spec(gone)
        except ModuleNotFoundError:
            found = None
        assert found is None, f"{gone} must not be importable — it was deleted with the API Gateway"
    # The successor properties exist and are guarded elsewhere; assert the guards themselves are
    # present so this record cannot point at nothing.
    for successor in ("test_public_edge_boundaries.py", "test_ic010_control_read_adapter_boundaries.py"):
        assert (pathlib.Path(__file__).parent / successor).is_file(), f"the successor guard {successor} must exist"


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
# 5. The PUBLIC tenant Startup edge: loopback, bounded methods, fail-closed, silent
# ---------------------------------------------------------------------------
def test_public_startup_edge_boundaries() -> None:
    assert _PUBLIC_EDGE.is_file(), "the public tenant Startup edge must exist"
    text = _PUBLIC_EDGE.read_text(encoding="utf-8")
    tree = _tree(_PUBLIC_EDGE)
    tops = _import_tops(_PUBLIC_EDGE)
    assert tops <= {"__future__", "json", "re", "typing", "fastapi", "database_router", "shared"}, (
        f"edge import surface violated: {sorted(tops)}"
    )
    assert not (tops & _FORBIDDEN_TOPS), "the public edge must import no driver/vendor/crypto/concurrency"
    served = _scan.registered_route_methods(tree)
    # The tenant family serves GET + PATCH (+ its OPTIONS preflight); health and readiness are GET.
    assert sorted(served) == ["get", "get", "get", "options", "patch"], f"the public edge's served method census drifted: {served}"
    assert 'host: str = "127.0.0.1"' in text, "the public edge must default to the loopback bind — exposure is a proxy decision"
    assert '"/tenant/startups/{startup_ref}"' in text, "the bounded parameterized family must be pinned"
    used = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)} | {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert "send_error" not in used, "the public edge must never call stdlib send_error"
    for marker in ("HTTPServer", "ThreadingHTTPServer", "ThreadingMixIn"):
        assert marker not in used, f"the public edge must hand-roll no server ({marker}); the shared runtime owns it"
    assert "build_asgi_server" in used, "the public edge must serve through the shared ASGI runtime"
    # STRICTLY STRONGER than the internal edge this replaces: it AUTHENTICATES before any executor
    # call. The internal edge read the tenant and actor from the request BODY.
    assert "admit" in used, "the public edge must admit through the shared boundary before any executor call"
    assert "require_tenant" in used, "the tenant must come from the signed claim, never from the request"
    # Request logging is silenced at the shared runtime (the migrated home of log_message).
    runtime = (_scan.BACKEND_ROOT / "shared" / "adapters" / "providers" / "asgi_runtime.py").read_text(encoding="utf-8")
    assert "access_log=False" in runtime and "log_config=None" in runtime, "request logging must stay silenced"


# ---------------------------------------------------------------------------
# 6. The CLM durable-audit partition homes EXACTLY the five ratified classes
# ---------------------------------------------------------------------------
def test_clm_durable_audit_partition_is_exactly_the_five_events() -> None:
    # D-43 (Post-10C.3 corrective): the durable set widened from four to exactly five —
    # adding the CarrierMismatch denial record and NO other audit class.
    assert frozenset(DURABLE_EDGE_AUDIT_ACTIONS) == frozenset(
        {
            ACTION_WORKSPACE_MEMBERSHIPS_READ,
            ACTION_TENANT_STARTUP_READ,
            ACTION_TENANT_STARTUP_UPDATE,
            ACTION_ROUTE_DENIED,
            ACTION_CARRIER_MISMATCH,
        }
    ), "the durably homed set is EXACTLY the IC-010 CLM audit evidence set (no wider audit expansion)"
    # The two remaining anomaly classes stay OUTSIDE the durable partition.
    for unhomed in (ACTION_CARRIER_ON_CONTROL_ANOMALY, ACTION_ISOLATION_ANOMALY):
        assert unhomed not in DURABLE_EDGE_AUDIT_ACTIONS, f"{unhomed} must stay on the in-memory no-sink emitter"
    # The durably homed actions carry EXACTLY the contract action strings. The emitter moved from
    # the Gateway to the route-owning edges; not one action string changed, which is what keeps
    # DDL 012's frozen CHECK satisfied without a schema migration.
    assert ACTION_TENANT_STARTUP_READ == "tenant_startup_read"
    assert ACTION_TENANT_STARTUP_UPDATE == "tenant_startup_update"
    assert ACTION_CARRIER_MISMATCH == "CarrierMismatch"


# ---------------------------------------------------------------------------
# 7. Composition selectors exist and stay fail-closed (no silent fallback)
# ---------------------------------------------------------------------------
def test_composition_selectors_pinned() -> None:
    dbr_main = _DBR_MAIN.read_text(encoding="utf-8")
    # The executor seam survives (the public edge composes through it); the two Gateway-facing
    # transport seams do not.
    assert "def build_tenant_startup_ops_from_env" in dbr_main, "the tenant Startup EXECUTOR seam must survive"
    assert 'SP2_DBR_PUBLIC_STARTUP_HOST = "SP2_DBR_PUBLIC_STARTUP_HOST"' in dbr_main
    assert 'SP2_DBR_PUBLIC_STARTUP_PORT = "SP2_DBR_PUBLIC_STARTUP_PORT"' in dbr_main
    assert 'SP2_EDGE_AUTH_ROUTER_BASE_URL = "SP2_EDGE_AUTH_ROUTER_BASE_URL"' in dbr_main, (
        "the public edge's REQUIRED authentication selector must be pinned — unset means no edge composes at all"
    )
    assert "def build_public_startup_edge_server_from_env" in dbr_main
    for gone in ("def build_tenant_startup_server_from_env", "def build_dispatch_server_from_env", "SP2_GW_"):
        assert gone not in dbr_main, f"{gone} went with the API Gateway and must not reappear"
    assert dbr_main.count("no silent fallback") >= 1, "the selector keeps the fail-closed no-silent-fallback posture"
    assert "fail closed" in dbr_main, "the composition root must document its fail-closed posture"


# ---------------------------------------------------------------------------
# 8. Governance: this slice closes no blocker
# ---------------------------------------------------------------------------
def test_stage_b_closes_no_blocker() -> None:
    guard_src = pathlib.Path(__file__).read_text(encoding="utf-8").lower()
    assert "closes no blocker" in guard_src, "the guard must declare that it closes no blocker"
    for module in (_DBR_OPS, _PUBLIC_EDGE, _EDGE_AUDIT):
        text = module.read_text(encoding="utf-8").lower()
        for overclaim in ("production ready", "production-ready", "activates production", "blocker closed"):
            assert overclaim not in text, f"{module.name} must not overclaim ({overclaim})"


if __name__ == "__main__":
    _scan.run(
        [
            test_update_parser_single_allowlisted_field_closure,
            test_the_withdrawn_gateway_side_subjects_are_really_absent,
            test_dbr_executor_boundaries_and_sole_mutable_column,
            test_public_startup_edge_boundaries,
            test_clm_durable_audit_partition_is_exactly_the_five_events,
            test_stage_b_closes_no_blocker,
            test_composition_selectors_pinned,
        ]
    )
