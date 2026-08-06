"""Static boundary guard for the CLM ACME tenant data-plane witness.

The witness is the only artifact that could ever produce `Database Router -> SecretRef -> ACME
physical tenant database -> Startup GET/PATCH` evidence. That makes its *failure modes* the thing
worth guarding: a witness that can be run without its preconditions, or that prints a DSN, or that
skips its restore, does not merely fail — it produces confident, wrong evidence.

What is pinned, and the specific way each check fails if it is not:

* **`run` refuses without an explicit START-GATE.** The `run` leg performs a real business write to a
  physical tenant database (Gate-B class M14). Under Gate A the harness is built and not run.
* **No subcommand resolves to the READ-ONLY path.** The standalone `requires_pg` runner invokes
  harnesses with no arguments; if that fell through to `run`, the write leg would fire from a bare
  invocation.
* **The `SP2_GW_TENANT_STARTUP_BASE_URL` precondition is checked before anything is called evidence.**
  Unset, the `/tenant/startups/<ref>` routes still answer — from the pre-CLM router handoff, having
  touched no tenant database. A witness that skips this collects a plausible non-answer and files it.
* **Durability is checked.** A routing view served from the in-memory Control store would let the
  witness pass with no physical ACME database involved at all.
* **The served-body discriminator CORRESPONDS TO THE REAL SERVED CONTRACT.** This guard imports
  ``api_gateway.portal``, computes the ``TenantStartupDetailDTO`` field set, loads the witness and
  calls its own derivation, and asserts the two are equal — a token-presence check is exactly what let
  a five-key literal the Gateway can never emit sit in the discriminator and abort every run,
  including a correct one. The guard additionally refuses any restated key-set literal in the witness.
* **The physical identity proof is the PAIR** `(system_identifier, current_database())`.
  `system_identifier` alone is shared by every database on a cluster and proves nothing about which
  one was reached.
* **Restore happens in `finally` and is proven by a before==after digest**, not by the UPDATE's
  return code.
* **Auth-stage and router-stage isolation are recorded separately.** The ZETA-claim denial fires in
  the Auth Router before any routing or tenant-DB contact; presenting it as router-stage isolation
  claims something it does not prove.
* **A LAWFUL fixture value cannot abort a correct run.** Two of the witness's own checks used to do
  exactly what the drifted key-set literal did, one field along: the no-leak scan rejected `://`
  inside `short_description` — which the serving edge declares lawful in business free text — and the
  positive control read the nullable value to decide whether the ROW existed. Both are now executed
  here against the real functions: a URL-bearing description and a present-but-NULL row must pass,
  while credential/token/PEM material and a genuinely absent row must still fail.
* **No DDL, no membership INSERT, no `os.environ` persistence, no static driver import, no secret in
  any captured artifact.**

Pure stdlib; runnable standalone:
    python tests/architecture/test_clm_dataplane_witness_boundaries.py
"""

from __future__ import annotations

import ast
import dataclasses
import importlib.util
import json
import pathlib
import re
import sys
from types import ModuleType
from typing import Any, List, Optional, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

sys.path.insert(0, str(_scan.BACKEND_ROOT))
from api_gateway.portal import TenantStartupDetailDTO  # noqa: E402

_WITNESS = _scan.BACKEND_ROOT / "tests" / "control_plane" / "requires_pg" / "test_pg_clm_acme_dataplane_witness.py"
_RUNBOOK = _scan.REPO_ROOT / "infrastructure" / "runbooks" / "clm_acme_dataplane_witness.md"
_TEMPLATE = _scan.REPO_ROOT / "docs" / "infrastructure" / "clm_dataplane_evidence_template.md"
_COMPLETENESS_GUARD = _scan.BACKEND_ROOT / "tests" / "architecture" / "test_live_pg_workflow_runset_completeness.py"


def _text() -> str:
    return _WITNESS.read_text(encoding="utf-8")


def _tree() -> ast.Module:
    return ast.parse(_text(), filename=str(_WITNESS))


def _func(name: str) -> ast.FunctionDef:
    for node in ast.walk(_tree()):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{_WITNESS.name} must define {name}()")


def _source(name: str) -> str:
    return ast.get_source_segment(_text(), _func(name)) or ""


