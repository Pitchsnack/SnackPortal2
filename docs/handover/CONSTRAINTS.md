# CONSTRAINTS

**Hard constraints (PRD-HO-03). Non-negotiable — any change requires a governance amendment first.**

## Governance

**Register → Contract → Specification → Code**, in that order.

## Contract-First

**Contracts precede implementation.** All behavior must trace to a contract; new behavior requires a new or amended contract first.

## No Authorization Carry-Forward

**Authorization never carries between PRDs.** Review and verification PRDs are documentation-only and authorize nothing executable.

## MVP Protection

**The Physical Multi-Database MVP cannot be weakened.** One Control Database + one physically separate PostgreSQL database per tenant. Never a shared database, never a shared schema, never `tenant_id` row-filtering as isolation, never logical isolation in place of physical isolation. One request resolves to the Control DB **or** exactly one tenant DB — never both, never several; no cross-tenant query, ever.

## No Implementation

**`api_gateway` remains scaffold only (`IMPLEMENTS_BEHAVIOR=False`).** **No API Gateway implementation is authorized.** Completion of the Phase-3A Architecture Specification authorizes no code; a separate implementation-authorization PRD remains mandatory. No client/frontend/network exposure of any backend surface until the gateway is built.

## Portability & Vendor

Cloud-portable standard PostgreSQL only (AWS RDS / Azure Database for PostgreSQL / Google Cloud SQL / self-hosted, interchangeably). No Supabase business logic (no RLS-as-authorization, no data SDK/PostgREST); no Lovable runtime dependence. Infrastructure deployable independently of application code.
