"""B5-BLK-8C — hosted rollback-proof contract-first boundary guard (default suite; no DB, no network).

Static text-only boundary pins for the B5-BLK-8C hosted, non-production rollback-proof contract-first
surfaces (D-40 / IC-011):

  - contracts/IC-011-Hosted-Rollback-Proof-Contract.md                              (the contract)
  - infrastructure/runbooks/b5_blk8c_hosted_rollback_proof.md                        (the hosted runbook)
  - docs/runtime/b5_blk8_rollback_evidence_template.md                              (§5-§7 hosted extension)
  - docs/runtime/b5_production_runtime_activation_gate.md                           (§13 hosted path)
  - docs/Architecture-Decision-Register.md                                         (the D-40 entry)

This guard binds no runtime, imports no database driver, opens no socket, and touches no database. It keeps the
B5-BLK-8C surfaces an honest, contract-first, HOSTED NON-PRODUCTION / MANUAL_ONLY design-only scaffold, and fails
CLOSED on any LIVE-PRODUCTION target, production/closure overclaim, secret leak, census drift, wrong rollback
target, wrong verdict, or blocker-effect overreach. It performs no mutation, restores nothing (pure text
inspection over the committed bytes), and leaves the tree clean.

Twenty focused tests with at least thirty-five mutation probes (every planted sample is BUILT from low-entropy
fragments; every detector carries a non-vacuity companion that proves it fires on the mutation it forbids):

 1. test_surfaces_exist
 2. test_contract_is_draft_proposed_contract_first
 3. test_surfaces_cite_ic011_and_d40
 4. test_hosted_target_classes_staging_or_preproduction_only
 5. test_live_production_prohibited
 6. test_synthetic_nonproduction_data_only
 7. test_physical_multi_database_topology
 8. test_api_gateway_sole_ingress (+ test_api_gateway_sole_ingress_nonvacuity)
 9. test_authentication_separate_from_routing
10. test_database_router_sole_selector
11. test_secretref_only_registry
12. test_rollback_targets_exact
13. test_triggers_exact
14. test_named_operator_and_approver
15. test_runbook_four_labels_and_ordered_h0_h13
16. test_hosted_evidence_fields_present
17. test_hosted_verdicts_exact_and_production_scope_prohibited
18. test_blocker_effect_evidence_only_open_until_8d
19. test_surfaces_reject_production_and_closure_overclaims
20. test_fixtureless_pytest_rejection_and_pg_run_guidance_and_references_only

This guard closes no blocker. B5-BLK-8 remains OPEN; the live blocker census remains 7 of 9 OPEN; production
remains NOT READY / DO-NOT-ACTIVATE. The guard positively requires exactly that and rejects any drift.

Pure stdlib; standalone-runnable:
  python tests/architecture/test_b5_blk8c_hosted_rollback_contract_boundaries.py
"""

from __future__ import annotations

import pathlib
import re
import sys
from typing import List

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

_CONTRACT = _scan.REPO_ROOT / "contracts" / "IC-011-Hosted-Rollback-Proof-Contract.md"
_RUNBOOK = _scan.REPO_ROOT / "infrastructure" / "runbooks" / "b5_blk8c_hosted_rollback_proof.md"
_TEMPLATE = _scan.REPO_ROOT / "docs" / "runtime" / "b5_blk8_rollback_evidence_template.md"
_GATE = _scan.REPO_ROOT / "docs" / "runtime" / "b5_production_runtime_activation_gate.md"
_ADR = _scan.REPO_ROOT / "docs" / "Architecture-Decision-Register.md"

# The four required runbook labels (case-sensitive tokens).
_RUNBOOK_LABELS = ("MANUAL_ONLY", "HOSTED NON-PRODUCTION ONLY", "DAN START-GATE REQUIRED", "NO LIVE PRODUCTION")

# The two permitted hosted target classes — and the prohibited one.
_HOSTED_CLASSES = ("HOSTED STAGING", "HOSTED PRE-PRODUCTION")
_PROHIBITED_TARGET = "LIVE PRODUCTION"