def _witness_module() -> ModuleType:
    """Load the witness by path and execute it.

    Safe: the module performs no I/O at import — it inserts `backend` on `sys.path` and defines
    constants; every connection, request and argparse call lives inside a command function. Loading
    it is what makes the DTO correspondence check REAL rather than textual.
    """
    spec = importlib.util.spec_from_file_location("_clm_dataplane_witness_under_guard", _WITNESS)
    assert spec is not None and spec.loader is not None, "the witness must be loadable by path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_witness_and_its_documentation_exist() -> None:
    assert _WITNESS.is_file(), "the CLM tenant data-plane witness must exist"
    assert _RUNBOOK.is_file(), "the witness operator runbook must exist"
    assert _TEMPLATE.is_file(), "the references-only evidence template must exist"


def test_witness_is_registered_as_a_manual_only_exception() -> None:
    guard = _COMPLETENESS_GUARD.read_text(encoding="utf-8")
    key = f"tests/control_plane/requires_pg/{_WITNESS.name}"
    assert key in guard, (
        f"{_WITNESS.name} must carry a justified MANUAL_ONLY_EXCEPTIONS key in the SAME commit as the file: "
        "INV-A fails without the key, INV-C fails without the file."
    )


def test_run_refuses_without_an_explicit_start_gate() -> None:
    source = _source("cmd_run")
    assert "confirm_start_gate" in source, "run must require an explicit START-GATE"
    gate_at = source.find("confirm_start_gate")
    write_at = min(i for i in (source.find('"PATCH"'), source.find("UPDATE startups")) if i != -1)
    assert gate_at < write_at, "the START-GATE check must precede any write"
    assert "--confirm-start-gate" in _text(), "the START-GATE must be an explicit CLI flag, not an env var"
    assert 'action="store_true"' in _text(), "the START-GATE flag must default to OFF"


def test_no_subcommand_resolves_to_the_read_only_path() -> None:
    source = _source("main")
    assert 'args.command = "status"' in source, (
        "a bare invocation must resolve to the READ-ONLY status path. The standalone requires_pg runner invokes "
        "harnesses with no arguments — if that fell through to `run`, the real tenant write would fire from a bare "
        "`python tests/.../test_pg_clm_acme_dataplane_witness.py`."
    )


def test_preconditions_gate_every_evidence_claim() -> None:
    gate = _source("evaluate_preconditions")
    assert "SP2_GW_TENANT_STARTUP_BASE_URL" in _text(), "the composition selector must be named"
    assert "TENANT_STARTUP_SELECTOR" in gate, (
        "the precondition gate must check the tenant-Startup selector. Unset, /tenant/startups/<ref> still answers — "
        "from the pre-CLM router handoff, having touched no tenant database at all."
    )
    assert "CONTROL_STORE_SELECTOR" in gate, (
        "the precondition gate must check Control-store durability: a routing view served from the in-memory store "
        "lets this witness pass with no physical ACME database involved"
    )
    assert "upstream_census" in gate, (
        "the gate must record an upstream liveness census, or a later 503 is four-ways ambiguous (dead tenant-Startup "
        "upstream, dead Auth Router, dead durable audit sink, or an unhandled edge exception)"
    )
    run = _source("cmd_run")
    gate_at = run.find("evaluate_preconditions")
    call_at = run.find("_http(")
    assert gate_at != -1 and gate_at < call_at, "run must evaluate preconditions BEFORE issuing any request"
    assert "served_record_fields()" in run, (
        "the served GET body must be asserted against the field set DERIVED from the served contract — that shape is "
        "what distinguishes a real CLM answer from a pre-CLM router handoff"
    )


def test_the_served_body_discriminator_matches_the_real_served_dto() -> None:
    """The correspondence check, not a token check.

    The route's only possible 200 body is `serialize_portal_dto(TenantStartupDetailDTO)` —
    `json.dumps(dataclasses.asdict(dto))` — reached through a TYPE-EXACT terminal. So the served key
    set is exactly that dataclass's field set, including the nullable fields (`asdict` renders them
    as `null` rather than omitting them). A witness that compares the body against anything else does
    not merely fail to discriminate: it rejects the GENUINE answer and aborts every run, including a
    correct one on a live Gate-B data plane, while printing a confident "this is a pre-CLM answer".
    """
    contract = frozenset(field.name for field in dataclasses.fields(TenantStartupDetailDTO))
    derived = _witness_module().served_record_fields()
    assert derived == contract, (
        "the witness's expected served field set does not equal the served TenantStartupDetailDTO contract.\n"
        f"  contract: {sorted(contract)}\n  witness : {sorted(derived)}"
    )
    assert len(contract) == 8, (
        f"the served TenantStartupDetailDTO carries eight contract-pinned fields, found {len(contract)}. If the "
        "contract genuinely changed, that is a governed IC-009 CLM change — re-stamp this count deliberately."
    )
    assert "short_description" in contract, "the sole CLM-mutable field must be part of the served shape"
    assert "record_ref" in contract, "the served body must carry the reference the route addressed"


