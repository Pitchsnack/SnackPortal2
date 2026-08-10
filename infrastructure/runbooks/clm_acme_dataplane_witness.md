# CLM ACME tenant data-plane witness (operator runbook)

> ## ⛔ WITHDRAWN — the API Gateway has been DELETED
>
> The CLM ACME dataplane witness (`tests/control_plane/requires_pg/test_pg_clm_acme_dataplane_witness.py`) and its 38-test boundary guard were DELETED: the witness drove `Gateway 8820 -> Tenant Startup 8004 -> Database Router -> one tenant database`, and BOTH of those processes were deleted. **There is currently no live tenant-data-plane proof for the Gateway-free topology.**
>
> Nothing in this document may be run, and no evidence produced by it before the removal may be
> cited as current. It is retained because the recorded scenario, its ordering rules and its
> evidence format are what a Gateway-free successor must reproduce.

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
| `SNACKPORTAL_SECRET_CONTROL_CONTROL_STORE_DSN_V1` | the denial-reason read | **presence-reported by `plan`; REQUIRED by `run`.** On a **read-only** connection `run` issues ONE correlation-filtered business-data read of `control_gateway_audit`, plus the `pg_control_system()` / `current_database()` **metadata** pair — and no routing cross-read. See §6.1 |
| `SP2_CLM_WITNESS_BEARER` | the served legs | **required by `run`.** Operator-local, never committed, never printed, never echoed into a shared terminal |
| `SP2_CLM_WITNESS_ZETA_CLAIM_BEARER` | the auth-stage isolation leg | **required by `run`** — a token whose signed tenant claim is **`zeta`**, for a principal that holds **no ZETA membership**. Not optional: a run that skipped this leg and still exited 0 would file an incomplete record as a complete one. A bearer that produces `carrier_mismatch` or `tenant_context_required` instead **fails** the E48 claim rather than passing as it — and so does the correct bearer, because E48 is currently **unprovable from the durable record**: see §4 and **GBR-4** |

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

> **What a current run actually reaches.** That is the intended sequence, not the one this runtime
> executes. `cmd_run` fails by construction at the **auth-stage E48 assertion** — E48 resolves to
> `NOT AVAILABLE / UNPROVEN` while **GBR-4** is unresolved — and the second isolation leg is sequenced
> *after* that assertion, so it is **not reached**. The `finally` restore and no-leak scan still run
> and still report; the run exits non-zero. See §4, §6.1 and GBR-4.

---

## 4. What `run` captures, and what each item is worth

**READ** — served `GET` `200` plus a body whose key set is **exactly** the served
`TenantStartupDetailDTO` contract field set (derived from the contract, not restated) and whose
`record_ref` echoes the reference the route addressed; **plus** an independent-connection `SELECT` of
the same row, **plus** `current_database()` and `system_identifier` of the connection that read it.

**WRITE** — served `PATCH` `200` plus the echoed new value; **plus** an independent-connection
`SELECT` confirming it; **plus** the ZETA table byte-identical and a row-count delta of **zero** on
both. Exactly one allow-listed content field is written: `short_description`, UTF-8, ≤ 500 chars.

**ISOLATION — two intended legs, recorded separately. Both are pre-routing; neither is a router-stage
proof.**

A `403` with an empty body **names no reason**. **Four** different upstream outcomes render exactly
that — `carrier_mismatch`, `tenant_context_required`, `tenant_access_denied` and `tenant_not_ready` —
so every denial leg mints its **own correlation id**, sends it as `X-Correlation-Id`, and reads the
**durable operational-audit record** for that request back out of `control_gateway_audit`. The reason
is **observed**, never assumed.