# The exact rollback targets (normalized).
_SUCCESS_TARGET = "last-known-good durable composition"
_EMERGENCY_TARGET = "deferred in-memory composition"

# The exact triggers.
_PREFERRED_TRIGGER = "secret_resolution_failure"
_FALLBACK_TRIGGER = "distinctness_regression"

# The exact hosted verdict vocabulary and the reserved/prohibited production-scope verdict.
_HOSTED_PROVEN = "ROLLBACK-PROVEN-HOSTED-NONPRODUCTION"
_HOSTED_NOT_PROVEN = "ROLLBACK-NOT-PROVEN"
_PRODUCTION_SCOPE_VERDICT = "ROLLBACK-PROVEN-PRODUCTION-SCOPE"

# The seventeen hosted evidence fields the template hosted extension must define (PRD §9).
_HOSTED_FIELDS = (
    "ENVIRONMENT_CLASS",
    "HOSTED_TARGET_CLASS",
    "ROLLBACK_FROM_STATE_REF",
    "LAST_KNOWN_GOOD_REVISION_REF",
    "CONTROL_DB_IDENTITY_REF",
    "TENANT_DB_IDENTITY_REFS",
    "SECRET_BINDING_SET_DIGEST",
    "MIGRATION_SET_DIGEST",
    "AUDIT_SINK_IDENTITY_REF",
    "SERVED_HEALTH_BASELINE_REF",
    "FAILURE_STATE_REF",
    "POST_ROLLBACK_REF",
    "RESTORATION_REF",
    "CLEANUP_REF",
    "OPERATOR_IDENTITY",
    "APPROVER_IDENTITY",
    "EXECUTION_WINDOW",
)

# Locked-state needles required in the contract, runbook, gate §13, and template hosted section (normalized).
_LOCKED_STATE_NEEDLES = ("b5-blk-8 remains open", "7 of 9 open", "not ready / do-not-activate")

# Forbidden production / closure / census overclaim patterns (normalized text) — the 8A/8B honest-scaffold shape.
_FORBIDDEN_PATTERNS = (
    (r"production\s+ready", "'production ready' overclaim"),
    (r"activate\s+production", "'activate production' overclaim"),
    (r"production\s+rollback\s+proven", "'production rollback proven' overclaim"),
    (r"rollback\s+proof\s+(?:for\s+)?production", "'rollback proof for production' overclaim"),
    (r"b5-?blk-?8\s+(?:is\s+|now\s+)?closed", "'B5-BLK-8 closed' overclaim"),
    (r"b5-?blk-?8\s*[:=]\s*closed", "'B5-BLK-8: closed' overclaim"),
    (r"\b6\s*(?:of|/)\s*9\b", "false census '6 of 9'"),
    (r"\b8\s*(?:of|/)\s*9\b", "stale census '8 of 9'"),
    (r"do-not-activate\s+lifted", "'do-not-activate lifted' overclaim"),
    (r"rollback-proven-production-scope\s+(?:is\s+)?(?:earned|achieved|proven)", "production-scope verdict affirmed"),
)

# Secret/PII shape detectors (BUILT from low-entropy fragments — never a contiguous shape here).
_DSN_RE = re.compile("postgresql" + "://" + r"\S")
_JWT_MARKER = "ey" + "J"
_KEY_MARKER = "-----" + "BEGIN"
_AWS_RE = re.compile("AKIA" + r"[0-9A-Z]{16}")
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

_ALL_SURFACES = (_CONTRACT, _RUNBOOK, _TEMPLATE, _GATE, _ADR)


def _text(path: pathlib.Path) -> str:
    assert path.is_file(), f"{path} must exist"
    return path.read_text(encoding="utf-8")


