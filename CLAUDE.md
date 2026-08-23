# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Status

SnackPortal2 is in **active build under contract-first governance**. Do **not** generate implementation code unless explicitly requested via an authorized PRD — contracts and decisions come first.

Current state (see `docs/SnackPortal2_Canonical_Overview_and_Decisions_v2.md` for the full, authoritative picture):

- **Target architecture (ratified 2026-08-21, [D-46](docs/D-46-Option-A-Gateway-Free-Target-Architecture-Ratification.md)):** **`Frontend → FastAPI BFF → FastAPI Services`, with ZERO API Gateway in the target runtime.** Under the **Option A Clean FastAPI Rebuild**, the existing backend is a source of **requirements, validated behaviour, schemas and tests — not architecture to preserve**. **IC-010 is `Superseded`** by **IC-013** (BFF Ingress) + **IC-014** (Access Control). Locked invariant #7 is revised to "**the BFF is the boundary**". The **BFF is not a renamed Gateway** — its operation surface is enumerated by contract, and a surface that merely relays a downstream body is forbidden; the names *FastAPI/BFF/Service/Routing/Compatibility Gateway* are prohibited.
- **Option A rebuild (branch `rebuild/fastapi-openapi-first`, unmerged):** the target architecture is **implemented** at `backend/snackportal2/` — a shared technical foundation plus the fourteen independently-bootable FastAPI services, each with its own `main.py` and `app = FastAPI()`, each generating an OpenAPI 3.1 document held to a standing contract gate. Governed by IC-013, IC-014 and **D-48**. The flat legacy packages sit beside it untouched and are unreachable from it by import-linter contract. **Not merged, not pushed, not production-ready.**
- **Backend (this repo, as-built):** core Phases 1–6 built and **accepted** (Control Plane, Authentication, Database Router, Import, Lineage; PostgreSQL-verified), plus an **API Gateway core** (`IMPLEMENTS_BEHAVIOR = True`, built under PRD 04 V2/V3) serving as one of nine native FastAPI/Uvicorn edges. **The entire public business surface is three operations** (`GET /memberships`, `POST /import/<ref>`, `GET|PATCH /tenant/startups/<ref>`). **The `api_gateway` package is classified "old architecture — do not port"** and is untouched on disk pending Phase 1+; **Access Control has never been built** (no permission engine exists in production code) and is the one genuinely greenfield service. See `docs/Phase-0-Requirements-Extraction-Report.md` (branch `phase/00-requirements-extraction`).
- **Frontend (Lovable `snack-cosmos`, separate repo):** ~70% of screens built, but on an **interim** Supabase data layer using *logical* (`tenant_id` + RLS) separation. It expects ~86 server-function operations against a backend that serves 3. Per decisions D3/D7 this data layer is **interim** and must be re-pointed to the **BFF** + physical tenant databases; cutover is **incremental and per-operation** by contract (IC-013 §22), never big-bang, and the old Gateway must **not** be used as an intermediate compatibility layer.

This project follows a **contract-first design approach**: interface contracts are defined and agreed upon *before* the corresponding implementation begins.

## Repository Structure

| Directory        | Purpose |
|------------------|---------|
| `contracts/`     | Architecture specifications and interface contracts (no code). Source of truth for system design. |
| `backend/`       | FastAPI / Python backend. |
| `frontend/`      | React / TypeScript frontend, Lovable-generated. |
| `infrastructure/`| Infrastructure-as-Code: Docker, Docker Compose, Terraform, Kubernetes manifests, environment templates. |
| `docs/`          | Project documentation (incl. the planning files imported below). |

## Interface Contracts

The `contracts/` directory holds the governing specifications. All implementation must conform to these; if implementation needs to diverge, **update the contract first**, then the code.

