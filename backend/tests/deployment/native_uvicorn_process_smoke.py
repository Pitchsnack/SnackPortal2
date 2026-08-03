"""Standalone native-Uvicorn PROCESS smoke for all nine SnackPortal2 FastAPI edges.

Not collected by ``pytest`` (no ``test_`` prefix): it starts nine real operating-system processes
through the actual Uvicorn command line, so it is deliberately kept out of the default suite. It is
the ONLY proof that the canonical operator path — and the security properties that live in the
command line rather than in the application — actually hold, because the native path builds its own
server configuration and never executes ``shared/adapters/providers/asgi_runtime.py``.

For each of the nine edges it proves:

* the process starts and the socket LISTENS;
* ``/docs``, ``/redoc`` and ``/openapi.json`` answer ``404`` and publish no schema and no FastAPI
  structural default body;
* the edge's own bounded route responds;
* NO ``Server`` header is emitted (``--no-server-header``);
* NO access log line is written to stderr, and no request target reaches it (``--no-access-log``);
* a trailing-slash spelling is never answered with a ``307`` redirect to the exposed spelling;
* an unsupported method returns an EMPTY body;
* the process terminates cleanly and leaves no orphan listener.

Usage (from ``backend/``)::

    python tests/deployment/native_uvicorn_process_smoke.py

Environment: set ``SP2_SMOKE_CONTROL_DSN`` to a disposable or local Control DSN and
``SP2_SMOKE_TENANT_SECRET_DIR`` to a scratch directory. Never point this at production or shared
staging. The smoke issues only bounded, unauthenticated probes: it writes no tenant data.
"""

from __future__ import annotations

import json
import os
import pathlib
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from typing import Dict, List, Optional, Tuple

_BACKEND = pathlib.Path(__file__).resolve().parents[2]

# (port, label, uvicorn target, probe route, probe method)
_EDGES: Tuple[Tuple[int, str, str, str, str], ...] = (
    (8080, "API Gateway", "api_gateway.adapters.providers.http_gateway_edge:create_app_from_env", "/health", "GET"),
    (8081, "Control Plane Read", "control_plane.adapters.providers.http_read_api:create_app_from_env", "/memberships", "GET"),
    (
        8082,
        "Auth Router",
        "auth_router.adapters.providers.http_authenticate_api:create_app_from_env",
        "/internal/auth/authenticate",
        "POST",
    ),
    (
        8083,
        "DB Router Dispatch",
        "database_router.adapters.providers.http_dispatch_api:create_app_from_env",
        "/internal/dispatch/route",
        "POST",
    ),
    (
        8084,
        "Tenant Startup",
        "database_router.adapters.providers.http_tenant_startup_api:create_app_from_env",
        "/internal/tenant/startups/read",
        "POST",
    ),
    (
        8085,
        "Gateway Audit",
        "control_plane.adapters.providers.http_gateway_audit_api:create_app_from_env",
        "/internal/gateway-audit/events",
        "POST",
    ),
    (
        8086,
        "Import Audit",
        "control_plane.adapters.providers.http_import_audit_api:create_app_from_env",
        "/internal/import-audit/events",
        "POST",
    ),
    (
        8087,
        "Routing Audit",
        "control_plane.adapters.providers.http_routing_audit_api:create_app_from_env",
        "/internal/routing-audit/events",
        "POST",
    ),
    (8088, "Import Service", "deployment.import_edge:create_app_from_env", "/internal/import/initiate", "POST"),
)

# The canonical runtime flags. On this path they are the ONLY thing standing between the edge and
# uvicorn's defaults (access_log=True, server_header=True, proxy_headers=True).
_CANONICAL_FLAGS = ("--workers", "1", "--no-access-log", "--no-server-header", "--no-proxy-headers")

_ISSUERS = json.dumps(
    {
        "https://issuer.smoke/": {
            "issuer": "https://issuer.smoke/",
            "audience": "sp2",
            "allowed_algs": ["RS256"],
            "jwks": {"keys": []},
            "tenant_claim": "tenant",
        }
    }
)


def _env() -> Dict[str, str]:
    env = dict(os.environ)
    env.update(
        {
            "SP2_CP_CONTROL_STORE": "postgres",
            "SP2_CP_CONTROL_STORE_DSN_REF": "control/control-store-dsn",
            "SNACKPORTAL_SECRET_CONTROL_CONTROL_STORE_DSN_V1": os.environ.get("SP2_SMOKE_CONTROL_DSN", ""),
            "SP2_AR_CONTROL_PLANE_READ_BASE_URL": "http://127.0.0.1:8081",
            "SP2_AR_ISSUERS": _ISSUERS,
            "SP2_DBR_ROUTING_READ_BASE_URL": "http://127.0.0.1:8081",
            "SNACKPORTAL_TENANT_SECRET_DIR": os.environ.get("SP2_SMOKE_TENANT_SECRET_DIR", str(_BACKEND / "build" / "_smoke_secrets")),
            "SP2_IMPORT_DIRECTORY_READ_BASE_URL": "http://127.0.0.1:8081",
            "SP2_GW_AUTH_ROUTER_BASE_URL": "http://127.0.0.1:8082",
            "SP2_GW_CONTROL_READ_BASE_URL": "http://127.0.0.1:8081",
            "SP2_GW_DB_ROUTER_BASE_URL": "http://127.0.0.1:8083",
        }
    )
    # The live-PostgreSQL harness variable must never double as runtime configuration.
    env.pop("SNACKPORTAL_TEST_DSN", None)
    return env