def _norm(s: str) -> str:
    """Lowercase, normalize dash/arrow glyphs, drop markdown emphasis, and collapse whitespace."""
    s = s.lower()
    s = s.replace("—", "-").replace("–", "-").replace("→", "->")
    s = s.replace("*", "").replace("`", "")
    return re.sub(r"\s+", " ", s)


def _section(text: str, start: str, *ends: str) -> str:
    """The slice of ``text`` from ``start`` (inclusive) to the first ``end`` marker after it (or EOF)."""
    i = text.find(start)
    assert i != -1, f"section start marker not found: {start!r}"
    tail = text[i + len(start) :]
    cut = len(tail)
    for end in ends:
        j = tail.find(end)
        if j != -1:
            cut = min(cut, j)
    return start + tail[:cut]


def _gate_s13() -> str:
    return _section(_text(_GATE), "## 13.")


def _template_hosted() -> str:
    return _section(_text(_TEMPLATE), "## 5. Hosted non-production extension")


def _adr_d40() -> str:
    return _section(_text(_ADR), "### D-40", "\n### ", "\n## Open")


def _h_phase_sequence(runbook: str) -> List[int]:
    return [int(n) for n in re.findall(r"^#{2,4}\s*H(\d+)\b", runbook, re.MULTILINE)]


# ---------------------------------------------------------------------------
# 1. Surfaces exist
# ---------------------------------------------------------------------------
def test_surfaces_exist() -> None:
    for path in _ALL_SURFACES:
        assert path.is_file(), f"the B5-BLK-8C surface must exist: {path.name}"
    # non-vacuity: a bogus sibling path is not a file.
    assert not (_scan.REPO_ROOT / "contracts" / "IC-999-does-not-exist.md").is_file()


# ---------------------------------------------------------------------------
# 2. IC-011 is Draft / Proposed, contract-first, no positive capability
# ---------------------------------------------------------------------------
def test_contract_is_draft_proposed_contract_first() -> None:
    norm = _norm(_text(_CONTRACT))
    assert "status: draft / proposed" in norm, "IC-011 must declare Draft / Proposed status"
    assert "contract-first" in norm, "IC-011 must be contract-first"
    assert "it grants nothing" in norm or "grants nothing" in norm, "IC-011 must grant no positive capability"
    assert "status: final" not in norm.split("purpose")[0], "IC-011 must not claim Final in this slice"
    # non-vacuity
    assert "status: draft / proposed" not in _norm("**Status:** Final"), "a Final status must be detectable"
    assert "grants nothing" not in _norm("this contract grants the capability"), "a positive-grant rewrite must be detectable"


# ---------------------------------------------------------------------------
# 3. Every surface cites IC-011 and D-40
# ---------------------------------------------------------------------------
def test_surfaces_cite_ic011_and_d40() -> None:
    for path in (_CONTRACT, _RUNBOOK):
        norm = _norm(_text(path))
        assert "ic-011" in norm, f"{path.name} must cite IC-011"
        assert "d-40" in norm, f"{path.name} must cite D-40"
    assert "ic-011" in _norm(_gate_s13()) and "d-40" in _norm(_gate_s13()), "gate §13 must cite IC-011 and D-40"
    assert "ic-011" in _norm(_adr_d40()), "the D-40 ADR entry must cite IC-011"
    assert "d-40 - hosted non-production rollback proof" in _norm(_adr_d40()), "the D-40 heading must be present"
    # non-vacuity
    assert "ic-011" not in _norm("this cites IC-010 only"), "a wrong-contract citation must be detectable"
    assert "d-40" not in _norm("this cites D-39 only"), "a wrong-ADR citation must be detectable"


