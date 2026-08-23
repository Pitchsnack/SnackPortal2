"""Architecture guards for the NATIVE ASGI application factories (all nine HTTP edges).

The canonical operator startup path is::

    uvicorn <module>:create_app_from_env --factory --host <h> --port <p> \\
      --workers 1 --no-access-log --no-server-header --no-proxy-headers

These guards police the properties that make that path safe, and that no default `pytest -q`
behavioral test can observe (the native path is a separate OS process built by the uvicorn CLI):

* every one of the nine edges exposes a no-argument ``create_app_from_env``;
* the factory BINDS NO SOCKET — ``build_asgi_server`` / ``AsgiEdgeServer`` stay confined to the
  retained compatibility ``build_*_server`` seam;
* the factory FAILS CLOSED — it raises and never returns ``None``, and never reaches for an
  in-memory substitute;
* there is ONE composition path — the dependency name the factory calls is the SAME name the
  compatibility ``*_server_from_env`` seam calls, so environment parsing and adapter wiring
  cannot drift between the two;
* the factory declares NO route of its own (the app shape stays owned by ``_make_app``);
* the runbook pins the four canonical runtime flags for all nine edges — these are the ONLY
  place the "no access log / no server header / no proxy headers" properties are established on
  the native path, because the uvicorn CLI builds its own config and never executes the shared
  ``asgi_runtime`` module those properties are otherwise asserted against.

Governance note (AT-D15T1-10): this file authorizes ONE uvicorn worker and ONE operating-system
process per edge, and no application-created worker, subprocess, or reload supervisor. It does not
redefine application-level request concurrency, which is the ASGI runtime's own event loop.

Pure stdlib; runnable standalone:  python tests/architecture/test_native_uvicorn_factories.py
"""

from __future__ import annotations

import ast
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

_BACKEND = _scan.BACKEND_ROOT
_RUNBOOK = _scan.REPO_ROOT / "docs" / "runbooks" / "backend_service_startup_fastapi.md"

# The nine native factory targets: (module path, the dependency-composition name the factory and
# the compatibility server seam MUST share). The shared name is the mechanical proof of "one
# composition path only" — if the two ever diverge, this census fails.
_EDGES = (
    ("api_gateway/adapters/providers/http_gateway_edge.py", "build_gateway_edge_deps_from_env"),
    ("control_plane/adapters/providers/http_read_api.py", "create_app"),
    ("auth_router/adapters/providers/http_authenticate_api.py", "build_authenticator_from_env"),
    ("database_router/adapters/providers/http_dispatch_api.py", "build_router_from_env"),
    ("database_router/adapters/providers/http_tenant_startup_api.py", "build_tenant_startup_ops_from_env"),
    ("control_plane/adapters/providers/http_gateway_audit_api.py", "build_gateway_audit_store_from_env"),
    ("control_plane/adapters/providers/http_import_audit_api.py", "build_import_audit_store_from_env"),
    ("control_plane/adapters/providers/http_routing_audit_api.py", "build_routing_audit_store_from_env"),
    ("deployment/import_edge.py", "build_import_service_from_env"),
)

# The compatibility server seam that must share each edge's dependency-composition name. The Import
# edge composes from the deployment root (its two cross-package ports cannot be built inside
# import_service — DAG independence), so its shared seam lives in import_service/main.py.
_SERVER_SEAMS = {
    "api_gateway/adapters/providers/http_gateway_edge.py": "api_gateway/main.py",
    "control_plane/adapters/providers/http_read_api.py": "control_plane/main.py",
    "auth_router/adapters/providers/http_authenticate_api.py": "auth_router/main.py",
    "database_router/adapters/providers/http_dispatch_api.py": "database_router/main.py",
    "database_router/adapters/providers/http_tenant_startup_api.py": "database_router/main.py",
    "control_plane/adapters/providers/http_gateway_audit_api.py": "control_plane/main.py",
    "control_plane/adapters/providers/http_import_audit_api.py": "control_plane/main.py",
    "control_plane/adapters/providers/http_routing_audit_api.py": "control_plane/main.py",
    "deployment/import_edge.py": "import_service/main.py",
}

