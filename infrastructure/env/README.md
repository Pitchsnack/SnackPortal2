# Environment Templates (reference-only)

**Rule:** templates carry **references and non-secret configuration only** — never
secret values (D-14). Secret values are resolved at runtime through the
`shared.secrets.SecretStore` port; configuration carries `{store_ref, version}`
references via the convention `KEY=ref:<store-ref>@<version>`.

- Keys ending in `_REF` MUST be empty or a `ref:` reference (CI-enforced by
  `tests/architecture/test_no_secret_literals.py`).
- No credentials, tokens, or private keys may appear in any template.
- Provider-selection keys (e.g. `SECRETSTORE_PROVIDER`) are vendor-neutral config,
  filled per environment; the concrete adapter lives under `adapters/providers/`.

See `example.env.template`.

## Environment profiles (SP2-NEXT-A-PORTABILITY)

`profiles/` holds the committed provider-neutral environment profiles:

- `sp2-local-mvp.profile.json` — the Official Controlled Local MVP Environment
  (`SP2-LOCAL-MVP-01`); runtime-capable; references only.
- `sp2-cloud-template.profile.json` — the non-operational cloud template; same
  logical identities and contract fields, all provider selectors `unselected`;
  it cannot activate runtime.

Profiles are validated by `backend/shared/portability` (schema
`sp2-environment-profile/v1`) and guarded by
`backend/tests/architecture/test_next_a_portability_boundaries.py`. Rules:

- **References only.** Endpoints are `ref:<store-ref>@<version>` (D-14 SecretRef),
  `service://<service-id>`, or `config://<key>` references — never hosts, ports,
  IPs, paths, DSNs, or credentials. Physical endpoints (e.g. the local fixture's
  loopback ports) live exclusively in untracked operator configuration
  (`sp2-local-mvp.env.template` documents the keys).
- **Logical identity is physically independent.** The logical database IDs
  (`control`, `tenant-acme`, `tenant-zeta`, `tenant-nova`) never change across
  environments; container/volume/database names and ports are operational
  handles, never identities.
- **No business rules.** A profile selects *where things live*, never *what the
  system does*; business-rule keys are rejected at any nesting depth.

Full documentation: `docs/runtime/portability_profile_and_guardrails.md`.
