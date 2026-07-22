# IC-009 — Portal Contracts

**Status:** Final · **Phase:** Architecture Planning · **Type:** Specification only (no implementation)
**Adopted:** 2026-06-17 under **PRD 03 V4 IC-009 Contract Amendment Package**, converting the **Reserved placeholder** (reserved 2026-06-12 by **D-37 §16**) into a Final governing contract. **Revision:** IC-009-R1 (downstream PRDs cite this revision). **Source draft:** PRD 03 V2 Portal Contracts Adoption Package (verified). **Adoption review:** PRD 03 V3 IC-009 Adoption Review Report (outcome PROCEED).
**Origin:** Reserved by **D-37-R3 §16**; layers on **IC-010** (API Gateway, Final). Cites IC-005, IC-008, IC-001/002/003/004, D-31/D-32/D-33/D-34/D-35/D-36/D-37.
**Physical Multi-Database MVP:** Mandatory and unchanged.
**Amendment (2026-07-18, PRD D-38 — Governed Sharing / IC-007 adoption):** §C/§M re-open the DEF→IC-007 visibility reservation for **exactly the four adopted Governed Sharing categories** (intra-Master-Agent Deal; Master-Agent → Master-Agent Startup; Control → Master-Agent Startup; Control → Master-Agent Investor); §D adds the references-only **`SharedItemReferenceDTO`** (DEC-4 owner-ref hiding). These additions are **authored-but-inert until IC-007 is Final**; cross-kind / introduction-shaped discovery stays **DEF→IC-007** and the end-user Global Deal-Directory cells stay **DEF\***. No positive sharing capability is implemented.
RFC-2119 keywords MUST/MUST NOT/SHOULD/MAY used normatively.

### Purpose
Define the per-portal data and visibility contracts for the six D-37 portal classes so portal behavior is contracted before any frontend implementation exists. Portals **display, discover, initiate**; they never determine database, tenant, authentication, authorization, ownership, routing, or residency (D-37 §3).

### Boundary (carried forward verbatim from the IC-009 placeholder + D-37)
- **No portal implementation** (frontend or backend surface) until IC-009 is designed+approved **and** the API Gateway (IC-010) is implemented (D-37 §22).
- **Gateway-only data access** — no portal-side database access and **no Supabase data access of any kind** (RLS, PostgREST, Supabase data SDKs), framed as business, display, or any logic (D-37 §5; IC-010 §I). The API Gateway is the sole portal-facing integration boundary.
- **Record-residency retrieval** (D-37 §13); **no cross-workspace/cross-tenant client caching** (D-37 §14); **Portal Import Rule** — discrete, user-initiated only (D-37 §9; IC-003); **audit representation** references-only (D-34 / D-37 §12).
- Cross-tenant capabilities remain **IC-007-deferred**; AI presentation remains **IC-006-deferred**; ownership mechanics governed by **IC-008** (Final).
- Portals **never** redefine portal/workspace/database/ownership/authorization/authentication/residency (D-37 §15).

### Layered-on contracts (REFERENCE — not re-derived here)
- **IC-005 (Final) owns:** OIDC stateless JWT (D-05; not Supabase Auth); active tenant = signed claim (D-06); one active tenant/request (D-04); role hierarchy (D-32); carriers + prohibited carriers + workspace terminology (D-33); **401/403 denial semantics**; **workspace switch = new tenant-scoped token** (D-33 §4.3–4.4). IC-009 cites these; it does not restate them as its own.
- **IC-010 (Final) owns:** sole ingress; carriers = subdomain + `X-Tenant-Id`, match-or-reject → 403 `carrier_mismatch` (§E); RequestContext references-only from AuthContext, canonical fields `correlation_id, principal_ref, role, tenant_context, workspace_type` (§G); endpoint dispatch taxonomy (§Q: Tenant Operation | Global Directory Read | MembershipsForPrincipal | Import Initiation); dispatch≠DB-resolution (§X); isolation one-request→one-DB (§K/§O); portal boundary (§I); **error model** (§L); **audit-event emission** `CarrierMismatch/CarrierOnControlAnomaly/RouteDenied/IsolationAnomaly` (§J). IC-009 maps onto these and **adds only the portal presentation layer**.

---

### A. Portal Classes (D-37 §6/§7 — exactly six; do not invent/split)

| Portal class | Roles served | Data scope (D-37 §7) |
|---|---|---|
| **Control Portal** | CONTROL | Control DB only — Global Startup/Investor/Deal Directories, publications, global audit (authenticated, audited control-plane reads, IC-005/D-31) |
| **Master Agent Portal** | MASTER_AGENT | Per-tenant operations within one active tenant; directory discovery (tenant-anonymous global reads); cross-tenant **reserved IC-007** (no authority granted — D-37 §7.2) |
| **Tenant Portal** (single class) | TENANT_ADMIN, TENANT_AGENT | The active tenant's DB only (tenant startups/investors/deals/ownership/activity) + approved directory discovery + import |
| **Startup Portal** | STARTUP_USER | Assigned startup records/deals/activities + Global Startup Directory (own-kind discovery) |
| **Investor Portal** | INVESTOR_USER | Assigned investor records/deals/introductions + Global Investor Directory (own-kind discovery) |
| **AI Portal (Reserved)** | — | Reserved; governed by **IC-006** (deferred); no implementation/routing/DB authority |

