# control_plane

SnackPortal2 backend service — **scaffold only (Build Phase 1)**.

- **Governing contracts:** IC-001; decisions D-01, D-10, D-11, D-12, D-31.
- **Status:** package skeleton — entrypoint + static liveness stub only.
- **Invariant:** never holds tenant-owned data (Control DB is global/control-plane
  scope + Global Discovery Platform).
- **Forbidden here:** bootstrap logic, registry, readiness evaluation, database
  access, any tenant data.
- **Deferred:** Build Phase 2 — Control Plane.
