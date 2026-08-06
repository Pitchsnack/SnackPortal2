"""IC-012 deployment composition-root boundary guard (default suite; no DB, no network, no imports of the root).

Implements the nine checks required by **IC-012 §14** (opened by **D-44 — Deployment Cross-Service Composition
Root (Edge 9 Import Edge)**), independently of import-linter:

  1. Cross-service singularity   — ``deployment`` is the ONLY production package with a module importing more
                                   than one service package; service-local composition is out of scope.
  2. Direction                   — no service package and not ``shared`` imports ``deployment``, in any form
                                   (plain, aliased, function-local, ``importlib``, ``__import__``, string).
  3. Import-time inertness       — every cross-service import in ``deployment`` is function-local; module scope
                                   calls nothing, reads no env, opens no connection, binds no socket.
  4. Composition-only            — no SQL/DDL, no DSN literal, no credential, no route declaration, no
                                   authorization decision, no tenant-selection decision, no lineage record.
  5. Seam reuse                  — the Edge 9 factory composes via the owning services' published seams and via
                                   ``http_import_api.create_app``; it hand-builds no transport, pool, or app.
  6. Factory shape               — ``create_app_from_env`` takes no parameters, returns ``FastAPI``, binds no
                                   host/port.
  7. No server binding           — ``deployment`` imports no concrete ASGI server (IC-012 §12).
  8. Text-drift                  — the IC-012 §3/§4 direction tables and the §14 check list are pinned.
  9. Authorized composition set  — ``deployment`` imports nothing outside the exhaustive §3 set, and its module
                                   census matches §16 exactly.

Two further pins support the same boundary: the ``[tool.importlinter]`` configuration required by IC-012 §13
(both ``forbidden`` contracts, ``deployment`` in ``root_packages``, the independence contract intact, and no
``ignore_imports`` anywhere), and the D-44 register entry's non-overclaim line.

Every required anchor carries a planted-removal non-vacuity companion, and every forbidden-authorization
detector carries a planted probe that MUST trip it. This guard closes no blocker: B5-BLK-5 remains OPEN,
B5-BLK-8 remains OPEN, seven of nine blockers remain OPEN, and production remains NOT READY / DO-NOT-ACTIVATE
— the guard positively requires the register to say exactly that.

Pure stdlib; standalone-runnable:
  python tests/architecture/test_deployment_composition_root_boundaries.py
"""

from __future__ import annotations

import ast
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

_DEPLOYMENT = _scan.BACKEND_ROOT / "deployment"
_PYPROJECT = _scan.BACKEND_ROOT / "pyproject.toml"
_IC012 = _scan.REPO_ROOT / "contracts" / "IC-012-Service-Composition-And-Deployment-Root-Contract.md"
_ADR = _scan.REPO_ROOT / "docs" / "Architecture-Decision-Register.md"

# IC-012 §3: the exhaustive authorized cross-package set. `shared` is the dependency leaf; the three service
# packages are exactly what the proven Edge 9 composition requires.
_AUTHORIZED_SERVICES = ("database_router", "import_service", "lineage_service")
_UNAUTHORIZED_SERVICES = ("api_gateway", "auth_router", "control_plane")

# IC-012 §16: the exhaustive module census of the root.
_CENSUS = ("__init__.py", "import_edge.py")
_EDGE9 = "import_edge.py"
_FACTORY = "create_app_from_env"

