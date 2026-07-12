"""DBR-AR-2 V1 — durable routing-audit CONTRACT guard (text-inspection only; no runtime, no driver import).

Pins the DBR-AR-2 V1 contract-capture record (PRD DBR-AR-2 V1, 2026-07-12, baseline
ac6ca9da48837b5c06cf6a9f1663af73fedf1b74) as evolved by DBR-AR-2A (2026-07-13): the dedicated contract document
and the readiness-matrix cross-reference must keep DBR-AR-2 OPEN, keep every B5-E decision sentence intact,
commit to the selected architecture (Option B — Control-Plane-owned durable routing-audit store behind a service
boundary), carry the event-schema minimums and the forbidden-data list, state explicit failure semantics with no
silent fail-open, claim no cross-database atomicity, authorize no cross-service import, claim no delivered
persistence / schema / production wiring, keep the blocker count at 8 of 9, record the implementation-slice
sequence and the exact next governed step, and carry the exact DBR-AR-2A status block (2A implemented when its
PR merges; DBR-AR-2 remains OPEN; 2B-2E not started) plus the Before/After early-denial coverage sentences.
Every detector carries a planted-mutation non-vacuity companion (PRD §12/§19 batteries). Text inspection only —
pure stdlib; standalone-runnable:
  python tests/architecture/test_dbr_ar_2_readiness_contract.py
"""

from __future__ import annotations

import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

_RUNTIME = _scan.REPO_ROOT / "docs" / "runtime"
_CONTRACT_DOC = _RUNTIME / "dbr_ar_2_durable_routing_audit_contract.md"
_MATRIX_DOC = _RUNTIME / "b5_runtime_readiness_matrix.md"
_BOTH_DOCS = (_CONTRACT_DOC, _MATRIX_DOC)

_BASELINE = "ac6ca9da48837b5c06cf6a9f1663af73fedf1b74"

# --- exact normalized anchors (lower-case; '*' and '`' stripped; whitespace collapsed) ---
_DBR_OPEN_SENTENCE = "dbr-ar-2 (durable routing audit) remains open — a separate database router follow-on"
_V1_STATUS_SENTENCE = (
    "dbr-ar-2 remains open. this v1 records the implementation contract only. no durable routing-audit adapter,"
    " schema, production wiring or activation change is delivered by v1."
)
_DECISION_A_SENTENCE = "decision a (b5-e, 2026-07-12, dan-authorized): b5-blk-4 — closed — evidence-bound governance decision"
_DECISION_B_SENTENCE = "decision b (b5-e, 2026-07-12, dan-authorized): physical multi-database mvp — accepted at database granularity"
_FAIL_CLOSED_SENTENCE = "production runtime activation remains not ready / do-not-activate — 8 of 9 activation blockers remain open"
_LOVABLE_SENTENCE = "the lovable cutover remains open"
_ARCH_SENTENCE = "selected architecture: option b — control-plane-owned durable routing-audit store behind a service boundary"
_NO_ATOMICITY_SENTENCE = (
    "no atomicity is claimed across the control database and any tenant database;"
    " there is no distributed transaction and no two-phase commit"
)
_NO_IMPORT_SENTENCE = "no cross-service import is authorized"
_NEXT_STEP_SENTENCE = "next implementation slice after dbr-ar-2a is merged, post-merge verified, and target-branch cleaned: dbr-ar-2b."

# --- DBR-AR-2A status + coverage anchors (contract doc only; the matrix carries none) ---
_2A_STATUS_SENTENCE = "dbr-ar-2a — implemented when this pr merges."
_2A_OPEN_SENTENCE = "dbr-ar-2 — remains open."
_2A_SLICES_SENTENCE = "dbr-ar-2b through dbr-ar-2e — not started."
_BEFORE_2A_SENTENCE = (
    "before dbr-ar-2a: two pre-target denials (tenant_routing_unavailable, no_active_tenant) had no router-edge audit event."
)
_AFTER_2A_SENTENCE = "after dbr-ar-2a: every completed or denied route() invocation produces exactly one router-edge in-memory event."
_DURABILITY_SENTENCE = "durability remains unimplemented."
_2A_ANCHORS = (
    _2A_STATUS_SENTENCE,
    _2A_OPEN_SENTENCE,
    _2A_SLICES_SENTENCE,
    _BEFORE_2A_SENTENCE,
    _AFTER_2A_SENTENCE,
    _DURABILITY_SENTENCE,
)

