# IC-014 — Access Control Contract

**Status:** Draft / Proposed · **Phase:** Architecture ratification (Phase 0) · **Type:** Contract-first specification (no implementation)
**Opened:** by **D-45 — FastAPI Implementation Proposal v2.2 Target-Architecture Ratification**. **Revision:** IC-014-DRAFT-1.
RFC-2119 keywords **MUST / MUST NOT / SHOULD / MAY** are used normatively.

> **Contract-first, no positive capability.** This contract defines **where authorization decisions live and what they may never do**. It grants no permission, no role, no route, no DTO, no error code, no cross-tenant capability, no audit class, and no DDL. It enumerates no permission catalogue — permissions remain contract-controlled and are added only by the contract that owns the capability. It changes no authentication, routing, or isolation semantics. IC-014 becomes **Final** only after independent verification and explicit human merge. **Production remains NOT READY / DO-NOT-ACTIVATE.**

---

## §1 — Purpose and the gap this closes

IC-005 owns authentication and tenant-scope authorization, and explicitly delegates per-feature authorization to "each feature contract". No contract has ever owned the **cross-cutting** permission model: how a role, a membership, an ownership reference, a workspace scope, a requested action, and (later) an AI-agent skill combine into a single allow-or-deny.

IC-014 is that home. It defines the **Access Control Service** as an independently bootable FastAPI service whose only product is a decision.

## §2 — The four-way separation (normative)

```
Authentication  = who is the principal?               -> IC-005
Access Control  = what may this principal do?          -> IC-014
Tenant Routing  = which single active tenant and DB?   -> IC-005 / Database Router
Database Access = the routed session itself            -> Database Router
```

**Authenticated is not authorized.** A valid token establishes identity and the signed tenant claim; it grants no application permission by itself.

**Authorized is not routed.** An allow decision grants no database, no tenant, and no session. Routing remains a separate act performed by a separate component from the signed claim.

## §3 — What the Access Control Service evaluates

The service takes a decision request and returns a decision. The inputs it MAY consider are:

- the authenticated principal reference;
- the active role (D-32);
- tenant membership as established by IC-005;
- the active tenant context, as a **read-only input** it did not choose;
- the workspace type, as a presentation-layer label it did not choose;
- ownership references (IC-008), used as **evidence**, never as routing or as an authority of their own;
- record residency, as a constraint on what may be asked, never as a database selector;
- the requested action;
- for AI agents: the assigned skill, the approved tool entitlement, and the applicable policy state;
- the workflow or lifecycle state of the subject record.

## §4 — Prohibitions (normative — these are the load-bearing rules)

The Access Control Service **MUST NOT**:

1. **select, influence, suggest, or override a database.** Database resolution is the Database Router's exclusive responsibility (IC-010 §X). An allow decision never carries a database, a DSN, a secret reference, or a connection.
2. **re-derive, choose, or change the active tenant.** The active tenant arrives from the signed claim and is an input, never an output.
3. **become the tenant-isolation mechanism.** Physical isolation is enforced by the signed claim, membership law, single-tenant routing, per-tenant credentials, and no cross-tenant connection reuse (D-30). Access Control is **defence in depth on top of** that mechanism and is never a substitute for it. A defect in Access Control MUST NOT be able to produce cross-tenant data access.
4. **widen what the signed claim permits.** An allow decision inside a tenant context can never reach another tenant's data, and can never turn a tenantless control-plane context into a tenant-scoped one.
5. **authenticate a caller, validate a token, or mint, exchange, or refresh a credential.**
6. **carry names, emails, PII, payloads, tokens, or secrets** in a decision request, a decision response, or a decision audit record. References only (D-34-R2).
7. **fail open.** A missing, ambiguous, unavailable, or malformed decision input produces a **deny**. An unavailable Access Control Service produces a **deny** at the caller, never a bypass.
8. **be bypassed by the ingress or by a domain service** for an action that requires a decision.

## §5 — Decision surface

The conceptual result is **allowed** or **denied**. A caller-facing presentation layer MAY additionally represent **loading** so a user interface does not flicker between states; loading is a presentation state only and is never a third decision value.

Concrete endpoints, request and response shapes, error codes, and the permission catalogue are **implementation bindings and are not granted here**. The phase that implements this contract defines them under its own authorized PRD, subject to §4.

## §6 — Relationship to the other contracts

- **IC-005** retains authentication, token validation, carrier law, the two-phase bootstrap model, membership law, and **tenant-scope authorization enforced at routing time**. None of that moves into IC-014. Moving tenant-scope authorization out of the routing path would weaken isolation and is prohibited.
- **IC-013** requires the ingress to consume this service's decision rather than evaluate access-control rules itself.
- **IC-008** supplies ownership as reference-only evidence. Ownership never routes and never authorizes on its own; a decision that considers ownership still produces a plain allow or deny.
- **IC-010** governs the enforcement boundary at which a denial is rendered; denial responses keep the fixed-status, empty-body posture and disclose nothing about topology or record existence.
- **IC-006** governs the deferred AI capability. IC-014 reserves the **shape** of an AI decision — agent, plus skill, plus tool entitlement, plus permission, plus tenant scope, plus approval policy — and grants **no** AI capability. The AI-invocation gate remains defined and unwired.
- **IC-002** and **IC-001** retain their audit-class homes. IC-014 opens **no** new audit class; access-denial auditing continues to use the classes those contracts already home.

## §7 — Service shape

The Access Control Service is an independently bootable FastAPI service and conforms to IC-013 §7, §8, §10 and §11: a no-argument fail-closed application factory, distinct liveness and readiness, one worker and one process, an internal-only loopback bind with schema generation and interactive documentation disabled, and Pydantic-native request and response models.

It holds no business logic belonging to Startup, Investor, Deal, Sharing, Import, Lineage, or Contacts.

## §8 — Enforcement requirements (for the phase that implements this contract)

The implementing phase MUST:

1. register the new package in the setuptools package list, the import-linter root packages, and the import-linter service-independence contract;
2. add it to the architecture scanner's service census with traceability metadata naming IC-014;
3. add a guard proving the service imports no database driver and constructs no database session, so §4.1 is machine-enforced rather than asserted in prose;
4. add a guard proving the decision path has no fail-open branch;
5. pin the edge's canonical startup command in the startup runbook.

None of these changes is authorized by IC-014 itself.

## §9 — Exclusions (normative)

IC-014 does not authorize, and MUST NOT be read as authorizing: any permission, role, or entitlement; any route, DTO, or error code; any AI-agent capability or model invocation; any audit class or DDL; any package creation; any import-linter change; any runtime code; the closure of any open blocker.
