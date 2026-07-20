"""B5-BLK-8A — rollback-evidence-scaffold text-drift guard (default suite; no DB, no network).

Static text-only boundary pins for the B5-BLK-8A rollback evidence scaffold:

  - infrastructure/runbooks/b5_blk8_rollback_to_deferred_composition.md
  - docs/runtime/b5_blk8_rollback_evidence_template.md

This guard binds no runtime, imports no database driver, opens no socket, and touches no database. It
exists to keep the rollback runbook and its references-only evidence template an honest,
NON-PRODUCTION / MANUAL_ONLY documentation-only scaffold, and to fail CLOSED on any production /
closure / destructive-rollback / secret-leak / census-drift overclaim.

Exactly twelve tests (1:1 with the twelve-mutation battery):

 1. test_manifest_runbook_and_template_exist
 2. test_runbook_is_manual_only_and_nonproduction
 3. test_runbook_requires_rollback_to_deferred_inmemory_composition
 4. test_runbook_requires_four_gate_s7_triggers
 5. test_runbook_requires_d24_nondestructive_no_tenant_data_deletion
 6. test_runbook_requires_d30_per_tenant_isolation
 7. test_runbook_requires_failure_recording
 8. test_runbook_rejects_production_and_closure_overclaims
 9. test_template_requires_mandatory_fields_and_enums
10. test_template_requires_before_after_digests_and_adjacent_tenant
11. test_scaffold_is_references_only_and_rejects_secret_shaped_literals
12. test_scaffold_preserves_blk8_open_and_census_and_do_not_activate

This scaffold closes no blocker. B5-BLK-8 remains OPEN; the live blocker census remains 7 of 9 OPEN;
production remains NOT READY / DO-NOT-ACTIVATE. The guard positively requires exactly that and rejects
any drift.

Pure stdlib; standalone-runnable:
  python tests/architecture/test_b5_blk8_rollback_evidence_scaffold_boundaries.py
"""

from __future__ import annotations

import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

_RUNBOOK = _scan.REPO_ROOT / "infrastructure" / "runbooks" / "b5_blk8_rollback_to_deferred_composition.md"
_TEMPLATE = _scan.REPO_ROOT / "docs" / "runtime" / "b5_blk8_rollback_evidence_template.md"

# --- runbook positive needles (matched against the normalized text) -----------------------------
_RUNBOOK_MANUAL_NEEDLES = ["manual_only", "non-production", "documentation-only"]
_RUNBOOK_INMEMORY_NEEDLES = ["deferred (in-memory) composition", "in-memory", "construction performs no i/o"]
_GATE_S7_TRIGGERS = ["identity mismatch", "distinctness regression", "router anomaly", "secret-resolution failure"]
_RUNBOOK_NONDESTRUCTIVE_NEEDLES = ["d-24", "non-destructive", "never deletes tenant business data"]
_RUNBOOK_ISOLATION_NEEDLES = ["d-30", "per-tenant", "isolated", "one request -> one active tenant -> one database"]
_RUNBOOK_FAILURE_NEEDLES = ["records the failure", "trigger reason"]

# --- template positive needles (matched against the raw text; field/enum tokens are case-sensitive)
_TEMPLATE_REQUIRED_FIELDS = [
    "EXECUTION_ID",
    "EXECUTION_DATE",
    "OPERATOR",
    "ENVIRONMENT_CLASS",
    "BASELINE_MAIN_SHA",
    "ACTIVATION_MODE",
    "ROLLBACK_TRIGGER",
    "ROLLBACK_PLAN_REF",
    "PRE_ROLLBACK_STATE_REF",
    "POST_ROLLBACK_STATE_REF",
    "TENANT_SCOPE",
    "ADJACENT_TENANT_SCOPE",
    "BEFORE_DATA_DIGEST",
    "AFTER_DATA_DIGEST",
    "ISOLATION_ASSERTION",
    "NON_DESTRUCTIVE_ASSERTION",
    "FAILURE_RECORD_REF",
    "AUDIT_RECORD_REF",
    "SECRET_REFERENCE_ONLY_ASSERTION",
    "DEFERRED_COMPOSITION_ASSERTION",
    "DISPOSAL_ASSERTION",
    "FINAL_VERDICT",
]
_ROLLBACK_TRIGGER_ENUM = [
    "identity_mismatch",
    "distinctness_regression",
    "router_anomaly",
    "secret_resolution_failure",
    "audit_sink_unavailable",
    "migration_readiness_failure",
    "operator_directed_abort",
]
_FINAL_VERDICT_ENUM = ["DO-NOT-ACTIVATE", "ROLLBACK-PROVEN-LOCAL"]
_TEMPLATE_DIGEST_NEEDLES = ["BEFORE_DATA_DIGEST", "AFTER_DATA_DIGEST", "ADJACENT_TENANT_SCOPE"]

