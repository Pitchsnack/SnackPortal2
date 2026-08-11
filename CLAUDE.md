# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Status

SnackPortal2 is in **active build under contract-first governance**. Do **not** generate implementation code unless explicitly requested via an authorized PRD — contracts and decisions come first.

Current state (see `docs/SnackPortal2_Canonical_Overview_and_Decisions_v2.md` for the full, authoritative picture):

- **Backend (this repo):** core Phases 1–6 built and **accepted** (Control Plane, Authentication, Database Router, Import, Lineage; PostgreSQL-verified).
- **API Gateway — REMOVED, AND THE REMOVAL IS NOW RATIFIED AT THE DESIGN LEVEL (this branch only).**
  On `experiment/complete-api-gateway-removal-mvp` the `api_gateway` package, the Database Router
  dispatch edge and the internal tenant-Startup envelope edge are deleted, and each MVP route family
  is served by the service that owns its records behind the shared `shared.public_edge` boundary
  (public edges on 8830 / 8831). **On `main` the Gateway is untouched.**

  **`D-45` (2026-08-11, explicit human architecture decision by Dan) ratifies the Gateway-free
  architecture at the design/governance level.** The ratified boundary is *an approved authenticated
  public edge owned by the service that owns the public route*; the closed approved set is the
  **public Startup edge** (`database_router`) and the **public Workspace edge** (`control_plane`).
  IC-010 is retargeted (now the *Public Edge Ingress Contract*), and IC-011, IC-009, IC-012, IC-005,
  IC-002, IC-001, IC-007 and IC-008 are reconciled. Canonical Overview locked invariant **#7** is
  superseded on the record, and **D-4** is superseded for the MVP. Read
  [`docs/D-45-Gateway-Free-Public-Edge-Architecture.md`](docs/D-45-Gateway-Free-Public-Edge-Architecture.md)
  **before** proposing anything that touches client ingress.

  **What ratification did NOT do.** It authorized no push, PR, merge, DDL, live-PostgreSQL,
  Keycloak, SecretRef, credential, frontend, or standing-runtime change, and it is **not a
  production approval**. **Only Dan may explicitly authorize the specific future PR merge.**
  Gate B remains **NOT GRANTED**; production remains **NOT READY / DO-NOT-ACTIVATE**; B5-BLK-5 and
  B5-BLK-8 remain OPEN. Still owed, separately governed: the frontend cutover to the **two** origins
  (IC-010 §Y), re-authoring the live proofs the removal cost (**B5-BLK-4 has lost its harness**), and
  the DDL 012/013 + SecretRef naming migration. `source_service = 'api_gateway'`,
  `control_gateway_audit` and the AW-1 SecretRef are **frozen compatibility artifacts** — never
  evidence that a Gateway runtime exists. Evidence:
  `docs/reports/SnackPortal2_Complete_API_Gateway_Zero_Residual_Removal_Result_Claude.md` and
  `docs/reports/SnackPortal2_Gateway_Free_Architecture_Contract_Ratification_Result_Claude.md`.
- **Frontend (Lovable, separate Lovable Cloud project):** ~70% of screens built, but on an **interim** Supabase data layer using *logical* (`tenant_id` + RLS) separation. Per decisions D3/D7 this data layer is **interim** and must be re-pointed to the approved public edges + physical tenant databases — under D-45 that is **two origins, not one** (IC-010 §Y); not yet brought into this repo's `frontend/`.

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
- **IC-008** — Ownership Contract *(Final)*
- **IC-009** — Portal Contracts *(Final, IC-009-R1)*
- **IC-010** — **Public Edge Ingress Contract** *(Final; retargeted 2026-08-11 by D-45 — formerly the "API Gateway Contract". The file name `IC-010-API-Gateway-Contract.md` is retained for cross-reference stability.)*
- **IC-011** — Hosted Rollback Proof Contract *(Draft / Proposed, IC-011-DRAFT-1 — opened by D-40)*
- **IC-012** — Service Composition & Deployment Root Contract *(Draft / Proposed, IC-012-DRAFT-1 — opened by D-44; governs the `backend/deployment/` cross-service composition root)*

## Architecture

### Tech Stack
- **Frontend:** React + TypeScript (Lovable-generated)
- **Backend:** FastAPI + Python
- **Database:** PostgreSQL

### Multi-Database Model (Physical Isolation)
SnackPortal2 uses **physical multi-database isolation**, not shared-schema multi-tenancy:

- **Control Database** — global/cross-tenant state, tenant registry, routing metadata.
- **Independent Tenant Databases** — one physically separate database per tenant. Tenant data must never share a database.

### Infrastructure Components
- **Approved authenticated public edges** — the client entry points, one per route-owning service (**D-45**; this replaces the single API Gateway). Today exactly two: the public Startup edge (`database_router`) and the public Workspace edge (`control_plane`), both behind the shared `shared.public_edge` boundary. Any new one needs an IC-010 §A.2 amendment plus a register entry.
- **Authentication Router** — routes/validates auth; governed by IC-005.
- **Database Router** — resolves the correct control vs. tenant database per request.

## Architecture Constraints (Non-Negotiable)

These constraints exist to preserve portability and tenant isolation. Do not violate them without an explicit contract change.

1. **Cloud-portable PostgreSQL only.** All database usage must remain compatible with standard PostgreSQL and runnable on AWS RDS, Azure Database for PostgreSQL, and Google Cloud SQL. Do not rely on provider-specific extensions or proprietary features.

2. **No vendor-specific business logic.**
   - **No Supabase-specific business logic** — Supabase APIs, RLS-as-business-logic, or Supabase auth must not be embedded in application logic.
   - **No Lovable-specific business logic** — the frontend is Lovable-generated, but business logic must not depend on Lovable runtime/platform features.

3. **Strict tenant isolation.** Code paths must always route through the Database Router. Never hardcode a tenant database, and never allow a query to span tenant databases.

4. **Infrastructure independent of application code.** `infrastructure/` must be deployable on its own and target AWS, Azure, Google Cloud, and self-hosted environments interchangeably.

5. **Contracts precede code.** Backend/frontend behavior must trace back to a contract in `contracts/`. New behavior requires a contract (new or amended) first.

> **Interim exception (tracked, not permanent):** the current Lovable frontend uses Supabase + RLS and therefore does **not** yet satisfy constraints 2–3. This is the agreed *interim* state under decisions D3/D7; it is resolved by re-pointing the frontend's data layer to the approved public edges + physical tenant databases at the cutover — **two origins under D-45**, each with its own exact-origin CORS allowlist (IC-010 §Y). Do not treat the Supabase data layer as the final architecture.

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
