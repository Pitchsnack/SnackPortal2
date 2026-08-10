"""The public workspace edge holds ONE read capability — behaviour, not documentation.

The architecture guard (``tests/architecture/test_gateway_free_mvp_boundaries.py``, GF-9) proves
the narrowing structurally. This file proves the two things a structural guard cannot:

* the edge still WORKS — an authenticated principal gets exactly the bytes it got before, an
  anonymous one is still refused, and no caller can select a different subject;
* the removed capabilities are removed *in the served path*, exercised over a real loopback
  socket rather than asserted about source.

Where a capability is absent BY TYPE rather than by a runtime branch, this file tests the
structural absence rather than fabricating a call path — inventing a `/provision` route just to
watch it 404 would test the invention, not the design. What is tested instead is that the object
the served application closes over cannot express the operation at all.

Isolation: in-memory doubles and ephemeral loopback ports only. No standing service is contacted,
no database is connected, no credential is resolved, and every environment variable this file
touches is restored.
"""

from __future__ import annotations

import pathlib
import sys

# APPEND, never insert(0): backend/tests contains packages named after the services
# (tests/database_router/, tests/control_plane/, tests/shared/). Putting it first makes those
# EMPTY stubs win over the production packages, which silently blinds any sys.modules census.
sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from gateway_free._fakes import (  # noqa: E402
    ACME,
    ACME_BEARER,
    ACME_PRINCIPAL,
    ZETA,
    ZETA_PRINCIPAL,
    HostedEdge,
    bearer,
    build_boundary,
    decode,
)

import control_plane.main as cp_main  # noqa: E402
from control_plane.adapters.providers.control_membership_reader import ControlStoreMembershipReader  # noqa: E402
from control_plane.adapters.providers.control_store_factory import PostgresControlStoreFactory, SharedControlStoreFactory  # noqa: E402
from control_plane.adapters.providers.http_public_workspace_edge import build_public_workspace_edge_server, make_app  # noqa: E402
from control_plane.adapters.providers.in_memory_store import InMemoryControlStore  # noqa: E402
from control_plane.membership import MembershipRegistry  # noqa: E402
from control_plane.ports import WorkspaceMembershipReadPort  # noqa: E402
from control_plane.records import Role  # noqa: E402

# Every capability the narrowing removes, by the method name the removed object exposed.
_REMOVED_OPERATIONS = (
    ("tenant database creation", "provision"),
    ("tenant database deletion/drop", "deprovision"),
    ("recovery compensation drop", "deprovision_tenant_database"),
    ("schema application/migration", "apply_schema"),
    ("onboarding", "onboard"),
    ("recovery", "recover"),
    ("re-association", "reassociate"),
    ("routing disablement", "disable_routing"),
    ("orphan scanning", "scan_for_orphans"),
    ("tenant registry write", "put_tenant"),
    ("tenant lifecycle CAS", "compare_and_swap_tenant"),
    ("membership write", "put_membership"),
    ("federation write", "put_federation"),
    ("directory write", "put_directory_record"),
    ("control audit write", "append_audit"),
)


def _seeded_reader(*memberships):
    """A narrow reader over a REAL in-memory ControlStore, seeded through a separate writer.

    The registry used for seeding is deliberately NOT handed to the edge — that is the whole
    point: production writes these rows elsewhere and the edge only reads them.
    """
    store = InMemoryControlStore()
    registry = MembershipRegistry(store)
    for principal_ref, tenant_id, role in memberships:
        registry.add_membership(principal_ref=principal_ref, tenant_id=tenant_id, role=role)
    return ControlStoreMembershipReader(SharedControlStoreFactory(store))


def _edge(*memberships, allowed_origins=()):
    reader = _seeded_reader(*memberships)
    boundary, auth, audit = build_boundary()
    server, base_url = build_public_workspace_edge_server(reader, boundary, host="127.0.0.1", port=0, allowed_origins=allowed_origins)
    return HostedEdge(server, base_url), reader, auth, audit


def _with_env(fn, **overrides):
    """Run ``fn`` with the given env overrides (None deletes), restoring everything after."""
    import os

    saved = {name: os.environ.get(name) for name in overrides}
    try:
        for name, value in overrides.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        return fn()
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


# ------------------------------------------------------------------------------------------
# P1..P3 — the narrowing did not break the route (§11.1 / §11.2 / §11.3)
# ------------------------------------------------------------------------------------------