`TENANT_ADMIN` and `TENANT_AGENT` are **roles within the single Tenant Portal**, not separate portals. No Public/External/Cross-Tenant portal exists; new portal classes require a new ADR + IC-009 amendment (D-37 §6 Future Portal Expansion — see §Q).

### B. Roles (IC-005/D-32 — exactly six MVP roles)
`CONTROL · MASTER_AGENT · TENANT_ADMIN · TENANT_AGENT · STARTUP_USER · INVESTOR_USER`. AI roles are **IC-006-deferred** (post-MVP) and are **excluded** from the MVP visibility matrix.

---

### C. Per-Role × Per-Directory Visibility Matrix  *(the keystone; derived from D-37 §7 + IC-008 eligibility + D-35 — NOT from any UI)*

Legend: **V** = visible (control-plane directory read, tenant-anonymous per D-35) · **V(own-kind)** = own-kind discovery only · **SCOPED** = tenant-resident, permission-scoped (assigned/**authorized** per backend permissions; **Ownership ≠ Visibility**, IC-008 P5) · **DEF→IC-007** = deferred to the cross-tenant contract · **DEF\*** = D-37 deliberately-deferred IC-009 decision (see Decision Register) · **—** = not applicable.

| Role | Global Startup Dir | Global Investor Dir | Global Deal Dir | Tenant records (Startup/Investor/Deal) |
|---|---|---|---|---|
| **CONTROL** | V (management) | V (management) | V (management) | — (Control workspace; tenantless CONTROL token can never reach a tenant DB — IC-005) |
| **MASTER_AGENT** | V (discovery) | V (discovery) | V (discovery) | SCOPED to the one active tenant (membership-bound; no cross-tenant — IC-007) |
| **TENANT_ADMIN** | V (discovery) | V (discovery) | V (discovery) | SCOPED (active-tenant admin scope) |
| **TENANT_AGENT** | V (discovery) | V (discovery) | V (discovery) | SCOPED (assigned/authorized per backend permissions) |
| **STARTUP_USER** | V(own-kind) | DEF→IC-007 (cross-kind / introduction-shaped) | **DEF\*** (end-user Deal-Directory — D-37 deliberately deferred) | SCOPED to assigned startup records/deals/activities |
| **INVESTOR_USER** | DEF→IC-007 (cross-kind) | V(own-kind) | **DEF\*** (end-user Deal-Directory) | SCOPED to assigned investor records/deals/introductions |

**Notes (corrections folded):**
- **Import (F-4):** for MASTER_AGENT/TENANT_ADMIN/TENANT_AGENT, directory **V** includes **import** on **all three** directory kinds (Startup ∨ Investor ∨ Deal), per IC-003/D-35 and the IC-008 Ownership Scope — not Deal-only. Import is discrete + user-initiated (D-37 §9) and yields an independent tenant copy with new tenant-side ownership (§K/§L).
- **DEF\* vs DEF→IC-007 (F-3):** the end-user **Global Deal Directory** cell is `DEF*` — a *D-37-reserved IC-009 decision* (DEC-1), distinct from cross-kind/introduction-shaped discovery, which is `DEF→IC-007` (DEC-2). The two re-open through different governance (see §Q).
- **Bases:** Control §7.1; Master Agent §7.2; Tenant §7.3; Startup §7.4 (own-kind); Investor §7.5 (own-kind). All directory cells are **tenant-anonymous** (D-35). Tenant-record cells are **permission-governed, never ownership-derived** (IC-008 P1/P5).
- **Per-cell authorization source (IR-02):** the *granting* authority for each cell is — **V** directory cells: IC-005 control-plane directory read (D-31) gated by D-33 workspace context; **SCOPED** tenant-record cells: IC-005 tenant-scope authorization **+ the per-feature feature contract**. For tenant **business** records (Startup/Investor/Deal), those feature contracts **do not yet exist** (Roadmap business-domain tier) — the matrix *shape* is contractable now, but the per-feature *grant* is a **contract-first dependency**, not an IC-009 deliverable.
- **Roadmap tier (§17):** global directory reads = *foundation*; tenant Startup/Investor/Deal records = *business-domain* (contractable shape now; built beyond the foundation phases); DEF cells = *deferred*.

---

### D. Portal DTO Contracts (D-37 §10 provenance + D-35 anonymity precedence + IC-010 §G references-only + IC-008)

**Global rules every DTO MUST obey:**
- **Provenance (D-37 §10):** carry `record_origin`, `record_residency`, `record_type` on all records, and `lineage_reference` **for tenant-resident records ONLY** — exact marker names; no competing vocabulary.
- **References-only (IC-010 §G):** no names/emails/PII/secrets/tokens/payloads/physical-DB identifiers/connection data/router decisions; identity resolves to display values at presentation only (D-03).

**Anonymity prohibition — scoped (IR-08).** The Tenant Anonymity Rule binds **directory/publication DTOs only**: those DTOs MUST NOT carry `tenant_id`/`tenant_name`/`tenant_code`/`tenant_reference`/`membership_reference` or any tenant-attributable field, and MUST NOT carry `lineage_reference` (D-35 Tenant Anonymity Rule, which **prevails on any conflict** with §10). **Membership and audit DTOs are NOT directory records** and lawfully carry tenant references (`tenant_id`/`tenant_ref`) by design (IC-002 Principal Membership Record; D-34/IC-001 Global Audit Representation Rule). The two record classes MUST never be conflated (IC-001 scope note).

**Ownership refs (IC-008 P5; DEC-4 — ADOPTED).** Owner references are reference-only and never imply visibility/authority. **Owner references are NOT surfaced to directory readers in MVP** (IC-008 P5; IC-008 routes this presentation decision to IC-009/IC-010). This is adopted contract law (DEC-4); see §L.

| DTO | Purpose | Key fields (references only) | Source contract | Residency / anonymity | Tier |
|---|---|---|---|---|---|
| `UserSessionDTO` | render the authenticated shell | `correlation_id`, `principal_ref`, `role`, `tenant_context` (ref), `workspace_type` *(field names = IC-010 §G canonical — F-6)* | IC-005/IC-010 §G | n/a; no PII | foundation |
| `WorkspaceMembershipDTO` | feed the workspace switcher | list of `{tenant_id, role, display_ref}` *(IC-002 canonical — IR-07; presentation alias e.g. `display_label` resolves from `display_ref` at presentation only)* | IC-002 MembershipsForPrincipal / Principal Membership Record (D-33-E1) | Control-plane; **lawfully carries `tenant_id`** (membership DTO, NOT a directory record); no DB identifiers | foundation |
| `PortalNavigationDTO` | backend-authoritative nav | nav entries gated by role/permission/active-tenant/tier | IC-009/IC-005 | n/a | foundation |
| `PermissionDTO` | per-feature authz flags | backend-authoritative permission flags | IC-005 + feature contracts | n/a | foundation |
| `GlobalStartupSummaryDTO` / `GlobalInvestorSummaryDTO` / `GlobalDealSummaryDTO` | directory discovery | discovery metadata grounded on the **four IC-001 categories** (Global / Reference / Discovery / Directory Data — DEC-10 RESOLVED); `record_origin/record_residency=global/record_type`; **no `lineage_reference`; tenant-anonymous** | IC-001 (categories) / D-35 | Control DB; **tenant-anonymous (D-35)** | foundation |
| `TenantStartupDTO` / `TenantInvestorDTO` / `TenantDealDTO` | tenant business records | `record_origin/record_residency=tenant/record_type`; `lineage_reference` if imported; `owner_agent_ref` (ref-only, not surfaced to directory readers); permission-scoped fields | IC-002/IC-008/IC-004 | tenant DB | business-domain |
| `ImportPreviewDTO` / `ImportInitiationDTO` | discovery→import | global **source reference** + active-tenant target; discrete, user-initiated; yields an independent tenant copy with new tenant-side owner — **single Tenant-DB write, NOT a Control-read-joined-to-tenant-write straddling request (IR-09)** | IC-003/D-35/IC-008 | resolves to **exactly one tenant DB** (global source carried by reference only) | foundation/business-domain |
| `ImportResultDTO` *(W1a — composed-core import completion; the `ImportInitiationDTO` completion sibling)* | discovery→import **completion** | `source_ref` (global source), `target_tenant_ref` (signed active tenant), `tenant_record_ref` (the `<tenant>:startups:<global_startup_id>` lineage-target shape — **no raw row PK**), `lineage_ref` (derivation ref = import job id), `import_id`, `outcome` ∈ `{created, replayed, noop}` — **references only**; composed by the gateway ONLY from a real, durably-audited import result; a zero-record import is the LW-1 §L denial and composes **no** DTO | IC-003/D-35/IC-008 | resolves to **exactly one tenant DB** (global source carried by reference only) | foundation/business-domain |
| `LineageSummaryDTO` | imported-record lineage | `lineage_reference` (tenant-resident only) | IC-004 | tenant DB | foundation |
| `AuditEventDTO` | portal-triggered audit | `actor_ref/user_ref/tenant_ref/ownership_ref/record_ref`, action, outcome, ts, correlation — refs only; lawfully carries `tenant_ref` | D-34 / D-37 §12 / IC-010 §J | per residency — **tenant-resident ownership-audit residency BLOCKED on the IC-002 audit extension (DEC-11)** | foundation |
| `ErrorDTO` | safe denial/errors | safe denial surface per IC-010 §L + IC-005 (401/403) + IC-002 readiness; **no DB name / tenant existence / router detail / stack trace** (see §J) | IC-010 §L (referenced) | n/a | foundation |
| `SharedItemReferenceDTO` *(Draft — IC-007 governed sharing; **inert until IC-007 Final**)* | the target's references-only read projection of a governed share (MVP visibility mechanism) | `share_id`, `share_type`, `source_record_ref`, `source_record_kind`, `owner_agent_ref` *(**DEC-4: hidden from a non-owner target**; owner-side only)*, `owning_tenant_ref` *(only where authorized)*, `target_ref`, `permission_scope`, `status`, `effective_at`, `expires_at`, `revoked_at`, `approved_reference_refs[]` — **references only**; **MUST NOT** carry tenant business payload, source-tenant live record, DB identity/name/DSN/topology, secret/credential/raw provider body, or PII | IC-007 (governed sharing) / IC-010 §V | Control DB (single Control-composed operation; **never a cross-tenant read**) | deferred (IC-007) |

**Governed Sharing projection (§D.1 — D-38, IC-007 adoption; inert until IC-007 Final).** `SharedItemReferenceDTO` is the **normative-home** definition of the references-only shared-item projection; IC-010 §V references this definition for gateway composition (one normative home — no split-definition drift). It is the **MVP visibility mechanism** for a governed share: a **single Control-DB read**, composed by the gateway under IC-010 §V.1, exposing only the approved reference scope. It carries **no tenant business payload** and never triggers a cross-tenant live retrieval. `SharingTransitionResultDTO` and `SharingListItemDTO` are its references-only siblings (each resolves to exactly one Control-DB operation). These DTOs are **authored-but-inert until IC-007 is Final** and add **no** code-level portal DTO in this slice.

Deferred DTOs (not in MVP): the remaining cross-tenant/shared-deal rich DTOs (owner-published snapshot, retrieval token — **IC-007**, beyond the four adopted governed-sharing categories); AI task/agent DTOs and any AI-owner-ref display (**IC-006**; D-37 §7.6). **Media/file DTOs: OUT OF MVP, no portal surface — a future contract (or IC-003/IC-004 extension) MUST home media/file handling before any such DTO is contracted (DEC-6/IR-14).**

---

### E. Portal Discovery Rules
Directory discovery is via **authenticated, audited control-plane reads** (IC-005/D-31) of **tenant-anonymous** global records (D-35), available per the principal's workspace context (D-33) and gated by the §C matrix. Discovery creates no ownership, no import, no synchronization (D-35). Own-kind vs cross-kind access is per §C (cross-kind = DEF→IC-007).

### F. Gateway-Facing Portal API Contracts (map onto IC-010 §Q — portal never selects the DB, §X)
Every portal request resolves to exactly one **IC-010 §Q dispatch category** → Control DB **or** exactly one tenant DB (one request → one category → one database, IC-010 §K/§O):

| Portal action | IC-010 §Q category | DB/residency | Notes |
|---|---|---|---|
| Directory discovery read | **Global Directory Read** | Control DB (tenant-anonymous) | own-kind/discovery per §C |
| Tenant business read/write | **Tenant Operation** | the one active tenant DB | from signed claim; permission-scoped |
| Workspace switcher list | **MembershipsForPrincipal** | Control DB (references only; membership records only) | IC-002/D-33-E1; self-or-CONTROL |
| Import a global record | **Import Initiation** | **exactly one tenant DB** (global source by reference only) | IC-003/D-35; new tenant-side owner (IC-008); not a straddling request (IR-09) |

RequestContext (§G), carriers (§E), and the error model (§L) are **IC-010's**, referenced here. **No global+tenant read may be combined in one request** (IC-010 §K) unless IC-010 explicitly composes a safe response.

#### F.1 Portal Operation Inventory (category-level — IR-01)
This inventory is **category-level by design**: it binds each portal class's gateway-facing operation *kind* to its single §Q category and DB residency. **Concrete endpoint enumeration (methods/paths/shapes) is deliberately OWNED BY THE API GATEWAY IMPLEMENTATION PRD** (IC-010 §Q: "concrete bindings are implementation details for the future execution PRD"); routes are illustrative only (no Lovable source — §16).

| Portal class | Gateway-facing operation kind | §Q category | DB residency | MVP tier |
|---|---|---|---|---|
| Control | manage/read Global Directories; publication governance; global audit read | Global Directory Read (+ control-plane reads) | Control DB | foundation |
| Master Agent | workspace-switcher list | MembershipsForPrincipal | Control DB | foundation |
| Master Agent | directory discovery / import-initiation | Global Directory Read / Import Initiation | Control DB read → **one** tenant DB write | foundation |
| Master Agent | active-tenant business read/write | Tenant Operation | one active tenant DB | business-domain |
| Tenant (ADMIN/AGENT) | active-tenant business read/write | Tenant Operation | one active tenant DB | business-domain |
| Tenant (ADMIN/AGENT) | directory discovery / import-initiation | Global Directory Read / Import Initiation | Control DB read → **one** tenant DB write | foundation |
| Startup | own-kind directory discovery | Global Directory Read | Control DB | foundation |
| Startup | assigned-record business read/write | Tenant Operation | one active tenant DB | business-domain |
| Investor | own-kind directory discovery | Global Directory Read | Control DB | foundation |
| Investor | assigned-record business read/write | Tenant Operation | one active tenant DB | business-domain |
| AI (Reserved) | — | — | — | IC-006-deferred |

> Every row resolves to **exactly one** §Q category and **exactly one** database per request (Import Initiation is one Tenant-DB write carrying a global source reference, not a straddle). No row, and no combination, may span the Control DB and a tenant DB or two tenant DBs in one request (§K; verified by §P.3/§P.4).

### G. Portal Access Contracts
Authorization is **separate from ownership** (D-36; IC-008 P1/P5) and from portal access and workspace selection (D-37 §11). Per-feature authorization is governed by IC-005 + the feature contracts; the portal **never computes authority** and never uses an ownership field as an access/visibility/routing input (IC-008 P1–P5).

### H. Channel Bindings (D-37 §6 Channel Rule)
The six portal classes are **channel-agnostic** presentation contracts: web, future mobile, and future API-platform consumers bind to **identical** IC-009 contracts and to the gateway-only (§5), residency (§13), and caching (§14) rules. No channel may bypass these. (New *channels* bind identically; new *portal classes* require a new ADR + IC-009 amendment — §Q.)

### I. Workspace-Switcher Contract (references IC-005/D-33/IC-010; adds portal layer)
Carrier/auth/switch semantics are **owned by IC-005/D-33 and IC-010 §E** (referenced, not redefined). A workspace switch is **settled law, not an open decision (DEC-9 removed):** selecting a workspace obtains a **new tenant-scoped token** (D-33 §4.3–4.4, audited, one active tenant) — never a header/cookie/query mutation (IC-005). Portal-layer specifics IC-009 adds: the switcher is a **shell-level capability in every portal class** (Master Agent its primary consumer — D-37 §8), fed by the **MembershipsForPrincipal** read; and the switch **invalidates the portal data context** before any subsequent retrieval (D-37 §14, no cross-workspace cache). The switcher may receive only the IC-002 membership fields (`tenant_id`, `role`, `display_ref` — resolved to a display label at presentation only; IR-07 vocabulary parity); it must **never** receive a physical DB name/URL/connection string/router decision/tenant secret/cross-tenant plan.

### J. Navigation & Error/Denial Model  *(F-1 rewrite — REFERENCE, do not re-derive)*
Navigation renders from the backend-authoritative `PortalNavigationDTO` (role + permission + active-tenant + tier); the portal **never infers access** from hardcoded tenant IDs, DB names, Supabase table visibility, local role overrides, or stale cache. **Denial sequencing MUST be Loading → Page or Loading → Denied — never Page → Denied-after-protected-data** (genuine portal-layer rule).

**Error model is IC-010's, referenced — not coined here.** The portal surfaces denials per **IC-010 §L** (fail-closed; the only IC-010-named code is **403 `carrier_mismatch`**, §E/§L), with denial semantics following **IC-005 (401 unauthenticated / 403 forbidden)** and **IC-002 readiness** (*not found* / *not ready* / *administratively disabled* / *unavailable*). The portal is a **renderer only**: the gateway is the audit **emitter** of `CarrierMismatch / CarrierOnControlAnomaly / RouteDenied / IsolationAnomaly` (IC-010 §J). No portal-visible error leaks a DB name, cross-tenant existence, router detail, secret, or stack trace.

> **PORTAL-LAYER PROPOSAL (pending IC-010 — change-control item, §Q):** any *additional granular* portal-surface error codes beyond IC-010 §L's `carrier_mismatch` (e.g. distinguishing membership-required vs role-not-allowed vs permission-required, or a 409 stale-workspace / 422 invalid-request / 503 dependency-not-ready surface) are a **portal-presentation proposal**, NOT existing "IC-010 §L codes." They are **not adopted** by this contract and must either be (a) standardized into IC-010 §L by an IC-010 amendment, or (b) carried as an explicit open decision for the API Gateway implementation PRD. Until then the portal surfaces only the IC-010 §L / IC-005 / IC-002 model above.

#### J.1 Error/Denial-to-Surface Map (IR-10 — portal renders only)

| Gateway condition (IC-010) | Code / semantic (IC-010 §L · IC-005 · IC-002) | Audit class emitted by gateway (§J) | Portal-rendered surface |
|---|---|---|---|
| Unauthenticated | 401 (IC-005) | — | Loading → Denied (re-auth) — no protected data shown |
| Carrier/claim mismatch | 403 `carrier_mismatch` (§E/§L) | `CarrierMismatch` | Loading → Denied |
| Recognized carrier on tenantless CONTROL token | claim-only; carrier ignored (§F) | `CarrierOnControlAnomaly` (mandatory) | Loading → Page (control scope) — portal does not surface the anomaly |
| Not a member of claimed tenant / not authorized | 403 forbidden (IC-005) | `RouteDenied` | Loading → Denied |
| Unknown / not-ready / suspended / failed tenant | consistent *not found* / *not ready* / *administratively disabled* / *unavailable* (IC-002) | `RouteDenied` (where applicable) | Loading → Denied (consistent denial — never leaks another tenant's existence) |
| Isolation-boundary breach attempt | rejected (§K) | `IsolationAnomaly` | Loading → Denied |

> The portal **renders** these surfaces; it **emits** none of the audit events (IC-010 §J). The 409/422/503 surfaces referenced above are the §J PORTAL-LAYER PROPOSAL, not adopted here.

### K. Global vs Tenant Record Rules (D-37 §10/§13, D-35, IC-003)
`Global Record ≠ Tenant Record`; `Import ≠ Synchronization`. Portal-visible data follows **record residency** (global → Control DB; tenant → tenant DB; imported → tenant DB even when lineage references a global record — point-in-time copy, IC-003). A directory DTO and a tenant-record DTO are distinct objects; the relationship is expressed only via provenance markers + `lineage_reference` (tenant-resident only). No portal silently syncs global into tenant; import is **discrete + user-initiated** and resolves to **exactly one tenant DB** carrying a global **source reference** only (IR-09; D-37 §9; IC-010 §Q).

### L. Ownership Rules (align to IC-008)
`Ownership ≠ Authorization / Visibility / Routing / Authentication` (IC-008 Principles 1–5). The portal never computes ownership authority. Owner references (`owner_agent_ref`; `owner_ai_agent_ref` NULL until IC-006) are reference-only; eligibility (who may own) is IC-008's role matrix and does **not** determine who may **see** a record. **Adopted decision (DEC-4):** owner references are **NOT surfaced to directory readers in MVP** — they are governance metadata, not discovery metadata, are not among the four IC-001 categories, and IC-008 routes "whether they surface to directory readers" to IC-009/IC-010 (IC-008 P5). This contract adopts the hide decision. **Ownership-audit residency (DEC-11):** the tenant-resident ownership-audit class is carried by the **pending IC-002 audit-section extension** ("specified, not yet executed"); the gateway PRD MUST NOT bind ownership-audit DTO residency until that amendment lands (§Q sequencing).

### M. Cross-Tenant (IC-007) & AI (IC-006) Deferrals
**IC-007 (deferred/out-of-MVP) — amended by D-38 for the four adopted Governed Sharing categories:** Shared Deals, cross-tenant sharing/introductions, Master-Agent cross-tenant scope, and any cross-kind/introduction-shaped discovery remain **DEF→IC-007** — no frontend fan-out, no multi-tenant-DB query, no defined authorization mechanism (D-37 §7.4/§7.5/§18) — **except** the **four adopted Governed Sharing categories** (intra-Master-Agent Deal; Master-Agent → Master-Agent Startup; Control → Master-Agent Startup; Control → Master-Agent Investor), which re-open **references-only** via `SharedItemReferenceDTO` and are **authored-but-inert until IC-007 is Final**. The re-open adds **no** frontend fan-out and **no** multi-tenant-DB query: every governed-sharing read resolves to the **Control DB only** (one request → one category → one database; a straddle → `IsolationAnomaly`). Cross-kind / introduction-shaped discovery and the end-user Global Deal-Directory (`DEF*`) remain closed.

**Dual-layer authority note (D-38).** A governed share is authorized across two distinct layers: the **six D-32 platform / token roles** (Layer A — the only JWT/token roles) gate route access and workspace/tenant scope, and the **seven tenant organizational roles** (Layer B — Owner, Head of Investment, Portfolio Manager, Investment Manager, Analyst, Marketing, Institutional Sales; **references-only, not token roles**) carry the human senior-approval step where the policy requires it (Owner-only assigns organizational roles; AI cannot authorize). The **portal computes no sharing authority** — it renders governed-sharing state under the Gateway; denial surfaces are IC-010 §L / IC-005 / IC-002 only. **DEC-11 sequencing preserved:** the sharing-audit *residency* is **Control-resident** (avoiding the tenant-residency wall) and its class-home binding still sequences under the pending IC-002 audit-section extension.

**IC-006 (deferred/post-MVP):** all AI presentation in every portal — including the D-37 §7.6 "Current AI Context" workspace-switcher element and any D-36 AI-owner-reference display — is deferred; the portal never calls AI providers, selects a model/provider, or sends tenant data to a vendor.

### N. Security & Privacy
No secrets / physical-DB identifiers / connection data / router decisions / service-role keys in any DTO; no cross-tenant data leakage; directory DTOs tenant-anonymous (D-35); no stale tenant data after a workspace switch (D-37 §14); references-only audit (D-34); no stack traces in frontend-visible errors; no PII in logs beyond the audit contract.

### O. Required-Content Fidelity Checklist (IC-009 placeholder / D-37 §16 — all six satisfied)
1. Portal DTO contracts under D-37 §10 provenance + D-35 anonymity → **§D** ✓
2. Per-role × per-directory visibility matrix incl. deliberately-deferred cells → **§C** ✓
3. Portal discovery rules (IC-005/D-31; D-33) → **§E** ✓
4. Portal API contracts (gateway-facing; IC-005 token contexts; stateless) → **§F (+ §F.1 operation inventory)** ✓
5. Portal access contracts (authz separate from ownership, D-36) → **§G/§L** ✓
6. Channel bindings (D-37 §6) → **§H** ✓

### P. Verification & Testability Specification (IR-03/IR-06 — the IC-009 mechanical-check set the gateway PRD inherits)
Each IC-009 normative rule maps to a mechanical check. These are **acceptance criteria for the future API Gateway / frontend-integration PRDs** (contracts precede code — none authorized here):

```text
P.1  Directory-DTO forbidden-field test — every directory/publication DTO field set EXCLUDES
     {tenant_id, tenant_name, tenant_code, tenant_reference, membership_reference} and any tenant-attributable field,
     and carries NO lineage_reference (D-35 Tenant Anonymity Rule; IC-001 line 70). Membership/audit DTOs are EXEMPT
     (they lawfully carry tenant_id/tenant_ref) — the test must target directory/publication DTOs only (IR-08).
P.2  No-physical-DB-identifier test — no DTO carries a physical-DB name/URL/DSN/connection descriptor/router decision/secret
     (IC-010 §G references-only; §N).
P.3  One-§Q-category test — every §F/§F.1 operation resolves to EXACTLY ONE IC-010 §Q category and EXACTLY ONE database;
     no operation (and no combination) straddles Control DB + tenant DB or two tenant DBs in one request (IC-010 §K/§Q).
P.4  MASTER_AGENT fan-out prohibition test (IR-06) — for a MULTI-MEMBERSHIP MASTER_AGENT, NO portal operation resolves to
     more than one tenant DB in one request; cross-tenant aggregation has NO defined mechanism and is DEF→IC-007
     (IC-005 anti-privilege-escalation lines 70–76; IC-010 §K; D-37 §7.2/§18/V9). This is the single highest-value isolation guard.
P.5  Frontend Repository Audit (§W-analogue) — the frontend repo contains NO database client, NO Supabase data SDK, NO PostgREST
     usage (D-37 §20 V3; IC-010 §W). Reserved as a future gateway-validation requirement; cannot run until a frontend repo exists.
P.6  Provenance-marker test — every record DTO carries record_origin/record_residency/record_type; lineage_reference appears
     on tenant-resident DTOs ONLY (D-37 §10).
P.7  Denial-surface test — portal error surfaces expose only the IC-010 §L / IC-005 / IC-002 model (§J); no DB name, cross-tenant
     existence, router detail, secret, or stack trace; denial sequencing is Loading→Page or Loading→Denied, never Page→Denied-after-data.
```

### R. D-37 §20 V1–V12 Conformance Mapping (IR-05 — the IC-009 analogue of IC-010 §W)

| D-37 §20 | Criterion | How IC-009 satisfies / inherits it |
|---|---|---|
| **V1** | Portal never determines DB routing | §A–§F, §I; portal never selects a DB (IC-010 §X/§H); test §P.3 |
| **V2** | Portal never determines tenant routing | §F/§I tenant from signed claim only (IC-005/D-06); test §P.3/§P.4 |
| **V3** | Data only through the API Gateway | §Boundary/§5; Frontend Repo Audit §P.5 |
| **V4** | Master Agent Portal grants no IC-007 capability | §A/§M; DEF→IC-007 cells in §C; test §P.4 |
| **V5** | Global discovery consistent with D-33 + the IC-009 matrix | §C/§E gated by D-33 workspace context |
| **V6** | Portal DTOs preserve provenance; directory DTOs tenant-anonymous | §D + tests §P.1/§P.6 (D-35 precedence) |
| **V7** | Portal data follows residency boundaries | §K (D-37 §13); imported → tenant DB |
| **V8** | Portal caches never cross tenant/workspace | §I/§N (D-37 §14); switch invalidates context |
| **V9** | No portal introduces cross-tenant visibility outside approved contracts | §C DEF→IC-007; §M; test §P.4 |
| **V10** | Portal imports discrete + user-initiated; independent tenant records; no portal sync | §K (D-37 §9; IC-003); §F.1 import = one Tenant-DB write |
| **V11** | Audit records comply with D-34 representation rule (incl. `ownership_ref`) | §D `AuditEventDTO` refs-only; §J (D-34/IC-001 rule) |
| **V12** | Physical Multi-Database MVP unchanged | whole contract; no rule weakened; tests §P.3/§P.4 |

### Q. Change-Control & Versioning (IR-04)
```text
(a) AMENDMENT PATH. IC-009 amendments follow the standard contract change-control: decision-register entry → Contract Amendment
    Package (D-37 §22 step 3) → promotion. No silent edit of an adopted IC-009 is permitted.
(b) NEW PORTAL CLASSES. A new portal class (e.g. LP / Advisor / Partner / Accelerator) requires a NEW ADR + an IC-009 amendment
    (D-37 §6 Future Portal Expansion); it must never be introduced under IC-009 alone or under D-37.
(c) DEFERRED-CELL RE-OPEN TRIGGERS (explicit — never a silent edit):
      • DEF→IC-007 cells (cross-kind/introduction; Master-Agent cross-tenant; Shared Deals) re-open ONLY via an IC-009 amendment
        AFTER IC-007 is designed+approved. IC-007 adoption is the named trigger.
        D-38 (2026-07-18) opens IC-007 (Draft/Proposed) and re-opens ONLY the four adopted Governed Sharing categories
        (intra-MA Deal; MA→MA Startup; Control→MA Startup; Control→MA Investor), references-only and INERT UNTIL IC-007 IS FINAL;
        cross-kind/introduction discovery stays DEF→IC-007.
      • DEF* cells (end-user Global Deal-Directory visibility) re-open ONLY via an IC-009 amendment carrying an explicit MVP-scope
        decision (D-37 deliberately-deferred; not an IC-007 dependency).
(d) REVISION MARKER. The adopted IC-009 carries a revision identifier; every downstream PRD (API Gateway impl, frontend-integration
    governance, portal implementation) MUST cite the specific adopted IC-009 revision it builds on.
```

### Frontend note
No Lovable frontend source exists in the repo (PRD 02). This contract is **derived from the architecture/contracts**, not from any UI. Any concrete frontend route/component/Supabase-usage claim is **UNKNOWN — FRONTEND SOURCE NOT PROVIDED** and is deliberately absent; route/screen mapping is for the future frontend-integration governance step (D-37 §22 step 6).

### R1 Principal Bootstrap & Memberships-Before-Tenant-Selection (B5-BLK-5 R1, D-41)

*Added under D-41 (B5-BLK-5 R1). Additive only; the served revision remains IC-009-R1. This section states the R1 portal-layer principal-bootstrap flow that precedes tenant selection. It amends no directory contract (§C/§D directory cells, §E discovery rules) and alters no IC-007 deferral boundary; workspace switch remains settled-law-but-deferred per §I.*

- **Principal-bootstrap flow.** After OIDC login, the portal renders the authenticated shell from a **principal-only** context (`active_tenant_id = null`, `role = null`; IC-005 R1 Principal-Only Bootstrap). Before any tenant is selected, the shell issues exactly one **MembershipsForPrincipal** read.
- **`GET /memberships` before tenant selection.** The workspace switcher is fed by the self-scoped **MembershipsForPrincipal** read, which is lawful **before** tenant binding (a Control-DB read that requires no active tenant and no role). No tenant-scoped retrieval occurs until the principal selects a workspace.
- **`WorkspaceMembershipDTO` exact fields.** The bootstrap membership read returns exactly `WorkspaceMembershipDTO` = list of `{ tenant_id, role, display_ref }` (the §D canonical shape; `display_ref` resolves to a display label at presentation only). It carries **no** email, name, `tenant_name`, `tenant_code`, physical-DB identifier, or tenant business payload.
- **Successful empty list.** An authenticated principal with no memberships receives a **lawful successful empty list** (an empty membership collection is a success, not a denial), and the switcher renders an empty state.
- **State model — loading / empty / denied / unavailable.** The shell renders: **loading** while the bootstrap read is in flight; **empty** for a successful zero-membership result; **denied** for `401`/`403`; **unavailable** for `503` (Control-plane read failure). These are distinct surfaces.
- **No Page → Denied-after-data transition.** Denial sequencing MUST be **Loading → Page** or **Loading → Denied** — never **Page → Denied-after-protected-data** (§J). The bootstrap read never renders protected data before a denial.
- **PII minimization.** The bootstrap read is **references-only** and MUST NOT carry PII or tenant-attributable business payload. The R1 cutover from the current PII-bearing session-context read to `WorkspaceMembershipDTO { tenant_id, role, display_ref }` **removes** `email`/`first_name`/`last_name`/`tenant_name`/`tenant_code` from the bootstrap surface — a security-positive that MUST be preserved.
- **Principal display identity from OIDC claims.** The authenticated principal's display identity (name/avatar for the shell) resolves **client-side from lawful OIDC `id_token` display claims**, **not** from a Control membership-bootstrap payload. The membership read is never a channel for principal PII.
- **Workspace switch remains deferred.** Selecting a different workspace remains the IC-005/D-33 tenant switch (settled law, not an open decision) and is **out of R1**: R1 authors only the principal bootstrap and the pre-selection memberships read. The switch invalidates the portal data context before any subsequent retrieval (§I), unchanged.
