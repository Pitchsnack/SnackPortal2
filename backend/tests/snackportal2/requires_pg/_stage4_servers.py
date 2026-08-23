"""Launch the rebuilt services as real uvicorn processes, composed from the environment.

The in-process ASGI harness (``tests/snackportal2/test_end_to_end.py``) reaches each service's
real application, which is enough to prove wiring — but it reaches it by *substituting* the
transport, so the production HTTP clients (``HttpAuthentication``, ``HttpControlPlaneRegistry``,
``RouterGrantProvider``, ``HttpControlPlaneMemberships``, ``HttpDomainService``, ``HttpAudit``)
never execute, and neither does the environment-driven composition inside each ``main.py``.

Stage 4 needs both. So this module starts the services the way a deployment does — one
``uvicorn`` process per service, configuration supplied only through environment variables —
and the tests drive them over real HTTP against real PostgreSQL.

Two properties are inherited from doing it this way rather than by hand-wiring objects:

* every ``build_*`` selector runs for real, so "configured PostgreSQL" is proven to be what
  the service actually chooses at boot rather than what a test injected afterwards; and
* each service's stdout/stderr is captured, which makes "no credential appears in logs"
  (§5) an assertion over real process output instead of an inspection of source.

Ports are chosen by asking the OS for a free one, so a Stage 4 run never collides with the
standing local fixture or with the rebuild's own default ports.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Mapping, Optional

from . import _stage4_pg as pg

#: How long a service is given to bind and answer ``/health``.
STARTUP_TIMEOUT_SECONDS = 45.0

#: Module path per service key, matching each service's own documented start command.
SERVICE_MODULE = {
    key: "snackportal2.services." + key + ".main:app"
    for key in (
        "bff",
        "authentication",
        "access_control",
        "control_plane",
        "database_router",
        "startups",
        "investors",
        "deals",
        "sharing",
        "import_service",
        "lineage",
        "contacts",
        "ai_agents",
        "audit",
    )
}


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@dataclass
class ServiceProcess:
    """One running service: where to reach it, and what it printed."""

    key: str
    port: int
    process: subprocess.Popen
    log_path: Path
    env_keys: List[str] = field(default_factory=list)

    @property
    def base_url(self) -> str:
        return "http://127.0.0.1:" + str(self.port)

    def log_text(self) -> str:
        try:
            return self.log_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""


class ServiceFleet:
    """A set of service processes started for one test module, stopped together."""

    def __init__(self, log_dir: Path) -> None:
        self._log_dir = log_dir
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self.services: Dict[str, ServiceProcess] = {}

    # -- lifecycle ---------------------------------------------------------------------

    def start(self, key: str, env: Mapping[str, str], port: Optional[int] = None) -> ServiceProcess:
        """Start one service with exactly the supplied environment additions.

        The child inherits the parent environment so that PATH and the Python install work,
        then the supplied mapping is layered on top. Every ``SP2_`` variable the parent
        happens to carry is stripped first, so a service can never be accidentally configured
        by a leftover variable from another test.
        """
        chosen = port if port is not None else free_port()
        child_env = {name: value for name, value in os.environ.items() if not name.startswith("SP2_")}
        child_env["PYTHONPATH"] = str(pg.BACKEND_ROOT)
        child_env["PYTHONUNBUFFERED"] = "1"
        child_env.update(env)

        log_path = self._log_dir / (key + ".log")
        handle = log_path.open("wb")
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                SERVICE_MODULE[key],
                "--host",
                "127.0.0.1",
                "--port",
                str(chosen),
                "--no-access-log",
            ],
            cwd=str(pg.BACKEND_ROOT),
            env=child_env,
            stdout=handle,
            stderr=subprocess.STDOUT,
        )
        service = ServiceProcess(key=key, port=chosen, process=process, log_path=log_path, env_keys=sorted(env))
        self.services[key] = service
        self._await_health(service)
        return service

    def _await_health(self, service: ServiceProcess) -> None:
        import httpx

        deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
        last: str = ""
        while time.monotonic() < deadline:
            if service.process.poll() is not None:
                raise RuntimeError(
                    service.key + " exited during startup (code " + str(service.process.returncode) + "):\n" + service.log_text()
                )
            try:
                response = httpx.get(service.base_url + "/health", timeout=1.0)
                if response.status_code == 200 and response.json().get("service") == service.key:
                    return
                last = "unexpected /health: " + str(response.status_code) + " " + response.text
            except Exception as exc:  # connection refused while the socket is not yet bound
                last = type(exc).__name__
            time.sleep(0.2)
        raise RuntimeError(service.key + " never became healthy (" + last + "):\n" + service.log_text())

    def stop(self) -> None:
        for service in self.services.values():
            if service.process.poll() is None:
                service.process.terminate()
        for service in self.services.values():
            try:
                service.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                service.process.kill()

    # -- inspection --------------------------------------------------------------------

    def url(self, key: str) -> str:
        return self.services[key].base_url

    def all_logs(self) -> Dict[str, str]:
        return {key: service.log_text() for key, service in self.services.items()}


def dsn_secret_fragments() -> List[str]:
    """The substrings that would betray a live DSN if one reached a response or a log.

    Derived from the configured DSNs themselves rather than hard-coded, so the check is
    about *these* credentials and cannot be satisfied by a placeholder. The fragments are
    never printed; only their absence is asserted.
    """
    from urllib.parse import urlsplit

    fragments: List[str] = []
    for name in ("control",) + tuple(pg.TENANTS):
        value = pg.dsn(name)
        if not value:
            continue
        fragments.append(value)
        parts = urlsplit(value)
        if parts.password:
            fragments.append(parts.password)
        if parts.hostname and parts.port:
            fragments.append(str(parts.hostname) + ":" + str(parts.port))
        path = parts.path.lstrip("/")
        if path:
            fragments.append(path)
    # Deduplicate while keeping the longest first, so a failure names the most specific leak.
    return sorted({fragment for fragment in fragments if fragment and len(fragment) > 3}, key=len, reverse=True)


__all__ = [
    "SERVICE_MODULE",
    "STARTUP_TIMEOUT_SECONDS",
    "ServiceFleet",
    "ServiceProcess",
    "dsn_secret_fragments",
    "free_port",
]
