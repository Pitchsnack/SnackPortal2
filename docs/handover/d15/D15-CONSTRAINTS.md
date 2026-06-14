# D15-CONSTRAINTS

**Non-negotiable constraints. Any change requires a governance amendment first. No implementation is authorized.**

## Mandatory architecture position

```text
Physical Multi-Database MVP is mandatory.
```

One Control Database **+** physically distinct Tenant Databases is required for the MVP. It is **not** optional, **not** future-only, **not** post-MVP, and **not** satisfied by a single shared database, shared-schema tenancy, or `tenant_id`-only isolation.

## Invariants (must hold)

```text
Physical Multi-Database MVP is mandatory.
One Request → One Active Tenant → One Database.
Authentication ≠ Routing.
Authentication ≠ Authorization.
Workspace ≠ Routing.
Gateway ≠ Database Resolution.
Database Router is the sole database selector.
Portal ≠ Routing.
Ownership ≠ Routing / Authorization / Residency.
Import ≠ Synchronization.
Global Record ≠ Tenant Record.
```

## Prohibited implementation patterns

```text
single shared database MVP
shared schema tenancy
tenant_id-only isolation
cross-tenant request fan-out
Control DB used as tenant DB
tenant DB used as Control DB
frontend database routing
Lovable direct multi-database business logic
workspace database routing
portal database routing
ownership database routing
gateway database selection
raw secrets in registry
PII in audit logs
D-17 as audit authority
D-11 as database association authority
```

## Governance constraints

- **Documentation-only** until `PRD-D15-IMPL-01` is written, independently reviewed, and approved.
- **No** ADR changes, contract changes, code changes, schema changes, infrastructure changes, or deployment.
- Provisioning audit derives from **IC-002 Audit Requirements → D-34 → IC-001 (reference-only) → IC-010 §J** — never D-17.
- Database association derives from **D-07 + IC-002** — never D-11.
- Cross-tenant operations are **IC-007-deferred** and not authorized by D15.
