"""Governed CI Live-PG Bundle (ATR-9) — live-PG workflow run-set COMPLETENESS guard (default suite; no DB).

The advisory ``live-pg-durable-path.yml`` workflow runs the ``requires_pg`` durable-path harnesses in a
``for h in … ; do`` loop. Before this guard, nothing tied the loop to the harnesses that EXIST — which is
exactly how the 07B-e2e, MCC, and 07C harnesses (≈45% of the live evidence, including everything proving
the newest schema slices and the composed Step-2b transaction) silently stayed OUT of CI while the
workflow reported green (07C-AT-1 / 07C-PM-2 / PM-07B1-1).

This pure-stdlib guard derives ground truth FROM DISK — it does NOT hardcode the known omissions — so a
FUTURE harness added under any ``backend/tests/*/requires_pg/`` without a matching CI loop entry fails the
default suite immediately:

* **INV-A** — every discovered on-disk harness that is not an explicit, justified MANUAL_ONLY exception is
  an active workflow loop entry (disk − exceptions ⊆ loop).
* **INV-B** — every workflow loop entry exists on disk (loop ⊆ disk): no phantom / renamed entry rots in CI.
* **INV-C** — every MANUAL_ONLY exception exists on disk: exceptions cannot go stale.
* **INV-D** — the loop parses and is non-empty: the guard cannot pass vacuously on an unparseable workflow.

COEXISTENCE. Complements (never contradicts) ``test_live_pg_docs_workflow_consistency.py`` — AT-5 pins the
loop COUNT and the docs↔workflow consistency; this guard pins SET completeness. The loop regex idiom is
REPLICATED from the AT-5/ATR-4 guards (self-containment precedent — those guards are not imported and not
edited). Helpers (``_pg.py``) are excluded by the ``test_*.py`` discovery pattern; ``__pycache__`` never
matches it. No ``_REVIEWED_*`` name appears here; no ``_COVERAGE`` registration applies (that meta-guard is
DDL-family-scoped).

Scope: run-set completeness only. Does NOT prove the harnesses PASS (the workflow's fail-closed
non-vacuity gate owns that), does NOT make the advisory workflow a required check (MCC-PM-2), and does NOT
close B5-BLK-4. Pure stdlib; standalone-runnable:

    python tests/architecture/test_live_pg_workflow_runset_completeness.py
"""

from __future__ import annotations

import pathlib
import re
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

_WORKFLOW = _scan.REPO_ROOT / ".github" / "workflows" / "live-pg-durable-path.yml"
_TESTS_ROOT = _scan.BACKEND_ROOT / "tests"

