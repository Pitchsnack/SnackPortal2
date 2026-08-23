# Runbook — starting the Option A rebuild services

**Scope:** the fourteen services under `backend/snackportal2/services/` (D-46). This runbook does
not cover the retired Gateway-era edges; those have their own runbook and are not part of this
runtime.

---

## The one thing to get right

> **Only the BFF is a public ingress.** Every other service binds loopback in local development
> and publishes no port when containerized (IC-013 §21.1 E-1/E-3).

The distinction is **BIND** versus **PUBLISH**. A process *binds* an address inside whatever
network namespace it runs in; a deployment *publishes* a port outward. Conflating them produces
both false alarms — a container binding `0.0.0.0` inside its own namespace is normal and
necessary — and real holes: a service correctly bound to a private interface, then published to
the world by one line in a compose file.

The most consequential service to expose by mistake is **Access Control**. A directly-reachable
authorizer can be asked for a decision that no BFF flow ever requested.

---

## Local development — one service at a time

Each service starts itself. No factory, no `--factory`, and no shared runtime module is required
(IC-013 §21 explicitly does not mandate any of them).

```bash
python -m snackportal2.services.bff.main
python -m snackportal2.services.authentication.main
python -m snackportal2.services.access_control.main
```

Or with an external ASGI server command, which production may also use:

```bash
uvicorn snackportal2.services.bff.main:app --host 127.0.0.1 --port 8000
```

### Ports

Ports are configuration, not business contracts. These are the defaults:

| Service | Port | Public ingress |
|---|---|---|
| BFF | 8000 | **yes — the only one** |
| Authentication | 8001 | no |
| Access Control | 8002 | no |
| Control Plane | 8003 | no |
| Database Router | 8004 | no |
| Startup | 8005 | no |
| Investor | 8006 | no |
| Deal | 8007 | no |
| Sharing | 8008 | no |
| Import | 8009 | no |
| Lineage | 8010 | no |
| Contacts | 8011 | no |
| AI Agent | 8012 | no |
| Audit | 8013 | no |

The retired Gateway-era edges occupied **8080–8088** and a standing local fixture still uses that
range, so the rebuild deliberately does not reuse it. Nothing in the new runtime binds a port the
retired architecture bound.

### Configuration

Every setting takes its secure default when unset (E-5 rule 1), so departing from one is always a
deliberate act rather than something that happened because someone forgot:

| Variable | Default | Notes |
|---|---|---|
| `SP2_<SERVICE>_HOST` | `127.0.0.1` | E-2. `0.0.0.0` is never the default for an internal service. |
| `SP2_<SERVICE>_PORT` | see table | |
| `SP2_<SERVICE>_RELOAD` | `false` | E-4. Local development only, never a shared environment. |
| `SP2_<SERVICE>_ACCESS_LOG` | `false` | E-5. Environment-configurable; some regulated environments require access logs. |
| `SP2_<SERVICE>_SERVER_HEADER` | `false` | E-5. Recommended default, not a locked invariant. |
| `SP2_<SERVICE>_PROXY_HEADERS` | `false` | E-5. Requires an **explicit trusted-proxy boundary**. A forwarded header is **never** a tenant carrier or a routing authority. |

**Unconfigured means closed.** With no trust anchor, no Control Plane URL and no service URLs
set, the topology starts and does nothing: nobody authenticates, nothing is authorized, no tenant
resolves. That is intentional — an unconfigured deployment should be useless, not open.

---

## Containers

```bash
docker compose -f infrastructure/docker/docker-compose.rebuild.yml \
  --env-file infrastructure/docker/.env.local up
```

That manifest is the E-6 subject: **exactly one application service has a `ports:` clause, and it
is the BFF.** Internal services declare `expose:` only — container-network reachability by service
name, and nothing else. Adding a `ports:` clause to an internal service is a contract violation,
not a convenience, and
`backend/tests/snackportal2/test_deployment_exposure.py` fails when one appears.

---

## Tenant connection grants (D-48)

Tenant-resident services hold their own database connections, obtained per request as a
short-lived single-tenant grant from the Database Router. Configure the router's allowlist:

```bash
SP2_DATABASE_ROUTER_GRANTEES='{"<credential>":"startups","<credential>":"investors"}'
```

The router **refuses to start** if that map names the BFF or the Access Control Service. Both are
permanently excluded (D-48 C-1): the process nearest the internet and the process that decides
access are both, deliberately, the furthest from a credential.

---

## Verifying a running service

```bash
curl -s http://127.0.0.1:8000/health
curl -s http://127.0.0.1:8000/readiness
curl -s http://127.0.0.1:8000/openapi.json | head -c 200
```

Health and readiness are public and minimally disclosing (IC-013 §17): they report liveness and
operational status and nothing about databases, tenants, topology, secret state, or why anything
failed.

To confirm an internal service is *not* publicly reachable, the check is the manifest, not the
port: a `curl` that fails proves only that it failed today.