_REQUIRED_SCHEMA_FIELDS = (
    "event_id",
    "event_version",
    "occurred_at",
    "recorded_at",
    "correlation_id",
    "actor_ref",
    "tenant_ref",
    "resolved_tenant_ref",
    "action",
    "outcome",
    "public_code",
    "association_store_ref",
    "association_version",
    "source_service",
    "source_version",
)
_FORBIDDEN_DATA_TERMS = (
    "raw dsns",
    "passwords",
    "private keys",
    "jwts",
    "bearer tokens",
    "authorization headers",
    "request/response bodies",
    "tenant result data",
    "secret values",
    "unnecessary personal data",
)
# the seven §11 failure conditions -> the classification token that must appear on the same row
_FAILURE_ROWS = (
    ("audit sink unavailable before dispatch", "fail closed"),
    ("audit write fails after successful dispatch", "fail open with alert"),
    ("denial event cannot be recorded", "fail open with alert"),
    ("retry causes duplicate audit submission", "retryable"),
    ("audit storage becomes read-only", "fail closed"),
    ("audit queue is full", "fail closed"),
    ("partial outage / network partition", "fail closed"),
)
_LIVE_PROOF_ANCHORS = (
    "successful route durably recorded",
    "denied route durably recorded",
    "unknown tenant recorded with zero tenant-db dispatch",
    "dormant standing tenant recorded",
    "audit event survives process restart",
    "duplicate submission is idempotent",
    "no credential / raw dsn / token / private key stored",
    "one request → one tenant → one database",
    "audit-sink failure follows the §10 posture",
    "append-only enforced",
    "cross-tenant audit reads denied",
    "standing topology unchanged by proof",
    "production activation remains blocked",
)
_SLICE_IDS = ("dbr-ar-2a", "dbr-ar-2b", "dbr-ar-2c", "dbr-ar-2d", "dbr-ar-2e")


def _norm(text: str) -> str:
    return " ".join(text.lower().replace("*", "").replace("`", "").split())


def _contract() -> str:
    return _CONTRACT_DOC.read_text(encoding="utf-8")


def _matrix() -> str:
    return _MATRIX_DOC.read_text(encoding="utf-8")


def _both() -> str:
    return _contract() + "\n" + _matrix()


# ---------------------------------------------------------------------------
# Presence pins (guard requirements, PRD §11)
# ---------------------------------------------------------------------------
def test_dbr2_docs_exist() -> None:
    assert _CONTRACT_DOC.is_file(), "missing docs/runtime/dbr_ar_2_durable_routing_audit_contract.md"
    assert _MATRIX_DOC.is_file(), "missing docs/runtime/b5_runtime_readiness_matrix.md"


def test_dbr2_baseline_pinned() -> None:
    assert _BASELINE in _contract(), "the contract doc must pin the exact verified baseline"
    assert _BASELINE in _matrix(), "the matrix cross-reference must pin the exact verified baseline"


def test_dbr2_baseline_nonvacuity() -> None:
    assert _BASELINE not in _contract().replace(_BASELINE, "ffffffff"), "baseline pin must detect removal"


def test_dbr2_open_status_pinned_per_document() -> None:
    for doc in _BOTH_DOCS:
        norm = _norm(doc.read_text(encoding="utf-8"))
        assert _DBR_OPEN_SENTENCE in norm, f"{doc.name} must carry the exact DBR-AR-2 open/follow-on sentence"
        assert _V1_STATUS_SENTENCE in norm, f"{doc.name} must carry the exact V1 status sentence"


def test_dbr2_open_status_nonvacuity() -> None:
    for doc in _BOTH_DOCS:
        norm = _norm(doc.read_text(encoding="utf-8"))
        assert _DBR_OPEN_SENTENCE not in norm.replace(_DBR_OPEN_SENTENCE, ""), doc.name
        assert _V1_STATUS_SENTENCE not in norm.replace(_V1_STATUS_SENTENCE, ""), doc.name
    assert _V1_STATUS_SENTENCE not in _norm("dbr-ar-2 remains open. v1 records a contract."), "shortened status must not satisfy"


def test_dbr2_standing_decisions_restated_intact() -> None:
    norm = _norm(_contract())
    assert _DECISION_A_SENTENCE in norm, "the contract doc must restate Decision A (B5-BLK-4 CLOSED) verbatim"
    assert _DECISION_B_SENTENCE in norm, "the contract doc must restate Decision B (MVP accepted at database granularity) verbatim"
    assert _FAIL_CLOSED_SENTENCE in norm, "the contract doc must restate the fail-closed 8-of-9 activation sentence verbatim"
    assert _LOVABLE_SENTENCE in norm, "the contract doc must record the Lovable cutover as OPEN"


def test_dbr2_standing_decisions_nonvacuity() -> None:
    norm = _norm(_contract())
    for anchor in (_DECISION_A_SENTENCE, _DECISION_B_SENTENCE, _FAIL_CLOSED_SENTENCE, _LOVABLE_SENTENCE):
        assert anchor not in norm.replace(anchor, ""), anchor


def test_dbr2_selected_architecture_pinned() -> None:
    assert _ARCH_SENTENCE in _norm(_contract()), "the contract doc must pin the exact selected-architecture sentence"
    assert "option b" in _norm(_matrix()), "the matrix cross-reference must name the selected architecture"


# Mutation 6 (architecture removed) + 7 (architecture changed without a decision update).
_ARCH_CHANGED_RE = re.compile(r"selected architecture:?\s*option\s+(?:a|c|d)\b")


def test_dbr2_architecture_not_changed_silently() -> None:
    assert not _ARCH_CHANGED_RE.search(_norm(_both())), "a different selected architecture requires a recorded decision update"


def test_dbr2_architecture_nonvacuity() -> None:
    assert _ARCH_SENTENCE not in _norm(_contract()).replace(_ARCH_SENTENCE, "")
    assert _ARCH_CHANGED_RE.search("selected architecture: option a — router-owned store")
    assert _ARCH_CHANGED_RE.search("selected architecture: option d")
    assert not _ARCH_CHANGED_RE.search("selected architecture: option b — control-plane-owned")
    assert not _ARCH_CHANGED_RE.search("option a — database router-owned durable store (rejected)")


