# api_gateway

SnackPortal2 backend service — **scaffold only (Build Phase 1)**.

- **Governing contracts:** IC-005 (entry/routing relationship), IC-001.
- **Status:** package skeleton — entrypoint + static liveness stub only.
- **Forbidden here:** business logic, authentication decisions, tenant routing,
  database access (delegated to `auth_router` / `database_router`).
- **Deferred:** ingress middleware (correlation, validation, rate-limiting,
  audit-initiation) to a later authorization.