def test_the_discriminator_is_derived_and_never_restated() -> None:
    """No duplicate literal may re-enter. A restated key set is what drifted in the first place."""
    tree = _tree()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        target = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
        if target not in {"frozenset", "set"}:
            continue
        for arg in node.args:
            if not isinstance(arg, (ast.Set, ast.List, ast.Tuple)):
                continue
            literals = [e.value for e in arg.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
            assert not literals, (
                f"{_WITNESS.name} restates a literal key set {sorted(literals)}. The served field set must be DERIVED "
                "from api_gateway.portal.TenantStartupDetailDTO at call time — a duplicated literal drifts from the "
                "contract silently, and a drifted literal rejects the genuine answer."
            )
    source = _source("served_record_fields")
    assert "TenantStartupDetailDTO" in source and "dataclasses.fields" in source, (
        "the derivation must read the authoritative dataclass, not a copy of its field names"
    )
    assert "importlib.import_module" in source, "the contract must be resolved at call time (no import-time I/O)"


def test_physical_identity_is_the_pair_not_the_system_identifier_alone() -> None:
    source = _source("physical_identity")
    assert "system_identifier" in source and "current_database" in source, (
        "the ACME identity proof must be the PAIR (system_identifier, current_database()). `system_identifier` alone "
        "is shared by every database on a cluster and proves nothing about which one was reached."
    )
    run = _source("cmd_run")
    assert "acme_identity != zeta_identity" in run, (
        "ACME and ZETA resolving to the same identity pair means the topology is not physically separated, and no "
        "isolation claim may be made from it"
    )


def test_independent_verification_is_a_separate_connection() -> None:
    run = _source("cmd_run")
    assert "read_short_description(acme" in run, "the served answer must be cross-checked against a direct ACME read"
    assert run.count("read_short_description(acme") >= 2, "both the READ and the WRITE leg must be independently verified"
    assert "P-4 FAILED" in run, "the independent-read mismatch must be named as the precondition it falsifies"


def test_restore_is_in_finally_and_proven_by_a_digest() -> None:
    node = _func("cmd_run")
    tries = [n for n in ast.walk(node) if isinstance(n, ast.Try) and n.finalbody]
    assert tries, "the write leg must sit inside a try/finally"
    finally_source = "\n".join(ast.get_source_segment(_text(), stmt) or "" for stmt in tries[0].finalbody)
    assert "UPDATE startups SET short_description" in finally_source, "the restore must run in `finally`"
    assert "before_digest" in finally_source, (
        "restoration must be proven by a before==after digest, not by the UPDATE's return code — an UPDATE that "
        "matched zero rows also returns without error"
    )
    assert "assert_no_leak" in finally_source, "every captured artifact must be scanned before anything is reported"


def test_isolation_stages_are_distinguished() -> None:
    run = _source("cmd_run")
    assert "isolation_auth_stage" in run and "isolation_router_stage" in run, (
        "auth-stage and router-stage isolation must be captured under distinct labels"
    )
    assert "AUTH STAGE" in run and "ROUTER STAGE" in run, "the two legs must be reported distinctly"
    assert "does NOT prove the Database Router would have refused" in run, (
        "the ZETA-claim denial fires in the Auth Router BEFORE any routing or tenant-DB contact. Presenting it as "
        "router-stage isolation claims something it does not prove, and the caveat must travel with the evidence."
    )


def _asserted_conditions(function: str) -> str:
    """The source of every `assert` TEST in a function — messages excluded.

    A `print("PASS: ...")` proves nothing, and neither does an assertion message that merely
    *mentions* the hazard. Only the tested expression counts.
    """
    node = _func(function)
    return "\n".join(ast.get_source_segment(_text(), stmt.test) or "" for stmt in ast.walk(node) if isinstance(stmt, ast.Assert))


def test_every_isolation_leg_asserts_and_a_200_breach_fails() -> None:
    """M-11. A leg that only PRINTS its observed status passes on an isolation breach.

    Both legs previously printed `PASS:` carrying the observed status and asserted nothing on the
    router stage, so an unregistered-tenant carrier answered `200` — the exact breach the leg exists
    to detect — still produced `PASS: ISOLATION (ROUTER STAGE)` and exit 0.
    """
    conditions = _asserted_conditions("cmd_run")
    assert "DENIAL_STATUSES" in conditions, (
        "each denial leg must assert its status is one of the declared denial statuses. 503 in particular is the "
        "upstream/audit-outage collapse: it is not a denial and must never be recorded as isolation evidence."
    )
    assert conditions.count("DENIAL_STATUSES") >= 2, (
        "both the router-stage isolation leg and the unknown-startup_ref leg must assert against the denial set"
    )
    # Word-anchored: a bare `"status != 200" in conditions` is satisfied by `unknown_status != 200`,
    # so it would pass with the router-stage assertion deleted — the exact defect M-11 reports.
    assert re.search(r"\bstatus != 200", conditions), "a 200 on the router-stage isolation leg must FAIL the run"
    assert re.search(r"\bunknown_status != 200", conditions), "a 200 for an unknown startup_ref must FAIL the run"
    assert re.search(r"\bbare_status != 200", conditions), "a 200 on the unexposed bare route must FAIL the run"
    text = _text()
    assert "DENIAL_STATUSES = (401, 403, 404)" in text, (
        "the denial set must be declared explicitly and must EXCLUDE 503 (audit/upstream collapse) and 0 (transport "
        "failure) — both would otherwise read as denials"
    )
    assert "positive control=200" not in text, (
        "the 404 disambiguation must pair every 404 with the OBSERVED positive control from the read leg, not with a "
        "hardcoded literal that is true by construction"
    )
    assert "positive control={read_status}" in text, "the positive control must be the status actually observed"


def test_the_auth_stage_isolation_leg_cannot_be_silently_skipped() -> None:
    """M-12. Instruction §11 requires BOTH isolation stages; a green run must not be able to carry neither."""
    run = _source("cmd_run")
    assert "if zeta_bearer:" not in run, (
        "the auth-stage isolation leg must not sit behind a presence test on its own bearer — that makes the required "
        "leg silently skippable while the run still exits 0"
    )
    assert "(ZETA_BEARER_ENV, zeta_bearer)" in run, (
        "the ZETA claim bearer must be in the MANDATORY value census alongside the ACME bearer and both tenant DSNs"
    )
    assert "SKIP: ISOLATION" not in _text(), "no isolation leg may report itself skipped and still be a complete run"
    conditions = _asserted_conditions("cmd_run")
    assert "status == 403" in conditions, "the auth-stage denial must be asserted, not merely printed"
    assert "legs_ok" in run and "return 0 if verdict else 1" in run, (
        "the exit code must depend on whether the legs actually ran and passed — a restore-only exit code is green "
        "for a run that proved nothing"
    )


def test_finally_cannot_mask_the_real_failure() -> None:
    """M-13. Every name the `finally` block dereferences must be bound BEFORE the `try`.

    This is the one harness whose premise is that failures must be attributable. A `NameError` raised
    inside `finally` escapes the `except AssertionError` handler and replaces the real cause.
    """
    node = _func("cmd_run")
    tries = [n for n in ast.walk(node) if isinstance(n, ast.Try) and n.finalbody]
    assert tries, "the write leg must sit inside a try/finally"
    block = tries[0]
    pre_try_bound = set()
    for stmt in node.body:
        if stmt is block:
            break
        for sub in ast.walk(stmt):
            if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Store):
                pre_try_bound.add(sub.id)
            elif isinstance(sub, ast.arg):  # pragma: no cover - defensive
                pre_try_bound.add(sub.arg)
    pre_try_bound |= {a.arg for a in node.args.args}
    for name in ("acme_identity", "zeta_identity", "before_digest", "original", "restored_ok", "no_leak_ok", "write_attempted"):
        assert name in pre_try_bound, (
            f"{name} is dereferenced by the `finally` block but is not bound before the `try`. If the statement that "
            "binds it raises, `finally` raises NameError and the ORIGINAL failure is lost."
        )