# IC-012 §5/§6/§7: the published seams the Edge 9 factory MUST compose through (never re-derive).
_REQUIRED_SEAMS = (
    "build_router_from_env",
    "PgRoutedSessionProvider",
    "EnvTenantSecretStore",
    "build_import_service_from_env",
    "LineageEmit",
    "create_app",
)
# IC-012 §6/§17: hand-built collaborators the root may never construct itself.
_HAND_BUILT = ("psycopg", "connect", "ConnectionPool", "Pool", "RoutingReadTransport", "HttpRoutingRead", "SessionRegistry")
# IC-012 §5/§14 check 6: the factory owns no address and binds nothing.
_ADDRESS_TOKENS = ("host", "port", "bind", "listen", "serve_forever", "server_address", "build_asgi_server", "AsgiEdgeServer")
# IC-012 §12/§14 check 7: no concrete ASGI server anywhere in the root.
_ASGI_SERVERS = ("uvicorn", "hypercorn", "daphne", "gunicorn", "granian", "waitress")
# IC-012 §14 check 3: module scope materializes nothing.
_INERTNESS_TOKENS = ("environ", "getenv", "connect", "socket", "bind", "listen", "execute", "executemany", "resolve", "mkdir")
# IC-012 §17: excluded decision classes, detected as identifiers.
_AUTHZ_TOKENS = ("has_role", "is_authorized", "check_permission", "require_role", "require_permission", "authorize", "Permission", "Role")
_TENANT_SELECT_TOKENS = ("resolve_tenant", "select_database", "choose_database", "tenant_to_database", "dsn_for", "database_for")
_LINEAGE_TOKENS = ("LineageRecord", "LineageEvent", "lineage_record", "emit_lineage", "record_lineage", "hash_chain", "chain_hash")

_SQL = re.compile(
    r"\b(?:select\s+[\w*]+\s+from\b|insert\s+into\b|update\s+\w+\s+set\b|delete\s+from\b"
    r"|create\s+(?:table|index|schema|trigger)\b|alter\s+table\b|drop\s+(?:table|schema)\b)",
    re.IGNORECASE,
)
_DSN = re.compile(r"postgres(?:ql)?://|\bdbname\s*=|\bsslmode\s*=", re.IGNORECASE)
_CREDENTIAL = re.compile(r"\bpassword\s*[=:]|\bpgpassword\b|\bapi[_-]?key\s*[=:]", re.IGNORECASE)
_DYNAMIC_IMPORT = re.compile(r"""(?:import_module|__import__)\s*\(\s*["']deployment""")
_TEXT_IMPORT = re.compile(r"^\s*(?:from|import)\s+deployment\b", re.MULTILINE)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _production_files():
    """Every production ``.py`` file under ``backend/`` — tests are not production and are out of scope."""
    for path in _scan.py_files():
        rel = _scan.relposix(path)
        if rel.startswith("tests/"):
            continue
        yield path


def _service_tops(path: pathlib.Path) -> set:
    return {m.split(".")[0] for m in _scan.imported_modules(path) if m.split(".")[0] in _scan.SERVICE_PACKAGES}


def _deployment_files():
    assert _DEPLOYMENT.is_dir(), f"the deployment composition root must exist at {_DEPLOYMENT} (IC-012 §16)"
    return sorted(p for p in _DEPLOYMENT.glob("*.py"))


def _tree(path: pathlib.Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _names(node: ast.AST) -> set:
    out = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
    out |= {n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)}
    return out


def _func(tree: ast.AST, name: str):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _module_level(tree: ast.Module):
    """Top-level statements that are NOT a function or class definition — i.e. what runs at import."""
    return [n for n in tree.body if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]


def _docstrings(tree: ast.AST) -> set:
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc is not None:
                out.add(doc)
    return out


def _code_strings(tree: ast.AST) -> list:
    """Every string constant that is NOT a docstring — docstrings describe the boundary, code enacts it."""
    docs = _docstrings(tree)
    return [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value not in docs]


def _norm(s: str) -> str:
    """Lowercase, normalize dash/arrow glyphs, drop markdown emphasis, collapse whitespace."""
    s = s.lower()
    s = s.replace("—", "-").replace("–", "-").replace("→", "->")
    s = s.replace("*", "").replace("`", "")
    return re.sub(r"\s+", " ", s)


def _ic012() -> str:
    assert _IC012.is_file(), f"IC-012 must exist at {_IC012}"
    return _norm(_IC012.read_text(encoding="utf-8"))


def _d44() -> str:
    assert _ADR.is_file(), f"the decision register must exist at {_ADR}"
    text = _ADR.read_text(encoding="utf-8")
    start = text.find("### D-44 —")
    assert start != -1, "the register must carry the D-44 detail block"
    tail = text[start:]
    cut = tail.find("\n## Open")
    return _norm(tail if cut == -1 else tail[:cut])