# --- forbidden production / closure / destructive-rollback / census patterns (normalized text) ---
# Each entry rejects an overclaim; the runbook's honest scaffold framing must never trip these.
_FORBIDDEN_PATTERNS = [
    (r"production\s+ready", "'production ready' overclaim"),
    (r"production\s+activation\s+authorized", "'production activation authorized' overclaim"),
    (r"activate\s+production", "'activate production' overclaim"),
    (r"production\s+rollback\s+proven", "'production rollback proven' overclaim"),
    (r"rollback\s+proof\s+(?:for\s+)?production", "'rollback proof for production' overclaim"),
    (r"b5-?blk-?8\s+(?:is\s+|now\s+)?closed", "'B5-BLK-8 closed' overclaim"),
    (r"b5-?blk-?8\s*[:=]\s*closed", "'B5-BLK-8: closed' overclaim"),
    (r"\b6\s*(?:of|/)\s*9\b", "false census '6 of 9'"),
    (r"\b8\s*(?:of|/)\s*9\b", "stale census '8 of 9'"),
    (r"destructive\s+rollback\s+authoriz", "'destructive rollback authorized' overclaim"),
    (r"delete[sd]?\s+tenant\s+data", "'delete tenant data' destructive claim"),
    (r"drop\s+tenant\s+database", "'drop tenant database' destructive claim"),
]

# --- locked-state needles required in BOTH documents (normalized text) ---------------------------
_LOCKED_STATE_NEEDLES = ["b5-blk-8 remains open", "7 of 9 open", "not ready / do-not-activate"]

# --- secret/PII shape detectors (BUILT from low-entropy fragments — never a contiguous shape here) -
_DSN_RE = re.compile("postgresql" + "://" + r"\S")
_JWT_MARKER = "ey" + "J"
_KEY_MARKER = "-----" + "BEGIN"
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")


def _text(path: pathlib.Path) -> str:
    assert path.is_file(), f"{path.relative_to(_scan.REPO_ROOT).as_posix()} must exist"
    return path.read_text(encoding="utf-8")


def _norm(s: str) -> str:
    """Lowercase, normalize dash/arrow glyphs, drop markdown emphasis, and collapse whitespace."""
    s = s.lower()
    s = s.replace("—", "-").replace("–", "-").replace("→", "->")
    s = s.replace("*", "").replace("`", "")
    return re.sub(r"\s+", " ", s)


def test_manifest_runbook_and_template_exist() -> None:
    assert _RUNBOOK.is_file(), "the B5-BLK-8A rollback runbook must exist at the manifest path"
    assert _TEMPLATE.is_file(), "the B5-BLK-8A rollback evidence template must exist at the manifest path"


def test_runbook_is_manual_only_and_nonproduction() -> None:
    norm = _norm(_text(_RUNBOOK))
    for needle in _RUNBOOK_MANUAL_NEEDLES:
        assert needle in norm, f"runbook must be labeled MANUAL_ONLY / non-production: missing {needle!r}"


def test_runbook_requires_rollback_to_deferred_inmemory_composition() -> None:
    norm = _norm(_text(_RUNBOOK))
    for needle in _RUNBOOK_INMEMORY_NEEDLES:
        assert needle in norm, f"runbook must require rollback to the deferred in-memory composition: missing {needle!r}"


def test_runbook_requires_four_gate_s7_triggers() -> None:
    norm = _norm(_text(_RUNBOOK))
    for trigger in _GATE_S7_TRIGGERS:
        assert trigger in norm, f"runbook must list the gate §7 post-activation trigger: missing {trigger!r}"


def test_runbook_requires_d24_nondestructive_no_tenant_data_deletion() -> None:
    norm = _norm(_text(_RUNBOOK))
    for needle in _RUNBOOK_NONDESTRUCTIVE_NEEDLES:
        assert needle in norm, f"runbook must state the D-24 non-destructive discipline: missing {needle!r}"


def test_runbook_requires_d30_per_tenant_isolation() -> None:
    norm = _norm(_text(_RUNBOOK))
    for needle in _RUNBOOK_ISOLATION_NEEDLES:
        assert needle in norm, f"runbook must state the D-30 per-tenant isolation discipline: missing {needle!r}"


