"""Architecture guards for the Gateway-free MVP (EXPERIMENT BRANCH ONLY).

Section 9 of the experiment instruction is explicit: a removed guard must be replaced by a new
explicit invariant and an adversarial test, never merely deleted. Nothing in this file weakens
an existing guard — every pre-existing API Gateway guard stays green because the Gateway source
is untouched. What this file adds is the set of invariants that make the *new* design checkable,
each with a non-vacuity probe.

The invariants, in order of how much they matter:

* **GF-1** the MVP composition never imports ``api_gateway`` — proved by EXECUTION in a clean
  subprocess, not by reading source;
* **GF-2** the replacement is a LIBRARY, not a gateway: the shared kernel can reach no service,
  holds no route table, and performs no dispatch or forwarding;
* **GF-3** tenant authority has exactly one source, and client-supplied tenant/actor fields are
  not accepted request inputs anywhere;
* **GF-4** the Database Router still performs no authentication (the ``§H`` separation survives);
* **GF-5** the denial vocabulary and the audit action vocabulary are unchanged — no new
  ``public_code``, no new, renamed, or re-homed audit class;
* **GF-6** the documented Gateway-free topology contains no Gateway edge, no port 8820, and no
  internal tenant-Startup envelope edge.

Pure stdlib; runs under pytest and standalone.
"""

from __future__ import annotations

import ast
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

_BACKEND = _scan.BACKEND_ROOT
_KERNEL = _BACKEND / "shared" / "public_edge.py"
_TRANSPORT = _BACKEND / "shared" / "adapters" / "providers" / "public_edge_transport.py"
_AUTH_CLIENT = _BACKEND / "shared" / "adapters" / "providers" / "http_principal_authenticator.py"
_EDGE_AUDIT = _BACKEND / "shared" / "adapters" / "providers" / "edge_audit.py"
_STARTUP_EDGE = _BACKEND / "database_router" / "adapters" / "providers" / "http_public_startup_edge.py"
_WORKSPACE_EDGE = _BACKEND / "control_plane" / "adapters" / "providers" / "http_public_workspace_edge.py"
_DBR_PORTAL = _BACKEND / "database_router" / "portal.py"
_CP_PORTAL = _BACKEND / "control_plane" / "portal.py"
_TOPOLOGY = _BACKEND.parent / "docs" / "runbooks" / "gateway_free_mvp_topology.md"

_PUBLIC_EDGE_FILES = (_KERNEL, _TRANSPORT, _AUTH_CLIENT, _EDGE_AUDIT, _STARTUP_EDGE, _WORKSPACE_EDGE, _DBR_PORTAL, _CP_PORTAL)

_SERVICES = ("api_gateway", "auth_router", "database_router", "control_plane", "import_service", "lineage_service")

# The two public-edge application factories the Gateway-free MVP topology runs.
_MVP_FACTORIES = (
    "database_router.adapters.providers.http_public_startup_edge",
    "control_plane.adapters.providers.http_public_workspace_edge",
)


def _text(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def _import_tops(path: pathlib.Path) -> set:
    """Every top-level package name imported ANYWHERE in a module (including lazily)."""
    tops = set()
    for node in ast.walk(ast.parse(_text(path))):
        if isinstance(node, ast.Import):
            for alias in node.names:
                tops.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            tops.add(node.module.split(".")[0])
    return tops


def _docstring_ids(tree: ast.AST) -> set:
    """The ``id()`` of every docstring constant, so prose can be excluded from code checks.

    Load-bearing for this whole file. These modules document their own security posture at
    length, so a raw substring search finds the WORD in a docstring and reports a defect that
    does not exist — a guard that flags a sentence proves nothing. Comments never reach the AST
    at all, so excluding docstrings leaves exactly the executable text.
    """
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            first = node.body[0] if node.body else None
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                out.add(id(first.value))
    return out


def _code_strings(path: pathlib.Path) -> set:
    """Every string LITERAL that is not a docstring."""
    tree = ast.parse(_text(path))
    docs = _docstring_ids(tree)
    return {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs}


def _identifiers(path: pathlib.Path) -> set:
    """Every name, attribute, definition, argument and keyword identifier in a module."""
    names = set()
    for node in ast.walk(ast.parse(_text(path))):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.keyword) and node.arg:
            names.add(node.arg)
    return names


