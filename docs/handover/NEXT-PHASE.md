# NEXT-PHASE

**Handover H6 — the approved next sequence as of `de3169a` (2026-06-13)**

**Current state: Governance Complete.** The D-33→IC-010 contract chain is authored, reviewed, and verified. What remains is **architecture and implementation**, each gated by its own authorizing PRD (register entry → contract → code). No work below is authorized yet.

## Approved Sequence

| Phase | PRD | Scope | Depends on / inputs |
|---|---|---|---|
| **Phase 3A** | **PRD-AGW-01 — API Gateway Architecture** | Design the gateway architecture/implementation plan against IC-010. **The next authorized phase.** | IC-010 (Final). Acceptance criteria already adopted: **D-33 §10 criteria 4–6** + **D-37 §20 V1–V3** + frontend-repository audit. Co-requisite at build time: durable audit persistence. |
| **Phase 3B** | **PRD-D15-01 — Provisioning Architecture** | The D-15 provisioning plan (IaC substrate + automated control-plane workflow). **Parallel-ready — no dependency on 3A.** | **Must add the tenant-DB physical-distinctness verification** (compare PostgreSQL system identifiers across tenants and vs the Control DB; `IsolationAnomaly` on collision — IC-010 §P reserves the hook). Standing inputs: D-14 secret-backend selection; durable audit persistence. |
| **Phase 3C** | **IC-009 — Portal Contracts** (authoring) | The per-role × per-directory visibility matrix; portal DTO contracts (provenance + anonymity precedence); discovery/API/access contracts; channel bindings. | D-37 §16; **unblocked now** (IC-010 exists). After/with the gateway architecture. |
| **Phase 3D** | **Frontend Integration Governance** | Govern the Lovable frontend under source control; map workspace switching onto token issuance; the data-access refactor onto the gateway. | After IC-009 + gateway. |

(Sequencing matches the D-37 §22 / Inventory R2 program order. A useful ride-along at any time: commit the governance corpus into `docs/governance/`, and refresh the stale front-door docs — `CLAUDE.md`, `Project-Overview`, `docs/PROJECT-HANDOVER-MASTER.md §11–§19`.)

## Explicit Non-Authorization

The handover authorizes nothing executable. As of this package:

- **No implementation authorized.**
- **No frontend work authorized.**
- **No portal work authorized.**
- **No gateway implementation authorized.**
- **No AI work authorized.**
- **No cross-tenant work authorized.**

Each phase above begins only under its own explicitly-authorizing execution PRD. Review/verification PRDs are documentation-only and never authorize implementation. The **Physical Multi-Database MVP is mandatory throughout** — no phase may weaken it.

## Standing conditions (absolute)

1. **No client, frontend, or network exposure of any backend surface** until the gateway is *built* (IC-010 contracts the edge enforcement; it is a scaffold today). Authoring contracts is not exposure.
2. **Contracts precede code; no implementation without an authorizing execution PRD;** authorization does not carry between PRDs.
3. **No approved ADR may be silently replaced** — every supersession explicit, cited, registered.