def test_dbr2_event_schema_minimums() -> None:
    norm = _norm(_contract())
    for field in _REQUIRED_SCHEMA_FIELDS:
        assert field in norm, f"event-schema minimum field missing from the contract doc: {field}"


def test_dbr2_event_schema_nonvacuity() -> None:
    norm = _norm(_contract())
    assert "event_id" not in norm.replace("event_id", "evt"), "schema pin must detect field removal"


def test_dbr2_forbidden_data_list() -> None:
    norm = _norm(_contract())
    for term in _FORBIDDEN_DATA_TERMS:
        assert term in norm, f"forbidden-data term missing from the contract doc: {term}"


def test_dbr2_forbidden_data_nonvacuity() -> None:
    norm = _norm(_contract())
    assert "tenant result data" not in norm.replace("tenant result data", ""), "forbidden-data pin must detect removal"


def _norm_line(raw_line: str) -> str:
    return " ".join(raw_line.lower().replace("*", "").replace("`", "").split())


def test_dbr2_failure_semantics_explicit() -> None:
    # Row-scoped (ATR-V2: no 400-char window bleed — a neighbor row's classification
    # token can never satisfy a different row): every physical line carrying a §11
    # condition must carry that condition's classification on the SAME line.
    lines = [_norm_line(raw) for raw in _contract().splitlines()]
    for condition, classification in _FAILURE_ROWS:
        rows = [line for line in lines if condition in line]
        assert rows, f"failure condition missing from the contract doc: {condition}"
        for row in rows:
            assert classification in row, f"condition {condition!r} must carry the classification {classification!r} on its own row"


def test_dbr2_failure_semantics_nonvacuity() -> None:
    norm = _norm(_contract())
    gutted = norm.replace("audit sink unavailable before dispatch", "")
    assert "audit sink unavailable before dispatch" not in gutted, "failure-row pin must detect removal"
    # a row whose classification was stripped is detected on its own line (no window bleed
    # from an adjacent classified row)
    fabricated = _norm_line("| 1 | Audit sink unavailable before dispatch | (unclassified) | the request proceeds |")
    assert "audit sink unavailable before dispatch" in fabricated and "fail closed" not in fabricated
    neighbor_bleed = [
        _norm_line("| 5 | Audit storage becomes read-only | (unclassified) | writes fail |"),
        _norm_line("| 6 | Audit queue is full | fail closed | no queue exists |"),
    ]
    assert "fail closed" not in neighbor_bleed[0] and "fail closed" in neighbor_bleed[1]


def test_dbr2_denial_events_recorded() -> None:
    norm = _norm(_contract())
    assert "routedenied" in norm, "the RouteDenied denial event class must be recorded"
    assert "route denied (any router-edge denial) | record" in norm, "route-denial events must be RECORD"
    assert "unknown tenant (router edge) | record" in norm, "unknown-tenant denial must be RECORD"
    assert "tenant_not_ready" in norm and "tenant_access_denied" in norm, "the auth/gateway-edge denial codes must be covered"


def test_dbr2_denial_events_nonvacuity() -> None:
    norm = _norm(_contract())
    assert "route denied (any router-edge denial) | record" not in norm.replace(
        "route denied (any router-edge denial) | record", "route denied | omitted"
    )


def test_dbr2_idempotency_defined() -> None:
    norm = _norm(_contract())
    assert "deduplication key: event_id" in norm, "the deduplication key must be defined"
    assert "duplicate submission is idempotent" in norm or "duplicate-tolerant" in norm, "duplicate tolerance must be defined"
    assert "order" in norm and "identity column" in norm, "the ordering authority must be defined"


def test_dbr2_idempotency_nonvacuity() -> None:
    norm = _norm(_contract())
    assert "deduplication key: event_id" not in norm.replace("deduplication key: event_id", "deduplication key: tbd")


def test_dbr2_live_proof_plan_present() -> None:
    norm = _norm(_contract())
    for anchor in _LIVE_PROOF_ANCHORS:
        assert anchor in norm, f"live-proof item missing from the contract doc: {anchor}"


def test_dbr2_live_proof_nonvacuity() -> None:
    norm = _norm(_contract())
    assert "audit event survives process restart" not in norm.replace("audit event survives process restart", "")


def test_dbr2_slice_sequence_recorded() -> None:
    norm = _norm(_contract())
    for slice_id in _SLICE_IDS:
        assert slice_id in norm, f"implementation slice missing from the contract doc: {slice_id}"
    assert _NEXT_STEP_SENTENCE in norm, "the exact next governed step must be recorded"


def test_dbr2_slice_sequence_nonvacuity() -> None:
    norm = _norm(_contract())
    assert "dbr-ar-2e" not in norm.replace("dbr-ar-2e", "dbr-ar-2x")
    assert _NEXT_STEP_SENTENCE not in norm.replace(_NEXT_STEP_SENTENCE, "next governed step: unstated")


