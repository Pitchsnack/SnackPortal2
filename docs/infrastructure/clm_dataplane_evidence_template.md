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

> The witness never sees a routing answer and never reads `control_tenants`. On a connection it
> opens `read_only`, it issues exactly one **business-data** read — a correlation-filtered `SELECT`
> from `control_gateway_audit` for the denial rows of its own two isolation requests (§7, runbook
> §6.1) — plus two **metadata** statements, `pg_control_system()` and `current_database()`, which
> read no table and exist so the no-leak census can bar the Control database's physical name. None of
> it touches anything below. Every row below is filled in by the operator from a separate read, and
> that read is the **only** thing that establishes the routing source was durable — D-2 is a
> declaration and does not.

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

## 7. Isolation evidence — **two legs, recorded separately; BOTH are pre-routing**

> **A `403` with an empty body names no reason.** **Four** outcomes render it identically —
> `carrier_mismatch`, `tenant_context_required`, `tenant_access_denied` and `tenant_not_ready`. Each
> leg therefore mints its own correlation id, sends it as `X-Correlation-Id`, and the witness reads
> the **durable operational-audit record** for that request out of `control_gateway_audit`. Record
> the reason the harness **observed** — never one inferred from the status code.

### 7a. Auth stage — **E48 (currently UNPROVABLE; see GBR-4)**

| Item | Observed |
|---|---|
| ACME-only principal presenting a ZETA claim | status `____`, body empty ☐ |
| Correlation id used for this leg (a reference; safe to record) | `____________________` |
| Durable denial reason reported by the harness | `____________________` |
| **E48 verdict** — expected on this runtime: `E48 NOT AVAILABLE / UNPROVEN` (an `AMBIGUOUS PRE-AUTH DENIAL`). Record what the harness printed, verbatim | `____________________` |
| ZETA table byte-identical afterwards | ☐ |

> **E48 cannot be satisfied from this record today, and the leg is expected to FAIL.** A
> `RouteDenied` row carrying **no** actor, tenant or carrier reference is emitted for
> `tenant_access_denied` (a non-member of a Ready tenant — genuine authorization denial) **and** for
> `tenant_not_ready` (a member of a known-but-dormant tenant — not an authorization denial at all).
> The `403`, the public code and the audit row are byte-identical in both cases, so the record cannot
> decide between them and the harness reports **`E48 NOT AVAILABLE / UNPROVEN`**. This is **GBR-4**,
> and it is a Dan decision (narrow Gate B, or accept an explicitly labelled substitute), or a
> governed production change — never a harness edit and never a re-pointed leg.
>
> **The other verdicts, and what each means.** `tenant_context_required` (a `RouteDenied` row that
> *does* carry an actor reference) means the bearer simply had no tenant claim — nobody was denied
> access to ZETA. `carrier_mismatch` means the request was refused for its carrier, not for the
> principal's authorization. **`NOT AVAILABLE / UNPROVEN`** with zero durable rows means the record
> could not be read at all — the sink was off, the row did not persist, or the local IdP cannot issue
> the bearer. Record the verdict verbatim; **do not record E48 as satisfied on a `403` alone, and do
> not record it as satisfied on an ambiguous pre-auth denial.**

> **Scope caveat, mandatory in every completed record.** This denial fires in the **Auth Router**,
> before any routing or tenant-DB contact. It proves **auth-stage** denial. It does **not** prove that
> the Database Router would have refused.

### 7b. Unregistered-tenant carrier — **NOT a router-stage proof (GBR-1); NOT REACHED while GBR-4 is unresolved**

> **Expect this table to be unfillable today.** This leg is sequenced after 7a's E48 assertion, which
> fails by construction, so `cmd_run` aborts before issuing it. Record it as **not reached**, citing
> GBR-4 — do **not** leave it blank as though it had been skipped by choice, do not mark it n/a, and
> do not re-point the leg or the run to make it fill.

| Item | Observed |
|---|---|
| Unregistered-tenant carrier denied | status `____` (must be 401/403/404 — a `200` is a breach and a `503` is the upstream/audit collapse, not a denial), body empty ☐ |
| Correlation id used for this leg | `____________________` |
| Durable denial reason **observed** (recorded, not asserted — any of the three is legitimate here) | `____________________` |
| Existence leak check: unknown tenant and non-member deny **identically** | ☐ |

> **This leg is resolved pre-routing**, in the Auth Router path — the same stage as 7a. It was
> formerly labelled "router stage"; that label is withdrawn. **Router-stage isolation — that the
> Database Router itself would have refused — remains UNPROVEN, by this leg and by this harness.** Do
> not write otherwise in a completed record.

> **Both legs are mandatory.** `SP2_CLM_WITNESS_ZETA_CLAIM_BEARER` and
> `SNACKPORTAL_SECRET_CONTROL_CONTROL_STORE_DSN_V1` are both required by `run`; a record carrying
> only one leg, or one with no durable denial reason, is not a complete isolation record.
>
> **And with GBR-4 unresolved, the harness cannot currently produce a complete two-leg isolation
> record.** 7a is executed first, and `cmd_run` asserts on E48 immediately afterwards. That assertion
> fails by construction on this runtime, so the run aborts **before** 7b is issued — **the second
> isolation leg is not reached while GBR-4 remains unresolved.** Read the two rules together and do
> not resolve the tension by relaxing either one:
>
> * **both legs remain mandatory for final acceptance** — the requirement is unchanged, and neither
>   leg may be dropped, waived, or marked n/a to close the record;
> * a record carrying only 7a is **INCOMPLETE / NOT ACCEPTABLE AS FINAL ISOLATION EVIDENCE**;
> * filing such a record **does not close GBR-4**, and must not be described as having done so;
> * **E48 and full isolation evidence may not be marked PASS until GBR-4 is resolved and both legs
>   execute.** Until then the honest entry is the observed abort, recorded as such.
>
> The correct outcome today is therefore an incomplete record that states plainly why it is
> incomplete — not a completed one, and not a narrowed requirement.

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
| `CarrierMismatch` | ☐ | ☐ |

This is the harness's `EXPECTED_AUDIT_ACTIONS` inventory verbatim — the two agree, so a reconciliation
against either finds no unaccounted row (GBR-2 closed). The two **denial** rows for the run's own
correlation ids are the only ones the witness itself reads, and it reads them as `IS NOT NULL`
booleans; the **success** rows and the value-absence column above are the operator's separate read.

Durable coverage is the **five** `_CLM_DURABLE_ACTIONS` classes only — the fifth,
`workspace_memberships_read`, belongs to a different journey and is correctly absent above.
`ISOLATION_ANOMALY` and its siblings stay in-memory **by design** — do not write "all Gateway audit
is durable" anywhere.

## 10. Secret & state guards

| Item | Observed |
|---|---|
| Witness no-leak scan over its **four captured artifacts** (`served_get`, `served_patch`, `isolation_auth_stage`, `isolation_unregistered_carrier`) | ☐ PASS |
| Scanned over the WHOLE artifact | the ACME, ZETA **and Control** DSNs verbatim, **both** bearer tokens, any of those DSNs' password substring, each physical database name (Control included) |
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

**While GBR-4 is unresolved this verdict cannot be a pass for isolation.** The run aborts at 7a's E48
assertion and never issues 7b, so the isolation record is incomplete by construction: neither E48 nor
full isolation evidence may be marked PASS here until GBR-4 is resolved **and both legs execute**.
Record the abort, name GBR-4, and leave the isolation claim open.
