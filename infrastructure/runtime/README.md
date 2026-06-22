# infrastructure/runtime — Reference-only runtime activation templates (PRD 06 B-5)

**Reference-only.** This directory holds the **forward-contract template** for the Production Runtime Activation Gate.
It is **not** production config, **not** runtime-wired, **not** secret-bearing, **not** cloud-resource creation, **not**
DDL, **not** the B-6 audit sink, and **not** a frontend cutover. It is independent of `backend/` application code
(CLAUDE.md constraint 4).

## Files

```
b5_activation_gate.template   forward-contract activation switch + D-14 reference keys (RUNTIME_ACTIVATION_ENABLED=false;
                              *_REF=ref:... only; no secret values). NOT read by runtime code in B-5.
```

## Relationship to the live mechanism (B5-D8)

The live fail-closed mechanism **today** is in `backend/control_plane/main.py`:
`SP2_CP_PROVISIONING_ADAPTER` / `SP2_CP_DISTINCTNESS_LEDGER` default to `in_memory`, and any other value raises
`NotImplementedError` (no silent fallback). A **future, separately-gated** runtime-activation phase may wrap or
supersede that mechanism with a wired gate that honors `RUNTIME_ACTIVATION_ENABLED` — always preserving fail-closed.
**B-5 wires nothing**; this template is documentation of the future contract only.

## Rules

```
references only (D-14): no raw DSNs, passwords, tokens, cloud credentials, or production secret values
disabled by default: RUNTIME_ACTIVATION_ENABLED=false
not active production config; not consumed by runtime; not under infrastructure/db|iac|docker|env
```

See `docs/runtime/b5_production_runtime_activation_gate.md` (gate spec), `b5_activation_blockers.md` (blocker register),
`b5_activation_evidence_template.md` (evidence), and `b5_runtime_readiness_matrix.md` (readiness mapping).