# ---------------------------------------------------------------------------
# Mutation detectors (PRD §12). Finite vocabularies; explicit negation masking.
# ---------------------------------------------------------------------------
_DONE_WORDS = (
    "complete",
    "completed",
    "done",
    "closed",
    "achieved",
    "wired",
    "in place",
    "in-place",
    "landed",
    "built",
    "implemented",
    "delivered",
    "finished",
    "satisfied",
    "shipped",
)
_OPEN_MARKER_RE = re.compile(r"\b(?:open|in-memory|follow-on|not|pending|remains|absent|outstanding|reserved|future)\b")


def _mask_v1_status(norm_text: str) -> str:
    # Exact-sentence masks only: any variant of a closure claim still trips m01.
    masked = norm_text.replace(_V1_STATUS_SENTENCE, " <v1-status-sentence> ")
    return masked.replace(_2A_STATUS_SENTENCE, " <2a-status-sentence> ")


# Mutation 1 — DBR-AR-2 marked closed (G9-shaped, scoped to routing-audit lines).
def _claims_dbr2_complete(text: str) -> bool:
    for raw_line in text.lower().splitlines():
        line = _mask_v1_status(" ".join(raw_line.replace("*", "").replace("`", "").split()))
        if "dbr-ar-2" not in line and "routing audit" not in line and "routing-audit" not in line:
            continue
        if _OPEN_MARKER_RE.search(line):
            continue
        if any(w in line for w in _DONE_WORDS):
            return True
    return False


def test_dbr2_m01_not_marked_closed() -> None:
    assert not _claims_dbr2_complete(_both()), "DBR-AR-2 must not be claimed closed/complete anywhere in the two documents"


def test_dbr2_m01_nonvacuity() -> None:
    assert _claims_dbr2_complete("DBR-AR-2 is closed")
    for word in _DONE_WORDS:
        assert _claims_dbr2_complete(f"the durable routing audit is {word}"), word
    assert not _claims_dbr2_complete("DBR-AR-2 (durable routing audit) remains OPEN")
    assert not _claims_dbr2_complete(_V1_STATUS_SENTENCE)


# DBR-AR-2A recognized as implemented — exact status/coverage anchors (contract doc only;
# the readiness matrix carries no 2A status line — the B5 gate guard scans it unmasked).
def test_dbr2_2a_status_pinned() -> None:
    norm = _norm(_contract())
    for anchor in _2A_ANCHORS:
        assert anchor in norm, f"missing DBR-AR-2A status/coverage anchor: {anchor!r}"


def test_dbr2_2a_status_nonvacuity() -> None:
    norm = _norm(_contract())
    for anchor in _2A_ANCHORS:
        assert anchor not in norm.replace(anchor, ""), anchor
    # The mask is exact-sentence only: near-miss closure claims still trip m01.
    assert _claims_dbr2_complete("dbr-ar-2a — implemented.")
    assert _claims_dbr2_complete("dbr-ar-2 — implemented when this pr merges.")
    assert not _claims_dbr2_complete("- DBR-AR-2A — implemented when this PR merges.")
    # Exactly-one cannot silently become zero-or-more, and the early-denial coverage
    # sentence cannot be reworded away without failing the anchor pin.
    assert _AFTER_2A_SENTENCE not in _norm("after dbr-ar-2a: zero or more router-edge in-memory events may be produced")
    assert _BEFORE_2A_SENTENCE not in _norm("before dbr-ar-2a: pre-target denials were fully audited")
    assert _2A_SLICES_SENTENCE not in _norm("dbr-ar-2b through dbr-ar-2e — started")


# Mutation 2 — B5-BLK-4 reopened.
_BLK4_REOPEN_RE = re.compile(
    r"\bb5-blk-4\b[^.;|]{0,80}?\b(?:reopened|re-opened|remains open|is open|back open|open again|no longer closed)\b"
)


def test_dbr2_m02_blk4_not_reopened() -> None:
    assert not _BLK4_REOPEN_RE.search(_norm(_contract())), "B5-BLK-4 must not be recorded as reopened"
    assert _DECISION_A_SENTENCE in _norm(_contract())


def test_dbr2_m02_nonvacuity() -> None:
    assert _BLK4_REOPEN_RE.search("b5-blk-4 is open again pending review")
    assert _BLK4_REOPEN_RE.search("b5-blk-4 — reopened")
    assert not _BLK4_REOPEN_RE.search("b5-blk-4 — closed — evidence-bound governance decision")


# Mutation 3 — MVP acceptance removed or weakened.
_MVP_WEAKENED_RE = re.compile(
    r"\bmvp\b[^.;|]{0,120}?\bacceptance\b[^.;|]{0,60}?\b(?:revoked|withdrawn|reversed|rescinded|voided|suspended)\b"
    r"|\bmvp\b[^.;|]{0,80}?\b(?:no longer|never)\s+accepted\b"
)


def test_dbr2_m03_mvp_acceptance_intact() -> None:
    assert not _MVP_WEAKENED_RE.search(_norm(_contract())), "the MVP acceptance must not be weakened"
    assert _DECISION_B_SENTENCE in _norm(_contract())


def test_dbr2_m03_nonvacuity() -> None:
    assert _MVP_WEAKENED_RE.search("the mvp acceptance is hereby revoked")
    assert _MVP_WEAKENED_RE.search("the physical multi-database mvp is no longer accepted")
    assert not _MVP_WEAKENED_RE.search("mvp acceptance at database granularity is not cluster-level proof")


