# api_gateway

SnackPortal2 backend service — **API Gateway (Build Phase 7)**. The sole approved
ingress into backend services (IC-010 §A; D-37 §5).

- **Governing contracts:** IC-010 (primary), IC-005, IC-002, IC-001.
- **Role:** ingress / policy-enforcement / request-coordination — an *enforcement
  boundary, not a decision-maker* (IC-010 §A/§B).
- **Per-request flow (IC-010 §C):** Authentication → Carrier Validation → RequestContext
  (constructed exclusively from `AuthContext`) → Database Router → Service → Response.
- **Boundaries:** never resolves or accesses a database (the Database Router is the sole
  selector — IC-010 §X/§H); reaches the router and authenticator only over **transport
  ports** — imports no other service package and no database driver (DAG independence;
  IC-010 §M). Emits the §J audit set through a **no-sink** port (AD-1 Option A); binds
  no ownership-audit DTO residency (DEC-11).
- **Vendor-neutral:** framework-agnostic core; no Supabase/Lovable/cloud-vendor SDK
  anywhere in the package.
- **Out of scope (deferred):** live end-to-end routing + `IsolationAnomaly` physical
  distinctness (D-15); the runtime-audit class-home (pending IC-005/IC-002 extension);
  frontend/portal implementation.