def test_the_no_leak_scan_covers_both_bearers() -> None:
    """M-18(a). The auth-stage artifact captures the response to the request that carried the ZETA bearer."""
    finally_source = "\n".join(
        ast.get_source_segment(_text(), stmt) or ""
        for node in ast.walk(_func("cmd_run"))
        if isinstance(node, ast.Try) and node.finalbody
        for stmt in node.finalbody
    )
    assert "zeta_bearer" in finally_source, (
        "the no-leak scan's verbatim secret census must include the ZETA bearer. Without it, only the generic `eyJ` "
        "shape would catch an echo — and a non-JWT bearer form does not carry that prefix."
    )
    for secret in ("acme_dsn", "zeta_dsn", "bearer"):
        assert secret in finally_source, f"the no-leak census must include {secret}"


def test_runtime_posture_is_declared_not_claimed_as_proof() -> None:
    """M-19. `os.environ` reads describe THIS process, never the Gateway/Control-Plane processes.

    The Gateway and the Control Plane are separate uvicorn processes composed from their own
    environments, and the governed launcher scrubs `SP2_*` out of every child — so the witness's own
    environment is structurally independent of theirs. The checks stay (they catch the commonest
    operator error) but must be labelled as declarations, with the authoritative facts named.
    """
    gate = _source("evaluate_preconditions")
    assert "D-1 FAILED" in gate and "D-2 FAILED" in gate, (
        "the two environment reads must be labelled as DECLARATIONS (D-1/D-2), not as proofs about the running Gateway or Control Plane"
    )
    assert "THIS process's environment" in gate, "the declaration must name whose environment it read"
    text = _text()
    assert "A-1" in text and "A-2" in text, "the authoritative, service-observed facts must be named distinctly"
    assert "TYPE-EXACT" in text, (
        "the real guarantee is the type-exact tenant Startup terminal: with the port absent a pre-CLM handoff cannot "
        "serve a conforming 200 at all. That, not the environment read, is what makes the evidence evidence."
    )
    # And the withdrawn claim must not creep back (M-9).
    assert "cross-reads the routing row" not in text, (
        "the witness performs NO Control-database read; CONTROL_DSN_ENV is presence-reported by `plan` only. Claiming "
        "a cross-read that does not exist is how a checkbox with no implementation reaches an evidence template."
    )
    control_dsn_uses = [n for n in ast.walk(_tree()) if isinstance(n, ast.Name) and n.id == "CONTROL_DSN_ENV"]
    assert len(control_dsn_uses) <= 2, (
        "CONTROL_DSN_ENV may appear only as its definition and a presence-only report. A connection using it would be "
        "a new Control-database read that neither the runbook nor the evidence template describes."
    )