# Mutation 4 — production activation marked ready.
def _activation_marked_ready(norm_text: str) -> bool:
    masked = norm_text.replace("not ready", " <notready> ").replace("do-not-activate", " <dna> ")
    return bool(
        re.search(
            r"\b(?:production|runtime)\s+(?:runtime\s+)?activation\s+(?:is|becomes|now|hereby)\s+ready\b"
            r"|\bready\s+to\s+activate\b|\bcleared\s+for\s+activation\b|\bactivation\s+may\s+proceed\b",
            masked,
        )
    )


def test_dbr2_m04_activation_not_ready() -> None:
    assert not _activation_marked_ready(_norm(_both())), "production activation must not be marked ready"
    assert _FAIL_CLOSED_SENTENCE in _norm(_contract())


def test_dbr2_m04_nonvacuity() -> None:
    assert _activation_marked_ready("production activation is ready")
    assert _activation_marked_ready("the gate is cleared for activation")
    assert _activation_marked_ready("runtime activation now ready; activation may proceed")
    assert not _activation_marked_ready("production runtime activation remains not ready / do-not-activate")


# Mutation 5 — Lovable cutover marked complete.
def _lovable_marked_complete(text: str) -> bool:
    for raw_line in text.lower().splitlines():
        line = " ".join(raw_line.replace("*", "").replace("`", "").split())
        if "lovable" not in line:
            continue
        if _OPEN_MARKER_RE.search(line):
            continue
        if any(w in line for w in _DONE_WORDS):
            return True
    return False


def test_dbr2_m05_lovable_open() -> None:
    assert not _lovable_marked_complete(_both()), "the Lovable cutover must not be claimed complete"
    assert _LOVABLE_SENTENCE in _norm(_contract())


def test_dbr2_m05_nonvacuity() -> None:
    assert _lovable_marked_complete("the lovable cutover is complete")
    assert _lovable_marked_complete("lovable cutover shipped")
    assert not _lovable_marked_complete("the lovable cutover remains open (separate track)")


# Mutations 8-11 — forbidden data allowed (raw DSN / token-JWT / request body / tenant
# result data / hostname-topology). ATR-V2: the negation mask stops at colons so a
# negated clause cannot hide an allowance introduced after a colon.
_FORBID_NEGATION_RE = re.compile(r"\b(?:never|not|no|nor|neither|must never|must not|cannot)\b[^.;|:]{0,60}")
_FORBID_ALLOW_RE = re.compile(
    r"\b(?:raw\s+dsns?|dsns?|passwords?|private\s+keys?|jwts?|bearer\s+tokens?|tokens?|authorization\s+headers?"
    r"|request\s+bod(?:y|ies)|response\s+bod(?:y|ies)|tenant\s+result\s+data|tenant\s+business\s+content|secret\s+values?"
    r"|database\s+hostnames?|physical\s+database\s+names?|connection\s+topology|tenantconnection)\b"
    r"[^.;|]{0,60}?\b(?:(?:may|can|shall|will)\s+be|(?:is|are)(?:\s+be)?)\s+"
    r"(?:allowed|permitted|recorded|stored|included|persisted|carried|written|logged)\b"
)

# ATR-V2: a forbidden field name must never enter an event-schema table row.
_FORBIDDEN_FIELD_ROW_RE = re.compile(r"\|\s*(?:request_body|response_body|jwt|bearer_token|dsn|password|access_token)\s*\|")


def _permits_forbidden_data(norm_text: str) -> bool:
    masked = _FORBID_NEGATION_RE.sub(" <negated-span> ", norm_text)
    return bool(_FORBID_ALLOW_RE.search(masked))


def test_dbr2_m08_to_m11_forbidden_data_never_allowed() -> None:
    assert not _permits_forbidden_data(_norm(_both())), "no forbidden data item may be recorded as allowed/storable"


def test_dbr2_m08_to_m11_nonvacuity() -> None:
    assert _permits_forbidden_data("raw dsns may be recorded for debugging")
    assert _permits_forbidden_data("jwts can be stored in the audit row")
    assert _permits_forbidden_data("the request body will be included in the event")
    assert _permits_forbidden_data("tenant result data is allowed in audit events")
    assert _permits_forbidden_data("bearer tokens are persisted alongside the record")
    assert _permits_forbidden_data("database hostnames are recorded for operator convenience")
    assert _permits_forbidden_data("connection topology is included in the row")
    assert _permits_forbidden_data("a tenantconnection is carried inside the event")
    assert not _permits_forbidden_data("raw dsns must never be recorded")
    assert not _permits_forbidden_data("no secret values are stored; references only")
    # colon-stop: a negation cannot mask an allowance introduced after a colon
    assert _permits_forbidden_data("never leak internals: raw dsns are recorded only here")


def test_dbr2_no_forbidden_field_row() -> None:
    assert not _FORBIDDEN_FIELD_ROW_RE.search(_norm(_both())), "a forbidden field name must never enter the event-schema table"