# The four canonical runtime flags. `--workers 1` pins one OS process per edge; the other three are
# the ONLY thing standing between the native path and uvicorn's defaults (access_log=True,
# server_header=True, proxy_headers=True).
_CANONICAL_FLAGS = ("--factory", "--workers 1", "--no-access-log", "--no-server-header", "--no-proxy-headers")

_FACTORY = "create_app_from_env"


def _text(rel: str) -> str:
    return (_BACKEND / rel).read_text(encoding="utf-8")


def _tree(rel: str) -> ast.Module:
    path = _BACKEND / rel
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _func(tree: ast.AST, name: str) -> ast.FunctionDef | None:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def _names(node: ast.AST) -> set[str]:
    out = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
    out |= {n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)}
    return out


def test_all_nine_edges_expose_a_no_argument_factory() -> None:
    for rel, _shared in _EDGES:
        tree = _tree(rel)
        factory = _func(tree, _FACTORY)
        assert factory is not None, f"{rel} must expose {_FACTORY} (the canonical native operator entrypoint)"
        args = factory.args
        total = len(args.posonlyargs) + len(args.args) + len(args.kwonlyargs)
        assert total == 0 and args.vararg is None and args.kwarg is None, (
            f"{rel}:{_FACTORY} must take NO arguments — host and port belong to the ASGI runtime, "
            f"not the application (found {total} parameter(s))"
        )
        returns = factory.returns
        assert isinstance(returns, ast.Name) and returns.id == "FastAPI", f"{rel}:{_FACTORY} must be annotated -> FastAPI"


def test_factory_binds_no_socket() -> None:
    # The bind seam stays confined to the retained compatibility path. This is the machine-checkable
    # proof that `uvicorn --factory` owns the socket and the application never claims an address.
    for rel, _shared in _EDGES:
        factory = _func(_tree(rel), _FACTORY)
        assert factory is not None
        used = _names(factory)
        for bind in ("build_asgi_server", "AsgiEdgeServer", "serve_forever", "server_address", "bind", "listen"):
            assert bind not in used, f"{rel}:{_FACTORY} must not reference {bind} — the factory binds no socket"


def test_factory_fails_closed_and_never_normalizes_in_memory() -> None:
    for rel, _shared in _EDGES:
        factory = _func(_tree(rel), _FACTORY)
        assert factory is not None
        returns_none = [
            n for n in ast.walk(factory) if isinstance(n, ast.Return) and isinstance(n.value, ast.Constant) and n.value.value is None
        ]
        assert not returns_none, f"{rel}:{_FACTORY} must never return None — an inactive composition is a startup failure"
        used = _names(factory)
        for stub in ("InMemoryControlStore", "InMemoryAuditSink", "InMemoryAuditEmitter", "InMemoryMetrics"):
            assert stub not in used, (
                f"{rel}:{_FACTORY} must never compose {stub} — an in-memory backend is test-only and must "
                "never silently become the standing configuration"
            )


def test_factories_that_gate_on_activation_raise() -> None:
    # The six edges whose composition seam can report "inactive" must convert that into a hard
    # startup failure: the operator started this process deliberately, so a no-op is a
    # misconfiguration. (The three durable-audit stores and the read edge fail closed inside their
    # own composition function instead, by raising on a blank secret reference / incoherent posture.)
    gated = (
        "api_gateway/adapters/providers/http_gateway_edge.py",
        "auth_router/adapters/providers/http_authenticate_api.py",
        "database_router/adapters/providers/http_dispatch_api.py",
        "database_router/adapters/providers/http_tenant_startup_api.py",
        "deployment/import_edge.py",
    )
    for rel in gated:
        factory = _func(_tree(rel), _FACTORY)
        assert factory is not None
        raises = [n for n in ast.walk(factory) if isinstance(n, ast.Raise)]
        assert raises, f"{rel}:{_FACTORY} must RAISE when its composition is inactive (fail closed)"


