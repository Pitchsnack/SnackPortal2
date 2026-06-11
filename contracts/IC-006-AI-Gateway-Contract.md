# IC-006 — AI Gateway Contract

**Status:** Draft · **Phase:** Architecture Planning · **Type:** Specification only (no implementation)

## Purpose
Define the contract for the **AI Gateway**: the single, provider-agnostic boundary through which the platform invokes AI/LLM capabilities. Centralizes request/response shape, tenant attribution, and lineage emission for AI-assisted operations.

## Scope
- Provider-agnostic request/response contract for AI operations.
- Tenant context propagation into AI requests.
- Lineage emission for AI-driven data changes (handoff to [IC-004](IC-004-Lineage-Contract.md)).
- Guardrails: input/output constraints, redaction expectations, rate/limit posture.
- Pluggable provider abstraction (no provider hardcoded into business logic).

## Non-goals
- Choosing or implementing a specific AI provider/SDK.
- Data import or transformation orchestration (see [IC-003](IC-003-Import-Contract.md)).
- Defining the lineage model (see [IC-004](IC-004-Lineage-Contract.md)).
- Any implementation, SDK wiring, or model-serving code.

## API Contract Placeholder
> _TBD._ Define the gateway's request/response contract for AI operations (prompt/operation in, structured result out). Specify method, path, shape, and status codes.

## DTO Contract Placeholder
> _TBD._ Define data shapes for: AI request, AI result, provider-neutral error, usage/cost metadata. Schema description only.

## Authentication Requirements
> _TBD._ Specify how callers of the AI Gateway authenticate and how tenant context is bound. Aligns with [IC-005](IC-005-Authentication-Routing-Contract.md). Provider credentials must never be exposed to clients.

## Authorization Requirements
> _TBD._ Define which roles may invoke AI operations and any per-tenant quotas/limits. AI operations are tenant-scoped.

## Multi-Database Compatibility
- AI-driven writes target only the resolved tenant's physical database via the Database Router.
- Any AI-related persistence (e.g. usage records) must use standard PostgreSQL (AWS RDS / Azure / Google Cloud SQL / self-hosted).
- No shared multi-tenant AI state table.

## Anti-Vendor-Lock-In Requirements
- Provider-agnostic by design: **no single AI provider hardcoded** into business logic.
- No Supabase-specific AI/edge-function logic.
- No Lovable-specific runtime dependencies.
- Provider abstraction must allow swapping/adding AI providers without changing callers.

## Open Questions
- Which AI provider(s) are targeted first, and what is the abstraction boundary?
- Are AI calls synchronous or queued/asynchronous?
- What redaction/PII rules apply before data leaves the tenant boundary?
- How are usage and cost tracked per tenant, and where stored?
- Which AI operations must emit lineage records, and at what granularity?
