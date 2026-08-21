# IC-014 — Access Control Contract

**Status:** Draft / Proposed · **Revision:** IC-014-DRAFT-1 · **Phase:** Architecture Planning · **Type:** Contract-first specification (no implementation)
**Opened:** 2026-08-21 by **D-46** (Option A Gateway-Free Target Architecture Ratification), Phase 0.5 — Contract Reconciliation.
**Supersedes (jointly with IC-013):** **IC-010 — API Gateway Contract** (`Final` → `Superseded`).
**Authored fresh.** No text is cherry-picked from the abandoned `phase/00-architecture-ratification` branch.

Requirement keywords **MUST / MUST NOT / SHOULD / MAY** are used in the RFC-2119 sense.

---

## §0 — Why this contract exists

Phase 0 established a finding that this contract answers directly:

> **No permission engine exists anywhere in SnackPortal2's production code.** Authentication checks identity (`auth_router`). Membership is *stored* but, in the Control Plane's own words, *"roles stored, never evaluated"*. Residency is enforced as a **side-effect** of routing. Edge role-gating lives inside the Gateway. **Nothing evaluates a permission.**

Authorization today is a *distributed implicit property*. That is workable only while the Gateway is the sole public surface and the surface is three operations wide. Under the Option A target — fourteen services, an enumerated and growing BFF surface, and eventually AI agents acting on records — an implicit property is not sufficient.

**Access Control is therefore the one genuinely greenfield service in the rebuild.** It has no existing implementation to port from. This contract is its first governing specification, and it exists **before** any code, as `CLAUDE.md` constraint #5 requires.

---

## §1 — Purpose

Define the **FastAPI Access Control Service**: the single home for cross-cutting authorization in SnackPortal2. It answers exactly one question:

```text
What is this principal allowed to do?
```

It returns **Allowed** or **Denied**. It does nothing else.

---

## §2 — The four-way separation *(ratified by D-46 §3)*

```text
Authentication  ≠  Access Control  ≠  Tenant Routing  ≠  Database Access
```

| Service | Question | Contract |
|---|---|---|
| Authentication | *Who are you?* | IC-005 |
| **Access Control** | *What are you allowed to do?* | **this contract** |
| Database Router | *Which active tenant and physical database may this request use?* | IC-005 / D-07 |
| Database Access | *the physical connection* | Database Router, exclusively |

**Access Control MUST NOT:**
- **authenticate** — it consumes an already-established `RequestContext`; it never validates a token, reads a JWKS, parses a claim, or issues a session;
- **select, name, resolve, or connect to any database** — it holds no DSN, no tenant→database mapping, no naming convention, and no override;
- **re-derive the active tenant** — the active tenant arrives in the `RequestContext` from the signed claim and is consumed as given;
- **read tenant business data** to reach a decision (§6);
- **fail open** — under any error, timeout, ambiguity, or unknown input, the answer is **Denied** (§8);
- **compose responses**, dispatch operations, or perform business logic.

---

## §3 — Position in the request flow *(IC-013 §4)*

```text
Request
  → Authentication            (IC-005)
  → Carrier Validation        (BFF — IC-013 §5)
  → RequestContext Creation   (BFF — IC-013 §7)
  → ACCESS CONTROL            ← this contract
  → Tenant Routing            (Database Router)
  → Service invocation
  → Response Composition      (BFF — IC-013 §19)
```

**Normative placement rules:**
- Access Control runs **after** `RequestContext` construction — so it always decides on a context built exclusively from `AuthContext`, never on client input.
- Access Control runs **before** Tenant Routing — so a denied request **never reaches the Database Router and never causes a tenant-database connection**. A decision made after routing would already have paid the isolation cost it exists to prevent.
- **No service may be invoked without a prior Allowed decision.** A service that is reachable without one is a contract violation regardless of what it does internally.

---

## §4 — The decision inputs (normative — exhaustive)

An authorization decision is computed from exactly these inputs, all of which are **references, codes, or enumerations — never payloads**:

| Input | Source | Notes |
|---|---|---|
| **Principal reference** | `RequestContext.principal_ref` | never a name, email, or identity payload |
| **Platform role** | `RequestContext.role` | one of the six D-32 MVP roles (§5) |
| **Active tenant context** | `RequestContext.tenant_context` | the signed claim, or *tenantless-CONTROL*; consumed as given |
| **Tenant membership** | Control Plane read | principal ↔ tenant ↔ role; 1:N membership (D-04) |
| **Requested action** | the BFF operation being attempted | from the §16 enumerated operation set (IC-013) |
| **Target record reference** | opaque record ref, where the action names one | never field content |
| **Record residency** | Control-resident vs tenant-resident | derived from the operation category, never from client input |
| **Ownership reference** | `owner_agent_ref` / `owner_ai_agent_ref` (IC-008) | **input only** — see §7 |
| **AI agent identity, assigned skills, approved tools** *(reserved — §9)* | AI Agent Service | inert until IC-006 is Draft-complete |

