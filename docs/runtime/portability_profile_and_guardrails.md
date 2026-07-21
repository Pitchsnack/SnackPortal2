# SP2-NEXT-A — Portability Profile and Guardrails

**Scope:** the bounded portability layer of the Official Controlled Local MVP Environment master
plan (Arc 1 / NEXT-A, PRD `SP2-NEXT-A-PORTABILITY`): stable logical identities, the
provider-neutral environment-profile contract, the references-only deployment manifest, and the
portability architecture guards. This document is the O-8 durable reference.

**Posture:** public production remains **NOT READY / DO-NOT-ACTIVATE**. Nothing in this layer
activates runtime, closes a B5 blocker, provisions infrastructure, selects a cloud provider, or
changes an architecture invariant. The core invariants are untouched and remain binding:

```text
Authentication ≠ Routing ≠ Authorization ≠ Database Access
One Request → One Active Tenant → One Database
Control DB ≠ Tenant DB;  ACME DB ≠ ZETA DB ≠ NOVA DB
Global Record ≠ Tenant Record; import creates an independent copy; no auto-sync
Lovable calls the Gateway; the frontend never selects or reaches a database
```

---

## 1. Identity model (O-1/O-2)

| Kind | Values | Defined in |
|---|---|---|
| Logical database IDs | `control`, `tenant-acme`, `tenant-zeta`, `tenant-nova` | `backend/shared/portability/identity.py` |
| Official local environment | `SP2-LOCAL-MVP-01` | same |
| Profiles | `sp2-local-mvp` (runtime-capable), `sp2-cloud-template` (non-operational) | `infrastructure/env/profiles/` |
| Environment types | `controlled-local-mvp`, `cloud-template` (closed vocabulary) | `identity.EnvironmentType` |

**Identity rules.** Logical identities are permanent, kebab-case, and physically independent.
They must never be — and are validated never to be — container names (`sp2_b3a_*`), compose
project names (`snackportal2-b3a-local`), physical database names (`snackportal2_*_local`),
volume names, ports (5540–5543), hostnames, IPs, loopback literals, cloud resource IDs, or file
paths. Those are **operational handles**: profile/operator configuration values that may change
per environment while the logical identity stays fixed. A future cloud environment keeps the same
four logical database IDs verbatim and re-points only configuration (master plan §33.1).

## 2. Environment-profile contract (O-3, §8.1)

`backend/shared/portability/profile.py` — schema `sp2-environment-profile/v1`, pure stdlib,
loaded from explicit paths only (no repo-layout or environment-variable assumption). A profile
selects: logical database bindings, service endpoint references, the SecretRef provider, artifact
and backup destinations, the monitoring exporter, the alert destination, TLS mode, service
discovery mode, and runtime health integration.

**Reference grammar (references only, D-14):**

```text
ref:<store-ref>@<version>   secret-resolvable (maps 1:1 onto shared.secrets.SecretRef)
service://<service-id>      logical service endpoint
config://<key>              non-secret operator configuration
```

**Validation (fail-closed):** unique `profile_id`/`environment_id` across a profile set; stable
identity grammars; supported environment type only; all four required logical database IDs, no
duplicates; reference-grammar-only endpoints; raw secrets/DSNs/IPs/host:port/Windows paths
rejected in every value (with **redacted** error messages — the offending value is never echoed);
business-rule keys rejected at any nesting depth; unknown fields rejected deterministically
(sorted, stable messages).

**Allowed profile-specific values:** endpoint references, provider selectors, posture selectors
(TLS/discovery/health), destinations — i.e. *where things live*. **Prohibited:** business rules,
tenant authority, ownership, sharing, import/lineage semantics, audit representation, routing
invariants, API contracts, blocker acceptance criteria — i.e. *what the system does* (master plan
§10.3).

## 3. Local MVP profile (O-4, §8.2)

`infrastructure/env/profiles/sp2-local-mvp.profile.json` — `SP2-LOCAL-MVP-01`,
`controlled-local-mvp`, runtime-capable. It contains **zero physical endpoints**: the local
fixture's loopback ports (5540–5543) and any artifact paths live exclusively in untracked
operator configuration; `infrastructure/env/sp2-local-mvp.env.template` documents the operator
keys (references only). Being runtime-capable does not activate anything — the B-5 activation
gate is a separate, unchanged mechanism.

