# AW-1 — least-privilege Gateway operational-audit writer (operator runbook)

**Scope:** NON-PRODUCTION / documentation only. This runbook governs the identity the Gateway-audit
ingest edge writes durable audit rows as, and the environment that process is allowed to hold.

> **Gate status.** The tooling, this runbook, the byte-pin guard and the Tier-A rehearsal are **Gate-A
> deliverables — repository only**. Creating the roles, minting the password, binding the credential
> and writing the local DSN material are **Gate-B (class M2)** acts and are authorized only when the
> frozen mutation inventory names all three credential actions explicitly (AW-1 U-3). If any is
> unnamed, those actions are **not authorized** and `apply` must not be run.
>
> **Production: NOT READY / DO-NOT-ACTIVATE.**

---

## 1. The problem this exists to solve

`build_gateway_audit_store_from_env` is **durable by construction**: it has no in-memory branch and
never consults `SP2_CP_CONTROL_STORE`. With no reference set it binds the **DEFAULT** ref
`control/control-store-dsn`, which by standing convention resolves to the **`sp2_local` superuser**
DSN. Because the standing topology's operator shell routinely exports superuser material, an ingest
edge started without an explicitly scoped environment does not merely *risk* writing as a superuser —
it does so by default, silently.

AW-1 replaces that with two roles:

| Role | Kind | Holds |
|---|---|---|
| `sp2_gateway_audit_writer` | **NOLOGIN** grant role | the entire privilege surface: `CONNECT` on the Control DB, `USAGE` on `public`, and `SELECT, INSERT` on `public.control_gateway_audit` — **nothing else, anywhere** |
| `sp2_gateway_audit_ingest` | **LOGIN** identity | membership in the writer, and a credential. No direct grants of its own. |

`SELECT` is load-bearing, not convenience: the adapter's `INSERT … ON CONFLICT DO NOTHING RETURNING`
falls through to a keyed `SELECT` to compare an exact replay. Without `SELECT`, every legitimate
replay collapses to `503` and the *first* insert's `RETURNING` fails too.

---

## 2. Tooling

`backend/tests/control_plane/requires_pg/aw1_gateway_audit_writer.py`, run from `backend/`:

| Command | Gate | What it does |
|---|---|---|
| `plan` | **safe before Gate B** | READ-ONLY. Observes role/attribute/membership/ACL/comment state and the Tier-B environment preconditions, classifies `MATCHING` / `MISSING` / `CONFLICTING`, exits non-zero on `CONFLICTING`. Also reports **material-sink readiness** so an operator learns before Gate B whether `apply` would refuse. Never binds, never mints, never executes the payload, never writes material, and writes nothing to the filesystem at all. |
| `apply` | **Gate B only** | Refuses without `--confirm-gate-b-m2`. Asserts the database pin, executes the byte-frozen payload in one transaction, performs the statement-logging observation, then takes exactly one credential-convergence branch. A **mutating** branch performs all four steps in the governed order — mint, bind, **write the material**, **re-probe** — and proves the sink writable *before* minting. |
| `status` | **safe any time** | READ-ONLY, fail-closed, fixed declared pass count. **This is the ingest edge's start gate.** |

The role/grant SQL is **embedded byte-for-byte** in that module and pinned by
`backend/tests/architecture/test_aw1_gateway_audit_writer_boundaries.py`. It is deliberately **not**
an `infrastructure/db/**/*.sql` file: as a file it would break the closed 15-file Control-DDL
inventory guard *and* force a PMA-AR-2 role-security family whose INV-A is structurally bound to
on-disk SQL.

---

## 3. Ordering — the start gate is not optional

```text
O-1  Gate A merges the tooling, byte-pin guard, Tier-A harness, this runbook, the launcher
        ↓
O-2  First `plan` (read-only): 012 table shape present; BOTH 013 triggers present AND ENABLED
        ↓
O-3  Backup + disposable test restore proven; the Tier-A privilege rehearsal runs on
     DISPOSABLE infrastructure (CREATE ROLE is cluster-scoped — never the standing cluster)
        ↓
O-4  Gate B granted, with the three credential actions named in the frozen inventory
        ↓
O-5  `apply --confirm-gate-b-m2` on the pinned database
        ↓
O-6  `status` must report OK — read-only, fixed pass count
        ↓
O-7  the Gateway-audit ingest process starts (the FIRST process ever able to write as the writer)
        ↓
O-8  SP2_GW_AUDIT_SINK_BASE_URL is set on the API Gateway; the durable pipeline goes live
        ↓
O-9  post-activation verification: one journey event → one durable row; connected-identity proof;
     historical-row integrity re-check
```