**Prohibited as a decision input** — these MUST NOT influence any decision, and MUST NOT be read by this service for any purpose:
a cookie · a query-string parameter · portal state · workspace state · client local storage · a request body field claiming identity, tenancy, role, or permission · an unrecognized header · a physical database identifier · a DSN, secret, credential, or token · tenant business data (§6).

---

## §5 — What is evaluated

### §5.1 — Roles *(IC-005 / D-32 — exactly six MVP platform roles)*

`CONTROL` · `MASTER_AGENT` · `TENANT_ADMIN` · `TENANT_AGENT` · `STARTUP_USER` · `INVESTOR_USER`

These are **platform/token roles**. They are not per-record permissions and they are not tenant organizational roles. Where IC-007's dual-layer model later introduces tenant organizational roles, those are **references-only** and are **not token roles** (D-38); this service MUST keep the two layers distinct.

The `CONTROL_AI` role remains **reserved and unused** (Canonical Overview Part 4B). This service MUST NOT bind it to any capability under this revision.

### §5.2 — Permissions

A permission is a named, enumerated capability required by a BFF operation. The permission set is **closed**: an operation requiring a permission that is not in the enumerated set MUST be denied.

The `ai.invoke` permission remains **defined but unwired** (Part 4B): it MUST exist in the permission vocabulary and MUST NOT be granted to any principal under this revision.

### §5.3 — Tenant membership and tenant access

Membership is **1:N** (one principal, many tenants) with **exactly one active tenant per request** (D-04). This service verifies that the principal holds a membership in the **active tenant named by the signed claim**. A principal whose claim names a tenant they are not a member of MUST be denied **before any routing occurs**.

**Membership is not a permission.** Being a member of a tenant establishes *tenant access*, not *what may be done there*. Both checks are required.

### §5.4 — Record residency

Every action targets either a **Control-resident** record or a **tenant-resident** record, determined by the operation category — never by client input.

**Access Control owns the single-domain decision** (re-homed from IC-010 §K by D-46 §4):

```text
One Request → One Active Tenant → One Physical Database
```

- A request MUST resolve to the Control DB **or** exactly one tenant DB — never both, never several.
- A request that would require two tenant domains, or a Control+tenant straddle, MUST be **Denied** with an isolation outcome.
- **There is no Control-DB fallback.** "Tenant DB unavailable" MUST NOT produce a Control-DB decision.
- **Cross-tenant access is denied by default.** Any cross-tenant capability is IC-007-deferred (§10).

**Division of authority with IC-013.** This service **decides** that the request's single resolution domain is lawful; the BFF **enforces** that exactly one domain was decided and refuses to invoke a service otherwise (IC-013 §11). Neither may be omitted: a decision without enforcement is advisory; enforcement without a decision is a guess.

---

## §6 — The no-tenant-data rule (normative)

**Access Control MUST NOT read tenant business data to reach a decision.**

It decides on references, roles, memberships, residency classifications and ownership *references* — never on the content of a startup, investor, deal, contact, or document.

*Rationale.* If this service could read tenant data, it would need a database connection; if it had a connection, it would need tenant routing; and the four-way separation would collapse into two. **The service that decides access must not be the service that has access.** Where an ownership reference is needed, it is supplied to this service as a reference by the caller or read through a governed, references-only port — never by opening a tenant database.

---

## §7 — Ownership is an input, never an authority *(IC-008)*

**Ownership ≠ Authorization.** Ownership never grants a permission (IC-008 V6). It is one *input* among several, consulted only where an operation's rule explicitly names it.

Carried forward from IC-008 and D-36, unchanged:
- **Ownership ≠ Database Residency** — ownership never changes Control-DB / tenant-DB boundaries.
- **Ownership ≠ Visibility** — visibility remains governed by permissions and contracts.
- **Cross-tenant ownership is impossible** (V7).
- Ownership references are **references only** — no names, no emails, no identity payloads (V8).
- `owner_ai_agent_ref` is **unpopulated platform-wide pre-IC-006** (V10). This service MUST treat a populated AI-owner reference as an error condition under this revision, not as a grant.