_SECTIONS = {"ic012": _ic012, "d44": _d44}


def _corpus() -> str:
    return " ".join(getter() for getter in _SECTIONS.values())


# ---------------------------------------------------------------------------
# IC-012 §14 check 8 — the pinned contract text
# ---------------------------------------------------------------------------
# §3 authorized set (exhaustive) and the un-authorized forward edges.
_IC012_FORWARD = (
    "deployment ──> import_service",
    "deployment ──> database_router",
    "deployment ──> lineage_service",
    "deployment ──> shared",
)
_IC012_FORWARD_FORBIDDEN = (
    "deployment ─╳─> api_gateway",
    "deployment ─╳─> auth_router",
    "deployment ─╳─> control_plane",
)
# §4 prohibited reverse direction — the load-bearing back-channel prohibition.
_IC012_REVERSE = (
    "import_service ↛ database_router",
    "import_service ↛ lineage_service",
    "database_router ↛ import_service",
    "lineage_service ↛ import_service",
    "shared ↛ any service",
    "shared ↛ deployment",
    "api_gateway ↛ deployment",
    "auth_router ↛ deployment",
    "control_plane ↛ deployment",
    "database_router ↛ deployment",
    "import_service ↛ deployment",
    "lineage_service ↛ deployment",
)
# §14 — the nine guard checks this file implements, pinned by name.
_IC012_CHECKS = (
    "cross-service singularity",
    "no module under any service package or shared contains an import of deployment",
    "import-time inertness",
    "composition-only",
    "seam reuse",
    "factory shape",
    "no server binding",
    "text-drift",
    "authorized composition set",
)
# The normative statements that make the authority narrow, singular, and non-blanket.
_IC012_ANCHORS = (
    "single authorized cross-service composition root",
    "service-local composition is expressly preserved and is not centralized here",
    "cross-service composition -> deployment only",
    "this list is exhaustive and closed",
    "confers no blanket cross-service composition authority",
    "deployment must not be imported by anything",
    "the pre-existing service-independence contract remains in force verbatim and unweakened",
    "canonical native asgi application factory for edge 9",
    "it must take no arguments",
    "§5.1 - future cross-service deployment modules (governance gate - normative)",
    "ic-012 does not pre-authorize sibling modules",
    "any malformed required startup selector or composition value -> the factory must raise",
    "this does not alter the lazy secretref resolution rule in §9",
    "the module census above is exhaustive and is not open-ended",
    # Anchored under Gate A so the IC-012 M-2 DEFERRAL is tamper-evident. This §11 sentence is the
    # exact text that the retained Edge-9 code contradicts: `import_service/main.py` returns None when
    # SP2_IMPORT_AUDIT_SINK_BASE_URL is unset, and the composition falls to `InMemoryAuditSink()`. The
    # divergence is DEFERRED, not resolved — IC-012 stays Draft / Proposed and standing Import stays
    # disabled (IMPORT-A / D-3). Anchoring the sentence means a future silent NARROWING of the
    # contract, which would make the divergence disappear without anyone deciding to, turns this guard
    # red instead. Removing this anchor is itself the governed act.
    "there must be no fallback to an in-memory session provider, a lineage double, or a non-durable audit sink",
    "degraded composition is prohibited, not merely discouraged",
    "backend/deployment/__init__.py",
    "backend/deployment/import_edge.py",
    "deployment must not be added to it",
    "lint-imports must report 0 broken contracts",
)
# D-44 register anchors: the ratified narrow grant plus the standing non-overclaim census.
_D44_ANCHORS = (
    "d-44 - deployment cross-service composition root (edge 9 import edge)",
    "api_gateway, auth_router, and control_plane are not authorized and must not be imported",
    "no service package and not shared may import deployment",
    "no blanket future authority",
    "atr-2b-1 (http-refusal hardening) and at-d15t1-10 (one worker / one os process per edge) are unaffected and remain open",
    "d-44 closes no blocker",
    "b5-blk-5 remains open",
    "b5-blk-8 remains open",
    "seven of nine blockers remain open",
    "production remains not ready / do-not-activate",
    "physical multi-database mvp mandatory and unchanged",
)

