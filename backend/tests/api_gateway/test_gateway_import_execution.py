"""W1a — composed-core IMPORT_INITIATION behavioral contract (default suite; no PostgreSQL, no network).

Covers the gateway-side composed-core import slice end to end WITHOUT a database or a real Import Service:

* the port-composed IMPORT_INITIATION path — with an ``ImportInitiationPort`` injected, the gateway EXECUTES
  the real import through the port exactly once and NEVER calls ``RouterDispatchPort.dispatch`` on that path
  (single-route); the total outcome mapping (``created`` / ``replayed`` / ``noop``) is composed only from a
  real, references-only ``ImportInitiationOutcome``; a zero-record completion is the LW-1 403 denial (no DTO)
  and every transport/engine/audit failure collapses to §L 503 ``unavailable`` (no DTO); the operation key is
  the bounded ``x-operation-key`` header, else gateway-minted; and a pre-port denial never invokes the port
  (non-execution);
* the port-absent default — with no ``ImportInitiationPort``, IMPORT_INITIATION is byte-behavior-unchanged
  (the router is dispatched once and the accepted-initiation ``ImportInitiationDTO`` envelope is composed;
  ``ImportResultDTO`` is never composed);
* the ``build_import_initiation_from_env`` selector — unset → None (port-absent default); valid http → the
  transport client; malformed → ValueError BEFORE any socket; and the transport client holds no database
  driver, no ``import_service`` import, and no ``start_import`` name.

Pure stdlib; standalone-runnable: ``python tests/api_gateway/test_gateway_import_execution.py``.
"""

from __future__ import annotations

import contextlib
import os
import pathlib
import sys
from typing import Iterator, List, Optional

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _gateway_doubles as D  # noqa: E402
import _h  # noqa: E402

from api_gateway.adapters.providers.http_import_initiation import HttpImportInitiation  # noqa: E402
from api_gateway.main import (  # noqa: E402
    GW_IMPORT_BASE_URL_ENV,
    build_gateway,
    build_import_initiation_from_env,
)
from api_gateway.portal import ImportInitiationDTO, ImportResultDTO  # noqa: E402
from api_gateway.ports import (  # noqa: E402
    ImportInitiationOutcome,
    ImportInitiationPort,
    ImportInitiationRequest,
)


class StubImportInitiation(ImportInitiationPort):
    """Records the references-only request(s) and returns a canned outcome (no network)."""

    def __init__(self, outcome: ImportInitiationOutcome) -> None:
        self._outcome = outcome
        self.requests: List[ImportInitiationRequest] = []

    def initiate(self, request: ImportInitiationRequest) -> ImportInitiationOutcome:
        self.requests.append(request)
        return self._outcome


def _outcome(
    *,
    ok: bool = True,
    state: str = "applied",
    replayed: bool = False,
    applied_count: int = 1,
    noop_count: int = 0,
    import_id: str = "job-1",
) -> ImportInitiationOutcome:
    return ImportInitiationOutcome(
        ok=ok, state=state, replayed=replayed, applied_count=applied_count, noop_count=noop_count, import_id=import_id
    )


def _composed_gateway(stub: ImportInitiationPort):
    authn = D.StubAuthenticator()
    authn.add_token("tok-t1", principal="p1", tenant="t1", role="TENANT_AGENT")
    router = D.StubRouterDispatch()
    gateway = build_gateway(authenticator=authn, router=router, import_initiation=stub)
    return gateway, router


def _import_req(*, operation_key: Optional[str] = None, token: str = "tok-t1"):
    headers = {"x-operation-key": operation_key} if operation_key is not None else None
    return D.req(method="POST", path="/import/g1", correlation_id="cid-1", authorization=token, headers=headers)


# ===========================================================================
# port-composed execution — single route, real outcome mapping
# ===========================================================================
def test_composed_import_executes_via_port_exactly_once_no_dispatch() -> None:
    stub = StubImportInitiation(_outcome())
    gateway, router = _composed_gateway(stub)
    resp = gateway.handle(_import_req())
    assert resp.status == 200 and resp.public_code == "ok" and resp.dispatched
    assert len(stub.requests) == 1, "the composed path must execute the import exactly once"
    assert router.handoffs == [], "single-route: the executed import path must NEVER call the Database Router dispatch"
    (req,) = stub.requests
    assert req.source_ref == "g1" and req.target_tenant_ref == "t1" and req.actor_ref == "p1" and req.correlation_id == "cid-1"


