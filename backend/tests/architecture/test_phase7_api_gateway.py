"""Build Phase 7 guards: api_gateway stays an edge-only enforcement boundary.

The gateway MUST import no other service in-process (DAG independence; IC-010 §H/§M —
the Database Router and Authenticator are reached over transport ports), no database
driver (it never accesses a database; IC-010 §X), and — because it is edge-only and
needs no vendor provider zone — NO vendor/cloud SDK ANYWHERE in the package, including
under adapters/providers (IC-010 Anti-Vendor-Lock-In). This api_gateway-scoped check is
stricter than the repo-wide containment test, which permits vendor imports inside any
``adapters/providers/`` path.
"""

from __future__ import annotations

import ast
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

AG = _scan.BACKEND_ROOT / "api_gateway"
FORBIDDEN_SERVICES = ["auth_router", "control_plane", "database_router", "import_service", "lineage_service"]
FORBIDDEN_LIBS = [
    # database drivers (the gateway accesses no database)
    "psycopg2",
    "psycopg",
    "asyncpg",
    "sqlalchemy",
    "databases",
    "aiopg",
    # vendor / cloud SDKs (no vendor provider zone in the gateway)
    "supabase",
    "lovable",
    "boto3",
    "botocore",
    "azure",
    "google.cloud",
    "google.auth",
    # observability / telemetry SDKs (OBS-3): metrics stay vendor-neutral — no provider SDK
    "datadog",
    "ddtrace",
    "opentelemetry",
    "prometheus_client",
    "statsd",
    "sentry_sdk",
    "newrelic",
]


def _matches(mod: str, prefixes: list) -> bool:
    return any(mod == p or mod.startswith(p + ".") for p in prefixes)


def test_api_gateway_no_forbidden_imports() -> None:
    for f in _scan.py_files(AG):
        for mod in _scan.imported_modules(f):
            top = mod.split(".")[0]
            assert top not in FORBIDDEN_SERVICES, f"{_scan.relposix(f)} imports service '{mod}'"
            assert not _matches(mod, FORBIDDEN_LIBS), f"{_scan.relposix(f)} imports forbidden lib '{mod}'"


def _governing_contracts() -> list:
    """The GOVERNING_CONTRACTS list literal from api_gateway/__init__.py (AST; no import)."""
    tree = ast.parse((AG / "__init__.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == "GOVERNING_CONTRACTS" and isinstance(node.value, ast.List):
                    return [e.value for e in node.value.elts if isinstance(e, ast.Constant)]
    raise AssertionError("api_gateway GOVERNING_CONTRACTS list literal not found")


def test_api_gateway_governing_contracts_lock_ic010() -> None:
    # DRIFT-04 lock (V4 TRACE-1): the legacy traceability test only checks GOVERNING_CONTRACTS
    # is non-empty; this asserts the gateway's primary governing contract IC-010 is a member.
    assert "IC-010" in _governing_contracts(), "api_gateway must declare IC-010 in GOVERNING_CONTRACTS (DRIFT-04 lock)"


# --- 07E-2-X (RX-5): references-only field discipline for the router-dispatch shapes ------
# The RouteOutcome seam (and the GatewayResponse it maps into) must never grow a field that
# could smuggle a body / tenant id / DB handle / DSN / secret / credential / payload across
# the edge (IC-010 §G/§T/§154). This AST census pins every field's TYPE to a primitive/enum
# allow-set and blocks a forbidden field NAME, so drift fails the build instead of the review.
_MODELS = AG / "models.py"
_ALLOWED_FIELD_TYPES = {"int", "str", "bool", "Optional", "DispatchCategory"}
_FORBIDDEN_FIELD_NAMES = {
    "body",
    "payload",
    "data",
    "content",
    "dsn",
    "secret",
    "credential",
    "connection",
    "tenant_db",
    "route_ref",
}
_REFERENCES_ONLY_SHAPES = ["RouteOutcome", "GatewayResponse"]


def _find_classdef(source: str, name: str) -> "ast.ClassDef | None":
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    return None


def _annotation_type_names(annotation: ast.expr) -> set:
    names: set = set()
    for node in ast.walk(annotation):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
    return names


def _references_only_violations(source: str, class_name: str) -> list:
    """Field-name + field-type violations for a references-only dataclass. Returns the
    sentinel ``["<class> not found"]`` when the class is absent so an empty match set can
    NEVER read as a pass (non-vacuity, per the repo 07E-1 census convention)."""
    node = _find_classdef(source, class_name)
    if node is None:
        return [f"{class_name} not found"]
    fields = [s for s in node.body if isinstance(s, ast.AnnAssign) and isinstance(s.target, ast.Name)]
    if not fields:
        return [f"{class_name} declares no annotated fields"]
    violations: list = []
    for s in fields:
        fname = s.target.id  # type: ignore[union-attr]  # narrowed above
        if fname.lower() in _FORBIDDEN_FIELD_NAMES:
            violations.append(f"{class_name}.{fname}: forbidden field name")
        for tname in _annotation_type_names(s.annotation):
            if tname not in _ALLOWED_FIELD_TYPES:
                violations.append(f"{class_name}.{fname}: type '{tname}' outside references-only allow-set")
    return violations


def test_route_dispatch_shapes_are_references_only() -> None:
    source = _MODELS.read_text(encoding="utf-8")
    # Non-vacuity: RouteOutcome must exist (07E-2-X introduces it) — the guard cannot pass
    # on an empty match set.
    assert _find_classdef(source, "RouteOutcome") is not None, "RouteOutcome must be defined in api_gateway/models.py"
    for cls in _REFERENCES_ONLY_SHAPES:
        violations = _references_only_violations(source, cls)
        assert violations == [], f"{cls} references-only violations: {violations}"


def test_references_only_guard_flags_unsafe_fields() -> None:
    # Self-test companion: the guard MUST flag a forbidden field name, an unsafe field type,
    # and an absent class — otherwise it could silently pass on real drift.
    unsafe = (
        "from dataclasses import dataclass\n"
        "@dataclass(frozen=True)\n"
        "class RouteOutcome:\n"
        "    status: int\n"
        "    body: str\n"  # forbidden NAME (safe type)
        "    connection: object\n"  # forbidden NAME + unsafe TYPE
    )
    v = _references_only_violations(unsafe, "RouteOutcome")
    assert any("body" in x for x in v), v
    assert any("connection" in x for x in v), v
    assert any("object" in x for x in v), v
    # Absent class → sentinel (proves the non-vacuity guard rejects an empty match set).
    assert _references_only_violations("x = 1\n", "RouteOutcome") == ["RouteOutcome not found"]


if __name__ == "__main__":
    _scan.run(
        [
            test_api_gateway_no_forbidden_imports,
            test_api_gateway_governing_contracts_lock_ic010,
            test_route_dispatch_shapes_are_references_only,
            test_references_only_guard_flags_unsafe_fields,
        ]
    )