* **Auth stage — E48, and it is currently UNPROVABLE here.** A ZETA-claim token from an ACME-only
  principal gives `(403, empty body)`, ZETA byte-identical, and a durable `RouteDenied` record
  carrying **no actor, tenant or carrier reference** — which the Gateway emits from the
  authenticator-rejection branch, before any `AuthContext` exists (`api_gateway/gateway.py:199-211`).
  **That row is not sufficient.** `tenant_not_ready` — a principal who *is* a member of a
  known-but-not-Ready tenant (`auth_router/tenant_context.py:47`) — produces the **byte-identical**
  row: `auth_router/models.py:96-97` gives `not_ready()` the same `403`,
  `http_authenticate_api.py:123-124` collapses every non-carrier-mismatch `403` to `forbidden`
  ("granular reasons … never leak past the status bucket"), and
  `http_authenticator.py:119-124` repeats the collapse. Only one of those two is authorization
  denial. The harness therefore classifies a no-reference `RouteDenied` row as an
  **AMBIGUOUS PRE-AUTH DENIAL** and reports **`E48 NOT AVAILABLE / UNPROVEN`** — it does **not**
  guess the convenient one. A record showing `tenant_context_required` (a `RouteDenied` row that
  *does* carry an actor reference, `gateway.py:237`) or `carrier_mismatch` (a `CarrierMismatch` row,
  `gateway.py:200-207`) fails the claim outright, and so does a missing record. **This leg will fail
  a Gate-B run by construction until GBR-4 is resolved — that is the honest outcome, not a harness
  defect.** **Scope caveat that must travel with the evidence:** this denial fires in the **Auth
  Router**, before any routing or tenant-DB contact. It would prove **auth-stage** denial — **not**
  that the Database Router would have refused.
* **Unregistered-tenant carrier.** The ACME bearer with `X-Tenant-Id: tenant-that-does-not-exist`.
  Recorded under a separate label and **asserted separately**: the status must be one of
  `401 / 403 / 404` with an empty body. A `200` is an isolation breach and **fails the run**; a `503`
  is the upstream/audit-outage collapse and is **not** a denial, so it fails too. The durable denial
  reason is recorded for this leg as well, **observed and not asserted** — any of the three is a
  legitimate outcome here. **This leg was formerly labelled "router stage"; it is not one.** It is
  resolved pre-routing in the Auth Router path (GBR-1). Both legs are mandatory — neither can be
  skipped — but a complete isolation record still leaves router-stage denial **UNPROVEN**.
  **And this leg is NOT REACHED on a current run.** It is sequenced *after* the auth-stage E48
  assertion, which fails by construction, so `cmd_run` aborts before it is issued. The requirement is
  unchanged — both legs remain mandatory and neither may be dropped — but **while GBR-4 remains
  unresolved the harness cannot execute this leg, and therefore cannot produce a complete two-leg
  isolation record at all.** Do not read the mandate as a description of what a run currently
  collects. See §6.1 and GBR-4.

**AUDIT** — with the durable sink enabled, the durably-homed rows `tenant_startup_read`,
`tenant_startup_update`, `RouteDenied` and `CarrierMismatch` in `control_gateway_audit`, with the
`short_description` **value absent from every cell**. Verifying the SUCCESS rows and the value-absence
is a separate operator read of the Control database and is never inferred from the run. The **denial**
rows are the exception, and only for a denial leg the run actually reaches: for such a leg the witness
reads exactly that leg's row, by that leg's own correlation id, as booleans (see §6.1).
**While GBR-4 is unresolved, `cmd_run` reaches the auth-stage (E48) leg only**, so current execution
produces the first-leg denial read and no other. The second leg is not dropped — it **remains
mandatory** for a complete Gate-B isolation record — but it is **not reached**, so current execution
**cannot produce the final two-leg evidence record at all**, and a one-leg record is
**INCOMPLETE / NOT ACCEPTABLE AS FINAL ISOLATION EVIDENCE**.

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
  `isolation_auth_stage`, `isolation_unregistered_carrier`) and fails the run on: the resolved ACME,
  ZETA **or Control** DSN verbatim, any of those DSNs' password substring, **both** bearer tokens,
  **each physical database name** (Control included), and the shape census.
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

### 6.1 The Control-DB reads — one bounded business read, plus metadata — and the routing cross-read, which is still NOT performed here

`SNACKPORTAL_SECRET_CONTROL_CONTROL_STORE_DSN_V1` is reported by `plan` for **presence only** and is
**required by `run`**. `run` opens a Control connection with `read_only = True` set at the
**connection level**, and executes exactly two kinds of statement on it.

**(a) One bounded business-data read** — `read_denial_audit`, the only statement that reads a row of
any Control table:

```sql
SELECT action, outcome, actor_ref IS NOT NULL, tenant_ref IS NOT NULL, carrier_ref IS NOT NULL
  FROM control_gateway_audit WHERE correlation_id = %s ORDER BY id
```