def test_zeta_is_proven_unchanged() -> None:
    run = _source("cmd_run")
    assert run.count("zeta_before_digest") >= 3, "ZETA must be proven byte-identical after the write AND after isolation"


def test_no_leak_scan_covers_every_shape() -> None:
    source = _source("assert_no_leak")
    for shape in ("secrets_in_play", "databases", "LEAK_SHAPES"):
        assert shape in source, f"the no-leak scan must cover {shape}"
    assert "TEXT_LEAK_SHAPES" in source and "CREDENTIAL_URI" in source, (
        "the bounded free-text field must be scanned under its OWN census — the token/PEM shapes plus a "
        "credential-bearing-URI pattern — rather than being exempted from the scan or scanned as a reference field"
    )
    text = _text()
    for shape in ("://", "eyJ", "-----BEGIN", "AKIA", "ghp_", "xox"):
        assert f'"{shape}"' in text, f"the leak-shape census must include {shape!r}"
    assert "_password_of" in text, "the scan must extract and search for the credential password substring"


# ---------------------------------------------------------------------------------------------
# Executed checks: a LAWFUL fixture value must not abort a correct run (RV-9 / RV-10).
#
# These call the witness's real functions. Structural checks cannot establish either property —
# the defect in both cases was a correct-looking assertion asking the wrong question.
# ---------------------------------------------------------------------------------------------

_FIXTURE_RECORD = {
    "record_ref": "clm-startup-1",
    "display_name": "CLM Fixture",
    "short_description": None,
    "investment_stage": "seed",
    "lineage_reference": "lineage/clm-startup-1",
}


def _served_artifact(short_description: object) -> str:
    """One captured artifact in the EXACT shape `cmd_run` records: `status=<n> body=<served JSON>`."""
    body = dict(_FIXTURE_RECORD)
    body["short_description"] = short_description
    return f"status=200 body={json.dumps(body)}"


class _FakeCursor:
    def __init__(self, row: Optional[Tuple[Any, ...]]) -> None:
        self._row = row

    def fetchone(self) -> Optional[Tuple[Any, ...]]:
        return self._row