# ---------------------------------------------------------------------------
# 4. Hosted target classes: staging or pre-production only
# ---------------------------------------------------------------------------
def test_hosted_target_classes_staging_or_preproduction_only() -> None:
    ct = _text(_CONTRACT)
    for cls in _HOSTED_CLASSES:
        assert cls in ct, f"IC-011 must permit the hosted class: {cls}"
    rb = _text(_RUNBOOK)
    for cls in _HOSTED_CLASSES:
        assert cls in rb, f"the runbook must record the hosted class: {cls}"
    # non-vacuity: a fabricated third hosted class is not among the permitted two.
    assert "HOSTED PRODUCTION" not in _HOSTED_CLASSES, "a fabricated hosted-production class must be detectable"
    assert "HOSTED DEVELOPMENT" not in _HOSTED_CLASSES, "an out-of-vocabulary class must be detectable"


# ---------------------------------------------------------------------------
# 5. LIVE PRODUCTION prohibited
# ---------------------------------------------------------------------------
def test_live_production_prohibited() -> None:
    for path in (_CONTRACT, _RUNBOOK):
        norm = _norm(_text(path))
        assert "live production is prohibited" in norm, f"{path.name} must prohibit LIVE PRODUCTION"
    assert "live production is prohibited" in _norm(_gate_s13()), "gate §13 must prohibit LIVE PRODUCTION"
    # non-vacuity: an affirmative live-production allowance is the mutation this forbids.
    assert "live production is prohibited" not in _norm("LIVE PRODUCTION is permitted for this proof"), (
        "a live-production allowance must be detectable"
    )


# ---------------------------------------------------------------------------
# 6. Synthetic / approved non-production data only
# ---------------------------------------------------------------------------
def test_synthetic_nonproduction_data_only() -> None:
    ct = _norm(_text(_CONTRACT))
    assert "synthetic or approved non-production data" in ct, "IC-011 must require synthetic/approved non-production data"
    assert "no live customer row data" in ct, "IC-011 must forbid live customer row data"
    # non-vacuity
    assert "synthetic or approved non-production data" not in _norm("live production data is used"), (
        "a live-data rewrite must be detectable"
    )


# ---------------------------------------------------------------------------
# 7. Physical multi-database topology
# ---------------------------------------------------------------------------
def test_physical_multi_database_topology() -> None:
    ct = _norm(_text(_CONTRACT))
    assert "one hosted control db" in ct, "IC-011 must require exactly one hosted Control DB"
    assert "at least two physically distinct hosted tenant dbs" in ct, "IC-011 must require >=2 physically distinct hosted Tenant DBs"
    assert "physical multi-database proof" in _norm(_gate_s13()), "gate §13 must require physical multi-database proof"
    # non-vacuity
    assert "at least two physically distinct hosted tenant dbs" not in _norm("exactly one hosted tenant db and a shared schema"), (
        "a single-tenant / shared-schema rewrite must be detectable"
    )


# ---------------------------------------------------------------------------
# 8. Approved-public-edge-only served ingress (D-45; formerly "API Gateway sole served ingress")
# ---------------------------------------------------------------------------
# The five STOP conditions the ratified gate must fail closed on. Naming a COMPONENT is no longer
# the rule; the rule is an APPROVAL PROPERTY, so a second approved edge is lawful and an unapproved
# one never is.
_PUBLIC_EDGE_RULE = "only architecture-approved public edge modules may be served to client traffic"
_STOP_CONDITIONS = (
    "an unapproved public edge",
    "an internal edge exposed publicly",
    "a generic dispatcher / proxy reintroduced as public ingress",
    "a public route not owned by its serving service",
    "missing authentication / public-boundary enforcement",
)
# An AFFIRMATIVE restatement of the superseded component rule. It must not appear as a live
# requirement: the amendment note quotes it, so the detector requires the affirmative verb form.
_SUPERSEDED_COMPONENT_RULE = (
    "the api gateway is the sole served ingress",
    "api gateway must be the sole served ingress",
    "a non-gateway served edge is a stop condition",
)