# The ONLY allowed omissions from the CI loop — explicit, named, justified. Adding a key here is a
# governed decision (it consciously keeps a live proof manual-only).
# NOTE ON SHAPE. Seven boundary guards elsewhere in this directory read this dict with
# ``ast.literal_eval``, so every value must be a plain string literal — a shared constant
# referenced by name would make the whole mapping unreadable to them and take those guards
# down. The Stage 4 entries below therefore repeat their common reason rather than factoring
# it out. That is deliberate, not duplication that wants removing.
MANUAL_ONLY_EXCEPTIONS = {
    # --- Stage 4 (Live PostgreSQL & Migration Verification), Option A rebuild -----------------
    # Every Stage 4 module needs FOUR physically distinct PostgreSQL clusters
    # (SP2_STAGE4_CONTROL_DSN / _ACME_DSN / _ZETA_DSN / _NOVA_DSN) so that cross-tenant absence
    # is a property of the topology rather than of one cluster's search path — the same B-7C-2
    # exclusion that keeps test_b3a_multi_database_topology.py out of the loop. Enrollment is
    # FORBIDDEN rather than deferred: all four EXPECTED_HARNESS_COUNT sites parse the loop TEXT
    # and compare len(entries), so bumping the count while the loop is unchanged takes the
    # default suite down. Run with the four DSNs exported:
    #     python -m pytest tests/snackportal2/requires_pg -q
    "tests/snackportal2/requires_pg/test_pg_a_migrations.py": (
        "Stage 4A migration verification: applies the Control chain (M-1 included) and the tenant chain "
        "to four disposable databases and creates two more from zero. Requires four physically distinct "
        "clusters plus CREATE/DROP DATABASE rights, which the single ephemeral CI service does not "
        "provide. Enrollment is forbidden, not deferred: the hosted 14-harness loop and the "
        "EXPECTED_HARNESS_COUNT/b7c2-doc lockstep are deliberately unchanged by Stage 4 (no .github "
        "changes in its authorized surface). Run: python -m pytest tests/snackportal2/requires_pg -q"
    ),
    "tests/snackportal2/requires_pg/test_pg_b_control_plane.py": (
        "Stage 4B live Control Plane verification against the real Control database. Requires the Stage 4 "
        "four-cluster fixture (SP2_STAGE4_* DSNs), which the single ephemeral CI service does not provide; "
        "the hosted loop and the EXPECTED_HARNESS_COUNT/b7c2-doc lockstep are deliberately unchanged by "
        "Stage 4. Run: python -m pytest tests/snackportal2/requires_pg -q"
    ),
    "tests/snackportal2/requires_pg/test_pg_c_database_router.py": (
        "Stage 4C live Database Router and D-48 grant verification. Requires the Stage 4 four-cluster "
        "fixture AND spawns real uvicorn processes for the Control Plane and the router, driving them over "
        "loopback HTTP — a shape the workflow's per-harness `python <file>` invocation does not support. "
        "The hosted loop and the EXPECTED_HARNESS_COUNT/b7c2-doc lockstep are deliberately unchanged by "
        "Stage 4. Run: python -m pytest tests/snackportal2/requires_pg -q"
    ),
    "tests/snackportal2/requires_pg/test_pg_d_domain_services.py": (
        "Stage 4D live tenant domain-service verification (Startup, Investor, Deal, Lineage, Import). "
        "Requires the Stage 4 four-cluster fixture and six real uvicorn processes composed from the "
        "environment; not runnable on the single ephemeral CI service. The hosted loop and the "
        "EXPECTED_HARNESS_COUNT/b7c2-doc lockstep are deliberately unchanged by Stage 4. "
        "Run: python -m pytest tests/snackportal2/requires_pg -q"
    ),
    "tests/snackportal2/requires_pg/test_pg_d2_audit.py": (
        "Stage 4D section 6.6 live Audit Service verification against migration M-1's "
        "control_ingress_audit table. Requires the Stage 4 Control database and a real uvicorn Audit "
        "process; not runnable on the single ephemeral CI service. The hosted loop and the "
        "EXPECTED_HARNESS_COUNT/b7c2-doc lockstep are deliberately unchanged by Stage 4. "
        "Run: python -m pytest tests/snackportal2/requires_pg -q"
    ),
    "tests/snackportal2/requires_pg/test_pg_f_bff_end_to_end.py": (
        "Stage 4F mandatory real BFF-to-PostgreSQL end-to-end path, plus the Stage 4E physical-isolation "
        "proof. Runs ELEVEN real uvicorn services against four physically distinct clusters and measures "
        "isolation with pg_stat_database.sessions inside each one; neither the topology nor the process "
        "fleet exists on the single ephemeral CI service. The hosted loop and the "
        "EXPECTED_HARNESS_COUNT/b7c2-doc lockstep are deliberately unchanged by Stage 4. "
        "Run: python -m pytest tests/snackportal2/requires_pg -q"
    ),
    "tests/snackportal2/requires_pg/test_pg_z_gates.py": (
        "Stage 4G/4H/4I standing gates re-run under a live-PostgreSQL configuration: all fourteen OpenAPI "
        "documents regenerated in a configured subprocess and compared byte-for-byte against the "
        "unconfigured ones. Requires the Stage 4 Control DSN to build that configuration, so it is bound "
        "to the four-cluster fixture like the rest of the suite. The hosted loop and the "
        "EXPECTED_HARNESS_COUNT/b7c2-doc lockstep are deliberately unchanged by Stage 4. "
        "Run: python -m pytest tests/snackportal2/requires_pg -q"
    ),
    "tests/control_plane/requires_pg/test_b3a_multi_database_topology.py": (
        "requires four physically distinct clusters (SP2_B3A_*_DSN, four distinct system_identifiers); "
        "cannot run on the single ephemeral CI service — the B-7C-2 exclusion, documented in the "
        "workflow header and the b7c2 runtime doc"
    ),
    "tests/control_plane/requires_pg/test_pg_b5_standing_topology.py": (
        "PRD B5-4 standing-topology disposable proof: single-cluster CI-capable, but loop enrollment "
        "requires editing the live-pg workflow (plus the EXPECTED_HARNESS_COUNT/b7c2-doc lockstep), "
        "which is out of the B5-4 slice's authorized surface (no .github changes); enrollment is a "
        "tracked follow-up in the B5-4 execution report ATR. "
        "AUTHFIX-B (Gate A): ANNOTATE, DO NOT RETIRE — this harness is disposable, does not depend "
        "on the vanished b5_standing standing rows, and is still green given only SNACKPORTAL_TEST_DSN; "
        "retiring it alongside the auth-fixture family would destroy 13 live checks for no reason"
    ),
    "tests/control_plane/requires_pg/test_pg_b5_standing_auth_fixture.py": (
        "PRD B5-4A V2 standing-authentication-fixture proof: bound to the ESTABLISHED B5-4 standing "
        "Control DB, the local Docker fixture, and the external secret root (control-store-standalone "
        "posture) — not runnable on the single ephemeral CI service; loop enrollment would additionally "
        "require the .github workflow edit plus the EXPECTED_HARNESS_COUNT/b7c2-doc lockstep, which is "
        "outside the B5-4A V2 authorized five-file surface; tracked follow-up in the B5-4A V2 execution "
        "report ATR. "
        "AUTHFIX-B (Gate A): this harness's subject state — the b5_standing trio — was replaced "
        "around 2026-07-21 by the four-cluster standing fixture, so it is SUPERSEDED and its non-zero "
        "exit is EXPECTED and EXPLICIT. It is retained, not retired: Stage 0 forbids partial retirement "
        "of this family and four default-suite guards still reference it. Accepted replacement: "
        "tests/control_plane/requires_pg/test_pg_clm_standing_auth_posture.py"
    ),
    "tests/control_plane/requires_pg/test_pg_smoke_c_integrated_live_proof.py": (
        "PRD Smoke C V2 integrated live proof: bound to the ESTABLISHED B5-4 standing topology, the "
        "B5-4A standing auth fixture, the local Docker fixture, and the external secret root — not "
        "runnable on the single ephemeral CI service; loop enrollment would additionally require the "
        ".github workflow edit plus the EXPECTED_HARNESS_COUNT/b7c2-doc lockstep, which is outside the "
        "Smoke C V2 authorized five-file surface; tracked follow-up in the Smoke C V2 execution report ATR. "
        "AUTHFIX-B (Gate A): this harness's subject state — the b5_standing trio — was replaced "
        "around 2026-07-21 by the four-cluster standing fixture, so it is SUPERSEDED and its non-zero "
        "exit is EXPECTED and EXPLICIT. It is retained, not retired: Stage 0 forbids partial retirement "
        "of this family and four default-suite guards still reference it. Accepted replacement: "
        "tests/control_plane/requires_pg/test_pg_clm_standing_auth_posture.py"
    ),
    "tests/control_plane/requires_pg/test_pg_b5_blk6_portal_binding_live_proof.py": (
        "PRD B5-BLK-6C-C disposable real-Control-DB portal-composition proof: single-cluster capable "
        "(creates and drops its own disposable Control DB), but deliberately MANUAL_ONLY — loop "
        "enrollment would require editing the live-pg workflow (plus the EXPECTED_HARNESS_COUNT/"
        "b7c2-doc lockstep), which is outside the 6C-C authorized surface (no .github changes); "
        "operator-run per infrastructure/runbooks/b5_blk6_portal_binding_live_proof.md and pinned by "
        "tests/architecture/test_b5_blk6_portal_binding_live_proof_boundaries.py"
    ),
    "tests/control_plane/requires_pg/test_pg_dbr_ar_2d_standing_witnesses.py": (
        "PRD DBR-AR-2D V3 standing-witness read-only verification: bound to the ESTABLISHED B5-4/B5-4A "
        "standing topology, the local Docker fixture, the external secret root, AND the Dan-authorized "
        "exactly-once V3 standing evidence (DDL 010/011 manually applied to the retained local Control "
        "DB + the four durable evidence rows) — not runnable on the single ephemeral CI service; the "
        "hosted 14-harness loop is deliberately UNCHANGED by the V3 slice (PRD DBR-AR-2D V3 §10), so "
        "enrollment is forbidden, not merely deferred. "
        "AUTHFIX-B (Gate A): this harness's subject state — the b5_standing trio — was replaced "
        "around 2026-07-21 by the four-cluster standing fixture, so it is SUPERSEDED and its non-zero "
        "exit is EXPECTED and EXPLICIT. It is retained, not retired: Stage 0 forbids partial retirement "
        "of this family and four default-suite guards still reference it. Accepted replacement: "
        "tests/control_plane/requires_pg/test_pg_clm_standing_auth_posture.py"
    ),
    "tests/control_plane/requires_pg/test_pg_gateway_audit_durable.py": (
        "Gateway Operational Audit Persistence V1a disposable durable-persistence proof: single-cluster "
        "capable (creates and drops its own disposable Control DB sp2_gateway_audit_v1a_proof, applies "
        "012/013 to it only), but deliberately MANUAL_ONLY — loop enrollment would require editing the "
        "live-pg workflow (plus the EXPECTED_HARNESS_COUNT/b7c2-doc lockstep), which is outside the V1a "
        "authorized surface (no .github changes); operator-run per "
        "infrastructure/runbooks/gateway_operational_audit_live_proof.md and pinned by "
        "tests/architecture/test_gateway_operational_audit_boundaries.py"
    ),
    "tests/control_plane/requires_pg/test_pg_import_copy_durable.py": (
        "W1a composed-core import copy + durable Import Audit disposable proof: single-cluster capable "
        "(creates and drops its own disposable databases sp2_w1a_import_proof_control / _t1 / _t2, applies "
        "control 014/015 + the 14-file tenant template to them only), but deliberately MANUAL_ONLY — loop "
        "enrollment would require editing the live-pg workflow (plus the EXPECTED_HARNESS_COUNT/b7c2-doc "
        "lockstep), which is outside the W1a authorized surface (no .github changes); operator-run per "
        "infrastructure/runbooks/import_copy_live_proof.md and pinned by "
        "tests/architecture/test_import_write_path_boundaries.py"
    ),
    "tests/control_plane/requires_pg/test_pg_controlled_served_write_rehearsal.py": (
        "controlled served-write rehearsal harness (the W1b served Gateway Edge joined to the W1a composed "
        "real-PostgreSQL import path in one test-owned deployment root): single-cluster capable (creates and "
        "drops its own disposable databases sp2_rehearsal_control / _alpha / _beta), but deliberately "
        "MANUAL_ONLY — an operator-run, disposable-topology rehearsal that requires an explicit human "
        "START-GATE (Dan) before any execution, never an automatic CI proof; loop enrollment would "
        "additionally require editing the live-pg workflow (plus the EXPECTED_HARNESS_COUNT/b7c2-doc "
        "lockstep), which is outside the rehearsal slice's authorized surface (no .github changes); "
        "operator-run per infrastructure/runbooks/controlled_served_write_rehearsal.md"
    ),
    "tests/control_plane/requires_pg/test_pg_controlled_rollback_rehearsal.py": (
        "controlled rollback rehearsal harness (composed-core Control Plane + Database Router; disposable "
        "local rollback-to-deferred-in-memory mechanism proof): single-cluster capable (creates and drops "
        "its own disposable databases sp2_rollback_control / _target / _adjacent, applies control 001-009 + "
        "the 14-file tenant template to them only; no audit-store DDL), but deliberately MANUAL_ONLY — an "
        "operator-run, disposable-topology rehearsal that requires an explicit human START-GATE (Dan) before "
        "any execution, never an automatic CI proof; loop enrollment would additionally require editing the "
        "live-pg workflow (plus the EXPECTED_HARNESS_COUNT/b7c2-doc lockstep), which is outside the B5-BLK-8B "
        "authorized surface (no .github changes); operator-run per "
        "infrastructure/runbooks/controlled_rollback_rehearsal.md and pinned by "
        "tests/architecture/test_controlled_rollback_rehearsal_boundaries.py"
    ),
    "tests/control_plane/requires_pg/test_pg_clm_standing_auth_posture.py": (
        "AUTHFIX-B REPLACEMENT standing authentication verification harness — the accepted successor to the "
        "B5-4A standing auth fixture, whose subject state (the b5_standing trio) was replaced around "
        "2026-07-21 and no longer exists. Read-only against the ESTABLISHED standing Control database, "
        "which does not exist on the single ephemeral CI service; it verifies structural invariants and "
        "REPORTS the roster rather than pinning it, precisely so a future governed fixture change cannot "
        "silently falsify it again. Deliberately MANUAL_ONLY: the hosted 14-harness loop and the "
        "EXPECTED_HARNESS_COUNT/b7c2-doc lockstep are unchanged by this slice. Pinned by "
        "tests/architecture/test_clm_standing_auth_posture_boundaries.py"
    ),
    "tests/control_plane/requires_pg/test_pg_clm_acme_dataplane_witness.py": (
        "CLM ACME tenant data-plane witness (Gateway 8820 -> Tenant Startup 8004 -> Database Router -> "
        "Control routing record -> SecretRef -> ACME physical tenant DB -> Startup GET/PATCH, plus ZETA "
        "denial/isolation): bound to the ESTABLISHED four-cluster standing topology, the standing Keycloak "
        "fixture, an operator-supplied bearer token, and the external tenant secret root — none of which "
        "exists on the single ephemeral CI service. Its `run` leg additionally performs a REAL business "
        "write to a physical tenant database (Gate-B class M14) and requires an explicit human START-GATE, "
        "so it must never be an automatic CI proof. Enrollment is FORBIDDEN rather than deferred: the "
        "hosted 14-harness loop and the EXPECTED_HARNESS_COUNT/b7c2-doc lockstep are deliberately unchanged "
        "by this slice. Operator-run per infrastructure/runbooks/clm_acme_dataplane_witness.md and pinned by "
        "tests/architecture/test_clm_dataplane_witness_boundaries.py"
    ),
    "tests/control_plane/requires_pg/test_pg_aw1_gateway_audit_writer_rehearsal.py": (
        "AW-1 Tier-A disposable least-privilege privilege rehearsal: deliberately MANUAL_ONLY and "
        "deliberately NOT loop-enrolled — not merely deferred. CREATE ROLE is CLUSTER-scoped, so the "
        "rehearsal roles land wherever the rehearsal runs; it must therefore own a disposable cluster it "
        "may create and drop roles on, and it creates the database name snackportal2_control_local exactly "
        "(asserted absent first) so the byte-frozen §5.4 payload executes verbatim. Neither condition holds "
        "on the single ephemeral CI service. Enrollment is additionally FORBIDDEN rather than pending: all "
        "four EXPECTED_HARNESS_COUNT sites parse the workflow loop TEXT and compare len(entries), so bumping "
        "14->15 while the loop stays 14 turns five assertions red and takes the default suite down. The "
        "hosted 14-harness loop is UNCHANGED by this slice. Operator-run per "
        "infrastructure/runbooks/aw1_gateway_audit_writer.md and pinned by "
        "tests/architecture/test_aw1_gateway_audit_writer_boundaries.py"
    ),
    "tests/control_plane/requires_pg/test_pg_clm_2day_stage_b_rehearsal.py": (
        "CLM 2-Day Stage B controlled-local rehearsal harness (the full D-42 journey: RS256/OIDC login -> "
        "principal-only auth -> served GET /memberships -> backend-validated ACME selection -> served "
        "GET/PATCH /tenant/startups/<startup_ref> -> unauthorized ZETA fail-closed denial -> four durable "
        "audit events -> rollback and restore, joined in one test-owned deployment root over six loopback "
        "served edges): single-cluster capable (creates and drops its own disposable databases sp2_clm_control "
        "/ _acme / _zeta, applies control 001-009 + 012 + 013 and the 14-file tenant template to them only), "
        "but deliberately MANUAL_ONLY — an operator-run, disposable-topology rehearsal that requires an "
        "explicit human START-GATE (Dan) before any execution, never an automatic CI proof; loop enrollment "
        "would additionally require editing the live-pg workflow (plus the EXPECTED_HARNESS_COUNT/b7c2-doc "
        "lockstep), which is outside the Stage B authorized surface (no .github changes); operator-run per "
        "infrastructure/runbooks/clm_2day_stage_b_rehearsal.md"
    ),
}

