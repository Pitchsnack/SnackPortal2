# db/tenant — Tenant-Database business schema (PRD 07C V5)

Portable, dependency-free SQL templates for the **tenant business schema** — the tables that live in
**every physical tenant database** (one database per tenant; CLAUDE.md Multi-Database Model). Introduced by
**PRD 07C V5 — Tenant Business Schema, Control Global Registry, and System Primary** (executed under the
V4-worded START-GATE per the exec-auth V2 §4 mapping note), authorized for **controlled non-production
implementation only**.

**Independence rule (CLAUDE.md constraint 4):** deployable on their own; no dependence on `backend/`
application code. Standard, cloud-portable PostgreSQL only — no extensions. **No `tenant_id` column
anywhere** — tenancy is physical (one DB per tenant), never a shared-DB column.

## Files (apply in EXACTLY this order; idempotent; transaction-safe)

| # | File | Purpose |
|---|------|---------|
| 1 | `001_agents.sql` | `agents` + **System Primary** singleton (partial unique index), safety CHECKs, and the protective trigger (DELETE / kind-flip blocked). 07C authors constraints ONLY — **07B.1 seeds the single System Primary row later**, in-transaction, after this family applies. |
| 2 | `002_ai_agents.sql` | Tenant-local AI Agents (mandatory `supervising_agent_id` FK; not seeded; none required at bootstrap). |
| 3 | `003_startups.sql` | Tenant-local startups (+ `global_startup_id` soft text ref to the Control Global Registry). |
| 4 | `004_investors.sql` | Tenant-local investors (+ `global_investor_id` soft text ref). |
| 5 | `005_deals.sql` | Tenant-local deals (never stored in the Control Global Registry; sharing tables deferred to IC-007). |
| 6 | `006_ownership.sql` | Six ownership tables — **at most one human Agent** (PK = entity id; UNASSIGNED = row absence = the System Primary bucket; claim = first-writer-wins INSERT) + **zero-or-more distinct AI Agents** (composite PKs). |
| 7 | `007_links.sql` | `startup_contacts`, `investor_contacts` (contact records — NOT `*_users`), `startup_investors`. |

The machine-readable ordered authority for this list is
`backend/tests/architecture/test_tenant_ddl_blob_drift.py` (per-file LF-normalized git-blob pins +
bidirectional directory completeness + the pinned apply order 07B.1 sequences). The live proof harness is
`backend/tests/control_plane/requires_pg/test_pg_tenant_business_schema_07c.py` (manual/local; tenant pins
under `_TENANT_BLOB_NNN`; control DDL applied unpinned).

## Citation mapping (07B.1 V2)

07B.1 V2 cites `07C V4 §6.4 / §9 / §13`. Formal mapping: **those citations resolve 1:1 to PRD 07C V5
§6.4 / §9 / §13** (section numbers byte-stable across V4 → V5). Do not renumber.

## Scope boundary (07C V5 — created, not applied)

This family is **created, not applied**: no runtime sequencing here. **07B.1** later appends exactly this
file list, in this order, to `default_tenant_schema_ddl_paths()` and seeds the System Primary inside the
existing Step-2b atomic transaction. **07C.2 — Roles, Permissions, Portfolio & AI Workflow** owns the
deferred items: portfolios (+ `portfolio_role`, portfolio links, `global_portfolio_id`), `agent_roles` /
`agent_role_assignments` / `role_entity_permissions` / `permission_tier` + the 7-role seed (and 07B.1 V3
seeding), two-layer supervision validation, `ai_draft_proposals` + AI runtime/approval workflow, the
deactivation cascade, `agent_actions` audit workflow, and the fund-of-funds model. Cross-tenant sharing
(`deal_shares` / `deal_share_targets` / `deal_introductions`, Control shared-deal inbox) is out of scope
until **IC-007**. Dedicated `global_startups` / `global_investors` / `global_deals` / `global_portfolios`
tables remain deferred — the MVP Control Global Registry anchor is MCC's `control_directory`. This PRD does
**not** close B5-BLK-4.
