"""Behavioral tests for the auth-router-side authentication server (07E-3b).

Hosts the single-threaded ``build_authenticate_server`` on a test-owned daemon thread (the
D-15-T1b server-test precedent) and drives it over real HTTP with ``http.client``. The
success path composes the REAL ``Authenticator`` from the stdlib auth_router doubles (no
PyJWT, no control-plane, no PostgreSQL); the fine-grained bridge/mapping assertions use a
recording spy. Proves the server half of the AUTH-TRANSPORT-SPEC-01 wire contract: the exact
envelope bridge (Bearer-strip, carriers-list -> single carrier_tenant, previous_tenant=None),
the references-only 4-field success response, the AuthDenied -> status mapping, the refusal
edges, and that no credential/token/PII/DB material ever crosses the wire.
"""

from __future__ import annotations

import contextlib
import http.client
import io
import json
import pathlib
import sys
import threading
from typing import List, Optional, Tuple
from urllib.parse import urlsplit

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _auth_doubles as D  # noqa: E402
import _h  # noqa: E402

from auth_router.adapters.providers.http_authenticate_api import build_authenticate_server  # noqa: E402
from auth_router.models import AuthContext, AuthDenied, Role, forbidden, not_ready, unauthenticated, unavailable  # noqa: E402

_PATH = "/internal/auth/authenticate"
_ISS = "https://platform.snackportal"
_SECRET = b"07e3b-server-secret"


class _SpyAuthenticator:
    """Records ``authenticate(...)`` calls and returns a canned result / raises a canned denial.

    Duck-typed in place of the real ``Authenticator`` (the D-15 ``_BoomRouter`` precedent); the
    server only calls ``.authenticate(token, *, correlation_id, carrier_tenant, previous_tenant)``.
    """

    def __init__(self, *, result: Optional[AuthContext] = None, denial: Optional[AuthDenied] = None, boom: bool = False) -> None:
        self.calls: List[dict] = []
        self._result = result
        self._denial = denial
        self._boom = boom

    def authenticate(self, token, *, correlation_id, carrier_tenant=None, previous_tenant=None):
        self.calls.append(
            {"token": token, "correlation_id": correlation_id, "carrier_tenant": carrier_tenant, "previous_tenant": previous_tenant}
        )
        if self._boom:
            raise RuntimeError("boom — internal detail that must never leak")
        if self._denial is not None:
            raise self._denial
        return self._result


def _ok_ctx(active_tenant_id: Optional[str] = "t1", role: Optional[str] = "TENANT_AGENT") -> AuthContext:
    return AuthContext(correlation_id="cid", principal_ref="u1", active_tenant_id=active_tenant_id, role=role)


def _compose_real() -> Tuple[object, str]:
    """A real composed Authenticator + a valid runtime-minted HS256 token (no hardcoded JWT)."""
    from auth_router.main import build_authenticator  # local import: compose with doubles

    cfg = D.issuer_cfg(issuer=_ISS, secret=_SECRET)
    read = D.FakeControlPlaneRead()
    read.set_tenant("t1", ready=True)
    read.add_member("u1", "t1", Role.TENANT_AGENT)
    authenticator = build_authenticator(verifier=D.HmacTestVerifier(), read=read, issuers={_ISS: cfg})
    token = D.make_hs256_jwt(D.claims(sub="u1", iss=_ISS, tenant="t1"), secret=_SECRET)
    return authenticator, token


def _host(authenticator: object):
    server, base_url = build_authenticate_server(authenticator, "127.0.0.1", 0)  # type: ignore[arg-type]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, base_url


def _env(
    *,
    authorization: Optional[str] = "Bearer opaque-credential-1",
    recognized_carriers: Optional[List[str]] = None,
    correlation_id: str = "cid",
    v: int = 1,
) -> dict:
    return {
        "v": v,
        "authorization": authorization,
        "recognized_carriers": [] if recognized_carriers is None else recognized_carriers,
        "correlation_id": correlation_id,
    }


