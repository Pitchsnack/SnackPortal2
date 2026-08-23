# SnackPortal2 — Option A rebuild migrations

Two migration homes exist deliberately, and the split is not accidental drift.

## `infrastructure/db/` — the legacy set (001–015), historical evidence

The Control, tenant, lineage and provisioning DDL authored under Phases 1–7 lives at
`infrastructure/db/`. It is **reused unchanged** by the rebuild: the Control Plane service
targets `control_tenants` (004), `control_memberships` (005) and `control_directory` (007),
and the Database Router targets `startups` (003), `investors` (004), `deals` (005) and the
lineage schema.

Those files are **byte-pinned** by `tests/architecture/test_b7c1_control_audit_ddl_blob_pins.py`
and cross-checked by `test_b7c1r2_control_ddl_pin_completeness.py`. D-46 §7 requires that
DDL 012/013 and their pins be left intact as the historical record of the retired Gateway's
audit table. Adding a file to `infrastructure/db/control/` therefore requires extending both
guards in lockstep — so the rebuild does not add files there.

## `backend/migrations/` — the rebuild's own migrations (this directory)

New migrations authored for the Option A architecture live here, following the 3-day plan's
`migrations/control/` and `migrations/tenant/` layout.

### `control/016_bff_ingress_audit.sql` — migration M-1 (D-46 §7)

The blocking dependency for all BFF audit emission. Control DDL 012 pins
`CHECK (source_service = 'api_gateway')` on `control_gateway_audit`, so that table
**physically rejects** a BFF-emitted row. M-1 creates a **new** append-only table,
`control_ingress_audit`, for the ingress-edge audit classes, leaving 012/013 and their
byte-pins untouched.

`control/017_bff_ingress_audit_append_only.sql` applies the append-only rule with the same
rule-based idiom the legacy 003/011/013 migrations use.

## Applying

Created, **not applied**. Applying either set to a live database is an operations/IaC
activity, never something a service does at runtime.
