"""Service configuration and the BIND-versus-PUBLISH exposure model.

The controlling distinction (IC-013 §21.1) is that a process *binds* an address inside its
own network namespace, while a deployment *publishes* a port outward. This module owns the
bind half, with the secure defaults the contract mandates:

* **E-1** — only the BFF is a public ingress. :data:`SERVICE_REGISTRY` records which one
  service that is, and the deployment-manifest check reads it.
* **E-2** — every internal service defaults to loopback. ``0.0.0.0`` is never what happens
  by omission; a developer who needs a wider bind must set it explicitly.
* **E-4** — ``reload`` defaults off and is local-development only.
* **E-5** — one process, access logging off, proxy headers untrusted, server header off,
  all by default, and all overridable per environment because they are deployment
  settings rather than architecture invariants.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, Mapping, Optional

#: The version every service in this rebuild reports. Bumped as a set, because the
#: fourteen services are released together as one backend.
BACKEND_VERSION = "1.0.0"

#: The loopback bind that E-2 makes the default for every internal service.
LOOPBACK = "127.0.0.1"


@dataclass(frozen=True)
class ServiceDescriptor:
    """Static identity of one service: what it is called and where it listens by default.

    ``public_ingress`` is the machine-readable form of IC-013 §13 / §21.1 E-1. Exactly one
    descriptor in :data:`SERVICE_REGISTRY` may carry ``True``, and it must be the BFF; the
    deployment-manifest check asserts both halves.
    """

    key: str
    title: str
    default_port: int
    public_ingress: bool = False


# The fourteen services of the Option A target architecture (IC-013 §2). Ports follow the
# 3-day plan §3.4 example block. The legacy Gateway-era edges occupied 8080-8088 and a
# standing local fixture still uses that range, so the new topology deliberately does not
# reuse it — nothing in the new runtime binds a port the retired architecture bound.
SERVICE_REGISTRY: Mapping[str, ServiceDescriptor] = {
    "bff": ServiceDescriptor("bff", "SnackPortal2 BFF", 8000, public_ingress=True),
    "authentication": ServiceDescriptor("authentication", "SnackPortal2 Authentication Service", 8001),
    "access_control": ServiceDescriptor("access_control", "SnackPortal2 Access Control Service", 8002),
    "control_plane": ServiceDescriptor("control_plane", "SnackPortal2 Control Plane Service", 8003),
    "database_router": ServiceDescriptor("database_router", "SnackPortal2 Database Router Service", 8004),
    "startups": ServiceDescriptor("startups", "SnackPortal2 Startup Service", 8005),
    "investors": ServiceDescriptor("investors", "SnackPortal2 Investor Service", 8006),
    "deals": ServiceDescriptor("deals", "SnackPortal2 Deal Service", 8007),
    "sharing": ServiceDescriptor("sharing", "SnackPortal2 Sharing Service", 8008),
    "import_service": ServiceDescriptor("import_service", "SnackPortal2 Import Service", 8009),
    "lineage": ServiceDescriptor("lineage", "SnackPortal2 Lineage Service", 8010),
    "contacts": ServiceDescriptor("contacts", "SnackPortal2 Contacts Service", 8011),
    "ai_agents": ServiceDescriptor("ai_agents", "SnackPortal2 AI Agent Service", 8012),
    "audit": ServiceDescriptor("audit", "SnackPortal2 Audit Service", 8013),
}

#: The one service permitted to be a public ingress (E-1). Derived, never hand-written, so
#: it cannot drift from the registry the services themselves are built from.
PUBLIC_INGRESS_SERVICE = next(key for key, svc in SERVICE_REGISTRY.items() if svc.public_ingress)


def _env_prefix(service_key: str) -> str:
    return "SP2_" + service_key.upper()


@dataclass(frozen=True)
class ServiceSettings:
    """Resolved runtime settings for one service instance."""

    key: str
    title: str
    version: str
    host: str
    port: int
    reload: bool
    access_log: bool
    server_header: bool
    proxy_headers: bool
    public_ingress: bool

    @property
    def docs_url(self) -> str:
        return "/docs"

    @property
    def redoc_url(self) -> str:
        return "/redoc"

    @property
    def openapi_url(self) -> str:
        return "/openapi.json"


def load_settings(service_key: str, env: Optional[Mapping[str, str]] = None) -> ServiceSettings:
    """Resolve one service's settings from the environment, secure-by-omission.

    Every knob below takes its secure default when unset (E-5 rule 1). Departing from a
    secure default is therefore always a deliberate, environment-scoped act — it can never
    happen because someone forgot to configure something.
    """
    source: Mapping[str, str] = os.environ if env is None else env
    descriptor = SERVICE_REGISTRY[service_key]
    prefix = _env_prefix(service_key)

    host = source.get(prefix + "_HOST", "").strip() or LOOPBACK

    raw_port = source.get(prefix + "_PORT", "").strip()
    port = int(raw_port) if raw_port else descriptor.default_port

    def flag(suffix: str, default: bool) -> bool:
        raw = source.get(prefix + suffix)
        if raw is None or raw == "":
            return default
        return raw.strip().casefold() in {"1", "true", "yes", "on"}

    return ServiceSettings(
        key=descriptor.key,
        title=descriptor.title,
        version=BACKEND_VERSION,
        host=host,
        port=port,
        # E-4: reload is a local-development convenience and is off unless explicitly asked for.
        reload=flag("_RELOAD", False),
        # E-5 secure defaults. Each is overridable per environment; none is an architecture invariant.
        access_log=flag("_ACCESS_LOG", False),
        server_header=flag("_SERVER_HEADER", False),
        # E-5 rule 2: forwarded headers are untrusted unless an explicit trusted-proxy
        # boundary is configured. Rule 3 still applies absolutely — enabling this changes
        # how the client address is derived and NOTHING else. It never introduces a tenant
        # carrier, a routing authority, or an identity source.
        proxy_headers=flag("_PROXY_HEADERS", False),
        public_ingress=descriptor.public_ingress,
    )


def default_ports() -> Dict[str, int]:
    """The service-to-default-port map, for launchers, runbooks and manifest checks."""
    return {key: svc.default_port for key, svc in SERVICE_REGISTRY.items()}


__all__ = [
    "BACKEND_VERSION",
    "LOOPBACK",
    "PUBLIC_INGRESS_SERVICE",
    "SERVICE_REGISTRY",
    "ServiceDescriptor",
    "ServiceSettings",
    "default_ports",
    "load_settings",
]
