# CI Evidence Reports

**Canonical path:** `docs/reports/ci-evidence/`
**Deprecated path:** `docs/ci-evidence/` — do **NOT** use for new work.

This folder stores durable CI evidence records and reports for SnackPortal2, produced under the
`PRD-CI-EVIDENCE-01` family (specification `PRD-CI-EVIDENCE-01-R1`; first execution
`PRD-CI-EVIDENCE-01-E1`, run via the verified revision `PRD-CI-EVIDENCE-01-E1-R1`).

Evidence records must be:

- commit-bound
- workflow-file-hash-bound
- run-URL-bound where available
- zero-secret
- classified by source (`source_classification`)
- classified by evidence strength (`evidence_strength`)
- explicit about `pass_gate_eligible`

**Validation status.** This evidence record is not yet asserted by any automated check; it is validated
for JSON well-formedness only. Schema/record validation (a guard test under
`backend/tests/architecture/`) is routed to a follow-up PRD:
`PRD-CI-EVIDENCE-01-E2 — CI Evidence Schema and Record Guard`.

Physical Multi-Database MVP remains mandatory. CI evidence work makes no SnackPortal2 runtime-architecture
change and does not weaken the CI hardening controls (ATR-S1/S2/S3) or the secret-scan regression guard.

This folder must **not** contain: GitHub tokens, PATs, the `GITHUB_TOKEN` value, authorization headers,
cookies, session values, database passwords, API keys, private keys, raw environment dumps,
structure-revealing masked secret placeholders, or unrelated PII. The only token form permitted to appear
is the `${{ secrets.GITHUB_TOKEN }}` placeholder.