def test_one_composition_path_only() -> None:
    # The factory and the compatibility server seam must reach for the SAME dependency-composition
    # name. This is the only mechanical proof that environment parsing, repository construction,
    # routing, auth, SecretRef resolution, audit wiring, and Import composition are not written twice.
    for rel, shared in _EDGES:
        factory = _func(_tree(rel), _FACTORY)
        assert factory is not None
        assert shared in _names(factory), f"{rel}:{_FACTORY} must compose through {shared} (the ONE composition path)"
        seam_text = _text(_SERVER_SEAMS[rel])
        assert shared in seam_text, (
            f"{_SERVER_SEAMS[rel]} must also compose through {shared} — the native factory and the "
            "compatibility server seam may not have separate composition implementations"
        )


def test_factory_declares_no_route_of_its_own() -> None:
    # The app shape (routes, methods, fail-closed handlers, disabled docs) stays owned by _make_app.
    for rel, _shared in _EDGES:
        factory = _func(_tree(rel), _FACTORY)
        assert factory is not None
        assert _scan.own_route_methods(factory) == [], f"{rel}:{_FACTORY} must declare no route; the app shape belongs to _make_app"


def test_factory_creates_no_worker_subprocess_or_supervisor() -> None:
    # AT-D15T1-10 (authorized scope): one uvicorn worker, one OS process per edge, and NO
    # application-created worker, subprocess, or reload supervisor.
    for rel, _shared in _EDGES:
        factory = _func(_tree(rel), _FACTORY)
        assert factory is not None
        used = _names(factory)
        for machinery in ("Thread", "Process", "Popen", "fork", "spawn", "run_in_executor", "create_task", "get_event_loop"):
            assert machinery not in used, f"{rel}:{_FACTORY} must create no {machinery} — the runtime owns the process model"


def test_no_edge_imports_the_asgi_server_directly() -> None:
    # uvicorn stays confined to the shared containment-zone runtime; the native path reaches it
    # through the CLI, never through an edge import.
    #
    # SCOPE (D-46 / IC-013 sec.21). This rule governs the NINE LEGACY EDGES, whose contract is the
    # shared `asgi_runtime` containment zone. It does NOT govern the Option A rebuild, where
    # IC-013 sec.21 rules the other way and says so explicitly: "A service-level `import uvicorn`
    # is permitted", and among the things "explicitly NOT mandated" is "a shared uvicorn runtime
    # module that every service must route through". Applying the legacy rule to the rebuild would
    # be enforcing the opposite of the ratified convention.
    #
    # The rebuild is therefore held to its own, narrower rule below: uvicorn may appear in a
    # service's own `main.py` and nowhere else — in particular, not in the shared foundation,
    # which is what "no shared uvicorn runtime module" actually means in practice.
    allowed = "shared/adapters/providers/asgi_runtime.py"
    rebuild_prefix = "snackportal2/"
    for path in _scan.py_files():
        rel = _scan.relposix(path)
        if rel == allowed or rel.startswith("tests/") or rel.startswith(rebuild_prefix):
            continue
        for module in _scan.imported_modules(path):
            assert module.split(".")[0] != "uvicorn", f"{rel} must not import uvicorn; only {allowed} may"


def test_rebuild_imports_uvicorn_only_in_service_entry_modules() -> None:
    """The Option A counterpart rule (IC-013 sec.21).

    Each rebuild service starts itself, so its `main.py` constructs the server. Nothing else may:
    a uvicorn import in the shared foundation would BE the shared runtime module the contract
    declines to mandate, and one in a non-entry service module would mean a service can be started
    from somewhere other than its documented entry point.
    """
    entry_suffix = "/main.py"
    rebuild_prefix = "snackportal2/services/"
    offenders = []
    for path in _scan.py_files():
        rel = _scan.relposix(path)
        if not rel.startswith("snackportal2/"):
            continue
        imports_uvicorn = any(module.split(".")[0] == "uvicorn" for module in _scan.imported_modules(path))
        if not imports_uvicorn:
            continue
        if rel.startswith(rebuild_prefix) and rel.endswith(entry_suffix):
            continue
        offenders.append(rel)
    assert offenders == [], f"uvicorn imported outside a rebuild service entry module: {offenders}"

    # Non-vacuity: the census must actually be seeing entry modules that import uvicorn, or the
    # emptiness above proves nothing.
    entry_modules = [
        _scan.relposix(p)
        for p in _scan.py_files()
        if _scan.relposix(p).startswith(rebuild_prefix)
        and _scan.relposix(p).endswith(entry_suffix)
        and any(m.split(".")[0] == "uvicorn" for m in _scan.imported_modules(p))
    ]
    assert len(entry_modules) >= 6, f"expected the rebuild's service entry modules to import uvicorn; found {entry_modules}"