filtered to a correlation id **the witness minted for its own request**, reading the reference
columns as **booleans** so no actor, tenant or carrier reference value ever enters the process. One
such read is issued **per denial leg**, each against that leg's own correlation id.

**How many legs a run actually reaches — and it is not both.** `cmd_run` executes the **auth-stage
(E48) leg first**: it issues the ZETA-claim request, reads that leg's denial record, and then asserts
`not e48_problems(...)`. On the current runtime that predicate can never return empty —
`tenant_access_denied` and `tenant_not_ready` produce a byte-identical durable row and
`RECOGNISED_UNIQUE_DENIAL_SIGNALS` is empty — so E48 resolves to **`NOT AVAILABLE / UNPROVEN`** and
**`cmd_run` fails at that assertion**. The second (unregistered-tenant carrier) isolation leg is
sequenced *after* that assertion, so **the second isolation leg is NOT REACHED while GBR-4 remains
unresolved**, and a current `run` issues this bounded Control business read **exactly once** — for
the auth-stage leg only. **Once GBR-4 is resolved in a way that lets the auth-stage leg pass**,
execution continues past that assertion, the second leg becomes reachable, and the Control audit read
is issued for that leg too, against its own correlation id. The statement itself is unchanged either
way; what changes is how many times a run reaches it. Do not read the per-leg rule as a per-run
count on this runtime.

**(b) Two physical-identity metadata statements** — `SELECT system_identifier FROM
pg_control_system()` and `SELECT current_database()`, issued by `physical_identity` on the same
connection. They read **no table and no business row**; they exist because the no-leak census must
bar the Control database's physical name, and it cannot bar a name it has not observed. Earlier
versions of this section called (a) the witness's *only* Control-database read; that was wrong, and
the distinction is now stated rather than glossed.

That is the whole of the witness's Control mandate, and the static guard bounds it by **allow-list,
not by banned table names**: the business statement is pinned verbatim, any statement touching any
governed Control table (including inside a CTE or a join) other than that one fails, the only write
permitted anywhere in the harness is the tenant-DB restore, `cmd_run`'s `control.read_only = True` is
pinned as an assignment, and the two metadata statements are named as metadata. Without (a) the E48
claim would be unfalsifiable — which is exactly the defect (RB-3) this replaced.

**The routing cross-read is still NOT performed.** The witness never sees a routing answer, never
reads `control_tenants`, and makes no claim about which store served the routing view. Confirming
that the routing row the Gateway resolved came from the **durable** Control store — rather than an
in-memory one seeded to look the same — is a **separate Gate-B read**, performed and recorded by the
operator. `D-2` above is a declaration about the witness's own shell and does not establish it. Do
not write, in this runbook, in the template, or in any report, that the witness cross-read the
routing row.

---

## 7. No overclaim

A green `run` proves the ACME tenant data plane for **one** startup record, on the **local**
non-production topology, at one point in time. It does not close any B5 blocker, does not activate
production, does not prove NOVA (which no tier connects to), and does not make IC-012 Final.

---

## 8. Gate-B-readiness items

**GBR-1 — the second isolation leg does not reach the Database Router. OPEN; the overclaiming label
is REMOVED.** The leg sends the ACME bearer with `X-Tenant-Id: tenant-that-does-not-exist`. That is
resolved as `carrier_mismatch` in the **Auth Router** path
(`api_gateway/adapters/providers/http_authenticator.py:122-123`, `api_gateway/gateway.py:200`) —
i.e. **pre-routing**, the same stage as the auth-stage leg. The denial is real and is correctly
asserted. What has changed: the harness no longer *calls* it router-stage. The artifact key is
`isolation_unregistered_carrier`, the printed label is `ISOLATION (UNREGISTERED-TENANT CARRIER)`, the
run output states that router-stage isolation "remains UNPROVEN by this harness", and the leg's
durable denial reason is now **observed and recorded** rather than assumed. Do not write, in a
completed record, that router-stage isolation was demonstrated. **The underlying gap is unchanged and
still open:** closing it needs a leg that reaches the resolver — a scope decision for the Gate-B
session.