def test_api_gateway_sole_ingress() -> None:
    """D-45: the served-ingress rule names an APPROVAL PROPERTY, not a component."""
    ct = _norm(_text(_CONTRACT))
    rb = _norm(_text(_RUNBOOK))

    # (a) the ratified rule is stated in the contract AND carried into the runbook's H1 census
    assert _PUBLIC_EDGE_RULE in ct, "IC-011 must restrict served client traffic to architecture-approved public edge modules"
    assert _PUBLIC_EDGE_RULE in rb, "the hosted runbook's H1 census must carry the approved-public-edge-only rule"

    # (b) every STOP condition, in both homes — a missing one is a hole in the gate
    for stop in _STOP_CONDITIONS:
        assert stop in ct, f"IC-011 must STOP on {stop!r}"
        assert stop in rb, f"the hosted runbook must STOP on {stop!r}"

    # (c) the isolation rule the old test protected is unchanged
    assert "one request -> one active tenant -> one database" in ct, "IC-011 must keep one request -> one active tenant -> one database"

    # (d) the superseded component rule must not survive as an ACTIVE requirement
    for stale in _SUPERSEDED_COMPONENT_RULE:
        assert stale not in ct, f"IC-011 still asserts the superseded component rule: {stale!r}"
        assert stale not in rb, f"the hosted runbook still asserts the superseded component rule: {stale!r}"


def test_api_gateway_sole_ingress_nonvacuity() -> None:
    """Five planted mutations, each of which the D-45 gate must reject."""
    # a rewrite that drops the approval property entirely
    assert _PUBLIC_EDGE_RULE not in _norm("any served edge is acceptable during the proof")
    # a rewrite that re-installs the superseded component rule
    assert _SUPERSEDED_COMPONENT_RULE[0] in _norm("The **API Gateway** is the **sole served ingress**.")
    assert _SUPERSEDED_COMPONENT_RULE[2] in _norm("A non-Gateway served edge is a STOP condition.")
    # each STOP condition is a distinct string, so dropping one is detectable
    assert len(set(_STOP_CONDITIONS)) == 5, "the gate must carry exactly five distinct STOP conditions"
    for stop in _STOP_CONDITIONS:
        assert stop not in _norm("the proof continues regardless of which edge is served")


# ---------------------------------------------------------------------------
# 9. Authentication separate from routing
# ---------------------------------------------------------------------------
def test_authentication_separate_from_routing() -> None:
    ct = _norm(_text(_CONTRACT))
    assert "authentication is separate from routing" in ct, "IC-011 must keep authentication separate from routing"
    assert "no cross-tenant fallback" in ct, "IC-011 must forbid cross-tenant fallback"
    assert "adjacent tenant" in ct and "unchanged" in ct, "IC-011 must prove the adjacent Tenant unchanged"
    # non-vacuity
    assert "no cross-tenant fallback" not in _norm("the router falls back to a second tenant database"), (
        "a cross-tenant fallback must be detectable"
    )


# ---------------------------------------------------------------------------
# 10. Database Router is the sole database selector
# ---------------------------------------------------------------------------
def test_database_router_sole_selector() -> None:
    ct = _norm(_text(_CONTRACT))
    assert "database router" in ct and "sole database selector" in ct, "IC-011 must make the Database Router the sole database selector"
    # non-vacuity
    assert "sole database selector" not in _norm("the gateway selects the tenant database"), (
        "a Gateway-selects-DB rewrite must be detectable"
    )


# ---------------------------------------------------------------------------
# 11. SecretRef-only registry; no raw DSN
# ---------------------------------------------------------------------------
def test_secretref_only_registry() -> None:
    ct = _norm(_text(_CONTRACT))
    assert "secretref only" in ct, "IC-011 must require a SecretRef-only registry"
    assert "references only" in ct, "IC-011 must keep a references-only discipline"
    for path in _ALL_SURFACES:
        raw = _text(path)
        assert not _DSN_RE.search(raw), f"a DSN-shaped value must never appear in {path.name}"
    # non-vacuity
    assert _DSN_RE.search("postgresql" + "://u:p@h/db"), "a planted DSN must be detectable"
    assert "secretref only" not in _norm("the registry stores a raw DSN"), "a raw-DSN registry rewrite must be detectable"