def _runbook_command_blocks() -> list[str]:
    """Every fenced block in the runbook whose body is a uvicorn invocation.

    Splitting on the fence and keeping blocks that CONTAIN `uvicorn ` is what the earlier guard did —
    but it then joined them all into one string and counted. That is the weakness this replaces: a
    file-wide `count(flag) >= 9` stays green when six newly added commands each omit a different flag,
    because the original nine still supply nine occurrences of every flag.
    """
    runbook = _RUNBOOK.read_text(encoding="utf-8")
    # `<module>` / `<port>` blocks are the prose TEMPLATE at the head of the runbook, not a command.
    return [block for block in runbook.split("```") if "uvicorn " in block and "<module>" not in block]


def _parse_command(block: str) -> tuple[str, int]:
    """(module target, port) for one command block."""
    target = re.search(r"uvicorn\s+([A-Za-z0-9_.]+:%s)" % _FACTORY, block)
    port = re.search(r"--port\s+(\d+)", block)
    assert target, f"a uvicorn command block must name a `<module>:{_FACTORY}` target:\n{block}"
    assert port, f"a uvicorn command block must pin an explicit --port:\n{block}"
    return target.group(1), int(port.group(1))


def _smoke_map_from_harness() -> dict[str, int]:
    """The isolated smoke map, read from the harness that HARD-CODES it — not restated here.

    Restating it would let the runbook and the harness drift apart while both guards stayed green.
    """
    text = (_BACKEND / "tests" / "deployment" / "native_uvicorn_process_smoke.py").read_text(encoding="utf-8")
    pairs = re.findall(r'\(\s*(\d{4}),\s*"[^"]+",\s*"([^"]+):%s"' % _FACTORY, text, re.DOTALL)
    return {f"{module}:{_FACTORY}": int(port) for port, module in pairs}


def test_runbook_pins_every_command_block_with_all_canonical_flags() -> None:
    # On the native path the uvicorn CLI builds its OWN config: access logging, the Server header, and
    # proxy-header trust default to ON. Each runbook command is therefore load-bearing security
    # documentation. The assertion is PER BLOCK: one command missing one flag fails, regardless of how
    # many other commands carry it.
    assert _RUNBOOK.is_file(), f"the operator runbook must exist at {_RUNBOOK}"
    blocks = _runbook_command_blocks()
    assert blocks, "the runbook must contain fenced uvicorn command blocks"
    for block in blocks:
        target, port = _parse_command(block)
        for flag in _CANONICAL_FLAGS:
            assert flag in block, f"the runbook command for {target} (port {port}) is missing {flag}"
        assert "--host 127.0.0.1" in block, (
            f"the runbook command for {target} (port {port}) must bind the loopback host explicitly. On the native path "
            "the composition seam's host allow-list is bypassed, so the command line is the ONLY place the internal-only "
            "bind (IC-010 §R/§M) is enforced — and an omitted --host additionally falls through to UVICORN_HOST."
        )
        for unauthorized in ("--host 0.0.0.0", "--reload", "gunicorn", "--workers 2", "--workers 4"):
            assert unauthorized not in block, f"{unauthorized} must never appear in a documented startup command ({target})"