def test_p1_a_valid_authenticated_membership_read_still_succeeds() -> None:
    edge, _reader, _auth, audit = _edge((ACME_PRINCIPAL, ACME, Role.TENANT_AGENT))
    with edge:
        status, body, _headers = edge.request("GET", "/memberships", headers=bearer(ACME_BEARER))
    assert status == 200, "the narrowed edge must still serve its one route"
    assert decode(body) == {
        "memberships": [{"tenant_id": ACME, "role": "TENANT_AGENT", "display_ref": "ref:tenant/" + ACME + "/display"}]
    }, "the read still returns the same records through the narrow port"
    assert audit.actions() == ["workspace_memberships_read"], "exactly one success event, unchanged (§11.11)"


def test_p2_an_anonymous_membership_read_still_fails_closed() -> None:
    edge, reader, _auth, audit = _edge((ACME_PRINCIPAL, ACME, Role.TENANT_AGENT))
    calls = []
    original = reader.memberships_for_principal
    reader.memberships_for_principal = lambda ref: calls.append(ref) or original(ref)  # type: ignore[method-assign]
    with edge:
        status, body, _headers = edge.request("GET", "/memberships")
    assert status == 401, "an anonymous read is still denied"
    assert body == b"", "and discloses nothing"
    assert calls == [], "the Control DB is never read for an unauthenticated caller"
    assert audit.actions() == ["RouteDenied"], "the denial is still evidenced"


def test_p3_the_public_request_cannot_choose_another_principal() -> None:
    """Neither the query string, the body, nor a header can move the subject off the caller."""
    edge, reader, _auth, _audit = _edge((ACME_PRINCIPAL, ACME, Role.TENANT_AGENT), (ZETA_PRINCIPAL, ZETA, Role.TENANT_AGENT))
    subjects = []
    original = reader.memberships_for_principal
    reader.memberships_for_principal = lambda ref: subjects.append(ref) or original(ref)  # type: ignore[method-assign]
    with edge:
        mine = edge.request("GET", "/memberships", headers=bearer(ACME_BEARER))
        via_query = edge.request("GET", "/memberships?p=" + ZETA_PRINCIPAL, headers=bearer(ACME_BEARER))
        via_header = edge.request(
            "GET", "/memberships", headers={**bearer(ACME_BEARER), "X-Principal-Ref": ZETA_PRINCIPAL, "X-Actor-Ref": ZETA_PRINCIPAL}
        )
        via_body = edge.request(
            "GET",
            "/memberships",
            headers={**bearer(ACME_BEARER), "Content-Type": "application/json"},
            body=b'{"actor_ref":"' + ZETA_PRINCIPAL.encode() + b'"}',
        )
    assert mine[0] == 200 and [e["tenant_id"] for e in decode(mine[1])["memberships"]] == [ACME]
    assert via_query[0] == 404, "a query-bearing target is not an exposed route"
    assert via_header[0] == 200, "an unknown header is ignored, not honoured"
    assert [e["tenant_id"] for e in decode(via_header[1])["memberships"]] == [ACME], "the header did not move the subject"
    # Every route on this edge declares a body budget of 0, so a body is refused pre-handler as
    # oversized (413) rather than parsed and ignored — the request never reaches a handler at all.
    assert via_body[0] == 413, f"a body on a body-less route is refused pre-handler; got {via_body[0]}"
    assert set(subjects) == {ACME_PRINCIPAL}, f"every Control-DB read was for the authenticated principal; got {subjects}"


# ------------------------------------------------------------------------------------------
# P4..P8 — the removed capabilities are absent by TYPE (§11.4 .. §11.8)
# ------------------------------------------------------------------------------------------


def test_p4_the_edge_composes_with_the_narrow_read_accessor() -> None:
    reader = _seeded_reader((ACME_PRINCIPAL, ACME, Role.TENANT_AGENT))
    assert isinstance(reader, WorkspaceMembershipReadPort), "the composed accessor IS the narrow port"
    boundary, _auth, _audit = build_boundary()
    app = make_app(reader, boundary)
    assert app is not None, "the application composes over the narrow port alone"
    # The env composition path produces the same kind of object — no ControlPlane in sight.
    deps = _with_env(
        cp_main.build_public_workspace_edge_deps_from_env,
        **{
            cp_main.SP2_EDGE_AUTH_ROUTER_BASE_URL: "http://auth.invalid",
            cp_main.SP2_EDGE_AUDIT_SINK_BASE_URL: None,
            cp_main.CONTROL_STORE_ENV: None,
        },
    )
    assert deps is not None
    assert isinstance(deps[0], WorkspaceMembershipReadPort), f"the env composition must yield the narrow port; got {type(deps[0]).__name__}"
    assert type(deps[0]).__name__ != "ControlPlane"


