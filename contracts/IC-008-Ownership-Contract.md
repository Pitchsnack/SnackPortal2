# IC-008 — Ownership Contract

**Status:** Reserved (future contract — not yet authored) · **Phase:** Architecture Governance · **Type:** Placeholder (no design, no implementation)
**Authority source:** Reserved by **D-36 — Ownership Architecture** (Approved 2026-06-12, register entry at `20368cf`); placeholder created under **PRD-D33-D37-V2-R1** Work Package C (remediating PRD-D33-D37-V2 finding Minor 8).

> This is a **placeholder**. It reserves the contract number and records its future scope. It contains no ownership rules and authorizes no implementation.

## Purpose
Reserve the dedicated contract that will govern the SnackPortal2 ownership model (Owning Agent, reserved Owning AI Agent reference) decided by D-36, keeping ownership from being smeared across IC-001/IC-002/IC-003.

## Future scope (per D-36 §14 — to be designed at authoring time, not decided here)
- **Ownership-eligibility matrix** over the D-32 roles (which principals may own which record kinds), honoring the already-decided D-36 §5 rule that Control-DB global-record owners are Control-domain (D-03 internal) principals only.
- **Initial owner assignment on import** (currently undefined; required before any import UX surfaces owners — D-36 §8).
- **Ownership transfer workflow** (explicit, authorized, audited per the D-36 §7 Audit Residency Rule).
- **Record-shape amendments:** `owner_agent_ref` / `owner_ai_agent_ref` fields on tenant and global Startup/Investor/Deal record shapes (the IC-001/IC-002 DTO touches routed through this contract).
- **Open decision item (PRD-D33-D37-V2 Minor 10):** whether every Control-DB global record requires a *named* Control-domain Owning Agent (the PRD 8A accountability intent) or named global-record ownership remains optional.
- AI-owner activation interface remains **IC-006-gated** (identity namespace, resolution, population rules — not this contract).

## Not yet authored · Implementation prohibited
No part of IC-008 exists as binding contract language. No ownership implementation (fields, workflows, UI, audit persistence) may proceed until IC-008 is designed and approved through the standard change-control process (register entry → contract → code). Until then, D-36's reference-only representation rule and domain rule stand as the governing ADR decisions, and the platform contains no ownership fields (verified at `dd5c132`).

## Dependencies
**D-36** (governing ADR) · **D-32** (role model) · **D-03** (identity model) · **D-14** (reference-only discipline) · **D-34** (audit representation + residency) · **IC-002/IC-003** (record/import interactions).