def test_runbook_documents_both_port_maps_and_pins_each_to_its_source() -> None:
    """The runbook carries TWO disjoint maps. Each is pinned to the artifact that owns it.

    `8080-8088` is the ISOLATED SMOKE map, owned by `native_uvicorn_process_smoke.py`.
    `8001/8002/8003/8004/8005/8820` is the STANDING map, owned by the governed launcher.

    Before Gate A the runbook carried only the smoke map, presented itself as the canonical standing
    method, ended its startup order at `API Gateway :8080`, and probed 8080 on shutdown — while the
    real standing Gateway ran on 8820, a number that appeared nowhere in the repository. An operator
    following the runbook verbatim started a SECOND Gateway and nothing would have revealed the split.
    No guard pinned any port, which is why nothing caught it.
    """
    import test_standing_launcher_flags as _launcher_guard  # same directory; single source for the standing map

    observed: dict[str, set[int]] = {}
    for block in _runbook_command_blocks():
        target, port = _parse_command(block)
        observed.setdefault(target, set()).add(port)

    smoke = _smoke_map_from_harness()
    assert len(smoke) == len(_EDGES), f"the smoke harness must enumerate all {len(_EDGES)} edges, found {len(smoke)}"

    standing = {f"{module}:{_FACTORY}": port for module, port in _launcher_guard.GOVERNED_STANDING_MAP.items()}

    for target, port in smoke.items():
        assert port in observed.get(target, set()), (
            f"the runbook must document the isolated-smoke command for {target} on port {port} "
            f"(found {sorted(observed.get(target, set()))})"
        )
    for target, port in standing.items():
        assert port in observed.get(target, set()), (
            f"the runbook must document the STANDING command for {target} on port {port} (found {sorted(observed.get(target, set()))})"
        )

    # Nothing outside the union of the two maps may appear as a documented port.
    allowed = set(smoke.values()) | set(standing.values())
    for target, ports in observed.items():
        stray = ports - allowed
        assert not stray, f"the runbook documents {target} on unpinned port(s) {sorted(stray)}"

    # The standing Gateway is 8820 and is never documented on 8080 as a standing command.
    gateway = f"api_gateway.adapters.providers.http_gateway_edge:{_FACTORY}"
    assert standing[gateway] == 8820, "the standing API Gateway must be 8820"
    assert observed[gateway] == {8080, 8820}, (
        "the runbook must document the Gateway exactly twice — once on the smoke map (8080) and once on the standing "
        f"map (8820), found {sorted(observed[gateway])}"
    )
    runbook = _RUNBOOK.read_text(encoding="utf-8")
    for scope_label in ("ISOLATED SMOKE", "STANDING"):
        assert scope_label in runbook, f"the runbook must label the maps explicitly ({scope_label})"


def test_runbook_port_map_guard_is_non_vacuous() -> None:
    assert _parse_command("uvicorn a.b:create_app_from_env --factory --host 127.0.0.1 --port 8820") == (
        "a.b:create_app_from_env",
        8820,
    )
    smoke = _smoke_map_from_harness()
    assert smoke.get("api_gateway.adapters.providers.http_gateway_edge:create_app_from_env") == 8080, (
        "the smoke-map parser must actually read the harness"
    )


def test_factory_census_nonvacuity() -> None:
    # The detectors must be able to see a violation.
    assert _func(ast.parse("def create_app_from_env(host):\n    return 1\n"), _FACTORY) is not None
    binder = ast.parse("def create_app_from_env():\n    return build_asgi_server(x)\n")
    assert "build_asgi_server" in _names(_func(binder, _FACTORY)), "a socket-binding factory must be detectable"
    noner = _func(ast.parse("def create_app_from_env():\n    return None\n"), _FACTORY)
    assert [n for n in ast.walk(noner) if isinstance(n, ast.Return) and isinstance(n.value, ast.Constant)], (
        "a None-returning factory must be detectable"
    )
    router = ast.parse("@app.get('/x')\ndef create_app_from_env():\n    pass\n")
    assert _scan.own_route_methods(_func(router, _FACTORY)) == ["get"], "a route-declaring factory must be detectable"
    assert len(_EDGES) == 9, "the census must cover exactly the nine HTTP edges"


if __name__ == "__main__":
    _scan.run(
        [
            test_all_nine_edges_expose_a_no_argument_factory,
            test_factory_binds_no_socket,
            test_factory_fails_closed_and_never_normalizes_in_memory,
            test_factories_that_gate_on_activation_raise,
            test_one_composition_path_only,
            test_factory_declares_no_route_of_its_own,
            test_factory_creates_no_worker_subprocess_or_supervisor,
            test_no_edge_imports_the_asgi_server_directly,
            test_rebuild_imports_uvicorn_only_in_service_entry_modules,
            test_runbook_pins_every_command_block_with_all_canonical_flags,
            test_runbook_documents_both_port_maps_and_pins_each_to_its_source,
            test_runbook_port_map_guard_is_non_vacuous,
            test_factory_census_nonvacuity,
        ]
    )
