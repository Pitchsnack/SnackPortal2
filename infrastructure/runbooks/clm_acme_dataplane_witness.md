# CLM ACME tenant data-plane witness (operator runbook)

**Scope:** NON-PRODUCTION / documentation only. The procedure for proving the one chain the
controlled local MVP still has no evidence for:

```text
Gateway 8820 -> Tenant Startup 8004 -> Database Router -> Control routing record
             -> SecretRef -> ACME physical tenant DB -> Startup GET -> Startup PATCH
```

plus ZETA denial / tenant isolation.

> **Status: UNPROVEN, and this runbook does not prove it.** The harness, this document and the
> evidence template are **Gate-A deliverables — build only**. The `run` leg performs a **real
> business write to a physical tenant database** (Gate-B class **M14**) and refuses without an
> explicit START-GATE. **Production: NOT READY / DO-NOT-ACTIVATE.**

---

## 1. The precondition that makes or breaks the whole proof

With `SP2_GW_TENANT_STARTUP_BASE_URL` unset, `build_tenant_startup_from_env` returns `None` and every
`TENANT_OPERATION` keeps the **pre-CLM router handoff**. The `/tenant/startups/<ref>` routes stay
registered and keep answering. A witness that does not check first collects a plausible response that
never touched a tenant database and files it as data-plane evidence.

The harness refuses to label anything data-plane evidence until all of the following hold. **They are
not the same kind of fact, and the difference decides what the evidence is worth:**