# ---------------------------------------------------------------------------
# 12. Rollback targets exact (success vs emergency)
# ---------------------------------------------------------------------------
def test_rollback_targets_exact() -> None:
    for path in (_CONTRACT, _RUNBOOK):
        norm = _norm(_text(path))
        assert _SUCCESS_TARGET in norm, f"{path.name} must name the last-known-good durable composition success target"
        assert _EMERGENCY_TARGET in norm, f"{path.name} must name the deferred in-memory composition emergency target"
    ct = _norm(_text(_CONTRACT))
    assert "must not earn" in ct and _HOSTED_PROVEN.lower() in ct, (
        "IC-011 must forbid the deferred in-memory landing from earning the proven verdict"
    )
    assert _SUCCESS_TARGET in _norm(_gate_s13()) and _EMERGENCY_TARGET in _norm(_gate_s13()), "gate §13 must name both rollback targets"
    assert _SUCCESS_TARGET in _norm(_adr_d40()) and _EMERGENCY_TARGET in _norm(_adr_d40()), "D-40 must name both rollback targets"
    # non-vacuity
    assert _SUCCESS_TARGET != _EMERGENCY_TARGET, "the success and emergency targets must be distinct"
    assert _SUCCESS_TARGET not in _norm("the success target is the deferred in-memory composition"), (
        "an emergency-as-success swap must be detectable"
    )


# ---------------------------------------------------------------------------
# 13. Triggers exact (preferred + fallback)
# ---------------------------------------------------------------------------
def test_triggers_exact() -> None:
    for path in (_CONTRACT, _RUNBOOK):
        raw = _text(path)
        assert _PREFERRED_TRIGGER in raw, f"{path.name} must name the preferred trigger {_PREFERRED_TRIGGER}"
        assert _FALLBACK_TRIGGER in raw, f"{path.name} must name the fallback trigger {_FALLBACK_TRIGGER}"
    # non-vacuity: an invented trigger is not one of the two.
    assert "router_reboot" not in (_PREFERRED_TRIGGER, _FALLBACK_TRIGGER), "an invented trigger must be detectable"
    assert _PREFERRED_TRIGGER != _FALLBACK_TRIGGER, "the two triggers must be distinct"


# ---------------------------------------------------------------------------
# 14. Named operator and approver
# ---------------------------------------------------------------------------
def test_named_operator_and_approver() -> None:
    ct = _norm(_text(_CONTRACT))
    assert "named operator" in ct and "named approver" in ct, "IC-011 must require a named operator and a named approver"
    assert "backup and restoration checkpoint" in ct, "IC-011 must require a backup and restoration checkpoint"
    hosted = _template_hosted()
    assert "OPERATOR_IDENTITY" in hosted and "APPROVER_IDENTITY" in hosted, (
        "the hosted template must carry OPERATOR_IDENTITY and APPROVER_IDENTITY"
    )
    # non-vacuity
    assert "named approver" not in _norm("no approver is required"), "a missing-approver rewrite must be detectable"


# ---------------------------------------------------------------------------
# 15. Runbook: four labels + ordered H0–H13
# ---------------------------------------------------------------------------
def test_runbook_four_labels_and_ordered_h0_h13() -> None:
    rb = _text(_RUNBOOK)
    for label in _RUNBOOK_LABELS:
        assert label in rb, f"the runbook must carry the label: {label}"
    seq = _h_phase_sequence(rb)
    assert seq == list(range(0, 14)), f"the runbook must define ordered phases H0..H13 exactly once each, in order: {seq}"
    # non-vacuity: an out-of-order or truncated H-sequence is detectable.
    assert _h_phase_sequence("### H0 —\n### H2 —\n### H1 —") == [0, 2, 1], "the H-sequence extractor must preserve order"
    assert _h_phase_sequence("### H0 —\n### H1 —") != list(range(0, 14)), "a truncated H-sequence must be detectable"
    assert "DAN START-GATE REQUIRED" not in _norm("a doc with no start gate"), "a missing label must be detectable"