# ------------------------------------------------------------------------------------------
# GF-1 — the MVP composition never imports api_gateway (EXECUTED, not read)
# ------------------------------------------------------------------------------------------


def test_gf1_importing_the_mvp_public_edges_never_loads_api_gateway() -> None:
    """Import both MVP edge modules in a CLEAN subprocess and inspect ``sys.modules``.

    A source scan can be defeated by a lazy import inside a function; executing the import and
    then asking the interpreter what it actually loaded cannot. The subprocess starts with no
    pre-imported SnackPortal2 modules, so a hit is a genuine dependency.
    """
    program = (
        "import sys\n"
        "import " + _MVP_FACTORIES[0] + "\n"
        "import " + _MVP_FACTORIES[1] + "\n"
        "loaded = sorted(m for m in sys.modules if m.split('.')[0] == 'api_gateway')\n"
        "print('API_GATEWAY_MODULES=' + repr(loaded))\n"
    )
    result = subprocess.run([sys.executable, "-c", program], cwd=str(_BACKEND), capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, f"importing the MVP public edges failed: {result.stderr[-2000:]}"
    assert "API_GATEWAY_MODULES=[]" in result.stdout, (
        f"the Gateway-free MVP composition must load NO api_gateway module; got {result.stdout.strip()}"
    )


def test_gf1b_composing_both_mvp_edges_never_loads_api_gateway() -> None:
    """The same proof one level deeper: build both applications, then re-inspect ``sys.modules``.

    Importing a module is weaker than composing one — a composition root can pull a dependency
    in lazily at build time. This composes both real FastAPI applications over doubles and
    asserts the interpreter still never loaded ``api_gateway``.
    """
    program = (
        "import sys\n"
        "sys.path.insert(0, 'tests')\n"
        "from gateway_free._fakes import TwoTenantProvider, build_boundary\n"
        "from database_router.tenant_startup_ops import TenantStartupOperations\n"
        "from database_router.adapters.providers.http_public_startup_edge import make_app as startup_app\n"
        "from control_plane.adapters.providers.http_public_workspace_edge import make_app as workspace_app\n"
        "from control_plane.adapters.providers.in_memory_store import InMemoryControlStore\n"
        "from control_plane.main import ControlPlane\n"
        "boundary, _a, _b = build_boundary()\n"
        "startup_app(TenantStartupOperations(TwoTenantProvider()), boundary, ())\n"
        "workspace_app(ControlPlane(store=InMemoryControlStore()), boundary, ())\n"
        "loaded = sorted(m for m in sys.modules if m.split('.')[0] == 'api_gateway')\n"
        "print('API_GATEWAY_MODULES=' + repr(loaded))\n"
    )
    result = subprocess.run([sys.executable, "-c", program], cwd=str(_BACKEND), capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, f"composing the MVP public edges failed: {result.stderr[-2000:]}"
    assert "API_GATEWAY_MODULES=[]" in result.stdout, (
        f"composing the Gateway-free MVP must load NO api_gateway module; got {result.stdout.strip()}"
    )


def test_gf1c_no_public_edge_source_names_api_gateway() -> None:
    for path in _PUBLIC_EDGE_FILES:
        tops = _import_tops(path)
        assert "api_gateway" not in tops, f"{_scan.relposix(path)} imports api_gateway"


def test_gf1_nonvacuity() -> None:
    # The executed probe must be able to FAIL: a subprocess that does import api_gateway reports it.
    program = (
        "import sys\n"
        "import api_gateway.gateway\n"
        "loaded = sorted(m for m in sys.modules if m.split('.')[0] == 'api_gateway')\n"
        "print('API_GATEWAY_MODULES=' + repr(loaded))\n"
    )
    result = subprocess.run([sys.executable, "-c", program], cwd=str(_BACKEND), capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, f"the positive control could not import api_gateway: {result.stderr[-2000:]}"
    assert "API_GATEWAY_MODULES=[]" not in result.stdout, "the probe must detect a real api_gateway import"
    assert "'api_gateway.gateway'" in result.stdout, "the probe must name the loaded module"


# ------------------------------------------------------------------------------------------
# GF-2 — the replacement is a library, not a gateway under another name
# ------------------------------------------------------------------------------------------


def test_gf2_the_shared_kernel_can_reach_no_service() -> None:
    """``shared`` is a dependency leaf, so the kernel STRUCTURALLY cannot forward to a service.

    This is the load-bearing anti-gateway proof: a gateway's defining act is receiving a request
    for service A and handing it onward. A module that cannot name a service cannot do that, and
    the constraint is machine-enforced by an existing, unmodified import-linter contract.
    """
    for path in (_KERNEL, _TRANSPORT, _AUTH_CLIENT, _EDGE_AUDIT):
        tops = _import_tops(path)
        offenders = tops & set(_SERVICES)
        assert not offenders, f"{_scan.relposix(path)} must import no service; found {sorted(offenders)}"


def test_gf2b_the_kernel_holds_no_route_table_and_performs_no_dispatch() -> None:
    """No path classification, no route map, no service selection, no forwarding, no I/O.

    The kernel decides *who the caller is*. It never decides *where a request goes* — there is
    nowhere for it to send one.
    """
    identifiers = _identifiers(_KERNEL)
    for banned in ("urlopen", "urlretrieve", "Request", "HTTPConnection", "create_connection", "sendall", "recv"):
        assert banned not in identifiers, f"the kernel must perform no transport I/O; found the {banned!r} identifier"
    assert not (_import_tops(_KERNEL) & {"http", "socket", "requests", "httpx", "fastapi", "starlette"}), (
        "the kernel must import no transport or web-framework machinery — it decides identity, not destination"
    )
    definitions = {
        node.name.lower()
        for node in ast.walk(ast.parse(_text(_KERNEL)))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }
    for banned in ("dispatch", "classify", "route", "forward", "proxy", "upstream", "backend"):
        assert not any(banned in name for name in definitions), f"the kernel must define no {banned!r} function or class"
    # No literal route/path table: a gateway needs one, an authenticator does not.
    route_like = sorted(value for value in _code_strings(_KERNEL) if value.startswith("/") and len(value) > 1)
    assert route_like == [], f"the kernel must hold no route literals; found {route_like}"


def test_gf2c_each_public_edge_serves_one_route_family_only() -> None:
    """A gateway serves many families; an owner's edge serves its own.

    Every non-operational route literal on each edge must sit under that edge's single business
    prefix. ``/health`` and ``/readiness`` are operational and are excluded by name.
    """
    expected = {_STARTUP_EDGE: "/tenant/startups/", _WORKSPACE_EDGE: "/memberships"}
    operational = {"/health", "/readiness"}
    for path, prefix in expected.items():
        literals = {
            node.value
            for node in ast.walk(ast.parse(_text(path)))
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.startswith("/")
        }
        business = {value for value in literals if value not in operational}
        stray = {value for value in business if not value.startswith(prefix)}
        assert not stray, f"{_scan.relposix(path)} must serve only {prefix!r}; found {sorted(stray)}"


def test_gf2_nonvacuity() -> None:
    probe = "import api_gateway\n_ROUTES = {'/memberships': 1}\n\ndef dispatch_request(x):\n    return x\n"
    tree = ast.parse(probe)
    tops = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert tops & set(_SERVICES) == {"api_gateway"}, "the service-import probe must flag a bad sample"
    names = {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    assert any("dispatch" in name.lower() for name in names), "the dispatch-name probe must flag a bad sample"
    routes = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value.startswith("/")]
    assert routes == ["/memberships"], "the route-literal probe must flag a bad sample"


# ------------------------------------------------------------------------------------------
# GF-3 — tenant authority has exactly one source
# ------------------------------------------------------------------------------------------


def test_gf3_client_supplied_tenant_and_actor_fields_are_not_accepted_inputs() -> None:
    """``target_tenant_ref`` and ``actor_ref`` must never be READ from a request.

    Two separate checks, because the same word is lawful in one position and fatal in another:

    * as a string LITERAL it would be a lookup key into a caller-supplied structure — banned
      outright. This is the exact shape of the internal envelope edge's defect, where
      ``envelope["target_tenant_ref"]`` made the tenant a body field;
    * as a keyword ARGUMENT it is an output handed DOWN to the executor — lawful, but only if
      its value comes from the trusted principal, which is asserted by dataflow below.
    """
    for path in (_STARTUP_EDGE, _WORKSPACE_EDGE, _DBR_PORTAL, _CP_PORTAL):
        literals = _code_strings(path)
        for banned in ("target_tenant_ref", "actor_ref"):
            assert banned not in literals, f"{_scan.relposix(path)} uses {banned!r} as a string key — it must never be read from a request"

    trusted_sources = {"principal_ref", "correlation_id"}
    for path in (_STARTUP_EDGE, _WORKSPACE_EDGE):
        for node in ast.walk(ast.parse(_text(path))):
            if not isinstance(node, ast.keyword) or node.arg not in ("actor_ref", "tenant_ref", "target_tenant_ref", "subject_ref"):
                continue
            value = node.value
            if isinstance(value, ast.Attribute):
                assert value.attr in trusted_sources and isinstance(value.value, ast.Name) and value.value.id == "principal", (
                    f"{_scan.relposix(path)}: {node.arg} must come from the trusted principal, not {ast.dump(value)}"
                )
            else:
                assert isinstance(value, ast.Name) and value.id == "tenant_ref", (
                    f"{_scan.relposix(path)}: {node.arg} must come from require_tenant's result, not {ast.dump(value)}"
                )


def test_gf3b_the_accepted_update_field_set_is_exactly_one_allowlisted_field() -> None:
    """Proved by EXECUTION, not by pinning the shape of the comparison.

    A text pin on ``set(body.keys()) != {...}`` would keep passing if the check were rewritten
    into a subset test that spells the same tokens. Running the parser cannot be fooled that way.
    """
    from database_router.portal import parse_tenant_startup_update_request

    assert parse_tenant_startup_update_request(b'{"short_description":"ok"}').short_description == "ok"
    assert parse_tenant_startup_update_request(b'{"short_description":null}').short_description is None
    rejected = [
        b'{"short_description":"x","target_tenant_ref":"t-acme"}',
        b'{"short_description":"x","actor_ref":"p-other"}',
        b'{"target_tenant_ref":"t-acme"}',
        b"{}",
        b'{"short_description":123}',
        b'{"short_description":"' + b"y" * 501 + b'"}',
        b"not json",
        b"[]",
    ]
    for payload in rejected:
        try:
            parse_tenant_startup_update_request(payload)
        except ValueError:
            continue
        raise AssertionError(f"the bounded parser must refuse {payload[:60]!r}")


def test_gf3c_require_tenant_is_the_only_producer_of_a_tenant_id_at_the_edge() -> None:
    """The edge must obtain its tenant from ``require_tenant`` and from nowhere else."""
    tree = ast.parse(_text(_STARTUP_EDGE))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "require_tenant"
    ]
    assert len(calls) == 1, f"exactly one require_tenant call site; found {len(calls)}"
    assigns = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "tenant_ref" for t in node.targets)
    ]
    assert assigns == [], "tenant_ref must never be assigned from anything but the require_tenant tuple return"