# SAME loop idiom as the AT-5 / ATR-4 guards (replicated for self-containment, not imported).
_LOOP_RE = re.compile(r"for\s+h\s+in\s+(?P<loop>.+?);\s*do", re.DOTALL)
_ENTRY_RE = re.compile(r"\S+\.py")


# --- pure helpers (no I/O beyond reads; exercised by the non-vacuity tests) -----------------------
def _loop_entries(workflow_text: str) -> list[str] | None:
    """Harness path tokens inside the workflow's ``for h in … ; do`` loop, or None if unparseable."""
    m = _LOOP_RE.search(workflow_text)
    return _ENTRY_RE.findall(m.group("loop")) if m else None


def _discovered_harnesses(tests_root: pathlib.Path = _TESTS_ROOT) -> set[str]:
    """All on-disk requires_pg harnesses in workflow path form (tests/<svc>/requires_pg/test_*.py).

    The ``test_*.py`` pattern excludes helpers (``_pg.py``) by construction; ``__pycache__`` cannot match."""
    return {f"tests/{p.relative_to(tests_root).as_posix()}" for p in tests_root.glob("*/requires_pg/test_*.py")}


# --- INV-D: the loop parses and is non-empty -------------------------------------------------------
def test_inv_d_workflow_loop_parses_nonempty() -> None:
    assert _WORKFLOW.is_file(), f"live-pg workflow missing: {_WORKFLOW}"
    entries = _loop_entries(_WORKFLOW.read_text(encoding="utf-8"))
    assert entries is not None, "could not parse the `for h in … ; do` run loop — guard would be vacuous"
    assert entries, "the live-pg workflow run loop is EMPTY — no harness would run"