class _FakeConnection:
    """A `conn.execute(...).fetchone()` stand-in. No driver, no database, no I/O of any kind."""

    def __init__(self, *, row_present: bool, value: Optional[str]) -> None:
        self._row_present = row_present
        self._value = value
        self.statements: List[str] = []

    def execute(self, statement: str, _parameters: object = None) -> _FakeCursor:
        self.statements.append(statement)
        if not self._row_present:
            return _FakeCursor(None)
        if statement.startswith("SELECT 1 "):
            return _FakeCursor((1,))
        return _FakeCursor((self._value,))


def test_lawful_url_free_text_passes_the_no_leak_scan_but_credential_shapes_still_fail() -> None:
    """RV-9. `://` is LAWFUL inside `short_description`, and this repository already says so.

    `database_router/adapters/providers/http_tenant_startup_api.py` splits `_REF_SECRET_SHAPES` (with
    `://`) from `_TEXT_SECRET_SHAPES` (without) for exactly this field. A witness that scanned the
    bounded free text against the URI shape would abort a CORRECT Gate-B run on a lawful fixture value
    — the same class of defect as a drifted key-set literal, one field along. Executed, not read.
    """
    witness = _witness_module()
    assert "://" in witness.LEAK_SHAPES, "the reference/topology census must still bar the URI shape"
    assert "://" not in witness.TEXT_LEAK_SHAPES, (
        "the bounded free-text census must NOT bar `://` — the serving edge that admits the field declares it lawful "
        "in business free text, so barring it here rejects a correct answer"
    )
    for shape in ("eyJ", "-----BEGIN", "AKIA", "ghp_", "xox", "password=", "PGPASSWORD"):
        assert shape in witness.TEXT_LEAK_SHAPES, f"credential/token/PEM detection must be undiminished in free text: {shape!r}"

    for lawful in (
        "Teaser deck at https://example.com/deck and notes at http://example.com:8080/notes",
        "Ships an API; see https://docs.example.com/v1 for the schema.",
    ):
        witness.assert_no_leak({"served_get": _served_artifact(lawful)}, [], [])

    # The PEM and AWS probes are ASSEMBLED, not written out: a full-shape literal in a tracked file is
    # exactly what `test_no_secret_literals` exists to refuse, and it refuses it here too. Do not
    # "tidy" these back into single literals — the guard will fail, correctly.
    for hostile in (
        "eyJ" + "hbGciOiJIUzI1NiJ9.payload.signature",
        "-----BEGIN " + "PRIVATE KEY-----",
        "postgresql://placeholder-user:placeholder-material@127.0.0.1:5541/placeholder_db",
        "AKIA" + "IOSFODNN7EXAMPLE",
        "PGPASSWORD",
    ):
        try:
            witness.assert_no_leak({"served_get": _served_artifact(hostile)}, [], [])
        except AssertionError:
            continue
        raise AssertionError(f"the no-leak scan accepted secret-shaped free text: {hostile[:28]!r}")

    # The partition is scoped to the ONE bounded free-text field. A URI in a REFERENCE field, or in a
    # body that does not parse, is still a leak — and the verbatim-secret and physical-database
    # censuses run over the WHOLE artifact regardless. The partition narrows one census, not three.
    reference_leak = json.dumps({**_FIXTURE_RECORD, "display_name": "acct://internal/host", "short_description": "plain text"})
    for artifact, secrets, databases in (
        ("status=503 body=postgresql://host/db", [], []),
        (f"status=200 body={reference_leak}", [], []),
        (_served_artifact("plain text"), ["clm-startup-1"], []),
        (_served_artifact("plain text"), [], ["lineage"]),
    ):
        try:
            witness.assert_no_leak({"served_get": artifact}, secrets, databases)
        except AssertionError:
            continue
        raise AssertionError("the whole-artifact censuses must still apply outside the bounded free-text field")