def test_gf3_nonvacuity() -> None:
    import tempfile

    sample = 'def h(envelope):\n    """A docstring mentioning target_tenant_ref harmlessly."""\n    return envelope["target_tenant_ref"]\n'
    with tempfile.TemporaryDirectory() as tmp:
        probe = pathlib.Path(tmp) / "probe.py"
        probe.write_text(sample, encoding="utf-8")
        vocabulary = _code_strings(probe) | _identifiers(probe)
        assert "target_tenant_ref" in vocabulary, "the tenant-input probe must flag a real code use"

        prose_only = pathlib.Path(tmp) / "prose.py"
        prose_only.write_text('"""This module never reads target_tenant_ref or actor_ref."""\n\nX = 1\n', encoding="utf-8")
        prose_vocabulary = _code_strings(prose_only) | _identifiers(prose_only)
        assert "target_tenant_ref" not in prose_vocabulary, "the probe must NOT flag a docstring mention (guards must not flag sentences)"


# ------------------------------------------------------------------------------------------
# GF-4 — the Database Router still performs no authentication
# ------------------------------------------------------------------------------------------


def test_gf4_database_router_performs_no_authentication() -> None:
    """IC-010 §H's "the Database Router never authenticates" survives the architecture change.

    The public edge CONSUMES authentication through a transport port; it does not perform it.
    The distinction is machine-checkable: no JWT/JWKS/crypto/OIDC library and no sibling service
    may appear anywhere in ``database_router``, and the routing/resolution core must be free of
    every authentication token.
    """
    forbidden = ("jwt", "jose", "authlib", "oauthlib", "oidc", "cryptography")
    for f in _scan.py_files(_BACKEND / "database_router"):
        for mod in _scan.imported_modules(f):
            top = mod.split(".")[0]
            assert top not in set(_SERVICES) - {"database_router"}, f"{_scan.relposix(f)} imports another service '{mod}'"
            assert top not in forbidden, f"{_scan.relposix(f)} imports authentication machinery '{mod}'"

    for name in ("router.py", "resolver.py", "session_provider.py", "tenant_startup_ops.py"):
        path = _BACKEND / "database_router" / name
        vocabulary = _identifiers(path) | _code_strings(path)
        for token in ("authenticate", "Bearer", "Authorization", "jwks", "verify_signature", "PublicBoundary", "admit"):
            assert token not in vocabulary, f"database_router/{name} must contain no authentication logic; found {token!r} in code"