def test_dbr2_no_forbidden_field_row_nonvacuity() -> None:
    assert _FORBIDDEN_FIELD_ROW_RE.search(_norm("| `request_body` | OPTIONAL | captured for debugging |"))
    assert _FORBIDDEN_FIELD_ROW_RE.search(_norm("| dsn | REQUIRED | connection detail |"))
    assert _FORBIDDEN_FIELD_ROW_RE.search(_norm("| `jwt` | OPTIONAL | inbound credential |"))
    assert not _FORBIDDEN_FIELD_ROW_RE.search(_norm("| `request_ref` | OPTIONAL | the RequestContext.request_id |"))


# Mutation 12 is covered by test_dbr2_failure_semantics_explicit (all seven rows classified).
# Mutation 13 — audit failure silently fails open.
def _silently_fails_open(norm_text: str) -> bool:
    masked = norm_text.replace("fail open with alert", " <sanctioned> ")
    masked = re.sub(r"\b(?:never|not)\s+(?:permitted|allowed)[:,]?\s*", " <negated> ", masked)
    masked = re.sub(r"\b(?:never|not)\s+silently\b", " <negated> ", masked)
    masked = re.sub(r"<negated>\s*(?:silently\s+)?fail(?:s|ing)?\s+open", " <negated-open> ", masked)
    return bool(
        re.search(r"\bsilently\s+fail(?:s|ing)?\s+open\b|\bfail(?:s|ing)?\s+open\s+silently\b|\bfail(?:s|ed|ing)?\s+open\b", masked)
    )


def test_dbr2_m13_no_silent_fail_open() -> None:
    assert not _silently_fails_open(_norm(_both())), "audit failure must never be recorded as (silently) failing open without alert"


def test_dbr2_m13_nonvacuity() -> None:
    assert _silently_fails_open("on sink failure the router silently fails open")
    assert _silently_fails_open("audit write failure: fail open")
    assert not _silently_fails_open("audit write fails after successful dispatch: fail open with alert")
    assert not _silently_fails_open("never permitted: silently failing open for an allowed route")


# Mutation 14 — false cross-database atomicity claim.
def _claims_cross_db_atomicity(norm_text: str) -> bool:
    masked = norm_text.replace(_NO_ATOMICITY_SENTENCE, " <no-atomicity-sentence> ")
    masked = re.sub(r"\bno\s+atomicity\b|\bnot\s+atomic\b|\bnever\s+atomic\b", " <negated> ", masked)
    masked = re.sub(r"\bno\s+distributed\s+transaction\b|\bno\s+two-phase\s+commit\b", " <negated> ", masked)
    return bool(
        re.search(
            r"\batomic(?:ally)?\s+across\b|\batomicity\s+across\b"
            r"|\btwo-phase\s+commit\s+(?:is|ensures|guarantees|provides)\b"
            r"|\bdistributed\s+transaction\s+(?:is|ensures|guarantees|provides|spans)\b",
            masked,
        )
    )


def test_dbr2_m14_no_false_atomicity() -> None:
    assert not _claims_cross_db_atomicity(_norm(_both())), "no cross-database atomicity may be claimed"
    assert _NO_ATOMICITY_SENTENCE in _norm(_contract()), "the explicit no-atomicity sentence must be present"


def test_dbr2_m14_nonvacuity() -> None:
    assert _claims_cross_db_atomicity("the audit row and tenant write commit atomically across both databases")
    assert _claims_cross_db_atomicity("a distributed transaction ensures consistency")
    assert _claims_cross_db_atomicity("two-phase commit guarantees the pair")
    assert not _claims_cross_db_atomicity(_NO_ATOMICITY_SENTENCE)
    assert not _claims_cross_db_atomicity("the insert commits atomically within that database")


# Mutation 15 — cross-service import authorized.
def _authorizes_cross_service_import(norm_text: str) -> bool:
    masked = re.sub(r"\b(?:does|do|did)\s+not\s+import\b|\bwithout\s+importing\b|\bnever\s+imports?\b", " <negated> ", norm_text)
    masked = masked.replace("no cross-service import", " <negated> ")
    return bool(
        re.search(
            r"\bcross-service\s+imports?\s+(?:is|are)\s+(?:authorized|permitted|allowed)\b"
            r"|\b(?:database_router|control_plane)\s+(?:imports|may\s+import|is\s+authorized\s+to\s+import)\b",
            masked,
        )
    )


def test_dbr2_m15_no_cross_service_import() -> None:
    assert not _authorizes_cross_service_import(_norm(_both())), "no cross-service import may be authorized"
    assert _NO_IMPORT_SENTENCE in _norm(_contract())


def test_dbr2_m15_nonvacuity() -> None:
    assert _authorizes_cross_service_import("for this slice a cross-service import is authorized")
    assert _authorizes_cross_service_import("cross-service imports are permitted for audit ingest")
    assert _authorizes_cross_service_import("database_router imports control_plane for the audit store")
    assert _authorizes_cross_service_import("control_plane may import database_router models")
    assert not _authorizes_cross_service_import("database_router does not import control_plane")
    assert not _authorizes_cross_service_import("no cross-service import is authorized")


# Mutation 16 — append-only requirement removed.
def _permits_mutation_of_rows(norm_text: str) -> bool:
    return bool(
        re.search(
            r"\brows?\s+may\s+be\s+(?:updated|deleted)\b|\bmay\s+(?:update|delete)\s+(?:audit\s+)?rows?\b"
            r"|\bupdates?\s+(?:and\s+deletes?\s+)?(?:is|are)\s+(?:permitted|allowed)\b",
            norm_text,
        )
    )