- **IC-001** — Global Startup Contract *(Final)*
- **IC-002** — Tenant Startup Contract *(Final)*
- **IC-003** — Import Contract *(Final)*
- **IC-004** — Lineage Contract *(Final)*
- **IC-005** — Authentication Routing Contract *(Final)*
- **IC-006** — AI Gateway Contract *(Draft — post-MVP, D-02)*
- **IC-007** — Deal Collaboration & Cross-Tenant Sharing Contract *(Draft / Proposed, IC-007-DRAFT-1 — opened by D-38; no positive sharing capability)*
- **IC-008** — Ownership Contract *(Final; amended by **D-47**, 2026-08-21 — AI-ownership cardinality ratified: **exactly one human owner + at most one *current* AI owner**, as single references on the record, never sets or join tables. Multiple AI Agents may **contribute** — recorded via task history / provenance / audit — but contribution is **never ownership** and **never an authorization input**. Option C reserved. `owner_ai_agent_ref` stays NULL platform-wide until IC-006.)*
- **IC-009** — Portal Contracts *(Final, IC-009-R1)*
- **IC-010** — API Gateway Contract *(**Superseded** 2026-08-21 by D-46 — jointly by IC-013 + IC-014. Retained as the historical record and the traceability source for its successors; **no longer normative for implementation**. D-46 §4 holds the exhaustive section-by-section re-homing map.)*
- **IC-011** — Hosted Rollback Proof Contract *(Draft / Proposed, IC-011-DRAFT-1 — opened by D-40)*
- **IC-012** — Service Composition & Deployment Root Contract *(Draft / Proposed, IC-012-DRAFT-1 — opened by D-44; amended by D-46: principles carried forward and re-scoped, Edge-9 specifics historical)*
- **IC-013** — BFF Ingress Contract *(Draft / Proposed, IC-013-DRAFT-1 — opened by D-46; the single frontend-facing ingress, the enumerated operation surface, the re-homed carrier / `RequestContext` / audit rules, and the independently-bootable service shape. **§8 amended 2026-08-23 by [D-48](docs/D-48-Tenant-Connection-Ownership.md)** — the Database Router keeps **resolution authority**, but a tenant-resident domain service may hold the connection it opens, under a router-issued single-tenant grant and only from an explicit allowlist that permanently excludes the BFF and Access Control.)*
- **IC-014** — Access Control Contract *(Draft / Proposed, IC-014-DRAFT-1 — opened by D-46; the home for cross-cutting authorization. It never authenticates, selects no database, re-derives no active tenant, reads no tenant business data, and never fails open)*
- **IC-015** — Contacts Service Contract *(**Reserved / unauthored** — named prerequisite for Phase 7; Action Tracker #22)*

## Architecture

### Tech Stack
- **Frontend:** React + TypeScript (Lovable-generated)
- **Backend:** FastAPI + Python
- **Database:** PostgreSQL

### Multi-Database Model (Physical Isolation)
SnackPortal2 uses **physical multi-database isolation**, not shared-schema multi-tenancy:

- **Control Database** — global/cross-tenant state, tenant registry, routing metadata.
- **Independent Tenant Databases** — one physically separate database per tenant. Tenant data must never share a database.

### Service Components (target — D-46 / IC-013)
- **FastAPI BFF** — the **single frontend-facing ingress**; governed by IC-013. Application-oriented frontend orchestration with an **enumerated** operation surface — *not* a gateway, *not* a proxy.
- **Authentication Service** — *who are you?* Validates identity/session/token, returns trusted principal context; governed by IC-005. Never authorizes, never chooses a tenant or a database.
- **Access Control Service** — *what are you allowed to do?* Evaluates role, permission, tenant membership, ownership, requested action, record residency (and, later, AI entitlement); returns Allowed/Denied; governed by IC-014. Never authenticates, never selects a database, never fails open.
- **Database Router** — *which active tenant and physical database?* Resolves the correct control vs. tenant database per request, registry-authoritatively from the signed claim. **The only service permitted to open a tenant database.**
- Plus: Control Plane, Startup, Investor, Deal, Contacts, Sharing, Import, Lineage, AI Agent, and Audit services — each independently bootable with its own `main.py`, port, health/readiness and tests (IC-013 §21).

**Approved startup convention (IC-013 §21).** Each service has its own `main.py` defining its own `app = FastAPI()`, starts independently, has a configurable port, and is testable independently. A service-level `import uvicorn` and a local-development `if __name__ == "__main__": uvicorn.run(..., host="127.0.0.1", reload=True)` block are **permitted**. **No shared uvicorn runtime module, no mandatory `create_app()` factory, and no mandatory `--factory` invocation** is imposed — a factory is an option, not an obligation. Production startup **may** use an external ASGI server command; `reload=True` is local-development only.

**Service exposure is non-negotiable (D-47 / IC-013 §21.1).** The controlling distinction is **BIND vs PUBLISH**. **Only the BFF is a public ingress** (E-1). Internal services default to **loopback/private** in local development — `0.0.0.0` is never an internal service's default bind (E-2). Containerized internal services **MAY bind `0.0.0.0` inside the container** but **MUST NOT publish** their port — no `ports:`, no `-p`; container-network reachability only (E-3). **`reload` is local-development only** (E-4). **Serving configuration is environment-specific with secure defaults** (E-5) — uvicorn process, logging, proxy-header and server-header settings are **deployment settings, not architecture invariants**; the architecture hard-codes no worker count and permanently prohibits neither access logging nor trusted proxy-header handling. Secure defaults apply on omission; proxy headers need an **explicit trusted-proxy boundary**; and a forwarded header is **never** a tenant carrier or routing authority. *(`--factory` is not mandated either — see the startup convention below.)* Because E-1/E-3 are violated by *configuration* rather than code, Phase-1 acceptance requires a **deployment-manifest check** proving exactly one service publishes a port and it is the BFF (E-6).

**The four-way separation is non-negotiable:** `Authentication ≠ Access Control ≠ Tenant Routing ≠ Database Access` (D-46 §3). The request flow is `Authentication → Carrier Validation → RequestContext → Access Control → Tenant Routing → Service → Response Composition`; **Access Control runs before Tenant Routing**, so a denied request never causes a tenant-database connection.

*(Historical: the **API Gateway** was previously the single entry point under IC-010. IC-010 is Superseded; the `api_gateway` package remains on disk as old architecture pending Phase 1+ and must not be ported or renamed.)*

## Architecture Constraints (Non-Negotiable)

These constraints exist to preserve portability and tenant isolation. Do not violate them without an explicit contract change.

1. **Cloud-portable PostgreSQL only.** All database usage must remain compatible with standard PostgreSQL and runnable on AWS RDS, Azure Database for PostgreSQL, and Google Cloud SQL. Do not rely on provider-specific extensions or proprietary features.

2. **No vendor-specific business logic.**
   - **No Supabase-specific business logic** — Supabase APIs, RLS-as-business-logic, or Supabase auth must not be embedded in application logic.
   - **No Lovable-specific business logic** — the frontend is Lovable-generated, but business logic must not depend on Lovable runtime/platform features.

3. **Strict tenant isolation.** Code paths must always route through the Database Router. Never hardcode a tenant database, and never allow a query to span tenant databases.

4. **Infrastructure independent of application code.** `infrastructure/` must be deployable on its own and target AWS, Azure, Google Cloud, and self-hosted environments interchangeably.

5. **Contracts precede code.** Backend/frontend behavior must trace back to a contract in `contracts/`. New behavior requires a contract (new or amended) first.

> **Interim exception (tracked, not permanent):** the current Lovable frontend uses Supabase + RLS and therefore does **not** yet satisfy constraints 2–3. This is the agreed *interim* state under decisions D3/D7; it is resolved by re-pointing the frontend's data layer to the **FastAPI BFF** + physical tenant databases at the cutover (D-46; IC-013 §22 — **incremental and per-operation**, never big-bang, and never via the old Gateway as a bridge). Do not treat the Supabase data layer as the final architecture.

> **Line 36 note:** IC-006's title says "AI **Gateway**". That is a *model-invocation* boundary for AI providers — a separate, deferred component (Canonical Overview Part 4B-C) — and is **unrelated** to the superseded API Gateway. It is not affected by D-46, and the D-46 "zero Gateway" rule does not reach it. IC-006 nonetheless remains an all-TBD placeholder and is a **named prerequisite for Phase 9**.

## Development Standards

- **Do not generate implementation code unless explicitly requested via an authorized PRD.** Produce contracts, specifications, diagrams, and architecture decisions otherwise.
- When proposing designs, verify them against the **Architecture Constraints** above and cite the relevant `IC-00x` contract.
- Keep portability front of mind: if a proposed approach would only work on one cloud or one vendor's platform, flag it and offer a portable alternative.
- Database designs must assume per-tenant physical databases plus a separate control database — not a single shared database with a `tenant_id` column.

## Planning & Decisions (imported)

These product-side planning documents load every session. The **Overview is authoritative** on scope and the eight locked decisions (D1–D8); if a request conflicts with it, flag **DRIFT** before acting. Keep the **Action Tracker** updated and commit changes.

@docs/SnackPortal2_Canonical_Overview_and_Decisions_v2.md
@docs/SnackPortal2_Action_Tracker.md
@docs/SnackPortal2_PRD_Index.md