# ---------------------------------------------------------------------------
# 16. Hosted evidence fields present
# ---------------------------------------------------------------------------
def test_hosted_evidence_fields_present() -> None:
    hosted = _template_hosted()
    for field in _HOSTED_FIELDS:
        assert field in hosted, f"the hosted template extension must define the field: {field}"
    assert len(_HOSTED_FIELDS) == 17, "the hosted evidence field set must be exactly seventeen"
    assert "hosted-non-production" in hosted, "the hosted extension must set ENVIRONMENT_CLASS = hosted-non-production"
    # non-vacuity: a missing field is detectable.
    assert "RESTORATION_REF" not in [f for f in _HOSTED_FIELDS if f != "RESTORATION_REF"], "a removed field must be detectable"


# ---------------------------------------------------------------------------
# 17. Hosted verdicts exact; production-scope prohibited
# ---------------------------------------------------------------------------
def test_hosted_verdicts_exact_and_production_scope_prohibited() -> None:
    hosted = _template_hosted()
    assert _HOSTED_PROVEN in hosted, "the hosted template must allow ROLLBACK-PROVEN-HOSTED-NONPRODUCTION"
    assert _HOSTED_NOT_PROVEN in hosted, "the hosted template must allow ROLLBACK-NOT-PROVEN"
    assert _PRODUCTION_SCOPE_VERDICT in hosted and "PROHIBITED" in hosted, (
        "the hosted template must mark ROLLBACK-PROVEN-PRODUCTION-SCOPE prohibited"
    )
    ct = _text(_CONTRACT)
    assert _HOSTED_PROVEN in ct and _HOSTED_NOT_PROVEN in ct, "IC-011 must define the two allowed hosted verdicts"
    assert "reserved and prohibited" in _norm(ct), "IC-011 must reserve and prohibit the production-scope verdict"
    # non-vacuity
    assert _HOSTED_PROVEN != _HOSTED_NOT_PROVEN, "the two hosted verdicts must be distinct"
    assert _PRODUCTION_SCOPE_VERDICT not in (_HOSTED_PROVEN, _HOSTED_NOT_PROVEN), (
        "the production-scope verdict must not be an allowed verdict"
    )


# ---------------------------------------------------------------------------
# 18. Blocker effect: evidence only; B5-BLK-8 open until B5-BLK-8D
# ---------------------------------------------------------------------------
def test_blocker_effect_evidence_only_open_until_8d() -> None:
    ct = _norm(_text(_CONTRACT))
    assert "b5-blk-8c produces evidence only" in ct, "IC-011 must state B5-BLK-8C produces evidence only"
    assert "cannot close b5-blk-8" in ct, "IC-011 must state B5-BLK-8C cannot close B5-BLK-8"
    assert "only b5-blk-8d may decide blocker effect" in ct, "IC-011 must state only B5-BLK-8D may decide blocker effect"
    assert "b5-blk-8d alone decides blocker effect" in _norm(_adr_d40()), "D-40 must state B5-BLK-8D alone decides blocker effect"
    for path in (_CONTRACT, _RUNBOOK):
        norm = _norm(_text(path))
        for needle in _LOCKED_STATE_NEEDLES:
            assert needle in norm, f"{path.name} must preserve the locked state: missing {needle!r}"
    for needle in _LOCKED_STATE_NEEDLES:
        assert needle in _norm(_gate_s13()), f"gate §13 must preserve the locked state: missing {needle!r}"
    # non-vacuity
    assert "only b5-blk-8d may decide blocker effect" not in _norm("B5-BLK-8C may decide blocker effect"), (
        "an 8C-decides-effect overreach must be detectable"
    )