def test_gf4b_the_public_edge_reaches_authentication_only_through_a_port() -> None:
    """The edge CONSUMES authentication through an injected port; it never performs it."""
    tops = _import_tops(_STARTUP_EDGE)
    assert "auth_router" not in tops, "the public edge must not import the Auth Router — it reaches it over transport"
    assert not (tops & {"jwt", "jose", "authlib", "oauthlib", "cryptography"}), "the public edge must perform no token validation"
    assert "PublicBoundary" in _identifiers(_STARTUP_EDGE), "the public edge must consume authentication through the injected boundary"
    # The whole edge holds exactly one admission call site, so there is no second, weaker path in.
    admits = [
        node
        for node in ast.walk(ast.parse(_text(_STARTUP_EDGE)))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "admit"
    ]
    assert len(admits) == 1, f"exactly one boundary.admit call site on the edge; found {len(admits)}"


def test_gf4_nonvacuity() -> None:
    sample = "import jwt\nfrom auth_router.authenticator import Authenticator\n"
    tops = {a.name.split(".")[0] for n in ast.walk(ast.parse(sample)) if isinstance(n, ast.Import) for a in n.names}
    tops |= {n.module.split(".")[0] for n in ast.walk(ast.parse(sample)) if isinstance(n, ast.ImportFrom) and n.module}
    assert "jwt" in tops and "auth_router" in tops, "the authentication probe must flag a bad sample"


