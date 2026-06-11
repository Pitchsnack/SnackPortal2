# lineage_service

SnackPortal2 backend service — **scaffold only (Build Phase 1)**.

- **Governing contracts:** IC-004; decisions D-22-D-25.
- **Status:** package skeleton — entrypoint + static liveness stub only.
- **Invariant:** lineage is tenant-resident and **distinct from operational audit**
  (IC-002); it never crosses tenants.
- **Forbidden here:** lineage record handling, append-only enforcement,
  hash-chaining, provenance graph, retention/archival, database access.
- **Deferred:** Build Phase 6 — Lineage Layer (write path co-developed with
  Build Phase 5).