def test_p5_to_p8_the_workspace_edge_cannot_invoke_any_removed_operation() -> None:
    """Structural absence, one assertion per named capability from the instruction's §7 list.

    Covers §11.5 (tenant create/drop), §11.6 (provisioning), §11.7 (schema application) and
    §11.8 (recovery/compensation) plus the Control-DB write surface. Asserted against the object
    the served application actually closes over — not against a source file.
    """
    reader = _seeded_reader((ACME_PRINCIPAL, ACME, Role.TENANT_AGENT))
    for label, operation in _REMOVED_OPERATIONS:
        assert not hasattr(reader, operation), f"the workspace edge's accessor must not expose {label} ({operation!r})"
    surface = sorted(name for name in dir(reader) if not name.startswith("_"))
    assert surface == ["memberships_for_principal"], f"the accessor's entire public surface is one read; got {surface}"


def test_p8b_the_durable_composition_retains_no_store_and_no_admin_reference() -> None:
    """The posture that matters: durable selection retains a secret REFERENCE, not a store.

    ``PostgresControlStoreFactory`` holds ``{secrets, ref}`` and constructs a fresh store per
    unit of work, so the composed process retains no object carrying the ControlStore write
    surface — and the allow-list it binds contains the control-store reference only, never
    ``control/provisioning-admin-dsn``.
    """
    deps = _with_env(
        cp_main.build_public_workspace_edge_deps_from_env,
        **{
            cp_main.SP2_EDGE_AUTH_ROUTER_BASE_URL: "http://auth.invalid",
            cp_main.SP2_EDGE_AUDIT_SINK_BASE_URL: None,
            cp_main.CONTROL_STORE_ENV: "postgres",
        },
    )
    assert deps is not None
    reader = deps[0]
    factory = reader._store_factory  # deliberately reaching past the private name — see GF-9
    assert isinstance(factory, PostgresControlStoreFactory), f"durable selection must compose the durable factory; got {type(factory)}"
    assert getattr(factory, "_dsn", "sentinel") is None, "no DSN literal transits the composition (D-14: references only)"
    allowed = set(factory._secrets._allowed)
    assert cp_main.PROVISIONING_ADMIN_DSN_REF not in allowed, (
        f"the workspace edge must not be able to resolve the admin DSN; allow-list={sorted(allowed)}"
    )
    assert factory._ref.store_ref == cp_main.DEFAULT_CONTROL_STORE_DSN_REF
    for _label, operation in _REMOVED_OPERATIONS:
        assert not hasattr(factory, operation), f"the durable factory must not expose {operation!r}"


# ------------------------------------------------------------------------------------------
# P9 — missing composition fails closed (§11.9)
# ------------------------------------------------------------------------------------------


def test_p9a_a_missing_boundary_composes_no_accessor_at_all() -> None:
    deps = _with_env(
        cp_main.build_public_workspace_edge_deps_from_env,
        **{cp_main.SP2_EDGE_AUTH_ROUTER_BASE_URL: None, cp_main.CONTROL_STORE_ENV: None},
    )
    assert deps is None, "no boundary -> no Control-DB accessor is composed (never a partial composition)"


def test_p9b_a_malformed_store_selector_refuses_to_compose_the_accessor() -> None:
    def _attempt():
        try:
            cp_main.build_workspace_membership_reader_from_env()
        except ValueError:
            return "raised"
        return "composed"

    assert _attempt.__name__  # keep the helper referenced for the standalone runner
    for bad in ("sqlite", "  ", "POSTGRES_"):
        outcome = _with_env(_attempt, **{cp_main.CONTROL_STORE_ENV: bad})
        assert outcome == "raised", f"an unsupported store selector {bad!r} must fail closed, never fall back"


def test_p9c_an_incoherent_selector_set_still_refuses_the_narrow_composition() -> None:
    """The PRD 07D-2a gate survived the narrowing — it used to run inside ``ControlPlane()``."""

    def _attempt():
        try:
            cp_main.build_workspace_membership_reader_from_env()
        except ValueError as exc:
            return str(exc)
        return "composed"

    message = _with_env(
        _attempt,
        **{cp_main.CONTROL_STORE_ENV: None, cp_main.PROVISIONING_ADAPTER_ENV: "postgres"},
    )
    assert "RULE 1" in message, f"a live-side postgres selector without the control store must still fail closed; got {message!r}"


