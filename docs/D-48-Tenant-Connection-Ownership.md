# D-48 — Tenant Connection Ownership

**Status:** ✅ Approved (Dan, 2026-08-23) — Option A rebuild, Day 1 checkpoint
**Date:** 2026-08-23
**Phase:** Option A Clean FastAPI Rebuild · execution
**Branch:** `rebuild/fastapi-openapi-first`
**Authority:** Dan's ruling at the Day 1 review checkpoint, in answer to finding **N-4** — *"Domain services should hold their own connections."*
**Amends:** **IC-013 §8** (Database Router Boundary). No other section changes.
**Implements:** the runtime change described here, in the same change set. Contract text precedes the code, per `CLAUDE.md` constraint #5.

RFC-2119 keywords **MUST / MUST NOT / SHOULD / MAY** are used normatively.

---

## §1 — What was contested (N-4)

Two governing statements could not both be literal once the architecture became fourteen
separately-deployed processes:

| Source | Statement |
|---|---|
| **IC-013 §8** | "The Database Router remains the **only** service permitted to open a tenant database." |
| **3-day plan, Day 3.6** | end-to-end flow: `… → Database Router → **Tenant Service → Tenant DB** → Response` |

Within one process these reconcile trivially — the router hands the caller a session object.
Across a process boundary they do not: either the tenant service never touches the database
(and the plan's flow is wrong), or something crosses the wire that lets it (and IC-013 §8's
"only" is wrong).

The Day 1 build implemented the first reading, with the router owning tenant record access
behind a closed record-family enum. **Dan ruled for the second reading:** domain services hold
their own connections, using a target the router resolves.

---

## §2 — The decision

> **A tenant-resident domain service MAY open its own tenant database connection, using a
> connection grant issued by the Database Router. The Database Router remains the sole
> AUTHORITY on which physical database a request may reach; it is no longer the sole HOLDER
> of a tenant connection.**

The distinction this decision turns on is **resolution authority** versus **connection
custody**. IC-013 §8 conflated them. They are separated here:

| Concern | Owner | Changed? |
|---|---|---|
| Which single physical database may this request reach? | **Database Router, exclusively** | unchanged |
| Registry-authoritative resolution from the signed claim | **Database Router, exclusively** | unchanged |
| Custody of the connection that reaches it | **the owning domain service** | **changed by this decision** |
| Who may be issued a grant at all | **Database Router, by explicit allowlist** | new |

**Nothing about isolation is relaxed.** One request still resolves to exactly one physical
database, there is still no Control-DB fallback, and no service can reach a tenant the signed
claim does not name. What moves is *where the socket is opened*, not *who decides which socket*.

---

## §3 — Why this is not simply a widening

Handing connection strings to more processes is a real increase in blast radius, and it is
recorded as such. Four constraints are **normative** and exist to bound it. Each is a
requirement on the implementation, not a recommendation.

**C-1 — Grants are issued to an explicit allowlist, never to any authenticated caller.**
The Database Router MUST hold an explicitly configured set of service identities permitted to
receive a tenant connection grant. A caller outside that set MUST be refused, even with a valid
internal credential. **The BFF MUST NOT appear in that set**: it is the public ingress, and the
whole point of the exposure model (IC-013 §21.1 E-1) is that the process nearest the internet is
the one furthest from a credential.

**C-2 — A grant is scoped to exactly one tenant and is short-lived.**
A grant names one tenant reference and carries an expiry. It is not a general database
credential, it is not reusable across tenants, and a service MUST NOT retain one beyond its
stated lifetime.

**C-3 — A grant is never disclosed onward.**
The connection string within a grant MUST NOT appear in any response body, log line, audit
record, error message, health or readiness disclosure, or exception trace. It MUST NOT be
returned to the BFF, to a portal, or to any client under any circumstance.

**C-4 — Resolution is still the router's, and still fails closed.**
A grant is issued only after the same registry-authoritative resolution that IC-013 §8 already
required: unknown tenant → consistent denial, non-ACTIVE tenant → not ready, missing or
unreachable association → unavailable, and **never** a Control-DB fallback. A domain service
cannot obtain a connection the router would not have opened itself.

---

## §4 — Amendment to IC-013 §8

IC-013 §8's third bullet is amended. The section's other rules are unchanged and unweakened.

**Before:**
> - The Database Router remains the **only** service permitted to open a tenant database.

**After:**
> - The Database Router is the **sole authority on tenant-database resolution**: it alone
>   determines which single physical database a request may reach, registry-authoritatively
>   from the signed claim. **A tenant-resident domain service MAY hold the connection it
>   opens**, but only under a Database Router connection grant, and only if that service is on
>   the router's explicit grant allowlist. The BFF is never on that allowlist. *(Amended
>   2026-08-23 by **D-48**; constraints C-1…C-4 of that decision are normative.)*

Everything else in §8 stands as written: `BFF → Database Router` remains the only approved
routing boundary; the BFF never chooses a database; the router never authenticates and never
authorizes; and no component may introduce an alternative database-selection path.

---

## §5 — What this decision does NOT change

- **IC-013 §4** — the request flow and its ordering. Access Control still runs before tenant
  routing, so a denied request still never causes a tenant-database connection.
- **IC-013 §11 / IC-014 §5.4** — one request, one active tenant, one physical database. No
  cross-tenant access, no straddle, no Control-DB fallback.
- **IC-013 §21.1** — the exposure model. Only the BFF is a public ingress; internal services
  bind loopback in local development and publish no port when containerized.
- **IC-014 §2 / §6** — **the Access Control Service is not a tenant-resident domain service and
  is never on the grant allowlist.** It holds no DSN and opens no database. "The service that
  decides access must not be the service that has access" is unchanged and absolute.
- **IC-013 §7** — `RequestContext` still carries no DSN or physical-database identifier.

---

## §6 — Acceptance criteria

Implementation under this decision MUST prove:

1. The BFF is refused a connection grant, and the refusal is tested.
2. A caller outside the allowlist is refused even with a valid internal credential.
3. The Access Control Service imports no database driver and holds no grant.
4. A grant names exactly one tenant, and a grant issued for one tenant cannot be used to reach
   another.
5. Grant issuance fails closed on the same six cases as resolution (unknown, tenantless,
   non-ACTIVE, missing association, unreachable association, unavailable registry) and never
   yields a Control-DB target.
6. No connection string appears in any response, log, audit record, or error path.

---

## §7 — Traceability

| Source | Relationship |
|---|---|
| **IC-013 §8** | amended by §4 above; all other bullets unchanged |
| **IC-013 §4 / §11 / §21.1** | unchanged and explicitly reaffirmed (§5) |
| **IC-014 §2 / §6 / §12** | unchanged; Access Control is permanently off the allowlist |
| **D-46** | the Option A target architecture this decision refines |
| **3-day plan, Day 3.6** | the end-to-end flow this decision makes literally implementable |
| **Day 1 status report, finding N-4** | the conflict this decision closes |