# ------------------------------------------------------------------------------------------
# GF-5 — no new public_code, no new audit class
# ------------------------------------------------------------------------------------------

_EXISTING_PUBLIC_CODES = frozenset({"unauthenticated", "forbidden", "carrier_mismatch", "isolation_anomaly", "not_found", "unavailable"})


def test_gf5_the_denial_vocabulary_introduces_no_new_public_code() -> None:
    tree = ast.parse(_text(_KERNEL))
    emitted = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "PublicBoundaryDenied":
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    emitted.add(arg.value)
    assert emitted, "the guard must find the denial constructions it is checking"
    assert emitted <= _EXISTING_PUBLIC_CODES, (
        f"the Gateway-free architecture must introduce no new public_code; found {sorted(emitted - _EXISTING_PUBLIC_CODES)}"
    )


def test_gf5b_the_audit_action_vocabulary_is_exactly_the_existing_store_set() -> None:
    """No audit class is added, removed, renamed, or re-homed — only the emitter changes."""
    from control_plane.gateway_audit import GATEWAY_AUDIT_STORE_ACTIONS
    from shared.public_edge import EDGE_AUDIT_ACTIONS

    assert set(EDGE_AUDIT_ACTIONS) == set(GATEWAY_AUDIT_STORE_ACTIONS), (
        "the public-edge action vocabulary must equal the Control-DB store vocabulary exactly, so the durable home is a no-op"
    )