**GBR-2 — `CarrierMismatch` is now represented. CLOSED.** `EXPECTED_AUDIT_ACTIONS` in the harness
lists `tenant_startup_read`, `tenant_startup_update`, `RouteDenied` **and `CarrierMismatch`** — the
fourth class D-43 durably homes (`control_plane/adapters/providers/http_gateway_audit_api.py:117`),
and the one the unregistered-tenant carrier leg actually emits. The harness printout and §9 of the
evidence template now agree, so an operator reconciling their separate Control-DB read against either
one no longer under-counts. Durable coverage is the **five** `_CLM_DURABLE_ACTIONS` classes; the
fifth, `workspace_memberships_read`, belongs to a different journey and is deliberately absent from
this inventory.

**GBR-3 — E48 requires the durable denial record, and says so when it cannot get it.** The ZETA leg
no longer asserts `403` + empty body alone. It correlates the denial with `control_gateway_audit` and
accepts **only** `tenant_access_denied`. If the durable sink is not enabled, if the record did not
persist, or if the local IdP cannot issue a bearer that exercises genuine ZETA non-membership denial,
the harness reports the reason as **`NOT AVAILABLE / UNPROVEN`** and **fails the leg**. Recording E48
as satisfied on any other basis is unsupported by this harness.

**GBR-4 — `tenant_access_denied` and `tenant_not_ready` are indistinguishable in the durable record,
so E48 is UNPROVABLE here. OPEN — and it needs a decision, not a harness change.** GBR-3 narrowed the
denial reasons from four to three; this is the pair it could not separate. A principal who holds a
membership for a known-but-**not-Ready** tenant is refused by `auth_router/tenant_context.py:47`
(`not_ready`), which is **not** an authorization denial. `auth_router/models.py:96-97` gives it the
same `403`; `http_authenticate_api.py:123-124` collapses every non-carrier-mismatch `403` to the one
public code `forbidden` — its docstring states that granular reasons "never leak past the status
bucket" — and `http_authenticator.py:119-124` repeats the collapse Gateway-side. By the time
`gateway.py:199-211` writes the audit event, both cases are the same row: `RouteDenied`, `rejected`,
actor/tenant/carrier all NULL.

This is **reachable here, not theoretical**: the standing local fixture deliberately provisions a
dormant tenant so that `tenant_not_ready` can be observed
(`infrastructure/runbooks/b5_standing_auth_fixture.md`).

The harness therefore classifies that row as **`AMBIGUOUS PRE-AUTH DENIAL (tenant_access_denied OR
tenant_not_ready)`** and reports **`E48 NOT AVAILABLE / UNPROVEN`**. Its
`RECOGNISED_UNIQUE_DENIAL_SIGNALS` set — the authoritative signals that would uniquely prove
`tenant_access_denied` — is **empty**, and a static guard asserts it stays empty until such a signal
genuinely exists.

**The consequence that must travel with GBR-4: it does not stop at the E48 verdict.** The E48
assertion is sequenced *before* the second isolation leg in `cmd_run`, so failing it aborts the run
there. **The second isolation leg is NOT REACHED while GBR-4 remains unresolved**, the bounded
Control audit read is therefore issued for one leg only, and **the complete two-leg isolation record
the evidence template mandates is currently unproducible.** That mandate is not weakened by this —
both legs remain required for final acceptance, and a one-leg record is **INCOMPLETE / NOT ACCEPTABLE
AS FINAL ISOLATION EVIDENCE**. It means the record cannot be completed at all until GBR-4 is
resolved. Neither E48 nor full isolation evidence may be marked PASS before that.

**Closing it is one of three things, and all three are outside this harness:**

1. a **production** change that makes the two reasons distinguishable in the durable record (a
   distinct audit action, a distinct public code, or a distinct status) — a governed IC-005 / IC-010
   change, not a witness edit;
2. **Dan narrows Gate B** — E48 and the ZETA legs marked out of scope, in writing;
3. **Dan accepts a labelled substitute artifact** — in writing, and explicitly labelled as a
   substitute, never recorded as E48.

Until one of those, **do not record E48 as satisfied**, and do not "resolve" the ambiguity by
pointing the leg at a tenant chosen to make the answer come out right. **The ZETA-scope decision
remains OPEN for Dan** — it was open before this correction and nothing here closes it; GBR-4 is a
second, independent reason the same decision is needed.