## 4. Cloud template (O-5, §8.3)

`infrastructure/env/profiles/sp2-cloud-template.profile.json` — same logical database IDs, same
service endpoints, same contract fields; every provider-choosing selector is `unselected`; no
provider SDK, no resources, no cloud choice. It is structurally non-operational:
`EnvironmentProfile.assert_runtime_capable()` raises `ProfileNotRuntimeCapableError` for the
`cloud-template` type, and validation rejects a cloud template that selects a concrete provider
or claims `SP2-LOCAL-MVP-01`.

## 5. Deployment manifest (O-6, §8.4)

`backend/shared/portability/manifest.py` — schema `sp2-deployment-manifest/v1` with exactly the
O-6 field set (`environment_id`, `profile_id`, `host_or_platform_ref`, `operator_ref`,
`repository_commit`, `configuration_digest`, `service_image_refs`, `database_image_refs`,
`migration_digest`, `logical_database_ids`, `secret_provider_type`, `backup_target_type`,
`monitoring_exporter_type`, `started_at`). References and digests only: `config://`/`ref:`
references, 40-hex commit, `sha256:`-tagged digests, digest-pinned image references, ISO-8601 UTC
timestamps. Serialization is canonical (sorted keys, canonicalized collection order, compact,
ASCII) and `manifest_digest` is the SHA-256 of exactly that serialization — reproducible across
processes and construction orders. Testable with no Docker and no database.

## 6. Guardrails (O-7, §8.5)

`backend/tests/architecture/test_next_a_portability_boundaries.py` — pure stdlib, default suite,
path-bounded to the runtime packages (`shared` + the six services); each detector has a paired
nonvacuity test proving it fires on a planted violation.

| Guard | Prohibits (in business code) | Sanctioned locations |
|---|---|---|
| Windows paths | drive-letter path literals | operator config / runbooks only |
| Loopback endpoints | `localhost` / `127.0.0.1` / `::1` string literals | `**/adapters/providers/**`, `<pkg>/main.py` composition roots, docstrings |
| Fleet handles & ports | `sp2_b3a_*`, `snackportal2-b3a`, `snackportal2_*_local`, ports 5540–5543 | none (operational handles never enter runtime code) |
| DSN/credential shapes | `postgres[ql]://…`, URLs with embedded credentials | none in runtime code, templates, or profiles (runbook *placeholder examples* remain allowed per master plan §25) |
| Provider SDKs | `hvac`, `kubernetes`, `docker`, `datadog`, `ddtrace`, `newrelic`, `sentry_sdk`, `prometheus_client`, `elastic_apm`, `splunklib` imports | `**/adapters/providers/**` (additive to `test_vendor_and_db_containment.py`, which keeps covering `boto3`/`azure`/`google.cloud`/`supabase` — pinned by an anti-regression check) |
| Profile hygiene | committed profiles failing validation; physical handles/ports/DSNs in profiles or env templates | — |
| Leaf discipline | `shared.portability` importing services or non-stdlib modules | — |

## 7. Future cloud migration behavior (O-8)

Cloud migration changes **configuration, not architecture** (master plan §33): a future
`sp2-cloud-<name>` profile keeps the same schema, the same four logical database IDs, the same
service IDs, and the same manifest shape, while re-pointing endpoint references and selecting
concrete providers (secret store, monitoring exporter, TLS, discovery) behind the existing
adapter boundaries (`**/adapters/providers/**`). No business code changes; guards enforce that
provider SDKs stay behind adapters. Local blocker evidence does not transfer automatically —
cloud environments require environment-specific revalidation (master plan §33.4).

## 8. Governance

Introduced by PRD `SP2-NEXT-A-PORTABILITY` (Arc 1 of the master plan) under Dan-only merge
authority with independent Opus verification. This layer closes **no** B5 blocker; the blocker
register and the production activation gate are unchanged.