def test_composed_created_composes_exact_import_result_dto() -> None:
    stub = StubImportInitiation(_outcome(applied_count=1, noop_count=0, import_id="job-9"))
    gateway, _router = _composed_gateway(stub)
    dto = gateway.handle(_import_req()).portal_dto
    assert isinstance(dto, ImportResultDTO)
    assert dto.outcome == "created"
    assert dto.source_ref == "g1" and dto.target_tenant_ref == "t1"
    assert dto.tenant_record_ref == "t1:startups:g1"
    assert dto.lineage_ref == "job-9" and dto.import_id == "job-9"


def test_composed_replayed_outcome() -> None:
    stub = StubImportInitiation(_outcome(replayed=True, applied_count=0, noop_count=1))
    dto = _composed_gateway(stub)[0].handle(_import_req()).portal_dto
    assert isinstance(dto, ImportResultDTO) and dto.outcome == "replayed"


def test_composed_noop_outcome() -> None:
    stub = StubImportInitiation(_outcome(replayed=False, applied_count=0, noop_count=1))
    dto = _composed_gateway(stub)[0].handle(_import_req()).portal_dto
    assert isinstance(dto, ImportResultDTO) and dto.outcome == "noop"


def test_composed_zero_record_is_403_forbidden_no_dto() -> None:
    stub = StubImportInitiation(_outcome(applied_count=0, noop_count=0))
    gateway, router = _composed_gateway(stub)
    resp = gateway.handle(_import_req())
    assert (resp.status, resp.public_code) == (403, "forbidden"), "zero-record is the LW-1 consistent denial"
    assert resp.portal_dto is None and router.handoffs == []


def test_composed_transport_failure_is_503_no_dto() -> None:
    stub = StubImportInitiation(_outcome(ok=False, state="", applied_count=0, noop_count=0, import_id=""))
    resp = _composed_gateway(stub)[0].handle(_import_req())
    assert (resp.status, resp.public_code) == (503, "unavailable") and resp.portal_dto is None


def test_composed_failed_state_is_503_no_dto() -> None:
    stub = StubImportInitiation(_outcome(ok=True, state="failed"))
    resp = _composed_gateway(stub)[0].handle(_import_req())
    assert (resp.status, resp.public_code) == (503, "unavailable") and resp.portal_dto is None


def test_composed_operation_key_from_header_else_minted() -> None:
    stub = StubImportInitiation(_outcome())
    gateway, _router = _composed_gateway(stub)
    gateway.handle(_import_req(operation_key="op-hdr"))
    assert stub.requests[-1].operation_key == "op-hdr", "a bounded x-operation-key header is used verbatim"
    gateway.handle(_import_req())  # no header -> gateway-minted uuid4().hex
    minted = stub.requests[-1].operation_key
    assert minted and minted != "op-hdr" and len(minted) == 32, "absent header -> a minted 32-hex operation key"


def test_composed_denial_before_port_no_execution() -> None:
    # A CONTROL principal (no signed active tenant) on the import path is denied at decide() BEFORE the port
    # is ever invoked (non-execution): zero import calls, no ImportResultDTO.
    stub = StubImportInitiation(_outcome())
    authn = D.StubAuthenticator()
    authn.add_token("tok-ctl", principal="ops", tenant=None, role="CONTROL")
    gateway = build_gateway(authenticator=authn, router=D.StubRouterDispatch(), import_initiation=stub)
    resp = gateway.handle(_import_req(token="tok-ctl"))
    assert resp.status == 403 and resp.public_code == "tenant_context_required"
    assert stub.requests == [], "a pre-port denial must never invoke the import port (non-execution)"


# ===========================================================================
# port-absent default — byte-behavior-unchanged
# ===========================================================================
def test_port_absent_default_dispatches_once_and_composes_envelope() -> None:
    authn = D.StubAuthenticator()
    authn.add_token("tok-t1", principal="p1", tenant="t1", role="TENANT_AGENT")
    router = D.StubRouterDispatch()
    gateway = build_gateway(authenticator=authn, router=router, control_read=D.StubControlPlaneRead())  # NO import_initiation
    resp = gateway.handle(_import_req())
    assert resp.status == 200 and resp.dispatched
    assert len(router.handoffs) == 1, "the port-absent default still dispatches to the Database Router exactly once"
    assert isinstance(resp.portal_dto, ImportInitiationDTO), "the port-absent default composes the accepted-initiation envelope"
    assert resp.portal_dto.source_ref == "g1" and resp.portal_dto.target_tenant_ref == "t1"