def _do(
    base_url: str,
    *,
    method: str = "POST",
    path: str = _PATH,
    payload: Optional[dict] = None,
    raw_body: Optional[bytes] = None,
) -> Tuple[int, bytes]:
    parts = urlsplit(base_url)
    conn = http.client.HTTPConnection(parts.hostname or "127.0.0.1", parts.port, timeout=5)
    try:
        body: Optional[bytes]
        if raw_body is not None:
            body = raw_body
        elif payload is not None:
            body = json.dumps(payload).encode("utf-8")
        else:
            body = None
        headers = {"Content-Type": "application/json"} if body is not None else {}
        conn.request(method, path, body=body, headers=headers)
        resp = conn.getresponse()
        return resp.status, resp.read()
    finally:
        conn.close()


# OBS-1 (D-15-T1c): the single-threaded stdlib server closes the connection immediately after a
# bodiless 405/404 (_respond_empty). On Windows loopback that immediate close intermittently
# surfaces client-side as ``ConnectionAbortedError``/reset while http.client reads the response.
# Linux CI is deterministic; the runtime is correct — this is a test-harness robustness concern.
_REFUSAL_PROBE_ATTEMPTS = 5


def _do_refusal_probe(base_url: str, *, method: str = "POST", path: str = _PATH, payload: Optional[dict] = None) -> Tuple[int, bytes]:
    """Retry wrapper used SOLELY for the OBS-1 refusal probes (GET wrong-method -> 405 empty,
    POST wrong-path -> 404 empty). Tolerates only the narrow transient Windows-loopback abort/
    reset classes and retries with a FRESH connection each attempt (``_do`` opens/closes its own
    connection). Every other exception (including AssertionError) propagates unchanged, and the
    last transient error re-raises after the bounded attempts. Restricted to the refusal probes,
    which reach no ``authenticate()`` call — so re-sending them is side-effect-free."""
    for attempt in range(_REFUSAL_PROBE_ATTEMPTS):
        try:
            return _do(base_url, method=method, path=path, payload=payload)
        except (ConnectionAbortedError, ConnectionResetError):
            if attempt == _REFUSAL_PROBE_ATTEMPTS - 1:
                raise
    raise AssertionError("unreachable: bounded refusal-probe retry exhausted without returning or raising")  # pragma: no cover


# --- success (real composed Authenticator) --------------------------------------------------------
def test_valid_request_returns_exact_four_field_success() -> None:
    authenticator, token = _compose_real()
    server, base_url = _host(authenticator)
    try:
        status, body = _do(base_url, payload=_env(authorization="Bearer " + token, recognized_carriers=["t1"]))
        assert status == 200
        data = json.loads(body)
        assert set(data.keys()) == {"correlation_id", "principal_ref", "active_tenant_id", "role"}, data
        assert data == {"correlation_id": "cid", "principal_ref": "u1", "active_tenant_id": "t1", "role": "TENANT_AGENT"}
    finally:
        server.shutdown()
        server.server_close()


def test_default_bind_is_loopback() -> None:
    server, base_url = _host(_SpyAuthenticator(result=_ok_ctx()))
    try:
        assert base_url.startswith("http://127.0.0.1:"), base_url
    finally:
        server.shutdown()
        server.server_close()


# --- authorization -> token bridge ----------------------------------------------------------------
def test_valid_bearer_strips_scheme_before_calling_authenticator() -> None:
    spy = _SpyAuthenticator(result=_ok_ctx())
    server, base_url = _host(spy)
    try:
        status, _ = _do(base_url, payload=_env(authorization="bEaReR opaque-credential-XYZ", recognized_carriers=["t1"]))
        assert status == 200
        assert spy.calls and spy.calls[0]["token"] == "opaque-credential-XYZ", "scheme (case-insensitive) must be stripped"
    finally:
        server.shutdown()
        server.server_close()


def test_missing_malformed_and_non_bearer_authorization_return_401_without_calling() -> None:
    for authorization in (None, "", "opaque-only-no-scheme", "Basic opaque-credential-1", "Bearer", "Bearer  double-space"):
        spy = _SpyAuthenticator(result=_ok_ctx())
        server, base_url = _host(spy)
        try:
            status, body = _do(base_url, payload=_env(authorization=authorization))
            assert status == 401, authorization
            assert json.loads(body) == {"status": 401, "public_code": "unauthenticated"}, authorization
            assert spy.calls == [], f"authenticator must NOT be called for {authorization!r}"
        finally:
            server.shutdown()
            server.server_close()