# Forbidden-authorization detectors: (regex, label, planted probe). Green control = the regex matches NONE of
# the real IC-012 + D-44 corpus; each planted probe MUST trip it.
_FORBIDDEN = (
    (
        r"(?:grants|confers)\s+blanket\s+cross-service\s+composition\s+authority",
        "Blanket-composition-authority",
        "This contract confers blanket cross-service composition authority.",
    ),
    (
        r"deployment(?:\s+root)?\s+may\s+import\s+any\s+service",
        "Unnarrowed-import-width",
        "The deployment root may import any service it happens to need.",
    ),
    (
        r"(?:sibling|future)\s+(?:cross-service\s+)?modules?\s+(?:are|is)\s+pre-authorized",
        "Pre-authorized-sibling-modules",
        "Future cross-service modules are pre-authorized by conformance alone.",
    ),
    (
        r"import_service\s+may\s+import\s+(?:database_router|lineage_service)",
        "Independence-weakened",
        "For Edge 9 the import_service may import database_router directly.",
    ),
    (
        r"(?:api_gateway|auth_router|control_plane)\s+(?:is|are)\s+(?:also\s+)?authorized",
        "Unauthorized-service-granted",
        "For future edges control_plane is authorized for the composition root.",
    ),
    (
        r"a\s+second\s+cross-service\s+composition\s+root\s+(?:is|may\s+be)\s+(?:permitted|introduced|authorized)",
        "Second-composition-root",
        "A second cross-service composition root is permitted for the audit edges.",
    ),
    (
        r"(?:routed\s+)?session\s+(?:may|can)\s+be\s+(?:serialized|proxied|carried\s+over\s+http)",
        "Session-crosses-the-wire",
        "A routed session may be carried over HTTP when the edge is remote.",
    ),
)


# ---------------------------------------------------------------------------
# IC-012 §14 check 1 — cross-service singularity (service-local composition is OUT OF SCOPE)
# ---------------------------------------------------------------------------
def test_check1_deployment_is_the_only_cross_service_composer() -> None:
    cross_service = []
    for path in _production_files():
        rel = _scan.relposix(path)
        tops = _service_tops(path)
        if rel.startswith("deployment/"):
            if len(tops) > 1:
                cross_service.append(rel)
            continue
        # A service composing its OWN objects is not a cross-service composition root and is not flagged:
        # only importing a SECOND service package is.
        assert len(tops) <= 1, f"{rel} imports more than one service package {sorted(tops)} — only deployment may (IC-012 §14.1)"
    assert cross_service == [f"deployment/{_EDGE9}"], (
        f"deployment must be the one cross-service composer, via {_EDGE9} alone (found {cross_service}) — IC-012 §14.1"
    )


# ---------------------------------------------------------------------------
# IC-012 §14 check 2 — direction: nothing may import the root
# ---------------------------------------------------------------------------
def test_check2_nothing_imports_the_deployment_root() -> None:
    for path in _production_files():
        rel = _scan.relposix(path)
        if rel.startswith("deployment/"):
            continue
        for mod in _scan.imported_modules(path):
            assert mod.split(".")[0] != "deployment", f"{rel} imports the composition root ({mod}) — nothing may (IC-012 §4)"
        text = path.read_text(encoding="utf-8")
        assert not _DYNAMIC_IMPORT.search(text), f"{rel} reaches the composition root through a dynamic import — nothing may (IC-012 §4)"
        assert not _TEXT_IMPORT.search(text), f"{rel} textually imports the composition root — nothing may (IC-012 §4)"