def test_port_absent_default_never_composes_import_result_dto() -> None:
    authn = D.StubAuthenticator()
    authn.add_token("tok-t1", principal="p1", tenant="t1", role="TENANT_AGENT")
    gateway = build_gateway(authenticator=authn, router=D.StubRouterDispatch(), control_read=D.StubControlPlaneRead())
    resp = gateway.handle(_import_req())
    assert not isinstance(resp.portal_dto, ImportResultDTO), "the port-absent default never composes ImportResultDTO"


# ===========================================================================
# build_import_initiation_from_env — selection + fail-closed
# ===========================================================================
@contextlib.contextmanager
def _env(value: Optional[str]) -> Iterator[None]:
    saved = os.environ.get(GW_IMPORT_BASE_URL_ENV)
    try:
        if value is None:
            os.environ.pop(GW_IMPORT_BASE_URL_ENV, None)
        else:
            os.environ[GW_IMPORT_BASE_URL_ENV] = value
        yield
    finally:
        if saved is None:
            os.environ.pop(GW_IMPORT_BASE_URL_ENV, None)
        else:
            os.environ[GW_IMPORT_BASE_URL_ENV] = saved


def test_build_import_initiation_selector_unset_returns_none() -> None:
    for blank in (None, "", "   "):
        with _env(blank):
            assert build_import_initiation_from_env() is None, "unset/blank keeps the port-absent default (envelope)"


def test_build_import_initiation_selector_valid_url_selects_client() -> None:
    with _env("http://127.0.0.1:9"):
        selected = build_import_initiation_from_env()
    assert isinstance(selected, HttpImportInitiation), "a valid http URL selects the transport client"


def test_build_import_initiation_selector_malformed_raises_before_socket() -> None:
    for bad in ("ftp://x", "https://x", "notaurl", "http://"):
        with _env(bad):
            try:
                build_import_initiation_from_env()
                raise AssertionError(f"malformed {bad!r} must raise ValueError (fail closed — no silent fallback)")
            except ValueError:
                pass


def test_transport_client_holds_no_db_driver_or_import_service() -> None:
    import ast

    import api_gateway.adapters.providers.http_import_initiation as mod

    path = pathlib.Path(mod.__file__)
    src = path.read_text(encoding="utf-8").lower()
    # No database driver / descriptor (references-only transport client).
    for banned in ("psycopg", "sqlalchemy", "asyncpg", "dsn", "postgresql://", "connect("):
        assert banned not in src, f"the gateway import transport client must not reference {banned!r}"
    # No in-process import of import_service and no start_import AST name (DAG independence; the port method
    # is ``initiate``). Structural, so the docstring may name them in prose.
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    imported |= {alias.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for alias in n.names}
    assert "import_service" not in imported, "the transport client must not import import_service (DAG independence)"
    called = {n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    called |= {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert "start_import" not in called, "the transport client must reference no import-execution name (start_import)"


if __name__ == "__main__":
    _h.run(
        [
            test_composed_import_executes_via_port_exactly_once_no_dispatch,
            test_composed_created_composes_exact_import_result_dto,
            test_composed_replayed_outcome,
            test_composed_noop_outcome,
            test_composed_zero_record_is_403_forbidden_no_dto,
            test_composed_transport_failure_is_503_no_dto,
            test_composed_failed_state_is_503_no_dto,
            test_composed_operation_key_from_header_else_minted,
            test_composed_denial_before_port_no_execution,
            test_port_absent_default_dispatches_once_and_composes_envelope,
            test_port_absent_default_never_composes_import_result_dto,
            test_build_import_initiation_selector_unset_returns_none,
            test_build_import_initiation_selector_valid_url_selects_client,
            test_build_import_initiation_selector_malformed_raises_before_socket,
            test_transport_client_holds_no_db_driver_or_import_service,
        ]
    )