def test_dbr2_m16_append_only_required() -> None:
    norm = _norm(_contract())
    assert "append-only" in norm, "the append-only requirement must be present"
    assert "no update path, no delete path" in norm, "the update/delete prohibition must be present"
    assert not _permits_mutation_of_rows(_norm(_both()))


def test_dbr2_m16_nonvacuity() -> None:
    assert _permits_mutation_of_rows("audit rows may be updated by an operator")
    assert _permits_mutation_of_rows("updates are permitted under legal hold")
    assert not _permits_mutation_of_rows("no update path, no delete path in any adapter port")
    norm = _norm(_contract())
    assert "no update path, no delete path" not in norm.replace("no update path, no delete path", "")


# Mutations 17-19 are covered by test_dbr2_denial_events_recorded, test_dbr2_idempotency_defined,
# and test_dbr2_live_proof_plan_present above (each with its own non-vacuity companion).


# Mutation 20 — implementation begins in V1 / 21 — schema-migration claimed delivered /
# 22 — production wiring claimed delivered.
_V1_NEG_MASKS = (
    re.compile(r"\b(?:does|do|did)\s+not\s+(?:\w+\s+){0,2}?(?:implement|add|apply|wire|create|build|ship|deliver)s?\b"),
    re.compile(r"\bnot\s+(?:implemented|added|applied|wired|created|built|shipped|delivered)\b"),
    re.compile(r"\bcreated-not-applied\b|\bcreated,\s+not\s+applied\b|\bnever\s+applied\b"),
    re.compile(r"\bno\s+(?:implementation|adapter|schema|migration|wiring|endpoint|queue|outbox|runtime\s+ddl)\b"),
    re.compile(r"\bnone\s+begins?\b"),
)
# ATR-V2: claim-verb list extended (begins/adds/includes/applies + past forms).
_V1_CLAIM_VERBS = (
    r"(?:delivers?|delivered|implements?|implemented|wires?|wired|creates?|created|builds?|built|ships?|shipped"
    r"|begins?|began|adds?|added|includes?|included|applies|applied)"
)
_V1_CLAIM_RE = re.compile(r"\bv1\b[^.;|]{0,120}?\b" + _V1_CLAIM_VERBS + r"\b" + r"|\b" + _V1_CLAIM_VERBS + r"\b[^.;|]{0,60}?\bv1\b")
_SCHEMA_DELIVERED_RE = re.compile(
    r"\b(?:ddl|schema|migration|table)\b[^.;|]{0,80}?\b(?:applied|delivered|landed|executed|migrated|in\s+place)\b"
    r"|\b(?:applied|delivered|landed|executed)\b[^.;|]{0,40}?\b(?:ddl|schema|migration)\b"
)
_WIRING_DELIVERED_RE = re.compile(
    r"\b(?:production|runtime)\s+wiring\b[^.;|]{0,60}?\b(?:delivered|landed|in\s+place|complete|completed|done|wired)\b"
)


def _masked_for_v1_claims(norm_text: str) -> str:
    masked = _mask_v1_status(norm_text)
    for mask in _V1_NEG_MASKS:
        masked = mask.sub(" <negated> ", masked)
    return masked


def _claims_v1_implements(norm_text: str) -> bool:
    return bool(_V1_CLAIM_RE.search(_masked_for_v1_claims(norm_text)))


def _claims_routing_schema_delivered(text: str) -> bool:
    for raw_line in text.lower().splitlines():
        line = _masked_for_v1_claims(" ".join(raw_line.replace("*", "").replace("`", "").split()))
        # ATR-V2: 'routing_audit' also matches future underscored table names
        # (e.g. control_routing_audit) so a delivered-table claim cannot hide there.
        if "dbr-ar-2" not in line and "routing audit" not in line and "routing-audit" not in line and "routing_audit" not in line:
            continue
        if _SCHEMA_DELIVERED_RE.search(line):
            return True
    return False


def _claims_production_wiring_delivered(norm_text: str) -> bool:
    return bool(_WIRING_DELIVERED_RE.search(_masked_for_v1_claims(norm_text)))


def test_dbr2_m20_no_v1_implementation_claim() -> None:
    assert not _claims_v1_implements(_norm(_both())), "V1 must not claim to implement/deliver any artifact"


def test_dbr2_m20_nonvacuity() -> None:
    assert _claims_v1_implements("this v1 delivers the durable adapter")
    assert _claims_v1_implements("the ingest endpoint was implemented in v1")
    assert _claims_v1_implements("v1 wires the production sink")
    assert _claims_v1_implements("v1 adds the durable ingest edge")
    assert _claims_v1_implements("the persistence layer was included in v1")
    assert _claims_v1_implements("v1 applies the routing-audit ddl")
    assert not _claims_v1_implements("this v1 records the implementation contract only")
    assert not _claims_v1_implements("none begin in v1")
    assert not _claims_v1_implements(_V1_STATUS_SENTENCE)


def test_dbr2_m21_no_schema_delivered_claim() -> None:
    assert not _claims_routing_schema_delivered(_both()), "no routing-audit schema/DDL/migration may be claimed applied/delivered"