**O-6 → O-7 is enforced, not advisory.** `backend/tools/local/start-sp2-local.ps1` runs `status` and
**refuses to start the ingest edge** on a non-zero exit. Starting anyway is precisely how an
ungoverned identity ends up writing durable audit rows.

---

## 4. The ingest process environment contract

The ingest edge is the **only** process that may hold the writer credential. Its environment is a
whitelist, not a filter.

| Rule | Why |
|---|---|
| `SP2_CP_CONTROL_STORE_DSN_REF=control/gateway-audit-writer-dsn` | Selects the writer's reference. **Zero code change** — the merged seam already parameterizes it. |
| Exactly ONE `SNACKPORTAL_SECRET_*` variable: `SNACKPORTAL_SECRET_CONTROL_GATEWAY_AUDIT_WRITER_DSN_V1` | Every other secret variable must be absent — **explicitly including** `SNACKPORTAL_SECRET_CONTROL_CONTROL_STORE_DSN_V1` and `SNACKPORTAL_SECRET_CONTROL_PROVISIONING_ADMIN_DSN_V1`, the two superuser materials. |
| **No `SNACKPORTAL_SECRET_DIR`** | The resolver has a *second* source: a file named `<dir>/control/control-store-dsn@1`. Excluding the env var alone leaves that path open. |
| **No libpq `PG*` variable of any kind** | `PGHOST`, `PGHOSTADDR`, `PGPORT`, `PGUSER`, `PGPASSWORD`, `PGPASSFILE`, `PGSERVICE`, `PGSERVICEFILE`, `PGDATABASE`, `PGOPTIONS`, `PGAPPNAME`, `PGSSL*`. See the blank-material hazard below. |
| No operative `~/.pgpass` / `pg_service.conf` for the ingest OS user | Same reason. |

The governed launcher implements this whitelist by scrubbing `SNACKPORTAL_SECRET_*`,
`SNACKPORTAL_TENANT_SECRET*` and `PG*` from the ingest window and keeping only the writer's own
variable. `Start-Process -UseNewEnvironment` — the textbook mechanism — is **not** used: on Windows
PowerShell 5.1.19041 it fails the child outright with *"Internal Windows PowerShell error. Loading
managed Windows PowerShell failed with error 8009001d"*. Explicit enumerated scrubbing is used
instead, and unlike `-UseNewEnvironment` it is visible in the file and machine-checkable.

### 4.1 Two silent-fallback hazards, and what closes each

**Blank material.** `psycopg.connect("")` does not fail — it falls back to **libpq connection
defaults**: the `PG*` environment variables, then `localhost:5432`, the OS user's name as the role,
and a `~/.pgpass` lookup. A set-but-empty credential variable therefore connects *somewhere*, chosen
by nobody. Closed by (a) the launcher refusing to start the ingest edge when the **selected** writer
material variable is unset, empty, **or whitespace-only after stripping** — implemented in
`backend/tools/local/start-sp2-local.ps1` inside the `-EnableDurableGatewayAudit` block, before that
edge starts, presence-only, and pinned by
`backend/tests/architecture/test_standing_launcher_flags.py::test_blank_writer_material_refuses_before_the_ingest_edge_starts`
— and (b) the `PG*` exclusion above. The check reads the variable **named by the launcher's own
`-GatewayAuditWriterSecretVar` parameter**, so it is always aimed at the variable the ingest window
actually keeps, and it tests blankness in place: the value is never captured, printed, or relayed.

**Lost or mis-set reference.** An unset **or set-empty** `SP2_CP_CONTROL_STORE_DSN_REF` falls to the
DEFAULT ref — the superuser DSN. (Only a *whitespace-only* value raises.) Closed by the environment
whitelist above: with both resolver sources shut, a lost reference resolves to `LookupError` → `503`.
That is **fail-closed, not fallback**. The independent detector is the connected-identity proof: the
ingest session must show `usename = 'sp2_gateway_audit_ingest'` **and**
`application_name = 'sp2-gateway-audit-ingest'`.

---

## 5. The credential

**References and names only, in every tracked file.**

