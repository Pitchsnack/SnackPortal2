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
  internal tenant-Startup envelope edge;
* **GF-9** the public workspace edge holds ONE read capability and nothing else — proved by
  source, by parameter type, and by walking the object graph a composed edge actually holds.

Pure stdlib; runs under pytest and standalone.
"""

from __future__ import annotations

import ast
import os
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

# The commit immediately BEFORE the API Gateway was deleted. GF-8 reads the Gateway's own
# sources out of git at this commit, because the baseline it establishes is a fact about the
# component that was removed — and that fact cannot be measured against an empty directory.
_PRE_REMOVAL_COMMIT = "8719f4f3"

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
        # APPEND, never insert(0). `backend/tests` contains EMPTY packages named after the
        # services (tests/database_router/, tests/control_plane/, tests/shared/). Putting it
        # first makes those stubs win over the production packages, and this census then cannot
        # see a dependency declared in a service's own __init__.py — the guard goes blind
        # exactly where a module-level import would sit. Verified by mutation: with insert(0),
        # `import api_gateway.gateway` added to database_router/__init__.py still printed [].
        "sys.path.append('tests')\n"
        "from gateway_free._fakes import TwoTenantProvider, build_boundary\n"
        "from database_router.tenant_startup_ops import TenantStartupOperations\n"
        "from database_router.adapters.providers.http_public_startup_edge import make_app as startup_app\n"
        "from control_plane.adapters.providers.http_public_workspace_edge import make_app as workspace_app\n"
        "from control_plane.adapters.providers.control_membership_reader import ControlStoreMembershipReader\n"
        "from control_plane.adapters.providers.control_store_factory import SharedControlStoreFactory\n"
        "from control_plane.adapters.providers.in_memory_store import InMemoryControlStore\n"
        "boundary, _a, _b = build_boundary()\n"
        "startup_app(TenantStartupOperations(TwoTenantProvider()), boundary, ())\n"
        "reader = ControlStoreMembershipReader(SharedControlStoreFactory(InMemoryControlStore()))\n"
        "workspace_app(reader, boundary, ())\n"
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
    """The executed probe must be able to FAIL - and it must fail for the RIGHT reason.

    The original positive control imported ``api_gateway.gateway`` in a clean subprocess and
    asserted the census saw it. That package is now deleted, so the same program raises
    ``ModuleNotFoundError``: the control would "detect" nothing, and its non-zero exit would look
    like a broken probe rather than a working detector.

    The control therefore imports a package that DOES exist and asserts the census reports it. That
    is the property under test - the ``sys.modules`` census genuinely sees a loaded service - and it
    now holds independently of which packages survive. The deleted package's own absence is proved
    separately by ``test_gf1_the_deleted_package_is_unimportable``.
    """
    program = (
        "import sys\n"
        "import auth_router.main\n"
        "loaded = sorted(m for m in sys.modules if m.split('.')[0] == 'auth_router')\n"
        "print('PROBE_MODULES=' + repr(loaded))\n"
    )
    result = subprocess.run([sys.executable, "-c", program], cwd=str(_BACKEND), capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, f"the positive control could not import the probe package: {result.stderr[-2000:]}"
    assert "PROBE_MODULES=" in result.stdout, "the positive control must report what the interpreter loaded"
    reported = result.stdout.split("PROBE_MODULES=", 1)[1]
    assert "auth_router" in reported, f"the sys.modules census must SEE a loaded service package; got {reported.strip()}"


def test_gf1_the_deleted_package_is_unimportable() -> None:
    """The other half of GF-1's non-vacuity: ``api_gateway`` is not merely unloaded, it is GONE.

    Executed, not read: a clean subprocess is asked to import it and must fail with
    ``ModuleNotFoundError``. A stale editable-install finder, an empty leftover directory or a
    ``.pth`` entry pointing at another worktree would each make this succeed - and that is exactly
    the class of residue a source-level census cannot see.
    """
    result = subprocess.run([sys.executable, "-c", "import api_gateway\n"], cwd=str(_BACKEND), capture_output=True, text=True, timeout=180)
    assert result.returncode != 0, "api_gateway must NOT be importable - it was deleted"
    assert "ModuleNotFoundError" in result.stderr, (
        f"the failure must be a genuine absence, not an error raised inside a surviving package: {result.stderr[-2000:]}"
    )


def test_gf1_probes_resolve_the_PRODUCTION_packages_not_the_test_stubs() -> None:
    """The census is only as good as which ``database_router`` the subprocess actually loaded.

    ``backend/tests`` contains EMPTY packages named after the services. If a probe puts that
    directory FIRST on ``sys.path``, those stubs shadow the production packages and the
    ``sys.modules`` census silently stops seeing anything declared in a service's own
    ``__init__.py``. An independent review found exactly that defect in GF-1b and demonstrated
    it with an A/B mutation; this test is what stops it coming back.
    """
    stubs = [_BACKEND / "tests" / name / "__init__.py" for name in ("database_router", "control_plane", "shared")]
    assert all(path.is_file() for path in stubs), "the shadowing stubs really do exist — that is why this test is needed"

    program = (
        "import sys\n"
        "sys.path.append('tests')\n"
        "import database_router, control_plane, shared\n"
        "print('RESOLVED=' + repr([m.__file__ for m in (database_router, control_plane, shared)]))\n"
    )
    result = subprocess.run([sys.executable, "-c", program], cwd=str(_BACKEND), capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, result.stderr[-2000:]
    resolved = result.stdout.strip()
    assert "tests" not in resolved.replace("\\\\", "/").replace("backend/tests", "").lower() or "backend\\\\tests" not in resolved, resolved
    for package in ("database_router", "control_plane", "shared"):
        assert f"backend\\\\{package}\\\\__init__" in resolved or f"backend/{package}/__init__" in resolved, (
            f"{package} must resolve to the PRODUCTION package, not the test stub; got {resolved}"
        )

    # And the negative control: putting `tests` first really does shadow them.
    shadowed = subprocess.run(
        [sys.executable, "-c", program.replace("sys.path.append", "sys.path.insert(0,", 1).replace("('tests')", "'tests')", 1)],
        cwd=str(_BACKEND),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert shadowed.returncode == 0, shadowed.stderr[-2000:]
    assert "tests" in shadowed.stdout, "negative control: tests-first must visibly shadow the production packages"


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
    from control_plane.gateway_audit import EDGE_AUDIT_STORE_ACTIONS
    from shared.public_edge import EDGE_AUDIT_ACTIONS

    assert set(EDGE_AUDIT_ACTIONS) == set(EDGE_AUDIT_STORE_ACTIONS), (
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


# ------------------------------------------------------------------------------------------
# GF-8 — the PRIVILEGE POSTURE of the public tier (a characterisation, not an approval)
# ------------------------------------------------------------------------------------------


def _imported_modules_of_tree(tree):
    """Absolute imported module names from an already-parsed tree (the `_scan.imported_modules`
    contract, for source that is read from git rather than from disk)."""
    mods = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            mods.append(node.module)
    return mods


def test_gf8_the_api_gateway_public_tier_was_credential_free_and_driver_free() -> None:
    """What ``main`` has today, stated as a fact so the comparison cannot be fudged.

    The Gateway is the only internet-facing process on ``main``, and it is STRUCTURALLY incapable
    of touching a database: driver containment permits drivers only under
    ``database_router/adapters/providers/`` and ``control_plane/adapters/providers/``, and every
    Gateway selector is non-secret routing config. Compromising it yields no database access.

    **This guard WENT VACUOUS when the package was deleted and has been repaired.** It used to walk
    ``_scan.py_files(_BACKEND / "api_gateway")``; that generator now yields nothing, so the loop body
    never executed and the test passed with ZERO assertions run — while remaining the baseline half
    of the entire privilege-regression argument. A silently-passing baseline is worse than no
    baseline, because the comparison in GF-8b then rests on nothing.

    The repair reads the deleted sources back out of git at the pre-removal commit, so the baseline
    is measured against the real Gateway rather than against an empty directory, and the census
    asserts it saw a non-empty file set before it asserts anything about the contents.
    """
    import subprocess

    drivers = {"psycopg", "psycopg2", "asyncpg", "sqlalchemy", "databases", "aiopg"}
    secrets = {"EnvTenantSecretStore", "EnvReferenceSecretStore", "SecretRef", "SecretStore"}
    listing = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", _PRE_REMOVAL_COMMIT, "backend/api_gateway"],
        cwd=str(_scan.REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert listing.returncode == 0, f"the pre-removal Gateway tree must be readable from git: {listing.stderr[-400:]}"
    modules = [p for p in listing.stdout.split() if p.endswith(".py")]
    # NON-VACUITY, first: the baseline must be measured against a real, non-empty package. This is
    # the assertion whose absence let the original version pass on an empty directory.
    assert len(modules) >= 15, f"the pre-removal Gateway must have at least 15 modules to measure; found {len(modules)}"
    checked = 0
    for rel in modules:
        blob = subprocess.run(
            ["git", "show", f"{_PRE_REMOVAL_COMMIT}:{rel}"], cwd=str(_scan.REPO_ROOT), capture_output=True, text=True, timeout=120
        )
        assert blob.returncode == 0, f"could not read {rel} at {_PRE_REMOVAL_COMMIT}"
        tree = ast.parse(blob.stdout, filename=rel)
        tops = {m.split(".")[0] for m in _imported_modules_of_tree(tree)}
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        assert not (tops & drivers), f"{rel} imported a database driver"
        assert not (names & secrets), f"{rel} named a credential store"
        checked += 1
    assert checked == len(modules), "every pre-removal Gateway module must have been inspected"


def test_gf8b_KNOWN_REGRESSION_the_gateway_free_public_tier_holds_database_credentials() -> None:
    """The dominant security consequence of removing the Gateway. Pinned, not buried.

    Because each public edge executes its own data access IN-PROCESS — the very thing that
    removes the hop — the internet-facing processes are composed INSIDE the credential-holding,
    driver-permitted zones. The Gateway was not only a request boundary, it was a PRIVILEGE
    boundary: a public tier that provably could not reach a database. Removing it collapses that
    tier. Nothing here says the trade is wrong — plenty of systems let a service expose its own
    API — but it is a decision, it is Dan's to make, and this test exists so it cannot be made
    silently.

    **Scope note (Workspace privilege narrowing).** This test originally pinned TWO instances of
    the regression. The workspace half asserted that the workspace edge is handed the whole
    ``ControlPlane`` — a defect, deliberately enshrined so it could not be lost. That defect has
    now been CORRECTED, so its assertion is inverted and moved to the GF-9 family below, which
    proves the narrowing positively and structurally. Nothing is weakened: a stronger, executed
    check replaced a source-text characterisation, and the guard's alerting purpose is preserved
    — GF-9 fails the moment the workspace edge is handed a broad object again.

    What remains here is the Startup half, UNCHANGED and still true: that edge's composition
    reaches ``build_router_from_env``, which wires ``EnvTenantSecretStore`` (every tenant's
    database credential) and ``PsycopgConnectionFactory``. It is explicitly out of scope for the
    workspace narrowing, and if it ever stops holding, the result document's risk section is
    stale — which is exactly when someone should re-read it.
    """
    dbr_main = _text(_BACKEND / "database_router" / "main.py")
    assert "build_public_startup_edge_deps_from_env" in dbr_main
    assert "build_tenant_startup_ops_from_env" in dbr_main and "build_router_from_env" in dbr_main
    for credential_bearing in ("EnvTenantSecretStore", "PsycopgConnectionFactory"):
        assert credential_bearing in dbr_main, (
            f"the public Startup edge's composition root still wires {credential_bearing} — the public tier holds tenant credentials"
        )

    # The full ControlPlane really does carry the privileged collaborators — which is WHY the
    # workspace edge must not be handed one. Retained as the statement of what GF-9 excludes.
    from control_plane.main import ControlPlane

    assigned = {
        node.attr
        for node in ast.walk(
            next(
                n
                for n in ast.walk(ast.parse(_text(_BACKEND / "control_plane" / "main.py")))
                if isinstance(n, ast.ClassDef) and n.name == "ControlPlane"
            )
        )
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "self"
    }
    for privileged in ("provisioning", "recovery", "secret_store", "store_factory"):
        assert privileged in assigned, f"ControlPlane composes {privileged!r} — the object GF-9 keeps out of the public workspace edge"
    assert ControlPlane is not None  # imported to prove the module composes, not merely parses


# ------------------------------------------------------------------------------------------
# GF-9 — the PUBLIC WORKSPACE EDGE holds one read capability and nothing else
# ------------------------------------------------------------------------------------------
#
# GF-8b above characterises the privilege collapse the Gateway removal causes. GF-9 is the
# correction for the workspace half of it, and it is asserted three ways because each way alone
# has a known blind spot:
#
#   * by SOURCE   (GF-9a) — the composition root no longer builds a ControlPlane. Cheap and
#     readable, but an AST call-name check can be satisfied while the posture is unchanged
#     (call ``create_app()`` under another name, or extract an accessor from it and hand that
#     over). So this is the weakest leg and is never relied on alone.
#   * by TYPE     (GF-9b) — the edge's own signature declares the narrow port. This is what
#     makes the narrowing survive an unrelated future edit: a handler cannot reach for a
#     capability its parameter type does not declare without widening the signature first.
#   * by EXECUTION (GF-9c/GF-9d) — the composition is RUN and the resulting object graph is
#     walked. This is the leg that cannot be talked around: it inspects what the process
#     actually holds, not what the source appears to say.
#
# HONEST LIMIT, stated here so the guard is never read as proving more than it does: this proves
# OBJECT-GRAPH narrowing, not PROCESS narrowing. ``control_plane.main`` stays importable in the
# workspace process, so code already inside that process can still rebuild a plane; and whichever
# ``SNACKPORTAL_SECRET_*`` values the process is started with remain resolvable by anything that
# constructs a wide enough allow-list. Narrowing the process is an environment/credential change,
# NOT a code change, and is deliberately out of this guard's scope.

# The exact capability TYPES the public workspace process must not hold, discovered from
# control_plane/main.py's own composition (both the in-memory and the postgres variants of each).
_FORBIDDEN_CAPABILITY_TYPES = frozenset(
    {
        "ControlPlane",
        # provisioning — CREATE DATABASE
        "InMemoryProvisioningOperator",
        "PostgresProvisioningOperator",
        # lifecycle mutation gate (CAS + audit + ledger writes); never posture-guarded
        "ProvisioningVerificationService",
        "_LazyControlEvidenceGate",
        # schema application / migration
        "InMemoryTenantSchemaApplicator",
        "PostgresTenantSchemaApplicator",
        # onboarding
        "OnboardingOrchestrator",
        "_MixedPostureOnboardingGuard",
        # recovery / compensation — DROP DATABASE — and orphan scanning
        "RecoveryCompensationService",
        "OrphanScanService",
        "_MixedPostureRecoveryGuard",
        "InMemoryRecoveryInspection",
        "PostgresRecoveryInspection",
        # distinctness evidence ledger
        "InMemoryDistinctnessLedger",
        "PostgresDistinctnessLedger",
        # mutation-oriented Control-Plane services
        "TenantRegistry",
        "MembershipRegistry",
        "GlobalDirectory",
        "FederationStore",
        "ControlPlaneAudit",
        "BootstrapController",
        # the tenant-DSN resolver (every tenant database credential)
        "EnvTenantDsnSecretStore",
    }
)

# The exact capability METHODS, by name, from the classes above.
_FORBIDDEN_CAPABILITY_METHODS = frozenset(
    {
        "provision",
        "deprovision",
        "deprovision_tenant_database",
        "apply_schema",
        "onboard",
        "recover",
        "reassociate",
        "disable_routing",
        "scan_for_orphans",
    }
)

# The Control-DB WRITE surface of the ControlStore port.
_CONTROL_STORE_WRITE_METHODS = frozenset(
    {
        "put_tenant",
        "compare_and_swap_tenant",
        "put_membership",
        "put_federation",
        "put_directory_record",
        "append_audit",
    }
)

# The POSITIVE census: every type name the composed workspace deps may legitimately reach.
# This is the load-bearing check, and it is an ALLOW-list on purpose. The deny-lists above name
# today's privileged classes and methods; they cannot, even in principle, catch a NEW privileged
# class with a NEW method name — an independent adversarial review demonstrated exactly that.
# An allow-list inverts the burden: anything not named here fails the guard, so a capability
# arriving under any name at all has to be argued for in this list, in review.
#
# The composed graph is ~18 objects, so this stays small and readable — that smallness IS the
# narrowing. If this list ever needs to grow by a Control-Plane service, the narrowing is over.
_ALLOWED_REACHABLE_TYPES = frozenset(
    {
        # the narrow read capability and the per-unit-of-work factories behind it
        "ControlStoreMembershipReader",
        "SharedControlStoreFactory",
        "PostgresControlStoreFactory",
        "InMemoryControlStore",  # test-only store retained by the UNSET posture (see GF-9d)
        # the Control-DB secret binding — a reference and its resolver, never a DSN literal
        "EnvReferenceSecretStore",
        "SecretRef",
        # the public-boundary kernel and its two injected ports
        "PublicBoundary",
        "HttpPrincipalAuthenticator",
        "InMemoryEdgeAudit",
        "DurableEdgeAuditPartition",
        "BoundedEdgeAuditPolicy",
        "HttpEdgeAudit",
        # CPython's ABC bookkeeping (``_abc_impl``), surfaced by the class-attribute traversal.
        # Allow-listed by TYPE rather than skipped by attribute name: nothing can make a
        # ControlPlane *be* an ``_abc_data``, whereas a name-based skip would be a hole.
        "_abc_data",
        # plain data
        "NoneType",
        "bool",
        "bytes",
        "dict",
        "float",
        "frozenset",
        "int",
        "list",
        "set",
        "str",
        "tuple",
        "type",
    }
)

_ATOMIC = (str, bytes, bytearray, int, float, complex, bool, type(None))

# Attributes that hold captured objects without ever being an instance attribute.
_INDIRECT_HOLDERS = ("func", "args", "keywords", "fget", "fset", "__wrapped__", "__defaults__", "__kwdefaults__")


def _reachable(root: object, limit: int = 20000) -> list:
    """Every object reachable from ``root`` by attribute / container traversal.

    Deliberately traverses PRIVATE attributes, bound-method owners, **closure cells**, **class
    attributes**, ``property`` accessors and ``functools.partial`` internals. An object hidden
    behind a leading underscore — or behind no name at all — is still held by the process, and
    "we only call the safe method" is exactly the reasoning this guard exists to refuse.

    The closure/partial/class-attribute legs are not hypothetical: an independent adversarial
    review smuggled a full ``ControlPlane`` into the composed deps through a single closure cell
    and every gate in this repository stayed green. A capability captured by a lambda is held
    just as firmly as one assigned to ``self``.

    Classes, modules and ``__globals__`` are traversal STOPS. Following a module namespace means
    walking the interpreter, and it would also collapse the distinction this guard is careful
    about: it proves the composed OBJECT GRAPH is narrow, not that the process is (see the
    family note above).
    """
    seen: set = set()
    out: list = []
    stack = [root]
    while stack and len(out) < limit:
        obj = stack.pop()
        if id(obj) in seen:
            continue
        seen.add(id(obj))
        out.append(obj)
        if isinstance(obj, _ATOMIC) or isinstance(obj, type) or type(obj).__name__ == "module":
            continue
        if isinstance(obj, dict):
            stack.extend(list(obj.keys()) + list(obj.values()))
            continue
        if isinstance(obj, (list, tuple, set, frozenset)):
            stack.extend(list(obj))
            continue
        state = getattr(obj, "__dict__", None)
        if isinstance(state, dict):
            stack.extend(state.values())
        for slot in getattr(type(obj), "__slots__", ()) or ():
            try:
                stack.append(getattr(obj, slot))
            except AttributeError:
                pass
        owner = getattr(obj, "__self__", None)  # a bound method carries the object it came from
        if owner is not None:
            stack.append(owner)
        for cell in getattr(obj, "__closure__", None) or ():  # a lambda's captured objects
            try:
                stack.append(cell.cell_contents)
            except ValueError:
                pass  # an empty cell
        for name in _INDIRECT_HOLDERS:  # functools.partial, property accessors, wrappers, defaults
            held = getattr(obj, name, None)
            if held is not None and not isinstance(held, type):
                stack.append(held)
        for name, value in vars(type(obj)).items():  # a capability parked as a CLASS attribute
            if not name.startswith("__") and not callable(value):
                stack.append(value)
    return out


def _capability_offences(root: object, *, include_store_writes: bool) -> dict:
    """The privilege verdict on one composed object graph.

    ``unexpected`` is the strongest key and is checked first by every caller: it is the positive
    census, so it catches capability arriving under a name no deny-list anticipated. The three
    deny-list keys are retained because they name the *specific* objects this narrowing removed,
    which is what makes a failure message diagnostic rather than merely red.
    """
    objects = _reachable(root)
    if len(objects) >= 20000:
        raise AssertionError("the reachability walk hit its bound — a truncated walk cannot clear a composition")
    methods = set(_FORBIDDEN_CAPABILITY_METHODS)
    if include_store_writes:
        methods |= _CONTROL_STORE_WRITE_METHODS
    present = {type(obj).__name__ for obj in objects}
    return {
        "unexpected": sorted(present - _ALLOWED_REACHABLE_TYPES),
        "types": sorted(present & _FORBIDDEN_CAPABILITY_TYPES),
        "methods": sorted({f"{type(obj).__name__}.{name}" for obj in objects for name in methods if hasattr(obj, name)}),
        "admin_refs": sorted({obj for obj in objects if isinstance(obj, str) and "provisioning-admin" in obj}),
    }


def _composed_workspace_deps(control_store: str) -> tuple:
    """Run the REAL env composition for the public workspace edge and return its deps.

    Inert by construction: both transport clients are lazy, both store factories are
    lazy-connect, and no bind knob is read — so nothing is dialled, connected, or bound. The
    Auth Router URL is an RFC 2606 reserved host, so even a future accidental probe could not
    reach a standing service. Env is saved and restored by the caller.
    """
    import control_plane.main as cp_main

    deps = cp_main.build_public_workspace_edge_deps_from_env()
    assert deps is not None, f"the workspace composition must be ACTIVE for this probe (SP2_CP_CONTROL_STORE={control_store!r})"
    return deps


def _with_workspace_env(control_store: str, fn, *, live_postgres: bool = False):
    """Run ``fn`` under the workspace-edge composition env, restoring every variable after.

    ``live_postgres`` selects the ALL-POSTGRES composition (all four selectors), which is the
    ONLY posture in which the old ``create_app()`` path bound ``PROVISIONING_ADMIN_DSN_REF``,
    composed the real ``PostgresProvisioningOperator`` (``CREATE DATABASE``) and left
    ``RecoveryCompensationService`` un-guarded (``DROP DATABASE``). Running the probe there is
    what makes the ``admin_refs`` assertion mean something instead of passing by absence.
    Composition remains lazy-connect, so this still opens no socket and no connection.
    """
    import control_plane.main as cp_main

    names = (
        cp_main.SP2_EDGE_AUTH_ROUTER_BASE_URL,
        cp_main.SP2_EDGE_AUDIT_SINK_BASE_URL,
        cp_main.SP2_EDGE_ALLOWED_ORIGINS,
        cp_main.CONTROL_STORE_ENV,
        cp_main.PROVISIONING_ADAPTER_ENV,
        cp_main.TENANT_SCHEMA_APPLICATOR_ENV,
        cp_main.DISTINCTNESS_LEDGER_ENV,
    )
    saved = {name: os.environ.get(name) for name in names}
    try:
        for name in names:
            os.environ.pop(name, None)
        # RFC 2606 reserved host: structurally valid for the selector and it can never resolve.
        os.environ[cp_main.SP2_EDGE_AUTH_ROUTER_BASE_URL] = "http://auth.invalid"
        if control_store:
            os.environ[cp_main.CONTROL_STORE_ENV] = control_store
        if live_postgres:
            for name in (cp_main.PROVISIONING_ADAPTER_ENV, cp_main.TENANT_SCHEMA_APPLICATOR_ENV, cp_main.DISTINCTNESS_LEDGER_ENV):
                os.environ[name] = "postgres"
        return fn()
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def test_gf9a_the_workspace_composition_root_builds_no_control_plane() -> None:
    """SOURCE leg: the composition function neither calls ``create_app`` nor names ``ControlPlane``.

    Asserted on the AST of the two functions themselves, so a docstring or a stale comment
    cannot satisfy it. This is the weakest of the three legs by design — see the family note
    above — and GF-9c is what actually settles the question.
    """
    cp_tree = ast.parse(_text(_BACKEND / "control_plane" / "main.py"))
    for fn_name in ("build_public_workspace_edge_deps_from_env", "build_workspace_membership_reader_from_env"):
        fn = next(node for node in ast.walk(cp_tree) if isinstance(node, ast.FunctionDef) and node.name == fn_name)
        called = {node.func.id for node in ast.walk(fn) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
        assert "create_app" not in called, f"{fn_name} must not build a ControlPlane for the public workspace edge"
        assert "ControlPlane" not in called, f"{fn_name} must not construct a ControlPlane directly"
        docs = _docstring_ids(fn)
        names = {n.id for n in ast.walk(fn) if isinstance(n, ast.Name)} | {
            n.value for n in ast.walk(fn) if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs
        }
        assert "ControlPlane" not in names, f"{fn_name} must not reference ControlPlane in executable code"


def test_gf9b_the_workspace_edge_declares_the_narrow_read_port_as_its_dependency() -> None:
    """TYPE leg: the edge's public constructors are ANNOTATED to the one-method read port.

    An AST call-name check (GF-9a) can be satisfied without the posture changing; a parameter
    TYPE cannot. This is what stops a future handler quietly reaching for a privileged method —
    it would first have to widen a signature that this guard reads.
    """
    tree = ast.parse(_text(_WORKSPACE_EDGE))
    for fn_name in ("make_app", "build_public_workspace_edge_server"):
        fn = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == fn_name)
        first = fn.args.args[0]
        assert first.annotation is not None, f"{fn_name}'s first parameter must be explicitly typed"
        rendered = ast.unparse(first.annotation).strip("\"'")
        assert rendered == "WorkspaceMembershipReadPort", (
            f"{fn_name} must declare the narrow read port as its Control-Plane dependency; got {rendered!r}"
        )
    # And the narrow port really is narrow: exactly ONE abstract method.
    from control_plane.ports import WorkspaceMembershipReadPort

    abstracts = sorted(getattr(WorkspaceMembershipReadPort, "__abstractmethods__", frozenset()))
    assert abstracts == ["memberships_for_principal"], f"the read port must declare exactly one operation; got {abstracts}"
    own = sorted(n for n, v in vars(WorkspaceMembershipReadPort).items() if callable(v) and not n.startswith("_"))
    assert own == ["memberships_for_principal"], f"the read port must define no other method; got {own}"


def test_gf9c_the_composed_workspace_edge_holds_no_privileged_capability() -> None:
    """EXECUTION leg: compose for real, then walk the object graph the process would hold.

    Run under all THREE postures, because they used to compose very different planes:

    * **durable** (``SP2_CP_CONTROL_STORE=postgres``, live selectors unset) — the only durable
      posture the runbook prescribes;
    * **all-postgres** (all four selectors) — the ONLY posture in which the old ``create_app()``
      path bound ``PROVISIONING_ADMIN_DSN_REF`` and composed the real ``CREATE``/``DROP DATABASE``
      operators. Running here is what makes ``admin_refs`` a real assertion rather than one that
      passes because the credential was never in play;
    * **default** (everything unset) — the test-only in-memory composition.

    The durable and all-postgres postures must additionally hold NO Control-DB WRITE method: only
    the test-only default retains a writer, and GF-9d pins that exception exactly.
    """
    for label, store, live, writes in (
        ("durable", "postgres", False, True),
        ("all-postgres", "postgres", True, True),
        ("default", "", False, False),
    ):
        offences = _with_workspace_env(
            store,
            lambda store=store, writes=writes: _capability_offences(_composed_workspace_deps(store), include_store_writes=writes),
            live_postgres=live,
        )
        # The POSITIVE census first: it is the only leg that catches capability arriving under a
        # name no deny-list anticipated.
        assert offences["unexpected"] == [], f"{label} workspace composition reaches an unapproved type: {offences['unexpected']}"
        assert offences["types"] == [], f"{label} workspace composition holds a privileged capability object: {offences['types']}"
        assert offences["methods"] == [], f"{label} workspace composition exposes a privileged/mutating method: {offences['methods']}"
        assert offences["admin_refs"] == [], (
            f"{label} workspace composition carries a provisioning-admin reference: {offences['admin_refs']}"
        )


def test_gf9d_the_only_control_db_writer_the_default_posture_retains_is_the_test_only_store() -> None:
    """The ONE documented exception, pinned so it can never quietly become something else.

    ``SharedControlStoreFactory`` (the UNSET/test-only posture) retains the process-local
    ``InMemoryControlStore``, which carries the whole ``ControlStore`` port — writes included —
    because a factory that yields a store must be able to reach one. That is a property of the
    in-memory test double, not of the durable path: ``PostgresControlStoreFactory`` retains only
    a secret reference and a resolver, which is why GF-9c can demand zero writers there.

    This test states the exception exactly. If the durable posture ever starts retaining a
    writer, GF-9c fails; if the default posture starts retaining a DIFFERENT writer, this fails.
    """
    writers = _with_workspace_env(
        "",
        lambda: sorted(
            {
                type(obj).__name__
                for obj in _reachable(_composed_workspace_deps(""))
                if any(hasattr(obj, name) for name in _CONTROL_STORE_WRITE_METHODS)
            }
        ),
    )
    assert writers == ["InMemoryControlStore"], (
        f"the default posture may retain exactly the test-only in-memory store as a writer; got {writers}"
    )


def test_gf9_nonvacuity() -> None:
    """The probes must FLAG a real ControlPlane — otherwise GF-9c proves nothing.

    A synthetic, controlled forbidden dependency: the very object the narrowing removed is
    dropped into a deps-shaped tuple and run through the SAME predicate the guard uses. No
    source is modified and nothing is left behind.
    """
    from control_plane.adapters.providers.in_memory_store import InMemoryControlStore
    from control_plane.main import ControlPlane

    synthetic = (ControlPlane(store=InMemoryControlStore()), object(), ())
    offences = _capability_offences(synthetic, include_store_writes=True)
    assert "ControlPlane" in offences["types"], "the type probe must flag an injected ControlPlane"
    for expected in ("OnboardingOrchestrator", "RecoveryCompensationService", "OrphanScanService", "TenantRegistry"):
        assert expected in offences["types"], f"the type probe must reach {expected} through the ControlPlane"
    for verb in ("onboard", "deprovision_tenant_database", "scan_for_orphans", "provision"):
        assert any(entry.endswith("." + verb) for entry in offences["methods"]), f"the method probe must flag {verb!r}"
    assert any(name.endswith(".put_tenant") for name in offences["methods"]), "the write probe must flag put_tenant"

    # The signature probe must equally reject a widened annotation.
    bad = ast.parse("def make_app(control_plane: 'ControlPlane', boundary, origins=()): ...")
    first = next(n for n in ast.walk(bad) if isinstance(n, ast.FunctionDef)).args.args[0]
    assert ast.unparse(first.annotation).strip("\"'") != "WorkspaceMembershipReadPort", "the signature probe must reject a broad annotation"

    # Every SMUGGLING SHAPE the walk must defeat. Each of these was demonstrated by an
    # independent adversarial review against an earlier version of this guard; the closure case
    # in particular got a full ControlPlane into the composed deps with all five GF-9 tests, the
    # whole 2163-test suite, ruff, mypy and import-linter green. A capability is held whether it
    # sits on `self`, on the class, in a closure cell, inside a partial, or behind a property.
    import functools

    plane = lambda: ControlPlane(store=InMemoryControlStore())  # noqa: E731 — a fresh plane per shape

    class _PrivateAttr:
        def __init__(self) -> None:
            self._secret = plane()

    class _ClassAttr:
        held = plane()

    class _Property:
        _held = plane()

        @property
        def anything(self):
            return self._held

    captured = plane()
    _default_held = plane()

    def _defaulted(_p=_default_held):
        return _p

    shapes = {
        "private attribute": _PrivateAttr(),
        "class attribute": _ClassAttr(),
        "property-backed attribute": _Property(),
        "bound method owner": plane().control_store_unit_of_work,
        "closure cell": (lambda: captured),
        "functools.partial argument": functools.partial(len, plane()),
        "default argument": _defaulted,
        "nested container": {"deps": [(plane(),)]},
    }
    for label, shape in shapes.items():
        found = _capability_offences(shape, include_store_writes=False)
        assert "ControlPlane" in found["types"], f"a capability held via a {label} must still be found; got {found['types']}"

    # The POSITIVE census must flag a capability arriving under a name no deny-list anticipated —
    # this is what a pure deny-list structurally cannot do.
    class TotallyNovelPrivilegedThing:
        def do_something_unanticipated(self) -> None: ...

    novel = _capability_offences((TotallyNovelPrivilegedThing(), ()), include_store_writes=False)
    assert novel["types"] == [], "the deny-list is blind to a novel class — that is exactly why the census exists"
    assert novel["unexpected"] == ["TotallyNovelPrivilegedThing"], (
        f"the positive census must flag an unapproved type regardless of its name; got {novel['unexpected']}"
    )


# ------------------------------------------------------------------------------------------
# GF-7 — the canonical uvicorn flags for the two PUBLIC edges
# ------------------------------------------------------------------------------------------

_CANONICAL_FLAGS = ("--factory", "--workers 1", "--no-access-log", "--no-server-header", "--no-proxy-headers")


def _command_blocks() -> list:
    """Every fenced ``uvicorn`` command in the Gateway-free topology document."""
    return [line.strip() for line in _text(_TOPOLOGY).splitlines() if line.strip().startswith("uvicorn ")]


def test_gf7_both_public_edges_have_a_pinned_canonical_startup_command() -> None:
    """The eight-edge census in ``test_native_uvicorn_factories.py`` is a hard-coded list and does
    NOT cover these two edges — so without this guard the canonical flags would be unenforced on
    the only two edges that terminate public requests. Uvicorn's defaults are ``proxy_headers=True``,
    ``server_header=True``, ``access_log=True``; every one of those is wrong for a public edge, and
    on the native path the command line is the only place the loopback bind is enforced.
    """
    blocks = _command_blocks()
    assert len(blocks) == 2, f"the topology must pin exactly one startup command per public edge; found {len(blocks)}"
    for factory in _MVP_FACTORIES:
        matching = [block for block in blocks if f"{factory}:create_app_from_env" in block]
        assert len(matching) == 1, f"exactly one command block for {factory}; found {len(matching)}"
        command = matching[0]
        for flag in _CANONICAL_FLAGS:
            assert flag in command, f"{factory} command is missing the canonical flag {flag!r}"
        assert "--host 127.0.0.1" in command, f"{factory} must bind loopback explicitly (an omitted --host falls through to UVICORN_HOST)"
        assert "--host 0.0.0.0" not in command and "--reload" not in command, f"{factory} must not bind all interfaces or reload"
        port = int(command.split("--port ")[1].split()[0])
        assert port in (8830, 8831), f"{factory} must use its documented public port; found {port}"
        assert port not in range(8080, 8089) and port != 8820, "a public edge must not land on the smoke range or the Gateway port"


def test_gf7_nonvacuity() -> None:
    bad = "uvicorn x.y:create_app_from_env --factory --host 0.0.0.0 --port 8830"
    missing = [flag for flag in _CANONICAL_FLAGS if flag not in bad]
    assert missing == ["--workers 1", "--no-access-log", "--no-server-header", "--no-proxy-headers"], (
        "the flag probe must flag a bad sample"
    )
    assert "--host 127.0.0.1" not in bad and "--host 0.0.0.0" in bad, "the bind probe must flag an all-interfaces sample"


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
