"""Federation read-route tests (B5-3 LW-2) — GET /federation?issuer=<urlencoded issuer>.

Proves the read dispatcher's new federation branch against the EXISTING FederationStore/port
contract: a URL-encoded issuer round-trips (parse_qs percent-decodes the client's quote());
the lookup resolves the DECODED issuer against configs read through the existing
``FederationStore.get(tenant_id)`` over ``list_tenant_ids()`` (sorted — deterministic when two
tenants share an issuer); found → 200 with EXACTLY the five client-compatible fields
(``FederationView(**body)`` decodes it); unknown issuer → 404; missing/empty/duplicate
``issuer`` → deterministic 400; wrong path stays 404; non-GET stays 405; and no unrelated
read route regresses.

Mutation reasoning (wrapper §8.4 items 4-6): a route that ALWAYS returns 200 fails
``test_unknown_issuer_404`` and the 400-rejection tests; a route that fails to URL-decode
the issuer never matches the percent-encoded round-trip issuer → ``test_found_round_trips...``
fails; a route accepting missing/duplicate issuer fails ``test_missing_empty_duplicate...``.

Stdlib-only; in-memory store; DB-free; runnable standalone:
  python tests/control_plane/test_read_api_federation.py
"""

from __future__ import annotations

import pathlib
import sys
from urllib.parse import quote

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _h  # noqa: E402

from control_plane.adapters.providers.in_memory_store import InMemoryControlStore  # noqa: E402
from control_plane.read_api import ControlPlaneReadDispatcher, ControlPlaneReadService  # noqa: E402
from control_plane.records import FederationConfig, TenantLifecycleState, TenantRecord  # noqa: E402
from shared.secrets import SecretRef  # noqa: E402

# An issuer whose wire form REQUIRES percent-encoding (space, ?, &, =) — the decode proof.
_ISS = "https://issuer.example/realm x?y=1&z=2"
_CLIENT_FIELDS = {"tenant_id", "oidc_issuer", "oidc_audience", "jwks_ref", "claim_to_tenant_rule"}


def _tenant(tenant_id: str) -> TenantRecord:
    return TenantRecord(
        tenant_id=tenant_id,
        organization_ref="org",
        lifecycle_state=TenantLifecycleState.READY,
        expected_schema_version="1",
        database_association_ref=SecretRef(f"tenant/{tenant_id}/db", "1"),
        federation_config_ref="fed",
        created_at="t",
        updated_at="t",
    )


def _config(tenant_id: str, issuer: str = _ISS) -> FederationConfig:
    return FederationConfig(
        tenant_id=tenant_id,
        oidc_issuer=issuer,
        oidc_audience="snackportal",
        jwks_ref=f"jwks/{tenant_id}",  # reference only — never key material inline
        claim_to_tenant_rule="tenant",
    )


def _dispatcher(*configs: FederationConfig) -> ControlPlaneReadDispatcher:
    store = InMemoryControlStore()
    for config in configs:
        store.put_tenant(_tenant(config.tenant_id))
        store.put_federation(config)
    return ControlPlaneReadDispatcher(ControlPlaneReadService(store))


# --- found: URL-encoded issuer round-trips into the client-compatible five-field JSON ----------------
def test_found_round_trips_urlencoded_issuer_with_client_shape() -> None:
    dispatcher = _dispatcher(_config("t1"))
    status, body = dispatcher.handle("GET", "/federation?issuer=" + quote(_ISS, safe=""))
    assert status == 200, f"a known issuer must serve 200 (got {status})"
    assert body is not None and set(body.keys()) == _CLIENT_FIELDS, (
        f"the body must carry EXACTLY the five FederationView fields; got {sorted(body or {})}"
    )
    assert body["tenant_id"] == "t1" and body["oidc_issuer"] == _ISS, (
        "the DECODED issuer must resolve the config (percent-encoded round-trip through parse_qs)"
    )
    assert body["oidc_audience"] == "snackportal" and body["jwks_ref"] == "jwks/t1"
    assert body["claim_to_tenant_rule"] == "tenant"
    assert "material" not in str(body).lower() and "secret" not in str(body).lower(), "reference-only response"