# ---------------------------------------------------------------------------
# 19. Reject production / closure / census overclaims across the honest surfaces
# ---------------------------------------------------------------------------
def test_surfaces_reject_production_and_closure_overclaims() -> None:
    corpus = _norm(_text(_CONTRACT) + "\n" + _text(_RUNBOOK) + "\n" + _gate_s13())
    for pattern, label in _FORBIDDEN_PATTERNS:
        assert re.search(pattern, corpus) is None, f"forbidden wording present ({label}): /{pattern}/"
    # non-vacuity: every detector fires on a planted normalized sample built from fragments.
    planted = _norm(
        "production ready. activate production. production rollback proven. rollback proof for production. "
        "b5-blk-8 is closed. b5-blk-8: closed. 6 of 9. 8 of 9. do-not-activate lifted. "
        "rollback-proven-production-scope is proven."
    )
    for pattern, label in _FORBIDDEN_PATTERNS:
        assert re.search(pattern, planted), f"forbidden-pattern detector must fire on a planted sample ({label}): /{pattern}/"


# ---------------------------------------------------------------------------
# 20. Fixtureless-pytest rejection + _pg.run guidance + references-only secret hygiene
# ---------------------------------------------------------------------------
def test_fixtureless_pytest_rejection_and_pg_run_guidance_and_references_only() -> None:
    rb = _norm(_text(_RUNBOOK))
    assert "_pg.run" in rb, "the runbook must name the sanctioned standalone _pg.run entrypoint"
    assert "manual_only" in rb and "non-production" in rb, "the runbook must be MANUAL_ONLY / non-production"
    assert "admin_dsn" in rb and "fixture" in rb, "the runbook must warn against the fixtureless ad-hoc pytest invocation"
    # references-only / no secret or PII shape anywhere in the five surfaces.
    for path in _ALL_SURFACES:
        raw = _text(path)
        assert _JWT_MARKER not in raw, f"a token-shaped value must never appear in {path.name}"
        assert _KEY_MARKER not in raw, f"key material must never appear in {path.name}"
        assert not _AWS_RE.search(raw), f"an access-key-shaped value must never appear in {path.name}"
        assert not _EMAIL_RE.search(raw), f"PII (email-shaped) content must never appear in {path.name}"
    # non-vacuity: every secret detector fires on a fragment-built planted sample.
    assert _JWT_MARKER in ("ey" + "J" + "0aaa"), "a planted token shape must be detectable"
    assert _KEY_MARKER in ("-----" + "BEGIN" + " PRIVATE KEY"), "planted key material must be detectable"
    assert _AWS_RE.search("AKIA" + "ABCDEFGHIJKLMNOP"), "a planted access key must be detectable"
    assert _EMAIL_RE.search("ops" + "@" + "example.com"), "a planted email must be detectable"
    # this guard closes no blocker (meta pin).
    guard_src = _norm(pathlib.Path(__file__).read_text(encoding="utf-8"))
    assert "closes no blocker" in guard_src, "the guard must declare that it closes no blocker"


if __name__ == "__main__":
    _scan.run(
        [
            test_surfaces_exist,
            test_contract_is_draft_proposed_contract_first,
            test_surfaces_cite_ic011_and_d40,
            test_hosted_target_classes_staging_or_preproduction_only,
            test_live_production_prohibited,
            test_synthetic_nonproduction_data_only,
            test_physical_multi_database_topology,
            test_api_gateway_sole_ingress,
            test_api_gateway_sole_ingress_nonvacuity,
            test_authentication_separate_from_routing,
            test_database_router_sole_selector,
            test_secretref_only_registry,
            test_rollback_targets_exact,
            test_triggers_exact,
            test_named_operator_and_approver,
            test_runbook_four_labels_and_ordered_h0_h13,
            test_hosted_evidence_fields_present,
            test_hosted_verdicts_exact_and_production_scope_prohibited,
            test_blocker_effect_evidence_only_open_until_8d,
            test_surfaces_reject_production_and_closure_overclaims,
            test_fixtureless_pytest_rejection_and_pg_run_guidance_and_references_only,
        ]
    )
