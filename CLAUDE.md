# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Status

SnackPortal2 is in the **architecture planning phase**. There is no implementation code yet, and none should be generated unless explicitly requested. The current focus is defining contracts, architecture constraints, and standards before any backend or frontend code is written.

This project follows a **contract-first design approach**: interface contracts are defined and agreed upon *before* the corresponding implementation begins.

## Repository Structure

| Directory        | Purpose |
|------------------|---------|
| `contracts/`     | Architecture specifications and interface contracts (no code). Source of truth for system design. |
| `backend/`       | FastAPI / Python backend (not yet implemented). |
| `frontend/`      | React / TypeScript frontend, Lovable-generated (not yet implemented). |
| `infrastructure/`| Infrastructure-as-Code: Docker, Docker Compose, Terraform, Kubernetes manifests, environment templates. |
| `docs/`          | Project documentation. |

## Interface Contracts

The `contracts/` directory holds the governing specifications. All implementation must conform to these; if implementation needs to diverge, **update the contract first**, then the code.

- **IC-001** — Global Startup Contract
- **IC-002** — Tenant Startup Contract
- **IC-003** — Import Contract
- **IC-004** — Lineage Contract
- **IC-005** — Authentication Routing Contract
- **IC-006** — AI Gateway Contract

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
- **API Gateway** — single entry point for backend services.
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

## Development Standards

- **Do not generate implementation code during the planning phase.** Produce contracts, specifications, diagrams, and architecture decisions instead.
- When proposing designs, verify them against the **Architecture Constraints** above and cite the relevant `IC-00x` contract.
- Keep portability front of mind: if a proposed approach would only work on one cloud or one vendor's platform, flag it and offer a portable alternative.
- Database designs must assume per-tenant physical databases plus a separate control database — not a single shared database with a `tenant_id` column.