# ---------------------------------------------------------------------------
# IC-012 §14 check 3 — import-time inertness
# ---------------------------------------------------------------------------
def test_check3_deployment_is_import_time_inert() -> None:
    for path in _deployment_files():
        rel = _scan.relposix(path)
        tree = _tree(path)
        top = _module_level(tree)
        for node in top:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                mod = node.module if isinstance(node, ast.ImportFrom) else node.names[0].name
                first = (mod or "").split(".")[0]
                assert first not in _scan.SERVICE_PACKAGES, (
                    f"{rel} imports the service package '{first}' at module scope — every cross-service import "
                    "must be function-local so the root stays import-time inert (IC-012 §14.3)"
                )
                continue
            calls = [n for n in ast.walk(node) if isinstance(n, ast.Call)]
            assert not calls, f"{rel} performs a call at module scope — the root composes only when a factory is CALLED (IC-012 §1)"
            for banned in _INERTNESS_TOKENS:
                assert banned not in _names(node), f"{rel} references '{banned}' at module scope — the root must be inert (IC-012 §14.3)"
    # Positive control: the Edge 9 factory really does hold the cross-service imports function-locally.
    factory = _func(_tree(_DEPLOYMENT / _EDGE9), _FACTORY)
    assert factory is not None, f"{_EDGE9} must expose {_FACTORY} (IC-012 §5)"
    local = {n.module.split(".")[0] for n in ast.walk(factory) if isinstance(n, ast.ImportFrom) and n.module}
    for svc in _AUTHORIZED_SERVICES:
        assert svc in local, f"{_FACTORY} must import '{svc}' function-locally (IC-012 §3 / §14.3)"


# ---------------------------------------------------------------------------
# IC-012 §14 check 4 — composition-only (§17 exclusions)
# ---------------------------------------------------------------------------
def test_check4_deployment_is_composition_only() -> None:
    for path in _deployment_files():
        rel = _scan.relposix(path)
        tree = _tree(path)
        for literal in _code_strings(tree):
            assert not _SQL.search(literal), f"{rel} carries SQL/DDL text — the root holds no query and no schema statement (IC-012 §17)"
            assert not _DSN.search(literal), f"{rel} carries a DSN literal — the root holds no DSN (IC-012 §9 / §17)"
            assert not _CREDENTIAL.search(literal), f"{rel} carries a credential literal — secrets are reference-only (D-14; IC-012 §9)"
        assert _scan.registered_route_methods(tree) == [], f"{rel} declares an HTTP route — the root serves nothing (IC-012 §17)"
        used = _names(tree)
        for banned in _AUTHZ_TOKENS:
            assert banned not in used, f"{rel} decides authorization ('{banned}') — no authorization policy in the root (IC-012 §17)"
        for banned in _TENANT_SELECT_TOKENS:
            assert banned not in used, f"{rel} selects a tenant ('{banned}') — the Database Router is the sole selector (IC-012 §6)"
        for banned in _LINEAGE_TOKENS:
            assert banned not in used, f"{rel} builds a lineage record ('{banned}') — lineage semantics are lineage_service's (IC-012 §7)"