def test_dbr2_m21_nonvacuity() -> None:
    assert _claims_routing_schema_delivered("the routing-audit table DDL is applied to production")
    assert _claims_routing_schema_delivered("dbr-ar-2 schema delivered and live")
    assert _claims_routing_schema_delivered("the control_routing_audit table is applied")
    assert not _claims_routing_schema_delivered("created-not-applied DDL for the routing-audit table")
    assert not _claims_routing_schema_delivered("the provisioning control_audit DDL (B-7A) is unrelated here")
    assert not _claims_routing_schema_delivered("internal code routing_audit_unavailable; wire disclosure stays the sanitized bucket")


def test_dbr2_m22_no_production_wiring_claim() -> None:
    assert not _claims_production_wiring_delivered(_norm(_both())), "no production wiring may be claimed delivered"


def test_dbr2_m22_nonvacuity() -> None:
    assert _claims_production_wiring_delivered("the production wiring is complete")
    assert _claims_production_wiring_delivered("runtime wiring landed in this change")
    assert not _claims_production_wiring_delivered("production wiring is a later slice")
    assert not _claims_production_wiring_delivered(_V1_STATUS_SENTENCE)


# Mutation 23 — blocker count changed.
_BLOCKER_COUNT_RE = re.compile(r"\b(\d+)\s+of\s+9\s+activation\s+blockers\b")


def test_dbr2_m23_blocker_count_unchanged() -> None:
    counts = _BLOCKER_COUNT_RE.findall(_norm(_both()))
    assert counts, "the 8-of-9 activation-blocker sentence must be present"
    assert all(c == "8" for c in counts), f"activation blocker count must remain 8 of 9, got: {counts}"


def test_dbr2_m23_nonvacuity() -> None:
    assert _BLOCKER_COUNT_RE.findall("7 of 9 activation blockers remain open") == ["7"]
    assert _BLOCKER_COUNT_RE.findall("9 of 9 activation blockers remain open") == ["9"]
    assert not all(c == "8" for c in _BLOCKER_COUNT_RE.findall("7 of 9 activation blockers"))


# Mutation 24 — one document loses the exact V1 status sentence: covered per-document by
# test_dbr2_open_status_pinned_per_document / test_dbr2_open_status_nonvacuity above.


if __name__ == "__main__":
    _scan.run(
        [
            test_dbr2_docs_exist,
            test_dbr2_baseline_pinned,
            test_dbr2_baseline_nonvacuity,
            test_dbr2_open_status_pinned_per_document,
            test_dbr2_open_status_nonvacuity,
            test_dbr2_2a_status_pinned,
            test_dbr2_2a_status_nonvacuity,
            test_dbr2_standing_decisions_restated_intact,
            test_dbr2_standing_decisions_nonvacuity,
            test_dbr2_selected_architecture_pinned,
            test_dbr2_architecture_not_changed_silently,
            test_dbr2_architecture_nonvacuity,
            test_dbr2_event_schema_minimums,
            test_dbr2_event_schema_nonvacuity,
            test_dbr2_forbidden_data_list,
            test_dbr2_forbidden_data_nonvacuity,
            test_dbr2_failure_semantics_explicit,
            test_dbr2_failure_semantics_nonvacuity,
            test_dbr2_denial_events_recorded,
            test_dbr2_denial_events_nonvacuity,
            test_dbr2_idempotency_defined,
            test_dbr2_idempotency_nonvacuity,
            test_dbr2_live_proof_plan_present,
            test_dbr2_live_proof_nonvacuity,
            test_dbr2_slice_sequence_recorded,
            test_dbr2_slice_sequence_nonvacuity,
            test_dbr2_m01_not_marked_closed,
            test_dbr2_m01_nonvacuity,
            test_dbr2_m02_blk4_not_reopened,
            test_dbr2_m02_nonvacuity,
            test_dbr2_m03_mvp_acceptance_intact,
            test_dbr2_m03_nonvacuity,
            test_dbr2_m04_activation_not_ready,
            test_dbr2_m04_nonvacuity,
            test_dbr2_m05_lovable_open,
            test_dbr2_m05_nonvacuity,
            test_dbr2_m08_to_m11_forbidden_data_never_allowed,
            test_dbr2_m08_to_m11_nonvacuity,
            test_dbr2_no_forbidden_field_row,
            test_dbr2_no_forbidden_field_row_nonvacuity,
            test_dbr2_m13_no_silent_fail_open,
            test_dbr2_m13_nonvacuity,
            test_dbr2_m14_no_false_atomicity,
            test_dbr2_m14_nonvacuity,
            test_dbr2_m15_no_cross_service_import,
            test_dbr2_m15_nonvacuity,
            test_dbr2_m16_append_only_required,
            test_dbr2_m16_nonvacuity,
            test_dbr2_m20_no_v1_implementation_claim,
            test_dbr2_m20_nonvacuity,
            test_dbr2_m21_no_schema_delivered_claim,
            test_dbr2_m21_nonvacuity,
            test_dbr2_m22_no_production_wiring_claim,
            test_dbr2_m22_nonvacuity,
            test_dbr2_m23_blocker_count_unchanged,
            test_dbr2_m23_nonvacuity,
        ]
    )