def test_p9d_an_unreachable_control_db_is_a_fixed_503_with_an_empty_body() -> None:
    """A reader whose store cannot be opened must not leak why."""

    class _Broken(WorkspaceMembershipReadPort):
        def memberships_for_principal(self, principal_ref: str) -> dict:
            raise RuntimeError("connection to host 10.0.0.7 port 5432 failed: password authentication failed")

    boundary, _auth, _audit = build_boundary()
    server, base_url = build_public_workspace_edge_server(_Broken(), boundary, host="127.0.0.1", port=0)
    with HostedEdge(server, base_url) as edge:
        status, body, _headers = edge.request("GET", "/memberships", headers=bearer(ACME_BEARER))
    assert status == 503, "a store failure is a fixed 503"
    assert body == b"", "and carries no provider text, host, port, or credential detail"


# ------------------------------------------------------------------------------------------
# P10..P12 — nothing else changed (§11.10 / §11.11 / §11.12)
# ------------------------------------------------------------------------------------------


def test_p10_the_public_response_contract_is_byte_identical_through_the_narrow_port() -> None:
    import control_plane.portal as cp_portal

    edge, _reader, _auth, _audit = _edge((ACME_PRINCIPAL, ACME, Role.TENANT_AGENT))
    with edge:
        status, body, headers = edge.request("GET", "/memberships", headers=bearer(ACME_BEARER))
    entry = cp_portal.MembershipEntryDTO(tenant_id=ACME, role="TENANT_AGENT", display_ref=cp_portal.compose_display_ref(ACME))
    expected = cp_portal.serialize_portal_dto(cp_portal.WorkspaceMembershipDTO(memberships=(entry,)))
    assert status == 200
    assert body == expected, "the served bytes must still equal the contract composition exactly"
    assert headers["content-type"].startswith("application/json")
    assert headers["cache-control"] == "no-store"


def test_p11_the_audit_behaviour_is_unchanged_including_the_empty_enumeration() -> None:
    edge, _reader, _auth, audit = _edge()  # a principal with zero memberships
    with edge:
        status, body, _headers = edge.request("GET", "/memberships", headers=bearer(ACME_BEARER))
    assert status == 200 and decode(body) == {"memberships": []}, "an empty enumeration is a lawful success"
    assert audit.actions() == ["workspace_memberships_read"], "exactly one event, empty enumeration included"
    event = audit.events[0]
    assert event.actor_ref == event.subject_ref == ACME_PRINCIPAL, "actor == subject == the authenticated principal"
    assert event.outcome == "success" and event.tenant_ref is None and event.record_ref is None


def test_p11b_an_audit_sink_failure_still_withholds_the_success() -> None:
    edge, _reader, _auth, audit = _edge((ACME_PRINCIPAL, ACME, Role.TENANT_AGENT))
    audit.fail_with = RuntimeError("sink down")
    with edge:
        status, body, _headers = edge.request("GET", "/memberships", headers=bearer(ACME_BEARER))
    assert status == 503, "evidence-before-hand-back survives the narrowing"
    assert body == b"", "and the withheld success discloses nothing"


def test_p12_the_narrowed_workspace_path_loads_no_api_gateway_module() -> None:
    import subprocess

    program = (
        "import sys\n"
        "sys.path.append('tests')\n"
        "from gateway_free._fakes import build_boundary\n"
        "from control_plane.adapters.providers.control_membership_reader import ControlStoreMembershipReader\n"
        "from control_plane.adapters.providers.control_store_factory import SharedControlStoreFactory\n"
        "from control_plane.adapters.providers.in_memory_store import InMemoryControlStore\n"
        "from control_plane.adapters.providers.http_public_workspace_edge import make_app\n"
        "boundary, _a, _b = build_boundary()\n"
        "make_app(ControlStoreMembershipReader(SharedControlStoreFactory(InMemoryControlStore())), boundary, ())\n"
        "print('API_GATEWAY_MODULES=' + repr(sorted(m for m in sys.modules if m.split('.')[0] == 'api_gateway')))\n"
    )
    backend = pathlib.Path(__file__).resolve().parents[2]
    result = subprocess.run([sys.executable, "-c", program], cwd=str(backend), capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, result.stderr[-2000:]
    assert "API_GATEWAY_MODULES=[]" in result.stdout, (
        f"the narrowed composition must load no api_gateway module; got {result.stdout.strip()}"
    )


if __name__ == "__main__":
    for _name, _fn in sorted(globals().items()):
        if _name.startswith("test_") and callable(_fn):
            _fn()
            print("ok", _name)
