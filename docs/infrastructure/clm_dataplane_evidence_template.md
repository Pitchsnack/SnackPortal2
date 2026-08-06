# CLM ACME tenant data-plane witness — evidence record (template)

**References only.** No DSN, password, bearer token, key material, or physical database name appears
in a completed instance of this template. Every identity is redacted to `scheme://host:port/database`
with the database name itself omitted where it is not already public. Fill in observations, never
values.

> **This template records ONE run of ONE chain on the LOCAL non-production topology.** It closes no
> blocker, activates nothing, and proves nothing about NOVA (which no tier connects to) or about
> production. Procedure: `infrastructure/runbooks/clm_acme_dataplane_witness.md`.

---

## 1. Identity & scope

| Item | Value |
|---|---|
| Backend commit SHA | `____________________` (claims bind to exactly this commit) |
| Frontend commit SHA (if the browser leg was used) | `____________________` |
| Date / operator | `____________` / `____________` |
| START-GATE authorization | who granted it, and where it is recorded |
| Gate status at run time | Gate A: ☐ complete · Gate B: ☐ granted · M14 explicitly authorized: ☐ |
| Harness invocation | `python tests/control_plane/requires_pg/test_pg_clm_acme_dataplane_witness.py run --confirm-start-gate --startup-ref <ref>` |

## 2. Topology

| Edge | Port | Observed UP | Notes |
|---|---:|---|---|
| Auth Router | 8001 | ☐ | |
| Database Router dispatch | 8002 | ☐ | |
| Control Plane read | 8003 | ☐ | |
| Tenant Startup | 8004 | ☐ | |
| Gateway Audit ingest | 8005 | ☐ | |
| API Gateway | **8820** | ☐ | not 8080 — record what, if anything, is on 8080 |

| Cluster | Port | `system_identifier` | Distinct from the others |
|---|---:|---|---|
| Control | 5540 | `____________` | ☐ |
| ACME | 5541 | `____________` | ☐ |
| ZETA | 5542 | `____________` | ☐ |

**ACME identity proof** — the PAIR `(system_identifier, current_database())`. Record the
`system_identifier`; the database name is redacted. `system_identifier` **alone is insufficient**:
every database on a cluster shares it.

## 3. Preconditions — **and they are not all the same kind of fact**