def test_gf5c_the_durably_homed_partition_is_exactly_the_five_clm_classes() -> None:
    from shared.adapters.providers.edge_audit import DURABLE_EDGE_AUDIT_ACTIONS

    assert DURABLE_EDGE_AUDIT_ACTIONS == frozenset(
        {"workspace_memberships_read", "tenant_startup_read", "tenant_startup_update", "RouteDenied", "CarrierMismatch"}
    ), "the durable partition must stay exactly the five CLM-homed classes — no silent widening"


def test_gf5_nonvacuity() -> None:
    sample = ast.parse("raise PublicBoundaryDenied(418, 'teapot')")
    found = {
        arg.value
        for node in ast.walk(sample)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "PublicBoundaryDenied"
        for arg in node.args
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str)
    }
    assert found == {"teapot"} and not found <= _EXISTING_PUBLIC_CODES, "the public_code probe must flag a new code"


# ------------------------------------------------------------------------------------------
# GF-6 — the documented Gateway-free topology
# ------------------------------------------------------------------------------------------


def test_gf6_the_documented_topology_has_no_gateway_edge_and_no_8820() -> None:
    text = _text(_TOPOLOGY)
    table = [line for line in text.splitlines() if line.startswith("| 8") and "create_app_from_env" in line]
    assert len(table) == 5, f"the Gateway-free topology must document exactly five edges; found {len(table)}"
    modules = {line.split("`")[1].split(":")[0] for line in table}
    assert not any(module.startswith("api_gateway") for module in modules), f"no api_gateway edge may appear; got {sorted(modules)}"
    assert "http_tenant_startup_api" not in " ".join(modules), "the internal tenant-Startup envelope edge must not be in the MVP topology"
    ports = {int(line.split("|")[1].strip()) for line in table}
    assert 8820 not in ports, "port 8820 must not appear in the Gateway-free topology"
    assert not (ports & set(range(8080, 8089))), f"no standing edge may land in the isolated smoke range; got {sorted(ports)}"
    for required in _MVP_FACTORIES:
        assert required in text, f"the topology must name the MVP factory {required}"


def test_gf6b_the_topology_states_its_experimental_status() -> None:
    # Markdown emphasis is stripped so a guard rail cannot be defeated by bolding a word inside it.
    text = _text(_TOPOLOGY).lower().replace("*", "")
    for anchor in ("experiment branch only", "not the standing topology", "do-not-activate"):
        assert anchor in text, f"the topology document must carry the {anchor!r} guard rail"


def test_gf6_nonvacuity() -> None:
    bad = "| 8820 | API Gateway | public | `api_gateway.adapters.providers.http_gateway_edge:create_app_from_env` |"
    module = bad.split("`")[1].split(":")[0]
    assert module.startswith("api_gateway"), "the topology probe must flag a Gateway row"
    assert int(bad.split("|")[1].strip()) == 8820, "the port probe must read the port column"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