# --- recognized_carriers -> carrier_tenant reduction ----------------------------------------------
def test_carrier_reduction_empty_one_and_duplicate() -> None:
    for carriers, expected in ([], None), (["t1"], "t1"), (["t1", "t1"], "t1"):
        spy = _SpyAuthenticator(result=_ok_ctx())
        server, base_url = _host(spy)
        try:
            status, _ = _do(base_url, payload=_env(recognized_carriers=carriers))
            assert status == 200
            assert spy.calls[0]["carrier_tenant"] == expected, (carriers, expected)
        finally:
            server.shutdown()
            server.server_close()


def test_two_distinct_carriers_reject_403_carrier_mismatch_without_calling() -> None:
    spy = _SpyAuthenticator(result=_ok_ctx())
    server, base_url = _host(spy)
    try:
        status, body = _do(base_url, payload=_env(recognized_carriers=["t1", "t2"]))
        assert status == 403 and json.loads(body) == {"status": 403, "public_code": "carrier_mismatch"}
        assert spy.calls == [], "two disagreeing carriers must reject WITHOUT calling the authenticator"
    finally:
        server.shutdown()
        server.server_close()


def test_previous_tenant_is_always_none() -> None:
    spy = _SpyAuthenticator(result=_ok_ctx())
    server, base_url = _host(spy)
    try:
        _do(base_url, payload=_env(recognized_carriers=["t1"]))
        assert spy.calls and spy.calls[0]["previous_tenant"] is None
    finally:
        server.shutdown()
        server.server_close()


# --- AuthDenied -> status mapping (no new public_code, no granular-reason leak) --------------------
def test_authdenied_maps_by_status() -> None:
    cases = [
        (unauthenticated("unknown_issuer"), 401, "unauthenticated"),
        (unauthenticated("invalid_signature"), 401, "unauthenticated"),
        (forbidden("carrier_mismatch"), 403, "carrier_mismatch"),
        (forbidden("tenant_access_denied"), 403, "forbidden"),
        (not_ready("tenant_not_ready"), 403, "forbidden"),
        (unavailable("control_plane_unavailable"), 503, "unavailable"),
    ]
    for denial, status, public_code in cases:
        spy = _SpyAuthenticator(denial=denial)
        server, base_url = _host(spy)
        try:
            got_status, body = _do(base_url, payload=_env(recognized_carriers=["t1"]))
            assert got_status == status, denial.public_code
            assert json.loads(body) == {"status": status, "public_code": public_code}, denial.public_code
            # The granular internal reason (e.g. unknown_issuer) never leaks past the status bucket.
            assert denial.public_code not in body.decode("utf-8") or denial.public_code == public_code
        finally:
            server.shutdown()
            server.server_close()


def test_unexpected_exception_fails_closed_503_empty_no_leak() -> None:
    spy = _SpyAuthenticator(boom=True)
    server, base_url = _host(spy)
    try:
        status, body = _do(base_url, payload=_env(recognized_carriers=["t1"]))
        assert status == 503 and body == b"", "an unhandled server exception must fail closed 503 empty (no stack/detail leak)"
    finally:
        server.shutdown()
        server.server_close()


# --- refusal edges + malformed envelope -----------------------------------------------------------
def test_wrong_path_and_non_post_are_refused_empty() -> None:
    spy = _SpyAuthenticator(result=_ok_ctx())
    server, base_url = _host(spy)
    try:
        s_get, b_get = _do_refusal_probe(base_url, method="GET")
        assert s_get == 405 and b_get == b"", "non-POST must be 405 empty body"
        s_path, b_path = _do_refusal_probe(base_url, path="/nope", payload=_env(recognized_carriers=["t1"]))
        assert s_path == 404 and b_path == b"", "wrong path must be 404 empty body"
        assert spy.calls == [], "a refused edge must never reach the authenticator"
    finally:
        server.shutdown()
        server.server_close()


