# import_service

SnackPortal2 backend service — **scaffold only (Build Phase 1)**.

- **Governing contracts:** IC-003; decisions D-18-D-21, D-09 (ingress).
- **Status:** package skeleton — entrypoint + static liveness stub only.
- **Forbidden here:** import processing, source adapters, ingress
  validation/PII handling, idempotency, database access, any write-back to the
  Global record.
- **Dependency note:** atomic provenance requires the lineage write path
  (Build Phase 6) before tenant data is committed (Build Phase 5).
- **Deferred:** Build Phase 5 — Import Layer.