# --- INV-A: every non-exempt disk harness is in CI -------------------------------------------------
def test_inv_a_all_disk_harnesses_in_ci_or_exempt() -> None:
    entries = set(_loop_entries(_WORKFLOW.read_text(encoding="utf-8")) or [])
    missing = _discovered_harnesses() - set(MANUAL_ONLY_EXCEPTIONS) - entries
    assert not missing, (
        f"requires_pg harness(es) exist on disk but are NOT in the live-pg CI loop and NOT a justified "
        f"MANUAL_ONLY exception: {sorted(missing)}. Add them to the workflow loop (same PR) or add an "
        f"explicit justified exception here — silent omission is how 07B-e2e/MCC/07C fell out of CI."
    )


# --- INV-B: every CI loop entry exists on disk ------------------------------------------------------
def test_inv_b_no_phantom_ci_entries() -> None:
    entries = set(_loop_entries(_WORKFLOW.read_text(encoding="utf-8")) or [])
    phantoms = entries - _discovered_harnesses()
    assert not phantoms, f"live-pg CI loop entry(ies) do not exist on disk (renamed/removed harness rotting in CI): {sorted(phantoms)}"


# --- INV-C: exceptions cannot go stale --------------------------------------------------------------
def test_inv_c_exceptions_exist_on_disk() -> None:
    stale = set(MANUAL_ONLY_EXCEPTIONS) - _discovered_harnesses()
    assert not stale, f"MANUAL_ONLY exception(s) no longer exist on disk — remove them: {sorted(stale)}"
    for path, reason in MANUAL_ONLY_EXCEPTIONS.items():
        assert reason.strip(), f"MANUAL_ONLY exception {path} must carry a written justification"