def test_malformed_and_invalid_envelopes_fail_closed_503_empty() -> None:
    spy = _SpyAuthenticator(result=_ok_ctx())
    server, base_url = _host(spy)
    try:
        cases: list = [
            {"raw_body": b"{not json"},  # malformed JSON
            {"raw_body": b"[1,2,3]"},  # non-object JSON
            {"payload": _env(recognized_carriers=["t1"], v=2)},  # unknown version
            {"payload": {"authorization": "Bearer opaque-credential-1", "recognized_carriers": [], "correlation_id": "cid"}},  # missing v
            {"payload": {**_env(recognized_carriers=["t1"]), "extra": 1}},  # extra top-level key
        ]
        for case in cases:
            status, body = _do(base_url, **case)
            assert status == 503 and body == b"", f"fail-closed 503 empty expected for {case}"
        # non-string entry in recognized_carriers is a malformed envelope
        assert _do(base_url, payload=_env(recognized_carriers=["t1", 5])) == (503, b"")  # type: ignore[list-item]
        # empty / non-string correlation_id is a malformed envelope
        assert _do(base_url, payload=_env(correlation_id="")) == (503, b"")
        assert spy.calls == [], "no malformed envelope may reach the authenticator"
    finally:
        server.shutdown()
        server.server_close()


# --- references-only / redaction ------------------------------------------------------------------
def test_no_credential_token_or_forbidden_field_ever_crosses_the_wire() -> None:
    authenticator, token = _compose_real()
    server, base_url = _host(authenticator)
    cred_authorization = "Bearer " + token
    try:
        # success body: exactly the 4 reference fields, none of the never-cross identifiers.
        status, body = _do(base_url, payload=_env(authorization=cred_authorization, recognized_carriers=["t1"]))
        assert status == 200
        text = body.decode("utf-8")
        assert token not in text and cred_authorization not in text, "the credential/token must never be returned"
        for forbidden_key in ("token", "authorization", "credential", "secret", "email", "roles", "memberships", "dsn", "database_url"):
            assert forbidden_key not in json.loads(body).keys(), forbidden_key
        # denial body: only {status, public_code}; still no credential/token.
        spy = _SpyAuthenticator(denial=forbidden("tenant_access_denied"))
        d_server, d_base = _host(spy)
        try:
            _, d_body = _do(d_base, payload=_env(authorization=cred_authorization, recognized_carriers=["t1"]))
            assert set(json.loads(d_body).keys()) == {"status", "public_code"}
            assert token not in d_body.decode("utf-8")
        finally:
            d_server.shutdown()
            d_server.server_close()
    finally:
        server.shutdown()
        server.server_close()


def test_credential_never_appears_in_server_stdout_or_stderr() -> None:
    # The no-token-log proof on the side that RECEIVES the live credential (SPEC Section C
    # rule 3): drive a success and a denial request carrying a distinctive credential while
    # capturing process stdout/stderr (the server thread writes synchronously within the
    # request/response window), and assert no trace of the credential is ever emitted.
    authenticator, token = _compose_real()
    server, base_url = _host(authenticator)
    marker = "opaque-distinctive-cred-marker-31415"
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            # success path (real composed Authenticator, runtime-minted token)
            status_ok, _ = _do(base_url, payload=_env(authorization="Bearer " + token, recognized_carriers=["t1"]))
            # denial path (the marker credential reaches _bearer_token, then the denial mapping)
            spy = _SpyAuthenticator(denial=forbidden("tenant_access_denied"))
            d_server, d_base = _host(spy)
            try:
                status_deny, _ = _do(d_base, payload=_env(authorization="Bearer " + marker, recognized_carriers=["t1"]))
            finally:
                d_server.shutdown()
                d_server.server_close()
        assert status_ok == 200 and status_deny == 403
        logged = buf.getvalue()
        assert token not in logged, "the live token must never appear in server stdout/stderr"
        assert marker not in logged, "the credential must never appear in server stdout/stderr"
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    _h.run(
        [
            test_valid_request_returns_exact_four_field_success,
            test_default_bind_is_loopback,
            test_valid_bearer_strips_scheme_before_calling_authenticator,
            test_missing_malformed_and_non_bearer_authorization_return_401_without_calling,
            test_carrier_reduction_empty_one_and_duplicate,
            test_two_distinct_carriers_reject_403_carrier_mismatch_without_calling,
            test_previous_tenant_is_always_none,
            test_authdenied_maps_by_status,
            test_unexpected_exception_fails_closed_503_empty_no_leak,
            test_wrong_path_and_non_post_are_refused_empty,
            test_malformed_and_invalid_envelopes_fail_closed_503_empty,
            test_no_credential_token_or_forbidden_field_ever_crosses_the_wire,
            test_credential_never_appears_in_server_stdout_or_stderr,
        ]
    )