| Element | Value |
|---|---|
| Secret reference | `control/gateway-audit-writer-dsn`, version `1` — a **NEW** ref. `control/control-store-dsn` is **never** reused. |
| Derived variable **name** | `SNACKPORTAL_SECRET_CONTROL_GATEWAY_AUDIT_WRITER_DSN_V1` |
| Form — **runtime** | **Env-var form**, in the ingest process only. Adopting the file form for the *ingest* process additionally requires closing the directory source (see §5.2); do that only deliberately. |
| Form — **`apply`'s sink** | **File form**, `$SNACKPORTAL_SECRET_DIR/control/gateway-audit-writer-dsn@1`. A child process cannot write its parent shell's environment, so the file form is the only mechanism through which `apply` can discharge §5.5's mandatory material write. The path is composed exactly as `EnvReferenceSecretStore.resolve` composes it, and is proven to resolve **outside every repository worktree** before anything is written. |
| DSN shape | `postgresql://sp2_gateway_audit_ingest:<password>@127.0.0.1:5540/snackportal2_control_local?application_name=sp2-gateway-audit-ingest` |
| Mandatory | `application_name=sp2-gateway-audit-ingest`, **byte-pinned**. It is the executable half of the connected-identity proof: the control cluster is a Docker container publishing `127.0.0.1:5540→5432`, so `client_addr`/`client_port` record the compose gateway and an ephemeral proxy port and can never identify the host process. Without `application_name` the session is unidentifiable. |
| Forbidden | Any libpq **`options`** keyword. Both adapter statements use the bare table name, so `public` resolution rests on the default `search_path`, and `options=-c search_path=…` is a documented, test-exercised mechanism for this DSN class. |
| Rotation | Separately governed. The bounded recovery re-bind is **M2 recovery**, explicitly *not* rotation. The seam hardcodes `version="1"`, so version-addressed rotation is unavailable without a governed code change. |

`plan`, `apply` and `status` never **print, log, hash or return** the material, and no agent reads it
out or transcribes it. `apply` **does write it** — that is not an oversight, it is the only way the
credential can exist: the password is generated inside the applying process and exists nowhere else,
so a tool that binds it without persisting it destroys it. See §5.2.

### 5.1 Which evidence label the first apply produces

| Situation | Label |
|---|---|
| First-ever apply — the roles did not exist before this run | **`M2 INITIAL CREATION`** |
| Roles already `MATCHING`, but material absent or not authenticating (a partial-crash recovery) | `M2 RECOVERY` |
| Material present and authenticating exactly as the ingest role, state `MATCHING` | `NO_CHANGES` — the bind and the material rewrite are **skipped** |
| Anything else | `CONFLICTING` → STOP |

The first row matters. On a first-ever apply every *recovery* precondition also holds — material
absent, role/grant state converged by the payload that just ran, bind not done — so an implementation
without an explicit initial-creation branch records the very first credential creation as recovery
from a crash that never occurred, and every downstream evidence pack inherits that falsehood.

**Why the converged branch must skip.** Re-binding even an *identical* password re-salts the SCRAM
verifier and mutates `pg_authid.rolpassword`. That is a real delta and a de-facto rotation.

---
### 5.2 The material sink — why `apply` writes it, and what it refuses

**The rule.** In a mutating branch `apply` performs four steps, in this order, and all four are
mandatory:

1. **mint** one password (RFC 3986 *unreserved* alphabet, so the composed DSN is always parseable);
2. **bind** it client-side (`psycopg.sql.Literal`), after the §6 statement-logging observation;
3. **write the material** to the governed file-form sink, atomically and in place (same ref, same
   version, same path);
4. **re-probe** — re-resolve the material through the *same* mechanism the runtime uses and require
   authentication **exactly** as `sp2_gateway_audit_ingest`.

**Why steps 3–4 cannot be left to the operator.** The minted password is never printed and never
returned, so after step 2 nobody — operator included — can construct the DSN. Skipping step 3 leaves
the role holding a credential that existed only in a process that has exited: the converged branch
becomes permanently unreachable, every later `apply` mints another unknowable password, `status` can
never report OK, and the §3 O-6 → O-7 start gate can therefore never open. Escaping that requires a
superuser `ALTER ROLE` outside this procedure — the class of act AW-1 exists to eliminate.

**What `apply` refuses, before minting anything (zero statements executed):**

| Refusal | Why |
|---|---|
| `SNACKPORTAL_SECRET_DIR` unset or blank | The sink has no location. `apply` will not mint a password it cannot persist. |
| `SNACKPORTAL_SECRET_CONTROL_GATEWAY_AUDIT_WRITER_DSN_V1` **set** in the `apply` shell | A child process cannot replace its parent shell's variable in place, which is what bounded recovery requires — and the env form **shadows** the file form in the resolver *even when blank*, so writing the file would leave the runtime reading the old value. Unset it in this shell, re-run, then reload the material from the governed file. |
| The sink resolves **inside** a repository worktree | An operator-local credential written into a repository is one `git add -A` from a committed secret. |
| The sink directory is not writable | Same reason as the first row. |
| Host auth includes `trust` | No credential probe can discriminate, so neither the converged decision nor the required re-probe would be decisive. |