**Cardinality — RATIFIED (D-47, 2026-08-21; CONF-4 closed).** This service MUST read ownership as **exactly one human owner reference and at most one *current* AI owner reference**, per IC-008 as ratified. Concretely:
- It MUST treat `owner_agent_ref` and `owner_ai_agent_ref` as **single references, never sets**. A decision path that iterates a collection of owners is a contract violation.
- **A contribution is not an owner.** Task-history, provenance (IC-004) and operational-audit (IC-002) records MAY show any number of AI Agents having contributed to a record. **None of them is an authorization input.** This service MUST NOT read a contribution record to reach a decision, MUST NOT treat contribution as ownership, and MUST NOT grant anything on the basis of it. This follows from §6 (no tenant-data reads) and Ownership Principle 1 (**Ownership ≠ Authorization**): if ownership itself grants nothing, contribution grants strictly less than nothing.
- Where a record's live AI-owner reference is populated at all — which it MUST NOT be pre-IC-006 (§7 above, IC-008 V10) — a **second concurrent** AI owner is an **error condition**, never a grant.
- **Option C** (a separate, explicitly non-ownership AI-involvement relation) is **reserved and inert**. Should it later be adopted, it arrives as an *involvement* relation and MUST NOT become an authorization input without an amendment to this contract.

---

## §8 — Decision semantics

### §8.1 — The result

The service returns exactly one of:

| Result | Meaning |
|---|---|
| **Allowed** | the request may proceed to Tenant Routing |
| **Denied** | the request terminates; a canonical denial code is returned |

There is no third value. There is no "allowed with warnings", no partial allow, and no allow-with-scope-narrowing — an operation is permitted in full or not at all.

### §8.2 — Fail closed (absolute)

**Under any of the following the answer is Denied:** an unknown principal · an unknown tenant · an unknown action · an unknown permission · a missing or malformed `RequestContext` field · an unavailable Control Plane read · a timeout · an internal error · an ambiguous rule · two rules in conflict · any condition not explicitly covered by a rule.

**Deny is the default outcome, not the exceptional one.** A decision path that could produce Allowed by omission — a missing branch, a fall-through, an unhandled case — is a contract violation. Rules grant; they never revoke a default grant, because there is no default grant.

### §8.3 — Consistent denial *(IC-002 / IC-005)*

**Unknown tenant and unauthorized tenant MUST be indistinguishable** to the caller. A denial MUST NOT reveal whether a tenant, principal, or record exists.

Denial responses carry **canonical codes only** — never tenant counts, tenant identities, database identifiers, topology, secret state, rule text, or internal failure reasons. The denial vocabulary reuses the existing canonical set (IC-005 401/403; IC-002 *not found* / *not ready* / *administratively disabled* / *unavailable*); **no new public denial code is introduced by this contract.**

### §8.4 — Determinism

The same inputs MUST produce the same decision. A decision MUST NOT depend on wall-clock time (beyond explicit validity windows), request ordering, cache warmth, or which instance served it.

---

## §9 — AI authorization *(reserved — inert under this revision)*

The Option A governance model is ratified as the *target*:

```text
AI Agent
+ Assigned Skills
+ Approved Tools
+ Permissions
+ Active Tenant / Data Residency
= Permitted AI Actions
```

The separations are **normative and MUST be preserved**:

```text
AI Skill  ≠  Permission
AI Skill  ≠  Tenant Access
AI Skill  ≠  Database Routing
```

- **A skill is a capability an agent has. A permission is an authorization to use it here, now, on this record.** Possessing a skill grants nothing.
- An AI agent's tenant access is evaluated **exactly as a human principal's is** (§5.3). An AI agent MUST NOT reach a tenant its identity is not scoped to.
- An AI agent MUST NOT influence database routing. Routing remains registry-authoritative from the signed claim.
- **AI cannot authorize.** An AI agent MUST NOT grant, escalate, or delegate a permission — to itself, to another agent, or to a human (D-38).

**Status: inert.** `ai.invoke` stays defined and unwired; the `CONTROL_AI` role stays reserved and unbound; no AI decision path is implemented under this revision. **IC-006 MUST be authored to Draft-complete before any AI authorization is implemented** (D-46 §6, CONF-5), and the Canonical Overview Part 4B governance gate — a compliance and permissions review is a prerequisite, not an afterthought — **applies and is unwaived**.

---

## §10 — Deferrals