def test_row_absence_is_distinguishable_from_a_lawful_null_short_description() -> None:
    """RV-10. Three states, three distinct answers — executed against the real helpers.

    `short_description` is nullable by DDL (`infrastructure/db/tenant/003_startups.sql`) and at the
    edge (`_bounded_short_description` returns `None` for a JSON `null`). A witness that read the
    VALUE to decide whether the ROW exists aborts a correct run with a factually false diagnostic.
    """
    witness = _witness_module()

    absent = _FakeConnection(row_present=False, value=None)
    assert witness.startup_row_exists(absent, "clm-startup-1") is False, "an ABSENT row must be reported as absent"
    assert witness.read_short_description(absent, "clm-startup-1") is None

    null_row = _FakeConnection(row_present=True, value=None)
    assert witness.startup_row_exists(null_row, "clm-startup-1") is True, (
        "a PRESENT row whose short_description is NULL must be reported as present — this is the lawful state that "
        "used to abort a correct run with 'does not exist in the ACME database'"
    )
    assert witness.read_short_description(null_row, "clm-startup-1") is None

    valued = _FakeConnection(row_present=True, value="a bounded description")
    assert witness.startup_row_exists(valued, "clm-startup-1") is True
    assert witness.read_short_description(valued, "clm-startup-1") == "a bounded description"

    assert any(statement.startswith("SELECT 1 ") for statement in null_row.statements), (
        "row presence must be established by its own existence probe, not by reading the nullable value and testing it"
    )


def test_the_positive_control_and_the_restore_do_not_key_on_a_nullable_value() -> None:
    """RV-10 at the call site. Correct helpers do not help if `cmd_run` still asks the wrong question."""
    conditions = _asserted_conditions("cmd_run")
    assert "startup_row_exists(acme" in conditions, (
        "the positive control must assert ROW EXISTENCE. Testing the nullable value conflates an absent row with a "
        "present row holding a lawful NULL, and then reports the second as the first."
    )
    assert "original is not None" not in conditions, "a nullable value may not stand in for row existence in any of the run's assertions"
    finally_source = "\n".join(
        ast.get_source_segment(_text(), stmt) or ""
        for node in ast.walk(_func("cmd_run"))
        if isinstance(node, ast.Try) and node.finalbody
        for stmt in node.finalbody
    )
    assert "write_attempted" in finally_source, (
        "the restore must key on whether the WRITE LEG ran. Keying on the nullable pre-state value left a run that "
        "wrote nothing in NEITHER branch, so it printed a restore failure it had not had."
    )
    assert "original is None" not in finally_source, "the nullable pre-state value must not be the 'nothing was written' signal"
    run = _source("cmd_run")
    set_at = run.find("write_attempted = True")
    patch_at = run.find('_http("PATCH"')
    assert set_at != -1 and patch_at != -1 and set_at < patch_at, (
        "the write-attempted flag must be set BEFORE the PATCH is issued: a write that reached the physical database "
        "and then failed a later assertion still has to be restored"
    )


def test_witness_carries_no_ddl_no_membership_write_and_no_env_persistence() -> None:
    text = _text()
    for banned in ("CREATE TABLE", "DROP TABLE", "ALTER TABLE", "CREATE DATABASE", "DROP DATABASE", "TRUNCATE"):
        assert banned not in text, f"the witness must apply no DDL ({banned})"
    assert "INSERT INTO control_memberships" not in text, (
        "the witness must never create a membership row. Creating one to make the journey pass is a Gate-B M6 "
        "mutation and it destroys the evidence."
    )
    assert "os.environ[" not in text, "the witness must not persist any environment variable"
    tree = _tree()
    for module in _scan.imported_modules(_WITNESS):
        assert module.split(".")[0] not in {"psycopg", "psycopg2", "asyncpg", "sqlalchemy"}, (
            f"no static driver import ({module}); psycopg must be located via importlib at call time"
        )
    assert "importlib.util.find_spec" in text, "the driver must be located at call time"
    assert isinstance(tree, ast.Module)


def test_plan_and_status_are_read_only() -> None:
    """Asserted against the AST, not the prose.

    `status` legitimately *names* the GET/PATCH chain when stating what it does NOT prove. A raw
    substring scan would read that disclaimer as a write.
    """
    write_methods = {"PATCH", "POST", "PUT", "DELETE"}
    for name in ("cmd_plan", "cmd_status"):
        node = _func(name)
        used = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
        used |= {n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)}
        for mutating in ("cmd_run", "commit"):
            assert mutating not in used, f"{name} must not reference {mutating}"
        # No _http() call may carry a write verb as its method argument.
        for call in (n for n in ast.walk(node) if isinstance(n, ast.Call)):
            target = call.func.id if isinstance(call.func, ast.Name) else getattr(call.func, "attr", "")
            if target != "_http" or not call.args:
                continue
            first = call.args[0]
            assert isinstance(first, ast.Constant) and first.value not in write_methods, (
                f"{name} issues an HTTP {getattr(first, 'value', '?')} — plan and status are read-only"
            )
        # No SQL write literal may appear as an executed constant.
        for const in (n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)):
            upper = const.upper().lstrip()
            assert not upper.startswith(("UPDATE ", "INSERT ", "DELETE ", "TRUNCATE ")), (
                f"{name} carries an executable write statement: {const!r}"
            )
    assert "read_only = True" in _source("cmd_plan"), "plan's connection must be read-only"