def test_unknown_issuer_404() -> None:
    dispatcher = _dispatcher(_config("t1"))
    status, body = dispatcher.handle("GET", "/federation?issuer=" + quote("https://nobody.example", safe=""))
    assert (status, body) == (404, {"error": "not_found"}), "an unknown issuer must serve the consistent 404"
    # An EMPTY store (no federation configs at all) also serves 404 — never a 200/None leak.
    empty = _dispatcher()
    assert empty.handle("GET", "/federation?issuer=" + quote(_ISS, safe=""))[0] == 404


# --- missing / empty / duplicate issuer -> deterministic 400 -----------------------------------------
def test_missing_empty_duplicate_issuer_rejected_400() -> None:
    dispatcher = _dispatcher(_config("t1"))
    for target in (
        "/federation",  # missing
        "/federation?other=x",  # missing (unrelated param)
        "/federation?issuer=",  # empty (keep_blank_values makes it visible)
        "/federation?issuer=a&issuer=b",  # duplicate
        "/federation?issuer=&issuer=" + quote(_ISS, safe=""),  # duplicate incl. one blank
    ):
        status, body = dispatcher.handle("GET", target)
        assert (status, body) == (400, {"error": "invalid_issuer"}), (
            f"{target!r} must be rejected with the deterministic 400 (got {(status, body)})"
        )


# --- duplicate issuer across tenants: deterministic sorted-first resolution --------------------------
def test_duplicate_issuer_across_tenants_resolves_deterministically() -> None:
    dispatcher = _dispatcher(_config("t2"), _config("t1"))  # same issuer on both; insertion order t2 first
    status, body = dispatcher.handle("GET", "/federation?issuer=" + quote(_ISS, safe=""))
    assert status == 200 and body is not None
    assert body["tenant_id"] == "t1", "resolution must scan sorted tenant ids (deterministic first match)"


# --- method / path behavior unchanged ----------------------------------------------------------------
def test_wrong_path_and_method_behavior_unchanged() -> None:
    dispatcher = _dispatcher(_config("t1"))
    assert dispatcher.handle("GET", "/federations?issuer=x")[0] == 404, "wrong path stays 404"
    assert dispatcher.handle("GET", "/federation/extra?issuer=x")[0] == 404, "extra segment stays 404"
    assert dispatcher.handle("POST", "/federation?issuer=x") == (405, {"error": "method_not_allowed"}), (
        "non-GET methods stay 405 (unchanged)"
    )


# --- no unrelated read route regresses ---------------------------------------------------------------
def test_unrelated_read_routes_unchanged() -> None:
    dispatcher = _dispatcher(_config("t1"))
    status, state = dispatcher.handle("GET", "/tenants/t1/state")
    assert status == 200 and state is not None and set(state.keys()) == {"tenant_id", "lifecycle_state", "ready"}
    status, view = dispatcher.handle("GET", "/internal/routing/tenants/t1")
    assert status == 200 and view is not None and view["database_association_ref"] == {"store_ref": "tenant/t1/db", "version": "1"}
    status, member = dispatcher.handle("GET", "/membership?p=u&t=t1")
    assert status == 200 and member == {"member": False}
    assert dispatcher.handle("GET", "/role?p=u&t=t1")[0] == 404
    assert dispatcher.handle("GET", "/unknown")[0] == 404


_TESTS = [
    test_found_round_trips_urlencoded_issuer_with_client_shape,
    test_unknown_issuer_404,
    test_missing_empty_duplicate_issuer_rejected_400,
    test_duplicate_issuer_across_tenants_resolves_deterministically,
    test_wrong_path_and_method_behavior_unchanged,
    test_unrelated_read_routes_unchanged,
]

if __name__ == "__main__":
    _h.run(_TESTS)
