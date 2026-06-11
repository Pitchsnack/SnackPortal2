# database_router

SnackPortal2 backend service — **scaffold only (Build Phase 1)**.

- **Governing contracts:** IC-005, IC-002; decisions D-07, D-13, D-30.
- **Status:** package skeleton — entrypoint + static liveness stub only.
- **Special role:** the **only** service permitted to access tenant databases.
  Database drivers may be imported **only** under
  `database_router/adapters/providers/**`.
- **Forbidden here:** registry resolution, pooling, any database access, hardcoded
  tenant database references, cross-tenant connection reuse.
- **Deferred:** Build Phase 4 — Database Router.