def test_only_the_allowlisted_content_field_is_written() -> None:
    text = _text()
    assert 'PATCH_FIELD = "short_description"' in text, "exactly one allow-listed content field (IC-010 CLM)"
    assert "PATCH_FIELD_MAX_CHARS = 500" in text, "the field is bounded at 500 characters"
    run = _source("cmd_run")
    assert "PATCH_FIELD_MAX_CHARS" in run, "the bound must be asserted before the write"


def test_guard_is_non_vacuous() -> None:
    assert _func("cmd_run") is not None and _func("cmd_plan") is not None and _func("cmd_status") is not None
    assert "evaluate_preconditions" in _text()
    node = _func("cmd_run")
    assert [n for n in ast.walk(node) if isinstance(n, ast.Try) and n.finalbody], "the try/finally detector must see one"
    # The assertion-condition extractor must read TESTS, not messages: a hazard named only in an
    # assertion message is exactly the failure mode these checks exist to catch.
    conditions = _asserted_conditions("cmd_run")
    assert conditions and "FAILED:" not in conditions, "the condition extractor must exclude assertion messages"
    # The restated-literal detector must be able to see a violation.
    probe = ast.parse('X = frozenset({"a", "b"})')
    found = [
        n
        for n in ast.walk(probe)
        if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "frozenset" and isinstance(n.args[0], ast.Set)
    ]
    assert found, "the restated-key-set detector must match the literal form it forbids"
    # And the DTO correspondence must be computed from the real contract, not a copy in this file.
    assert dataclasses.is_dataclass(TenantStartupDetailDTO), "the served contract must be a dataclass to be derivable"
    # The free-text partition must actually SPLIT the artifact this guard hands it. A partition that
    # silently found no body would make every RV-9 case pass for the wrong reason.
    reference_text, free_text = _witness_module()._partition_artifact(_served_artifact("https://example.com/deck"))
    assert free_text == ["https://example.com/deck"], "the bounded free-text value must be handed back for its own census"
    assert "https://example.com/deck" not in reference_text, "the free-text value must be removed from the reference text"
    assert '"record_ref": "clm-startup-1"' in reference_text, "every other field must remain under the full census"
    # And the fake connection must be able to express all three row states the positive control faces.
    assert _FakeConnection(row_present=True, value=None).execute("SELECT 1 x", None).fetchone() == (1,)
    assert _FakeConnection(row_present=False, value=None).execute("SELECT 1 x", None).fetchone() is None


if __name__ == "__main__":
    _scan.run(
        [
            test_witness_and_its_documentation_exist,
            test_witness_is_registered_as_a_manual_only_exception,
            test_run_refuses_without_an_explicit_start_gate,
            test_no_subcommand_resolves_to_the_read_only_path,
            test_preconditions_gate_every_evidence_claim,
            test_the_served_body_discriminator_matches_the_real_served_dto,
            test_the_discriminator_is_derived_and_never_restated,
            test_physical_identity_is_the_pair_not_the_system_identifier_alone,
            test_independent_verification_is_a_separate_connection,
            test_restore_is_in_finally_and_proven_by_a_digest,
            test_isolation_stages_are_distinguished,
            test_every_isolation_leg_asserts_and_a_200_breach_fails,
            test_the_auth_stage_isolation_leg_cannot_be_silently_skipped,
            test_finally_cannot_mask_the_real_failure,
            test_the_no_leak_scan_covers_both_bearers,
            test_runtime_posture_is_declared_not_claimed_as_proof,
            test_zeta_is_proven_unchanged,
            test_no_leak_scan_covers_every_shape,
            test_lawful_url_free_text_passes_the_no_leak_scan_but_credential_shapes_still_fail,
            test_row_absence_is_distinguishable_from_a_lawful_null_short_description,
            test_the_positive_control_and_the_restore_do_not_key_on_a_nullable_value,
            test_witness_carries_no_ddl_no_membership_write_and_no_env_persistence,
            test_plan_and_status_are_read_only,
            test_only_the_allowlisted_content_field_is_written,
            test_guard_is_non_vacuous,
        ]
    )