| # | Class | Check | How it is established, and what it proves |
|---|---|---|---|
| D-1 | **declaration** | `SP2_GW_TENANT_STARTUP_BASE_URL` declared, non-blank, and equal to the governed `http://127.0.0.1:8004` | Read from **the witness process's own environment** and compared. The Gateway is a *separate* uvicorn process composed from its own environment, and the governed launcher scrubs `SP2_*` out of every child — so this is a statement about the operator's shell, not a read of the Gateway. It catches the commonest operator error (running the witness from a shell whose posture does not match the launcher's). It is **not** evidence about the running Gateway. |
| D-2 | **declaration** | `SP2_CP_CONTROL_STORE=postgres` | Same class, same limitation. A routing view served from the in-memory store would let the witness pass with no physical ACME database involved at all — but proving which store the **running** Control Plane used is a separate Gate-B read (see §6.1). |
| P-2 | **observed** | The declared tenant-Startup edge answers on its own surface | Direct probe, recorded at the moment of the call, so a later `503` can be attributed instead of guessed. |
| A-1 | **authoritative, edge-observed** | The served `GET` returns `200` **and** the body carries **exactly** the field set of the served `TenantStartupDetailDTO` contract | This is the real discriminator. The tenant Startup terminal is **type-exact**, so with the port absent a pre-CLM handoff cannot serve a conforming `200` at all — it collapses to `503`. The expected field set is **derived from the DTO at call time**, never restated in the harness: a duplicated literal drifts from the contract silently, and a drifted literal rejects the *genuine* answer. |
| A-2 | **authoritative, independent** | An independent connection to the physical ACME database returns the same value | Different process, different connection, different code path — the one thing no composition can fake. |

---

## 2. Prerequisites

| Requirement | Detail |
|---|---|
| Standing topology | All six standing edges up per `docs/runbooks/backend_service_startup_fastapi.md` §5.1, with **`SP2_GW_TENANT_STARTUP_BASE_URL` and `SP2_CP_CONTROL_STORE=postgres` deliberately SET** — both are Gate-B activations |
| Physical topology | Control 5540 + ACME 5541 + ZETA 5542, physically distinct |
| Membership | The authenticated principal must hold an ACME membership row. **Creating one to make the witness pass is a Gate-B class-M6 mutation and it destroys the evidence** — if the membership is absent, that is the finding |
| Fixture | One ACME Startup row whose `global_startup_id` is the `--startup-ref` argument |
| START-GATE | An explicit human authorization for the `run` leg |

### Environment — **NAMES ONLY**, never values

| Name | Used by | Notes |
|---|---|---|
| `SNACKPORTAL_TENANT_SECRET_TENANT_ACME_DSN_V1` | independent ACME verification | **required by `run`** — existing tenant-secret convention |
| `SNACKPORTAL_TENANT_SECRET_TENANT_ZETA_DSN_V1` | independent ZETA verification | **required by `run`** |
| `SNACKPORTAL_SECRET_CONTROL_CONTROL_STORE_DSN_V1` | **presence report only** | `plan` reports whether it is set. **The witness opens no Control-database connection** — see §6.1 |
| `SP2_CLM_WITNESS_BEARER` | the served legs | **required by `run`.** Operator-local, never committed, never printed, never echoed into a shared terminal |
| `SP2_CLM_WITNESS_ZETA_CLAIM_BEARER` | the auth-stage isolation leg | **required by `run`** — a token for a principal that is **not** an ACME member. Not optional: a run that skipped this leg and still exited 0 would file an incomplete record as a complete one |

> ⚠️ **Pin the tenant identity mapping before Gate B.** No committed artifact registers `acme` /
> `zeta` / `nova` as Control-DB tenants — `tenant/acme`, `tenant/zeta` and `tenant/nova` appear in no
> fixture, launcher, compose file or config. Whoever writes the Gate-B provisioning is inventing the
> mapping fresh. Pin it, and adjudicate the `"acme"` vs `"tenant-acme"` spelling (both exist, for
> different purposes) **before** anything depends on it.

---

## 3. Sequence

```bash
python tests/control_plane/requires_pg/test_pg_clm_acme_dataplane_witness.py plan
```

Read-only. Reports configuration completeness, the precondition verdict, and the ACME physical
identity pair. Exits non-zero if the preconditions are not satisfied. **`plan` proves nothing about
the data plane — it only establishes whether a `run` could.**

```bash
python tests/control_plane/requires_pg/test_pg_clm_acme_dataplane_witness.py status
```

Read-only, fail-closed. Same preconditions, plus an explicit statement of what remains unproven. A
bare invocation with no subcommand resolves here, never to `run`.

```bash
python tests/control_plane/requires_pg/test_pg_clm_acme_dataplane_witness.py run --confirm-start-gate
```

**Gate-B M14.** Served `GET`, served `PATCH`, both isolation legs, restore, no-leak scan.

---

## 4. What `run` captures, and what each item is worth

**READ** — served `GET` `200` plus a body whose key set is **exactly** the served
`TenantStartupDetailDTO` contract field set (derived from the contract, not restated) and whose
`record_ref` echoes the reference the route addressed; **plus** an independent-connection `SELECT` of
the same row, **plus** `current_database()` and `system_identifier` of the connection that read it.

**WRITE** — served `PATCH` `200` plus the echoed new value; **plus** an independent-connection
`SELECT` confirming it; **plus** the ZETA table byte-identical and a row-count delta of **zero** on
both. Exactly one allow-listed content field is written: `short_description`, UTF-8, ≤ 500 chars.

**ISOLATION — two stages, and they prove different things:**

* **Auth stage.** A ZETA-claim token from an ACME-only principal ⇒ `(403, empty body)`, ZETA
  byte-identical. **Asserted, not merely printed.** **Scope caveat that must travel with the
  evidence:** this denial fires in the **Auth Router**, before any routing or tenant-DB contact. That
  is the correct fail-closed posture, but it proves **auth-stage** denial — **not** that the Database
  Router would have refused.
* **Router stage.** An unregistered-tenant carrier, producing the resolver's `not_found` path.
  Recorded under a separate label and **asserted separately**: the status must be one of
  `401 / 403 / 404` with an empty body. A `200` is an isolation breach and **fails the run**; a `503`
  is the upstream/audit-outage collapse and is **not** a denial, so it fails too. A complete isolation
  claim needs both stages, and both are mandatory — neither can be skipped.

**AUDIT** — with the durable sink enabled, exactly the durably-homed rows `tenant_startup_read`,
`tenant_startup_update` and `RouteDenied` in `control_gateway_audit`, with the `short_description`
**value absent from every cell**. Verifying that is a separate read of the Control database; it is
never inferred from the run.

**RESTORE** — a before==after digest of the ACME `startups` table, computed in `finally`. The digest
is the proof, not the `UPDATE`'s return code: an `UPDATE` that matched zero rows also returns without
error. Restoration is keyed on whether the served `PATCH` was **issued**, and the flag is set *before*
the request — a write that reached the database and then failed a later assertion is still restored.
A run that aborted before the write reports `PASS: RESTORE — vacuous`, because it wrote nothing; that
is not a second failure and must not be recorded as one.

**A missing value is not a missing row.** `short_description` is **nullable** — in the tenant DDL and
at the serving edge — so the positive control probes row **existence** separately (`SELECT 1`) and
reads the value afterwards. `POSITIVE CONTROL FAILED` therefore means the row is genuinely absent. A
present row whose `short_description` is `NULL` is a **lawful** fixture state: the run proceeds, and
the restore puts the `NULL` back.

---

## 5. Abort conditions

Stop, record, and do **not** improvise:

* any precondition unsatisfied — nothing collected can be data-plane evidence;
* the positive control failing — the `--startup-ref` row is **absent** from the ACME database (this is
  row absence, established by its own existence probe; a present row holding a lawful `NULL` does not
  abort the run);
* ACME and ZETA resolving to the same `(system_identifier, current_database())` pair — the topology is
  not physically separated and no isolation claim may be made from it;
* the served `GET` value disagreeing with the independent ACME read (**P-4**);
* the restore digest not matching;
* the no-leak scan finding anything.

### Two ambiguities that must not be resolved by guessing

**`503` is four-ways ambiguous** — dead tenant-Startup upstream, dead Auth Router, dead durable audit
sink, or an unhandled edge exception. Record which upstream was probed and its liveness at the moment
of the call; the harness captures that census up front.

**`404` is two-ways ambiguous** — bounded-matcher rejection pre-core vs a genuine unknown
`startup_ref`. Every `404` is paired with a positive control.

**Audit-coupled fail-closed:** with a durable sink selected, a sink outage turns a legitimate `200`
into a `503` and a legitimate `403` into a `503`. Evidence collected during a sink outage
misrepresents the data plane as broken.

---

## 6. Secret hygiene

The routing answer's `database_association_ref` is `{store_ref, version}` and is contract-declared
**non-secret**; the DSN **value** is structurally excluded (resolved in memory at connect time,
`repr`-suppressed). That is a property of the contract and the router, not something this witness
observes — the witness never sees a routing answer.

**What the witness actually does**, stated exactly:

* **`redacted()` strips CREDENTIALS, not topology.** It reduces a DSN to
  `scheme://host:port/database` — userinfo and any query string are dropped, so no username, no
  password and no connection parameter is ever emitted. The **database name is part of what it
  keeps**, and `plan` prints one such line for the ACME connection. That is deliberate: `plan` is
  read-only and operator-local, and the physical name is what tells the operator they are pointed at
  the right cluster. Note the pairing on the two adjacent `plan` lines — the identity-pair line
  prints `database=<redacted>` while the connection line prints the redacted DSN including the
  database. Treat `plan` output as operator-local: do not paste it into a shared terminal, a ticket,
  or the evidence record.
* **Captured artifacts are held to the stricter rule**, and that is where the no-leak scan applies.
  It runs over the **four in-memory artifacts** (`served_get`, `served_patch`,
  `isolation_auth_stage`, `isolation_router_stage`) and fails the run on: the resolved ACME or ZETA
  DSN verbatim, either DSN's password substring, **both** bearer tokens, **each physical database
  name**, and the shape census.
* **The shape census has two tiers, matching the serving edge.** Reference/topology/status text is
  scanned for `://`, `eyJ`, `-----BEGIN`, `AKIA`, `ghp_`, `xox`, `password=`, `PGPASSWORD`. The one
  bounded free-text field, `short_description`, is scanned for the same set **minus `://`**, plus a
  credential-bearing-URI pattern (`scheme://user:secret@host`). This mirrors
  `_REF_SECRET_SHAPES` / `_TEXT_SECRET_SHAPES` in
  `database_router/adapters/providers/http_tenant_startup_api.py`, which states the rule directly:
  `://` is lawful inside business free text, a credential or key block never is. **A fixture whose
  `short_description` contains a URL is therefore lawful and will not fail the run**; a token, PEM
  block or credential DSN in that same field still will. The verbatim-secret, password-substring and
  database-name scans are **not** partitioned — they run over the whole artifact either way.

**What it does not do:** it does not read, scan, or open the evidence markdown; it does not inspect
`store_ref` (that field never reaches this process); and a bare `@` is **not** a shape in either tier
— the credential-URI pattern keys on `user:secret@` *inside a URI*, so an email address in free text
stays lawful. Scanning the completed evidence record is an **operator** step — see §10 of the
template.

Record results in `docs/infrastructure/clm_dataplane_evidence_template.md`.

### 6.1 The Control-DB routing cross-read — NOT performed here

The witness opens **no** connection to the Control database.
`SNACKPORTAL_SECRET_CONTROL_CONTROL_STORE_DSN_V1` is reported by `plan` for **presence only**.

Confirming that the routing row the Gateway resolved came from the **durable** Control store — rather
than an in-memory one seeded to look the same — is a **separate Gate-B read**, performed and recorded
by the operator. `D-2` above is a declaration about the witness's own shell and does not establish
it. Do not write, in this runbook, in the template, or in any report, that the witness cross-read the
Control database.

---

## 7. No overclaim

A green `run` proves the ACME tenant data plane for **one** startup record, on the **local**
non-production topology, at one point in time. It does not close any B5 blocker, does not activate
production, does not prove NOVA (which no tier connects to), and does not make IC-012 Final.

---

## 8. Gate-B-readiness items — recorded here, deliberately NOT fixed

Two known gaps predate this harness's corrections and are **carried forward unresolved**. Neither
produces a false PASS; both bear on how the Gate-B evidence must be read, so they are recorded rather
than left in a review document.

**GBR-1 — the "ROUTER STAGE" leg does not reach the Database Router.** The leg sends the ACME bearer
with `X-Tenant-Id: tenant-that-does-not-exist`. That is resolved as `carrier_mismatch` in the **Auth
Router** path (`api_gateway/adapters/providers/http_authenticator.py:122-123`,
`api_gateway/gateway.py:200`) — i.e. **pre-routing**, the same stage as the auth-stage leg. The
denial is real and is correctly asserted, but the *label* over-reaches: **the claim that the Database
Router itself would have refused remains UNPROVEN by this harness.** Do not write, in a completed
record, that router-stage isolation was demonstrated. Closing this needs a leg that reaches the
resolver — a scope decision for the Gate-B session, not a wording change here.

**GBR-2 — the expected audit-action inventory omits `CarrierMismatch`.** `EXPECTED_AUDIT_ACTIONS` in
the harness lists `tenant_startup_read`, `tenant_startup_update` and `RouteDenied`. D-43 durably homes
a fourth class, `CarrierMismatch`
(`control_plane/adapters/providers/http_gateway_audit_api.py:117`), and it is what the GBR-1 leg
actually emits. The harness only *advises* the operator's separate Control-DB read, so the consequence
is an **incomplete expected set**, not a failed check — but an operator who reads that list as
exhaustive will under-count. §9 of the evidence template already carries the `CarrierMismatch` row;
use the template, not the harness printout, as the inventory.