| # | Class | Check | Observed | Verdict |
|---|---|---|---|---|
| D-1 | **declaration** (witness's own shell) | `SP2_GW_TENANT_STARTUP_BASE_URL` declared, non-blank, governed value | SET / UNSET | ☐ |
| D-2 | **declaration** (witness's own shell) | `SP2_CP_CONTROL_STORE=postgres` | | ☐ |
| P-2 | observed | The declared tenant-Startup edge answers | | ☐ |
| A-1 | **authoritative** (edge-observed) | The served `GET` body carries **exactly** the served `TenantStartupDetailDTO` contract field set, and `record_ref` echoes the addressed reference | keys observed: `____` | ☐ |
| A-2 | **authoritative** (independent) | An independent connection to the physical ACME DB returns the same value | | ☐ |
| — | observed | Upstream liveness census recorded at call time | | ☐ |

> **D-1 and D-2 are declarations, not proofs.** They read the *witness process's* environment. The
> Gateway and the Control Plane are separate uvicorn processes composed from their own environments,
> and the governed launcher scrubs `SP2_*` out of every child. Record them — they catch the commonest
> operator error — but do not cite them as evidence about the running services. **A-1 and A-2 are what
> make the record evidence:** the tenant Startup terminal is type-exact, so a pre-CLM handoff cannot
> serve a conforming `200` at all.

**If any is ☐ unsatisfied, stop here.** Nothing below is data-plane evidence.

## 4. Routing view — **operator-collected; the witness observes none of this**

> The witness never sees a routing answer and opens **no** Control-database connection. Every row
> below is filled in by the operator from a separate read, and it is the **only** thing that
> establishes the routing source was durable — D-2 is a declaration and does not.

| Field | Value |
|---|---|
| `tenant_id` | `acme` |
| `lifecycle_state` / `ready` | |
| `database_association_ref.store_ref` | `tenant/____/dsn` — **reference only**, contract-declared non-secret |
| `database_association_ref.version` | |
| `expected_schema_version` | |
| Answer carries ONLY these keys | ☐ |
| `store_ref` begins with `tenant/`, contains no `://`, no `@`, no secret shape | ☐ (operator-checked) |
| **Gate-B verification item:** the same routing row read **directly from the Control database** agrees | ☐ (separate operator read — *not* performed by the witness) |

## 5. Read evidence

| Item | Observed |
|---|---|
| Served `GET` status | |
| Body key set == the served `TenantStartupDetailDTO` contract field set (derived, not restated) | ☐ |
| `record_ref` echoes the reference the route addressed | ☐ |
| `short_description` (pre-state) — **record a digest, not the value, if it is not already public.** `NULL` is a lawful pre-state; record it as `NULL`, not as a missing row | |
| Positive control: the `--startup-ref` row EXISTS (its own `SELECT 1` probe, independent of the value) | ☐ |
| Independent ACME `SELECT` of the same row agrees | ☐ |
| `current_database()` / `system_identifier` of the reading connection | |

## 6. Write evidence

| Item | Observed |
|---|---|
| Served `PATCH` status | |
| Echoed new value matches what was sent | ☐ |
| Independent ACME `SELECT` confirms the new value | ☐ |
| Field written | `short_description` only, ≤ 500 chars |
| ZETA row byte-identical | ☐ |
| Row-count delta on ACME / ZETA | 0 / 0 |

## 7. Isolation evidence — **two stages, recorded separately**

### 7a. Auth stage

| Item | Observed |
|---|---|
| ACME-only principal presenting a ZETA claim | status `____`, body empty ☐ |
| ZETA table byte-identical afterwards | ☐ |

> **Scope caveat, mandatory in every completed record.** This denial fires in the **Auth Router**,
> before any routing or tenant-DB contact. It proves **auth-stage** denial. It does **not** prove that
> the Database Router would have refused.

### 7b. Router stage

| Item | Observed |
|---|---|
| Unregistered-tenant carrier → resolver `not_found` | status `____` (must be 401/403/404 — a `200` is a breach and a `503` is the upstream/audit collapse, not a denial), body empty ☐ |
| Existence leak check: unknown tenant and non-member deny **identically** | ☐ |

> **Both stages are mandatory.** `SP2_CLM_WITNESS_ZETA_CLAIM_BEARER` is required by `run`; a record
> carrying only one stage is not a complete isolation record.

## 8. Ambiguity disambiguation

| Item | Observed |
|---|---|
| Every `503` paired with the upstream census at the moment of the call | ☐ / n/a |
| Every `404` paired with a positive control | ☐ |
| Durable audit sink reachable throughout (a sink outage turns a legitimate 200 into a 503) | ☐ / n/a |

## 9. Audit evidence (only when the durable sink is enabled)

| Action class | Row present | `short_description` value absent from every cell |
|---|---|---|
| `tenant_startup_read` | ☐ | ☐ |
| `tenant_startup_update` | ☐ | ☐ |
| `RouteDenied` | ☐ | ☐ |
| `CarrierMismatch` (only if a carrier-mismatch leg was run) | ☐ | ☐ |

Durable coverage is the **five** `_CLM_DURABLE_ACTIONS` classes only. `ISOLATION_ANOMALY` and its
siblings stay in-memory **by design** — do not write "all Gateway audit is durable" anywhere.

## 10. Secret & state guards

| Item | Observed |
|---|---|
| Witness no-leak scan over its **four captured artifacts** (`served_get`, `served_patch`, `isolation_auth_stage`, `isolation_router_stage`) | ☐ PASS |
| Scanned over the WHOLE artifact | both ACME/ZETA DSNs verbatim, **both** bearer tokens, either DSN's password substring, each physical database name |
| Shape census — reference / topology / status text | `://`, `eyJ`, `-----BEGIN`, `AKIA`, `ghp_`, `xox`, `password=`, `PGPASSWORD` |
| Shape census — the bounded free-text `short_description` | the same set **minus `://`**, plus a credential-bearing-URI pattern. `://` is lawful in business free text (the serving edge says so: `_TEXT_SECRET_SHAPES`), so a URL-bearing fixture value does **not** fail the run; a token, PEM block or credential DSN still does |
| **Operator** re-scan of THIS completed document for the same shapes — the witness does not read it | ☐ PASS |
| No membership row created to make the journey pass | ☐ |
| No DDL applied | ☐ |
| No environment variable persisted | ☐ |

## 11. Restore

| Item | Observed |
|---|---|
| Original value restored in `finally` (a lawful `NULL` pre-state is restored as `NULL`) | ☐ |
| Before == after digest of the ACME `startups` table | ☐ (digest: `____`) |
| ZETA before == after | ☐ |
| If the run aborted **before** the served `PATCH` was issued, the witness reports `PASS: RESTORE — vacuous` | ☐ / n/a — nothing was written; this is not a second failure |

## 12. Outcome

```text
VERDICT: ____________________
```

State plainly what was proven, for which record, on which topology, at what time — and what remains
unproven. If the membership was absent and the journey returned an empty set, that **is** the result;
record it. Do not create the row and re-run.