def _probe(port: int, path: str, method: str = "GET", body: Optional[bytes] = None):
    request = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method=method, data=body)
    try:
        with urllib.request.urlopen(request, timeout=6) as response:
            return response.status, response.read(), dict(response.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), dict(exc.headers)
    except Exception as exc:  # noqa: BLE001 - a transport failure is a probe result, not a crash
        return None, repr(exc).encode(), {}


def _wait_listening(port: int, proc: "subprocess.Popen[str]", timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            return False
        with socket.socket() as probe:
            probe.settimeout(0.4)
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.2)
    return False


def _wait_released(port: int, timeout: float = 6.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket() as probe:
            probe.settimeout(0.3)
            if probe.connect_ex(("127.0.0.1", port)) != 0:
                return True
        time.sleep(0.2)
    return False


def _check_edge(port: int, label: str, target: str, route: str, method: str, env: Dict[str, str]) -> List[str]:
    failures: List[str] = []
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        target,
        "--factory",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        *_CANONICAL_FLAGS,
    ]
    proc = subprocess.Popen(command, env=env, cwd=str(_BACKEND), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        if not _wait_listening(port, proc):
            output = proc.stdout.read() if proc.stdout else ""
            return [f"{label}: never began listening. Output tail:\n{output[-1200:]}"]

        # The docs/OpenAPI surface must be unavailable and must publish neither a schema nor
        # FastAPI's structural default body. Edges owning a catch-all route answer with their own
        # non-disclosing envelope instead of an empty body; both are acceptable.
        for docs in ("/docs", "/redoc", "/openapi.json"):
            status, body, _ = _probe(port, docs)
            lowered = body.lower()
            if status != 404:
                failures.append(f"{label}: {docs} answered {status}, expected 404")
            for leak in (b"detail", b"swagger", b"openapi"):
                if leak in lowered:
                    failures.append(f"{label}: {docs} disclosed {leak!r}")

        payload = b"" if method == "POST" else None
        status, _body, headers = _probe(port, route, method, payload)
        if status is None:
            failures.append(f"{label}: the bounded route {route} did not respond")
        if any(name.lower() == "server" for name in headers):
            failures.append(f"{label}: a Server header was disclosed (--no-server-header not effective)")

        slash_status, _b, slash_headers = _probe(port, route + "/", method, payload)
        if slash_status == 307 or "Location" in slash_headers:
            failures.append(f"{label}: a trailing-slash spelling was redirected ({slash_status})")

        _s, method_body, _h = _probe(port, route, "DELETE")
        if method_body != b"":
            failures.append(f"{label}: an unsupported method returned a non-empty body {method_body[:60]!r}")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)
            failures.append(f"{label}: did not exit on terminate; required a kill")
        if not _wait_released(port):
            failures.append(f"{label}: port {port} still listening after termination (orphan process)")
        # --no-access-log: no request line, target, or header may have been written to stderr.
        output = proc.stdout.read() if proc.stdout else ""
        for logged in (route, "GET /", "POST /", '"GET', '"POST'):
            if logged and logged in output:
                failures.append(f"{label}: an access-log line leaked to stderr ({logged!r})")
                break
    return failures


def main() -> int:
    if not os.environ.get("SP2_SMOKE_CONTROL_DSN"):
        print("SP2_SMOKE_CONTROL_DSN is not set — point it at a disposable or local Control DSN.")
        print("Never point this harness at production or shared staging.")
        return 2
    pathlib.Path(_env()["SNACKPORTAL_TENANT_SECRET_DIR"]).mkdir(parents=True, exist_ok=True)
    env = _env()
    all_failures: List[str] = []
    for port, label, target, route, method in _EDGES:
        failures = _check_edge(port, label, target, route, method, env)
        if failures:
            all_failures.extend(failures)
            print(f"[FAIL] {port} {label}")
        else:
            print(f"[ OK ] {port} {label:20s} native uvicorn --factory startup + security posture verified")
    print()
    if all_failures:
        print("FAILURES:")
        for failure in all_failures:
            print("  -", failure)
        return 1
    print(f"ALL {len(_EDGES)} EDGES START NATIVELY VIA uvicorn --factory WITH THE CANONICAL FLAGS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