**After a successful mutating run**, the operator loads the ingest process's env-var form from that
file. The next `apply` then resolves the material — by either form — probes it, and reports
`NO_CHANGES`. **A successful run that cannot converge on the next run is a defect, not a posture.**

**Ingest-process caveat (unchanged).** §4's whitelist still forbids `SNACKPORTAL_SECRET_DIR` in the
*ingest* process. The sink directory belongs to the *operator's* shell. If the file form is ever
adopted for the ingest process itself, the launcher must first verify that the governed directory
contains no file other than `control/gateway-audit-writer-dsn@1`.


## 6. Before any bind: the statement-logging observation

PostgreSQL performs **no password redaction in statement logging**. Immediately before the bind, in
the same session, `apply` records `log_statement`, `log_min_duration_statement`,
`log_min_error_statement` and the sampling GUCs.

**The bind is refused** if `log_statement ∈ {ddl, mod, all}`, if `log_min_duration_statement ≥ 0`, or
if any sampling GUC is active. Remediation is a server configuration change and is outside AW-1's
scope.

**Accepted residual.** `log_min_error_statement = 'error'` is the PostgreSQL default and is *not*
treated as blocking — so a **failing** bind is written to the server log in full. The bind runs only
after the role is proven to exist in the same apply, which bounds the likelihood; the environment is
controlled non-production with an operator-local log. The observation is also point-in-time: a GUC
changed afterwards is not detected, and the statement is transiently visible in
`pg_stat_activity.query`. Bounded, not eliminated.

---

## 7. Verification

**Tier A — disposable rehearsal (before Gate B).**
`python tests/control_plane/requires_pg/test_pg_aw1_gateway_audit_writer_rehearsal.py`

Requires `SNACKPORTAL_TEST_DSN` pointing at a **disposable** instance — never the standing Control
database, and never the standing cluster: `CREATE ROLE` is cluster-scoped, so the rehearsal roles
land wherever the rehearsal runs. The harness creates the database name `snackportal2_control_local`
exactly (asserted absent first) so the frozen payload executes verbatim, applies control DDL 001–009
then blob-pinned 012 then 013, proves the positive and negative surface, and drops everything in
`finally` in the order **database → ingest role → writer role** (a role still referenced by any ACL
cannot be dropped).

**Every denial assertion pins SQLSTATE `42501`.** A refusal with any other SQLSTATE is a FAILURE.
Without the 001–009 content, every unrelated-table probe would raise `undefined_table` (42P01) and
pass for the wrong reason.

**Tier B — standing pre-activation (read-only).** `plan` and `status` cover it: catalog privilege
probes for the login role, the complete role-state census, ACL enumeration, both 013 triggers present
and enabled, the control-cluster tenant-database census, the historical-row baseline, and the
statement-logging observation. **No tier inserts a synthetic row into the standing table** — the
first real journey event is the positive INSERT proof.

**Tier C — post-activation.** `status` re-asserted with its fixed pass count; the connected-identity
proof; one real journey event producing exactly one durable row; and the historical-row fingerprint
recomputed **byte-identically** to prove the pre-existing rows are unchanged in every column.

---

## 8. Rollback — and the trap in the cheapest option

Every rollback action is governed; none is improvised.

> ⚠️ **`ALTER ROLE sp2_gateway_audit_ingest NOLOGIN` is the cheapest way to disable the writer, and it
> creates exactly the state the specification declares `CONFLICTING`.** The pinned attribute vector
> for the ingest role requires `rolcanlogin = true`; a pre-existing role with `rolcanlogin = false` is
> a finding to be **adjudicated**, not a state to be silently corrected — which is also why the frozen
> payload's ingest `ALTER ROLE` deliberately does **not** re-assert `LOGIN`. If you disable the role
> this way, record it, because the next `plan` will correctly refuse to proceed and the reason will
> not be obvious.

Preferred disable path: unset `SP2_GW_AUDIT_SINK_BASE_URL` so the next Gateway composition returns to
the prior no-sink posture, or stop the ingest edge (served successes then fail closed to `503` —
audit-before-hand-back). **Audit rows are never altered, moved, or removed.**

---

## 9. Standing rules

- Secret **references only** — never a DSN, password, token or credential in this document, in a
  shell-history echo, or in any evidence artifact.
- **Fail-closed** — any missing or ambiguous proof stops the procedure.
- **No runtime DDL.** No runtime service applies DDL, and this tooling applies none either: it creates
  roles and grants, never tables.
- The frozen payload is **byte-frozen including its comments**. Changing one byte is a governed AW-1
  amendment plus a lockstep guard re-stamp, never an in-place edit.