# --- non-vacuity (tempfile only; never mutates governed files; standalone-runnable like the INVs) ---
def test_nv_missing_harness_detected() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        (root / "svc" / "requires_pg").mkdir(parents=True)
        (root / "svc" / "requires_pg" / "test_pg_probe.py").write_text("x = 1\n", encoding="utf-8")
        (root / "svc" / "requires_pg" / "_pg.py").write_text("helper\n", encoding="utf-8")
        discovered = _discovered_harnesses(root)
        assert discovered == {"tests/svc/requires_pg/test_pg_probe.py"}  # helper excluded by pattern
        loop = _loop_entries("for h in \\\n  tests/other/requires_pg/test_pg_other.py ; do\n done") or []
        assert discovered - set(loop), "a disk harness absent from the loop WOULD fail INV-A"


def test_nv_phantom_entry_detected() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        (root / "svc" / "requires_pg").mkdir(parents=True)
        loop = _loop_entries("for h in \\\n  tests/svc/requires_pg/test_pg_ghost.py ; do\n done") or []
        assert set(loop) - _discovered_harnesses(root) == {"tests/svc/requires_pg/test_pg_ghost.py"}
        # a loop entry with no disk file WOULD fail INV-B


def test_nv_stale_exception_detected() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        assert {"tests/svc/requires_pg/test_pg_gone.py"} - _discovered_harnesses(pathlib.Path(tmp))
        # an exception key with no disk file WOULD fail INV-C


def test_nv_unparseable_and_empty_loop_detected() -> None:
    assert _loop_entries("no loop here at all") is None  # unparseable WOULD fail INV-D
    assert _loop_entries("for h in  ; do\n done") == []  # empty loop WOULD fail INV-D


if __name__ == "__main__":
    _scan.run(
        [
            test_inv_d_workflow_loop_parses_nonempty,
            test_inv_a_all_disk_harnesses_in_ci_or_exempt,
            test_inv_b_no_phantom_ci_entries,
            test_inv_c_exceptions_exist_on_disk,
            test_nv_missing_harness_detected,
            test_nv_phantom_entry_detected,
            test_nv_stale_exception_detected,
            test_nv_unparseable_and_empty_loop_detected,
        ]
    )