def test_runbook_requires_failure_recording() -> None:
    norm = _norm(_text(_RUNBOOK))
    for needle in _RUNBOOK_FAILURE_NEEDLES:
        assert needle in norm, f"runbook must record the failure and its trigger reason: missing {needle!r}"


def test_runbook_rejects_production_and_closure_overclaims() -> None:
    norm = _norm(_text(_RUNBOOK))
    for pattern, label in _FORBIDDEN_PATTERNS:
        assert re.search(pattern, norm) is None, f"forbidden wording present in runbook ({label}): /{pattern}/"
    # non-vacuity: every detector must fire on a planted normalized sample built from fragments.
    planted = _norm(
        "production ready. production activation authorized. activate production. "
        "production rollback proven. rollback proof for production. b5-blk-8 is closed. "
        "b5-blk-8: closed. 6 of 9. 8 of 9. destructive rollback authorized. "
        "deletes tenant data. drop tenant database."
    )
    for pattern, label in _FORBIDDEN_PATTERNS:
        assert re.search(pattern, planted), f"forbidden-pattern detector must fire on a planted sample ({label}): /{pattern}/"


def test_template_requires_mandatory_fields_and_enums() -> None:
    text = _text(_TEMPLATE)
    for field in _TEMPLATE_REQUIRED_FIELDS:
        assert field in text, f"template must define the mandatory field: {field}"
    for member in _ROLLBACK_TRIGGER_ENUM:
        assert member in text, f"template must enumerate the ROLLBACK_TRIGGER value: {member}"
    for member in _FINAL_VERDICT_ENUM:
        assert member in text, f"template must enumerate the FINAL_VERDICT value: {member}"


def test_template_requires_before_after_digests_and_adjacent_tenant() -> None:
    text = _text(_TEMPLATE)
    for needle in _TEMPLATE_DIGEST_NEEDLES:
        assert needle in text, f"template must require before/after digests and adjacent-tenant evidence: {needle}"


def test_scaffold_is_references_only_and_rejects_secret_shaped_literals() -> None:
    template_norm = _norm(_text(_TEMPLATE))
    assert "references only" in template_norm, "template must declare a references-only discipline"
    assert "ref:" in _text(_TEMPLATE), "template must use ref:... reference placeholders"
    for path in (_RUNBOOK, _TEMPLATE):
        raw = _text(path)
        assert not _DSN_RE.search(raw), f"a DSN-shaped value must never appear in {path.name}"
        assert _JWT_MARKER not in raw, f"a token-shaped value must never appear in {path.name}"
        assert _KEY_MARKER not in raw, f"key material must never appear in {path.name}"
        assert not _EMAIL_RE.search(raw), f"PII (email-shaped) content must never appear in {path.name}"
    # non-vacuity: every detector must fire on a fragment-built planted sample.
    assert _DSN_RE.search("postgresql" + "://u:p@h/db"), "a planted DSN must be detectable"
    assert _JWT_MARKER in ("ey" + "J" + "0aaa"), "a planted token shape must be detectable"
    assert _KEY_MARKER in ("-----" + "BEGIN" + " PRIVATE KEY"), "planted key material must be detectable"
    assert _EMAIL_RE.search("ops" + "@" + "example.com"), "a planted email must be detectable"


def test_scaffold_preserves_blk8_open_and_census_and_do_not_activate() -> None:
    for path in (_RUNBOOK, _TEMPLATE):
        norm = _norm(_text(path))
        for needle in _LOCKED_STATE_NEEDLES:
            assert needle in norm, f"{path.name} must preserve the locked state: missing {needle!r}"
    guard_src = _norm(pathlib.Path(__file__).read_text(encoding="utf-8"))
    assert "closes no blocker" in guard_src, "the guard must declare that it closes no blocker"


if __name__ == "__main__":
    _scan.run(
        [
            test_manifest_runbook_and_template_exist,
            test_runbook_is_manual_only_and_nonproduction,
            test_runbook_requires_rollback_to_deferred_inmemory_composition,
            test_runbook_requires_four_gate_s7_triggers,
            test_runbook_requires_d24_nondestructive_no_tenant_data_deletion,
            test_runbook_requires_d30_per_tenant_isolation,
            test_runbook_requires_failure_recording,
            test_runbook_rejects_production_and_closure_overclaims,
            test_template_requires_mandatory_fields_and_enums,
            test_template_requires_before_after_digests_and_adjacent_tenant,
            test_scaffold_is_references_only_and_rejects_secret_shaped_literals,
            test_scaffold_preserves_blk8_open_and_census_and_do_not_activate,
        ]
    )
