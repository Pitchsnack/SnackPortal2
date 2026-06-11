# auth_router

SnackPortal2 backend service — **scaffold only (Build Phase 1)**.

- **Governing contracts:** IC-005; decisions D-03, D-05, D-06, D-32.
- **Status:** package skeleton — entrypoint + static liveness stub only.
- **Forbidden here:** authentication logic, JWT validation, OIDC, tenant
  resolution, database access. Authentication MUST remain DB-free (D-01/D-05).
- **Deferred:** Build Phase 3 — Authentication Layer.