- **Cross-tenant sharing authorization** is governed by **IC-007** (`Draft / Proposed`). Under this revision, cross-tenant access is **denied by default** and no positive sharing capability exists. IC-007 MUST be promoted to `Final` before any sharing authorization is implemented (D-46 §6, CONF-6).
- **AI authorization** — §9, deferred to IC-006.
- **Tenant organizational roles** (IC-007's dual-layer model) remain references-only and are **not token roles**; binding them is IC-007 work.

---

## §11 — Audit

Every **Denied** decision at the ingress edge surfaces as a `RouteDenied` ingress-edge audit event, and every detected single-domain breach as an `IsolationAnomaly` (IC-013 §10). **The BFF is the sole emitter**; this service does not emit ingress-edge audit itself.

Where this service's own decisions are recorded, records are **references only** — `actor_ref`, `subject_ref`, `tenant_ref`, `record_ref`, action, outcome, timestamp, correlation id.

**Prohibited in any record:** names, emails, PII, tenant business data, field content, raw rows, rule text that would disclose policy internals, database identity, DSN, secret, credential, token, or stack trace.

---

## §12 — Service shape

This service follows IC-013 §21 in full: its own package, its own entry module, independent start/stop, configurable port, liveness/readiness (minimally disclosing — IC-013 §17), its own tests, app-factory shape, and the pinned serving posture.

**Additional constraints:**
- It MUST NOT depend on `psycopg` or any database driver. It holds no database connection of any kind.
- It MUST NOT import another service's internal implementation; it reaches the Control Plane over a governed, references-only transport port.
- It MUST be reachable **only** internally (IC-013 §13), under the exposure model at **IC-013 §21.1**: loopback/private bind by default in local development (E-2), container-network reachability with **no published port** when containerized (E-3), and `reload` local-development only (E-4). **The BFF is the sole public ingress (E-1).** An Access Control Service reachable from a client network zone is a contract violation — and, of every service in the topology, the most consequential one to get wrong: a directly-reachable authorizer can be asked for a decision that no BFF flow ever requested.
- It MUST be **stateless** with respect to decisions. Caching of membership/role reads is permitted with a bounded TTL and explicit tenant-scoped invalidation (D-11); a cache MUST NOT extend a grant beyond its TTL, and a cache miss or error MUST fail closed (§8.2).

---

## §13 — Acceptance Criteria

When this service is built under a separate, explicitly-authorizing execution instruction, it MUST satisfy:

1. **Separation proofs.** Architecture tests prove it imports no database driver, opens no database, validates no token, and imports no other service's internal implementation.
2. **Fail-closed proof.** Every error, timeout, unknown input, and unhandled case yields **Denied** — proven by fault injection, not by inspection. A mutation that removes a deny branch MUST cause a test failure.
3. **No-fall-through proof.** A test proves there is no code path reaching Allowed without an explicit granting rule.
4. **Membership proof.** A principal whose signed claim names a tenant they are not a member of is denied **before any Database Router contact** — proven by observing that no connection was attempted.
5. **Single-domain proof.** An operation requiring two tenant domains, or a Control+tenant straddle, is denied with an isolation outcome. `ACME → ACME DB + ZETA DB` is denied. `ACME DB unavailable → Control DB` is denied.
6. **Consistent-denial proof.** Unknown tenant and unauthorized tenant produce byte-identical responses.
7. **Ownership-is-not-authorization proof.** A principal who owns a record but lacks the permission is denied; ownership alone never grants.
8. **Determinism proof.** Identical inputs yield identical decisions across instances and cache states.
9. **Reference-only proof.** No decision record or response contains a name, email, PII, payload, database identifier, or credential.
10. **AI inertness proof.** `ai.invoke` is ungranted, `CONTROL_AI` is unbound, and a populated `owner_ai_agent_ref` never produces Allowed under this revision.

---

## §14 — Anti-Vendor-Lock-In Requirements

- No Supabase RLS-as-authorization, PostgREST, or Supabase Auth — authorization is application logic in a governed service, never a database feature.
- No Lovable or frontend-platform runtime dependency.
- No cloud-provider IAM primitive as the decision engine; the model must run identically on AWS, Azure, Google Cloud, and self-hosted.
- Python · FastAPI · Pydantic only (Option A §3).

---

## §15 — Not implemented · Implementation prohibited

**No authorization behaviour is implemented by this contract.** No runtime is created or changed. No blocker is closed. Production remains **NOT READY / DO-NOT-ACTIVATE**.

Implementation proceeds only under a separate, explicitly-authorizing execution instruction (register entry → contract → code), inheriting the §13 acceptance criteria.

---

## §16 — Traceability

| Source | Relationship |
|---|---|
| **D-46** | Opens this contract; ratifies the four-way separation; §4 re-homing map assigns §5.4 here |
| **IC-010** | **Superseded** by this contract + IC-013. §K isolation decision authority re-homed here |
| **IC-013** | Co-successor — the BFF calls this service (§4) and enforces its single-domain decision (§11) |
| **IC-005** | Authentication boundary; six-role hierarchy (D-32); denial vocabulary |
| **IC-002** | Tenant lifecycle, readiness gating, consistent-denial semantics |
| **IC-008** | Ownership is reference-only and never authorizes (§7); CONF-4 open |
| **IC-009** | Per-role × per-directory visibility matrix — the presentation-layer counterpart to these decisions |
| **IC-006 / IC-007** | Deferrals (§9, §10) |
| **D-04 / D-11 / D-30 / D-32 / D-36 / D-38** | 1:N membership with one active tenant; cache invalidation; isolation enforcement; role hierarchy; ownership architecture; dual-layer roles and "AI cannot authorize" |
| **Canonical Overview Part 4B** | `CONTROL_AI` role reserved; `ai.invoke` defined but unwired; AI governance gate |