# ---------------------------------------------------------------------------
# IC-012 §14 check 5 — seam reuse, not re-derivation
# ---------------------------------------------------------------------------
def test_check5_edge9_factory_reuses_published_seams() -> None:
    factory = _func(_tree(_DEPLOYMENT / _EDGE9), _FACTORY)
    assert factory is not None
    used = _names(factory)
    for seam in _REQUIRED_SEAMS:
        assert seam in used, f"{_FACTORY} must compose through the published seam '{seam}' — the root re-derives no wiring (IC-012 §5)"
    for banned in _HAND_BUILT:
        assert banned not in used, f"{_FACTORY} must not hand-build '{banned}' — that composition belongs to its owning service (IC-012 §6)"
    called = {n.func.id for n in ast.walk(factory) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "FastAPI" not in called, f"{_FACTORY} must build the app via http_import_api.create_app, not by constructing FastAPI (IC-012 §5)"


# ---------------------------------------------------------------------------
# IC-012 §14 check 6 — factory shape
# ---------------------------------------------------------------------------
def test_check6_edge9_factory_shape() -> None:
    tree = _tree(_DEPLOYMENT / _EDGE9)
    factory = _func(tree, _FACTORY)
    assert factory is not None
    args = factory.args
    total = len(args.posonlyargs) + len(args.args) + len(args.kwonlyargs)
    assert total == 0 and args.vararg is None and args.kwarg is None, (
        f"{_FACTORY} must take NO arguments — host and port belong to the runtime process (IC-012 §5); found {total}"
    )
    returns = factory.returns
    assert isinstance(returns, ast.Name) and returns.id == "FastAPI", f"{_FACTORY} must be annotated -> FastAPI (IC-012 §5)"
    used = _names(factory)
    for banned in _ADDRESS_TOKENS:
        assert banned not in used, f"{_FACTORY} must not reference '{banned}' — the factory binds no socket and owns no address (IC-012 §5)"
    exported = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    assert _FACTORY in exported, f"{_EDGE9} must export {_FACTORY} in __all__ (IC-012 §16)"


# ---------------------------------------------------------------------------
# IC-012 §14 check 7 — no concrete ASGI server
# ---------------------------------------------------------------------------
def test_check7_deployment_imports_no_concrete_asgi_server() -> None:
    for path in _deployment_files():
        rel = _scan.relposix(path)
        tops = {m.split(".")[0] for m in _scan.imported_modules(path)}
        for server in _ASGI_SERVERS:
            assert server not in tops, f"{rel} imports the concrete ASGI server '{server}' — the root produces an app only (IC-012 §12)"


# ---------------------------------------------------------------------------
# IC-012 §14 check 8 — contract text-drift pins
# ---------------------------------------------------------------------------
def test_check8_ic012_direction_text_is_pinned() -> None:
    ic012 = _ic012()
    for needle in _IC012_FORWARD:
        assert needle in ic012, f"IC-012 §3 must pin the authorized edge: {needle!r}"
    for needle in _IC012_FORWARD_FORBIDDEN:
        assert needle in ic012, f"IC-012 §3 must pin the UN-authorized forward edge: {needle!r}"
    for needle in _IC012_REVERSE:
        assert needle in ic012, f"IC-012 §4 must pin the prohibited reverse edge: {needle!r}"
    for needle in _IC012_CHECKS:
        assert needle in ic012, f"IC-012 §14 must name the guard check: {needle!r}"
    for needle in _IC012_ANCHORS:
        assert needle in ic012, f"IC-012 must carry the normative anchor: {needle!r}"
    assert "status: draft / proposed" in ic012, "IC-012 must remain Draft / Proposed until independent verification and human merge (§19)"
    assert "revision: ic-012-draft-1" in ic012, "IC-012 must declare revision IC-012-DRAFT-1"
    assert "production remains not ready / do-not-activate" in ic012, "IC-012 must restate the standing production posture"


def test_check8_register_carries_d44_without_overclaim() -> None:
    d44 = _d44()
    for needle in _D44_ANCHORS:
        assert needle in d44, f"the D-44 register entry must carry: {needle!r}"
    assert "status: ✅ approved" in d44, "D-44 must be ratified (Approved) in the register"


# ---------------------------------------------------------------------------
# IC-012 §14 check 9 — authorized composition set + module census
# ---------------------------------------------------------------------------
def test_check9_authorized_composition_set_and_module_census() -> None:
    census = sorted(p.name for p in _deployment_files())
    assert census == sorted(_CENSUS), f"the deployment module census must match IC-012 §16 exactly: want {sorted(_CENSUS)}, got {census}"
    extra = [p.name for p in _DEPLOYMENT.iterdir() if p.is_dir() and p.name != "__pycache__"]
    assert extra == [], f"IC-012 §16 admits no sub-package under deployment (found {extra}); one needs the §5.1 amendment gate"
    for path in _deployment_files():
        rel = _scan.relposix(path)
        text = path.read_text(encoding="utf-8")
        for mod in _scan.imported_modules(path):
            top = mod.split(".")[0]
            if top in _scan.SERVICE_PACKAGES:
                assert top in _AUTHORIZED_SERVICES, (
                    f"{rel} imports '{mod}' — outside the exhaustive IC-012 §3 authorized set "
                    f"{list(_AUTHORIZED_SERVICES)}; widening it requires the §5.1 amendment (IC-012 §14.9)"
                )
        for unauthorized in _UNAUTHORIZED_SERVICES:
            assert not re.search(rf"^\s*(?:from|import)\s+{unauthorized}\b", text, re.MULTILINE), (
                f"{rel} imports the un-authorized service '{unauthorized}' (IC-012 §3)"
            )
            assert not re.search(rf"""(?:import_module|__import__)\s*\(\s*["']{unauthorized}""", text), (
                f"{rel} dynamically imports the un-authorized service '{unauthorized}' (IC-012 §3)"
            )


# ---------------------------------------------------------------------------
# IC-012 §13 / §19 — the import-linter configuration is the machine enforcement
# ---------------------------------------------------------------------------
def test_importlinter_config_enforces_ic012_section13() -> None:
    toml = _PYPROJECT.read_text(encoding="utf-8")
    linter = toml[toml.index("[tool.importlinter]") :]
    assert '"deployment",' in linter, "deployment must be listed in root_packages so the root is POLICED, not merely unlisted (IC-012 §13)"
    assert 'name = "nothing may import the deployment composition root (it is the top of the DAG)"' in linter, (
        "the reverse forbidden contract (nothing imports the root) must be present (IC-012 §13)"
    )
    assert 'name = "the deployment root may compose only the authorized Edge 9 services"' in linter, (
        "the forward-narrowing forbidden contract must be present (IC-012 §13)"
    )
    # The pre-existing service-independence contract must survive verbatim and unweakened.
    independence = (
        "[[tool.importlinter.contracts]]\n"
        'name = "services are mutually independent (no service imports another)"\n'
        'type = "independence"\n'
        "modules = [\n"
        '  "api_gateway",\n'
        '  "auth_router",\n'
        '  "database_router",\n'
        '  "control_plane",\n'
        '  "import_service",\n'
        '  "lineage_service",\n'
        "]\n"
    )
    assert independence in toml, "the service-independence contract must remain byte-identical and unweakened (IC-012 §13; D-44 (10))"
    assert "deployment" not in independence, "deployment must never be added to the independence contract (IC-012 §13)"
    assert "ignore_imports" not in linter, "no ignore_imports exemption may exist anywhere under [tool.importlinter] (IC-012 §13)"


# ---------------------------------------------------------------------------
# B-10 — the package docstring states the ratified, narrow boundary
# ---------------------------------------------------------------------------
def test_deployment_docstring_cites_the_ratified_governance() -> None:
    doc = ast.get_docstring(_tree(_DEPLOYMENT / "__init__.py")) or ""
    for citation in ("D-44", "IC-012"):
        assert citation in doc, f"the deployment package docstring must cite {citation} — the root is governed, not self-declared"
    for stale in ("not yet named by a governing IC", "requires ratification", "MAY import any service", "may import any service"):
        assert stale not in doc, f"the deployment package docstring must not retain the pre-ratification wording {stale!r}"
    for svc in _AUTHORIZED_SERVICES + ("shared",):
        assert svc in doc, f"the docstring must state the narrow authorized import set — '{svc}' missing (IC-012 §3)"
    for svc in _UNAUTHORIZED_SERVICES:
        assert svc in doc, f"the docstring must name '{svc}' as NOT authorized (IC-012 §3)"


# ---------------------------------------------------------------------------
# Forbidden authorizations: green control + planted-probe proof
# ---------------------------------------------------------------------------
def test_forbidden_authorizations_absent() -> None:
    corpus = _corpus()
    for pattern, label, _probe in _FORBIDDEN:
        assert re.search(pattern, corpus) is None, f"forbidden authorization present ({label}): /{pattern}/"


def test_forbidden_detectors_catch_probes() -> None:
    corpus = _corpus()
    for pattern, label, probe in _FORBIDDEN:
        norm_probe = _norm(probe)
        assert re.search(pattern, norm_probe), f"detector must fire on its probe ({label}): /{pattern}/"
        assert norm_probe not in corpus, f"probe wording must be absent from the real corpus ({label})"


# ---------------------------------------------------------------------------
# Non-vacuity: every detector in this file can actually observe a violation
# ---------------------------------------------------------------------------
def test_detectors_are_non_vacuous() -> None:
    # Text pins: removing an anchor makes its presence check fail.
    ic012 = _ic012()
    for needle in _IC012_FORWARD + _IC012_FORWARD_FORBIDDEN + _IC012_REVERSE + _IC012_CHECKS + _IC012_ANCHORS:
        assert needle not in ic012.replace(needle, ""), f"IC-012 anchor detector is vacuous: {needle!r}"
    d44 = _d44()
    for needle in _D44_ANCHORS:
        assert needle not in d44.replace(needle, ""), f"D-44 anchor detector is vacuous: {needle!r}"
    # AST pins: each violation shape is detectable in a synthetic module.
    offender = ast.parse("import api_gateway\nimport database_router\n")
    tops = {m.split(".")[0] for m in ([a.name for n in ast.walk(offender) if isinstance(n, ast.Import) for a in n.names])}
    assert len(tops & set(_scan.SERVICE_PACKAGES)) == 2, "a two-service module must be detectable (check 1)"
    assert _DYNAMIC_IMPORT.search('importlib.import_module("deployment.import_edge")'), "a dynamic root import must be detectable (check 2)"
    assert _TEXT_IMPORT.search("from deployment import import_edge\n"), "a textual root import must be detectable (check 2)"
    eager = ast.parse("x = build_router_from_env()\n")
    assert [n for n in ast.walk(_module_level(eager)[0]) if isinstance(n, ast.Call)], "a module-scope call must be detectable (check 3)"
    assert _SQL.search("SELECT id FROM tenant"), "SQL must be detectable (check 4)"
    assert _DSN.search("postgresql://u@h/db"), "a DSN literal must be detectable (check 4)"
    assert _CREDENTIAL.search("password=hunter2"), "a credential literal must be detectable (check 4)"
    routed = ast.parse("@app.get('/x')\ndef f():\n    pass\n")
    assert _scan.registered_route_methods(routed) == ["get"], "a route declaration must be detectable (check 4)"
    shaped = _func(ast.parse("def create_app_from_env(host):\n    return build_asgi_server(1)\n"), _FACTORY)
    assert shaped is not None and len(shaped.args.args) == 1, "a parameterized factory must be detectable (check 6)"
    assert "build_asgi_server" in _names(shaped), "a socket-binding factory must be detectable (check 6)"
    # Docstrings are excluded from the literal scan, and non-docstring literals are not.
    sample = ast.parse('"""doc SELECT a FROM b"""\nq = "SELECT a FROM b"\n')
    assert _code_strings(sample) == ["SELECT a FROM b"], "the literal scan must skip docstrings and see code strings (check 4)"
    assert len(_CENSUS) == 2 and len(_AUTHORIZED_SERVICES) == 3 and len(_UNAUTHORIZED_SERVICES) == 3, (
        "the census and the authorized/un-authorized partition must stay exactly as IC-012 §3/§16 ratified them"
    )


if __name__ == "__main__":
    _scan.run(
        [
            test_check1_deployment_is_the_only_cross_service_composer,
            test_check2_nothing_imports_the_deployment_root,
            test_check3_deployment_is_import_time_inert,
            test_check4_deployment_is_composition_only,
            test_check5_edge9_factory_reuses_published_seams,
            test_check6_edge9_factory_shape,
            test_check7_deployment_imports_no_concrete_asgi_server,
            test_check8_ic012_direction_text_is_pinned,
            test_check8_register_carries_d44_without_overclaim,
            test_check9_authorized_composition_set_and_module_census,
            test_importlinter_config_enforces_ic012_section13,
            test_deployment_docstring_cites_the_ratified_governance,
            test_forbidden_authorizations_absent,
            test_forbidden_detectors_catch_probes,
            test_detectors_are_non_vacuous,
        ]
    )
