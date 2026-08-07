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
* **Both isolation legs are recorded separately, and NEITHER is labelled router-stage.** The
  ZETA-claim denial fires in the Auth Router before any routing or tenant-DB contact, and so does the
  unregistered-tenant carrier leg; presenting either as router-stage isolation claims something it
  does not prove (GBR-1).
* **A `403` with an empty body cannot establish E48 on its own — and on this runtime nothing can.**
  FOUR reasons render it identically: `carrier_mismatch`, `tenant_context_required`,
  `tenant_access_denied` and `tenant_not_ready`. The durable record separates the first two and
  **cannot separate the last two** — `not_ready()` carries the same `403`, the Auth Router edge
  collapses every non-carrier-mismatch `403` to `forbidden`, and the Gateway emits a `RouteDenied`
  row with no references either way. So a no-reference row is an **ambiguous pre-auth denial** and
  E48 resolves to `NOT AVAILABLE / UNPROVEN`, never to a pass. All of it is EXECUTED here against the
  witness's own functions with synthetic durable rows, including that the `tenant_access_denied`
  branch is reachable given a recognised authoritative signal — and that the shipped set of such
  signals is empty, because this runtime emits none.
* **The Control-database read stays as narrow as it is described — bounded by an ALLOW-LIST.** The
  one permitted business statement is pinned verbatim; any statement touching any governed Control
  table (including inside a CTE) other than that one fails; the only permitted write anywhere is the
  tenant-DB restore; `cmd_run`'s `control.read_only = True` is pinned as an assignment; and the
  physical-identity metadata reads are named as metadata rather than counted as business reads. The
  first version of this rule forbade the read outright, which enshrined the claim-blind denial leg;
  the second banned five table names, which a CTE and every unlisted Control table stepped around.
* **The shipped prose matches `cmd_run`'s real control flow (F-6).** The E48 assertion is sequenced
  BEFORE the second isolation leg, and — proven here by EXECUTING `e48_problems` against the ambiguous
  durable row this runtime emits — it cannot pass, so leg 2 is unreachable. The ordering is read from
  the AST as statement indices within one try-body, never from line numbers. The runbook and the
  evidence template must state the consequence: no per-run leg count, leg 2 not reached while GBR-4
  is open, the mandated two-leg record currently unproducible, and a one-leg record not acceptable as
  final isolation evidence. Documenting a record the code cannot produce is the same defect class as
  documenting a read the code no longer performs.
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
import contextlib
import dataclasses
import importlib.util
import json
import pathlib
import re
import sys
from types import ModuleType
from typing import Any, Callable, FrozenSet, Iterator, List, Optional, Sequence, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

sys.path.insert(0, str(_scan.BACKEND_ROOT))
from api_gateway.portal import TenantStartupDetailDTO  # noqa: E402

_WITNESS = _scan.BACKEND_ROOT / "tests" / "control_plane" / "requires_pg" / "test_pg_clm_acme_dataplane_witness.py"
_RUNBOOK = _scan.REPO_ROOT / "infrastructure" / "runbooks" / "clm_acme_dataplane_witness.md"
_TEMPLATE = _scan.REPO_ROOT / "docs" / "infrastructure" / "clm_dataplane_evidence_template.md"
_COMPLETENESS_GUARD = _scan.BACKEND_ROOT / "tests" / "architecture" / "test_live_pg_workflow_runset_completeness.py"
_CONTROL_DDL_DIR = _scan.REPO_ROOT / "infrastructure" / "db" / "control"
_CREATE_TABLE = re.compile(r"CREATE TABLE IF NOT EXISTS\s+(?P<table>\w+)", re.IGNORECASE)

# ---- C2-4: the Control-DB read surface, allow-listed by SHAPE ---------------------------------
# The ONE Control business-data statement the witness may execute, pinned verbatim (whitespace
# normalized). An allow-list, because a deny-list of table names cannot bound a surface that grows —
# and because a CTE, a join or a second statement steps around a name ban without touching it.
_PERMITTED_CONTROL_READ = (
    "SELECT action, outcome, actor_ref IS NOT NULL, tenant_ref IS NOT NULL, carrier_ref IS NOT NULL "
    "FROM control_gateway_audit WHERE correlation_id = %s ORDER BY id"
)
# The ONE write the witness may execute at all: the tenant-DB restore, in `finally`.
_PERMITTED_WRITE = "UPDATE startups SET short_description = %s WHERE global_startup_id = %s"
# Cluster/session METADATA: no table, no business row. Explicitly permitted, and explicitly NOT
# counted as Control business-table reads — the documentation that called the correlation read the
# witness's "only" Control-database read was wrong precisely because these exist.
_PERMITTED_METADATA = ("SELECT system_identifier FROM pg_control_system()", "SELECT current_database()")
_WRITE_VERBS = ("INSERT", "UPDATE", "DELETE", "TRUNCATE", "MERGE", "CREATE", "ALTER", "DROP", "GRANT", "REVOKE", "COPY", "CALL", "DO ")


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


def test_isolation_legs_are_distinguished_and_neither_claims_router_stage() -> None:
    """RB-3 wording correction. Two legs, distinct labels, and NEITHER labelled router-stage.

    The second leg presents the ACME bearer with an unregistered-tenant carrier. That is resolved as
    `carrier_mismatch` in the **Auth Router** path (`http_authenticator.py:122-123`,
    `gateway.py:200`) — pre-routing, the same stage as the ZETA leg. The denial is real and is
    correctly asserted; calling it "ROUTER STAGE" claimed a stage it never reached (GBR-1), and a
    completed evidence record inherited that claim.
    """
    run = _source("cmd_run")
    assert "isolation_auth_stage" in run and "isolation_unregistered_carrier" in run, (
        "the two isolation legs must be captured under distinct, ACCURATE labels"
    )
    assert "AUTH STAGE" in run and "UNREGISTERED-TENANT CARRIER" in run, "the two legs must be reported distinctly"
    assert "does NOT prove the Database Router would have refused" in run, (
        "the ZETA-claim denial fires in the Auth Router BEFORE any routing or tenant-DB contact. Presenting it as "
        "router-stage isolation claims something it does not prove, and the caveat must travel with the evidence."
    )
    text = _text()
    assert "isolation_router_stage" not in text and "ROUTER STAGE" not in text, (
        "no leg may be labelled 'router stage'. Both legs are resolved pre-routing, so the label asserts a stage "
        "neither reaches — and the label, not the assertion, is what travels into the evidence record."
    )
    assert "remains UNPROVEN by this harness" in run, (
        "the harness must state, in its own run output, that router-stage isolation is unproven — the operator reads "
        "the printout, not this guard"
    )
    for document, label in ((_RUNBOOK, "runbook"), (_TEMPLATE, "evidence template")):
        body = document.read_text(encoding="utf-8")
        assert "isolation_router_stage" not in body, f"the {label} must not name a retired artifact key"


def test_the_expected_audit_inventory_includes_the_carrier_mismatch_class() -> None:
    """GBR-2. `CarrierMismatch` is durably homed by D-43 and IS what the second leg emits.

    Listing three of the four classes made the inventory read as exhaustive while under-counting by
    one: an operator reconciling their separate Control-DB read against it would find a durable row
    they had no entry for, and the natural resolution of that is to doubt the row.
    """
    witness = _witness_module()
    assert "CarrierMismatch" in witness.EXPECTED_AUDIT_ACTIONS, (
        "the expected durable audit inventory must include CarrierMismatch (D-43, "
        "control_plane/adapters/providers/http_gateway_audit_api.py:117)"
    )
    for action in ("tenant_startup_read", "tenant_startup_update", "RouteDenied"):
        assert action in witness.EXPECTED_AUDIT_ACTIONS, f"{action} must remain in the inventory"
    # And the inventory must not silently widen: the fifth durable class belongs to another journey.
    assert "workspace_memberships_read" not in witness.EXPECTED_AUDIT_ACTIONS, (
        "workspace_memberships_read is durably homed but is NOT emitted by this journey; listing it would over-count"
    )
    template = _TEMPLATE.read_text(encoding="utf-8")
    assert "`CarrierMismatch`" in template, "the evidence template's audit inventory must carry the CarrierMismatch row"


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
    assert "not e48" in conditions, (
        "the auth-stage denial must be asserted through the E48 predicate, not merely printed. Asserting `status == 403 "
        "and not body` at the call site is exactly the claim-blind check RB-3 reports: all FOUR denial reasons render "
        "that response, and two of them are indistinguishable even in the durable record."
    )
    assert "(CONTROL_DSN_ENV, control_dsn)" in run, (
        "the Control reference must be in the MANDATORY value census. Without the durable denial record the E48 claim "
        "is unfalsifiable, and an unfalsifiable claim that still exits 0 is the defect."
    )
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
        "the witness makes no claim about which store served the routing view. Claiming a cross-read that does not "
        "exist is how a checkbox with no implementation reaches an evidence template."
    )


def governed_control_tables() -> FrozenSet[str]:
    """Every Control business table, DERIVED from the governed on-disk DDL.

    Derived, not listed: the predecessor of this check banned five table names, so the Control
    tables it had never heard of — `control_directory`, `control_distinctness_ledger`,
    `control_import_audit` — were readable without limit. A deny-list of names cannot bound a surface
    that grows.
    """
    tables: set = set()
    for path in sorted(_CONTROL_DDL_DIR.glob("*.sql")):
        tables |= {match.group("table") for match in _CREATE_TABLE.finditer(path.read_text(encoding="utf-8"))}
    return frozenset(tables)


def _normalized(statement: str) -> str:
    return " ".join(statement.split())


def _executed_statements() -> List[str]:
    """Every SQL statement the witness actually EXECUTES, read from its `.execute(...)` call sites.

    Call sites, not "string constants that look like SQL": a docstring legitimately NAMES
    `control_tenants` when stating what the witness does *not* read, and a prose scan would flag the
    disclaimer as the thing it disclaims. Fail-closed — a statement that is not a literal at its call
    site cannot be read by this guard, so it is a FAILURE here rather than an unexamined pass.
    """
    statements: List[str] = []
    for node in ast.walk(_tree()):
        method = getattr(getattr(node, "func", None), "attr", "")
        # Any OTHER way of handing SQL to the driver would route around the allow-list below, so the
        # alternatives are refused outright rather than parsed.
        assert method not in ("executemany", "copy", "copy_expert", "copy_from", "copy_to", "callproc"), (
            f"the witness must reach the database only through `.execute(<literal>)`; `{method}()` would carry SQL past "
            "the shape allow-list below"
        )
        if not isinstance(node, ast.Call) or method != "execute":
            continue
        assert node.args, f"an execute() call with no statement argument cannot be bounded (line {node.lineno})"
        first = node.args[0]
        assert isinstance(first, ast.Constant) and isinstance(first.value, str), (
            f"every executed statement must be a string LITERAL at its call site (line {node.lineno}), so this guard "
            "can read it. A statement assembled elsewhere is unreadable here, and an unreadable statement is not a "
            "bounded one."
        )
        statements.append(first.value)
    return statements


def test_the_control_database_read_is_bounded_to_an_allow_listed_shape() -> None:
    """RB-3 / C2-4. The Control read exists now — bounded by an ALLOW-LIST of the exact shape.

    Before RB-3 this guard forbade any use of `CONTROL_DSN_ENV` beyond a presence report, which had
    the effect of ENSHRINING the claim-blind ZETA leg: the only discriminator between the denial
    reasons lives in the Control database. Its replacement banned five table names — which a CTE
    stepped around, and which said nothing at all about the Control tables not on the list, or about
    whether the connection was even read-only.

    So the rule is stated the other way round: the permitted Control business statement is pinned
    verbatim, every other Control-table access fails whatever its syntax, the only permitted write is
    the tenant-DB restore, and the metadata reads are named as metadata rather than being invisible.
    """
    governed = governed_control_tables()
    assert "control_gateway_audit" in governed and len(governed) >= 5, (
        f"the governed Control DDL must be parseable for this check to bound anything; parsed tables: {sorted(governed)}"
    )
    statements = _executed_statements()
    assert statements, "the witness must execute at least one statement, or this guard is vacuous"

    # (1) The Control connection is READ-ONLY at the connection level. Asserted as an assignment in
    # the AST — `"read_only = True" in source` is satisfied by the ACME/ZETA connections and by any
    # comment, and it was: only `cmd_plan`'s read_only was pinned, never `cmd_run`'s Control one.
    run_node = _func("cmd_run")
    read_only_assignments = [
        node
        for node in ast.walk(run_node)
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Attribute)
        and node.targets[0].attr == "read_only"
        and isinstance(node.targets[0].value, ast.Name)
        and node.targets[0].value.id == "control"
        and isinstance(node.value, ast.Constant)
        and node.value.value is True
    ]
    assert read_only_assignments, (
        "cmd_run's Control connection must be set `control.read_only = True`. Without it the harness holds a writable "
        "handle on the Control database for the whole run, and 'it only ever SELECTs' is a property of today's code "
        "rather than of the connection."
    )
    control_connects = [
        node.value
        for node in ast.walk(run_node)
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id == "control"
        and isinstance(node.value, ast.Call)
    ]
    assert control_connects, "cmd_run must open the Control connection by an assignment this guard can find"
    for call in control_connects:
        assert not any(keyword.arg == "autocommit" for keyword in call.keywords), (
            "the Control connection must not be opened autocommit — the ACME/ZETA connections are, and copying that "
            "onto a read-only census connection is how a write surface appears by accident"
        )

    # (2) BUSINESS-DATA SQL: any statement touching any governed Control table, by any syntax. A CTE
    # (`WITH t AS (SELECT ... FROM control_tenants) ...`) is caught here because the test is on the
    # table NAME anywhere in the statement, not on the leading verb or the FROM clause.
    business = {
        _normalized(statement): {table for table in governed if re.search(rf"\b{table}\b", statement)}
        for statement in statements
        if any(re.search(rf"\b{table}\b", statement) for table in governed)
    }
    assert list(business) == [_PERMITTED_CONTROL_READ], (
        "the witness's Control business-data SQL must be EXACTLY the one allow-listed statement.\n"
        f"  permitted: {_PERMITTED_CONTROL_READ}\n"
        f"  found    : {list(business)}\n"
        "Its Control mandate is the denial record for its own correlation ids and nothing else; the durable routing "
        "cross-read is a separate Gate-B operator step."
    )
    assert business[_PERMITTED_CONTROL_READ] == {"control_gateway_audit"}, (
        f"the permitted statement must touch ONE Control table, found {sorted(business[_PERMITTED_CONTROL_READ])}"
    )
    # Stated as their own reasons, because the byte-pin above says WHAT but not WHY.
    assert "WHERE correlation_id = %s" in _PERMITTED_CONTROL_READ, (
        "the Control read is filtered to ONE correlation id — the one this witness minted for its own request. An "
        "unfiltered read is a scan of an audit table this harness has no mandate over."
    )
    assert "IS NOT NULL" in _PERMITTED_CONTROL_READ and "actor_ref," not in _PERMITTED_CONTROL_READ, (
        "the reference columns are read as IS NOT NULL BOOLEANS, never as values: presence is the whole discriminator, "
        "and a value that never enters the process cannot leak from it"
    )

    # (3) WRITES, of any kind, anywhere in the witness. The only one permitted is the tenant-DB
    # restore in `finally`; an INSERT/UPDATE/DELETE/TRUNCATE/DDL against anything else fails here
    # whether or not it names a Control table.
    writes = [_normalized(statement) for statement in statements if _normalized(statement).upper().startswith(_WRITE_VERBS)]
    assert writes == [_PERMITTED_WRITE], (
        f"the only write the witness may execute is the tenant-DB restore.\n  permitted: {_PERMITTED_WRITE}\n  found    : {writes}"
    )

    # (4) METADATA reads are ALLOWED, and are explicitly not business-table reads. Naming them is the
    # point: the documentation used to say the correlation read was the ONLY Control-database read,
    # which was false — `physical_identity` runs these two on the same connection.
    for metadata in _PERMITTED_METADATA:
        assert any(_normalized(statement) == metadata for statement in statements), (
            f"the metadata read {metadata!r} must be present — the physical-identity pair and the no-leak census both depend on it"
        )
        assert not [table for table in governed if re.search(rf"\b{table}\b", metadata)], (
            f"{metadata!r} must name no governed Control table; it is cluster/session metadata, not business data"
        )

    # (5) The bounded read lives in its own named function, and both legs read their own record.
    assert "control_gateway_audit" in _source("read_denial_audit"), "the bounded read must live in its own named function"
    run = _source("cmd_run")
    assert "uuid.uuid4().hex" in run and "CORRELATION_HEADER" in run, (
        "each denial leg must mint its own correlation id and hand it to the Gateway. Without one the Gateway mints an "
        "id this process never sees, and an audit row nobody can find is not evidence."
    )
    assert run.count("read_denial_audit(control") == 2, "both denial legs must read their own durable record"


# ---------------------------------------------------------------------------------------------
# RB-3 — the five properties the corrected E48 claim must have. EXECUTED against the witness's own
# functions with synthetic durable rows: no database, no service, no bearer.
#
# Row shape is `read_denial_audit`'s projection:
#   (action, outcome, actor_ref IS NOT NULL, tenant_ref IS NOT NULL, carrier_ref IS NOT NULL)
# ---------------------------------------------------------------------------------------------
def _row(action: str, *, actor: bool = False, tenant: bool = False, carrier: bool = False) -> tuple:
    return (action, "rejected", actor, tenant, carrier)


def _denial_rows(witness: ModuleType) -> dict:
    """The synthetic durable record each UPSTREAM denial reason produces, as the Gateway emits it.

    Keyed by the reason the Auth Router raised, NOT by what the record proves — because two of the
    four keys map to the SAME row, and that collision is the C2-3 finding.
    """
    return {
        # tenant_context.py:45 -> forbidden -> gateway.py:199-211, the authenticator-rejection
        # branch: it runs before any AuthContext exists, so no reference is carried.
        "tenant_access_denied": [_row(witness.ROUTE_DENIED_ACTION)],
        # tenant_context.py:47 -> not_ready -> models.py:96 gives it the SAME 403 ->
        # http_authenticate_api.py:123 collapses it to `forbidden` -> the SAME durable row.
        "tenant_not_ready": [_row(witness.ROUTE_DENIED_ACTION)],
        # gateway.py:237 — the post-authentication dispatch branch: actor_ref=principal_ref.
        "tenant_context_required": [_row(witness.ROUTE_DENIED_ACTION, actor=True)],
        # gateway.py:200-207 — the D-43 durably homed carrier-mismatch record.
        "carrier_mismatch": [_row(witness.CARRIER_MISMATCH_ACTION, carrier=True)],
    }


@contextlib.contextmanager
def _a_recognised_signal(witness: ModuleType, name: str = "e48_probe_signal") -> Iterator[str]:
    """Temporarily give the witness ONE recognised authoritative signal.

    The shipped set is empty, so without this the `tenant_access_denied` branch is unreachable and
    could be dead code that no test distinguishes from a hard-wired refusal. Patching it proves the
    branch is live AND lets the wire-shape necessity checks run against a record that would satisfy
    E48 — while the assertion that the SHIPPED set is empty keeps the honest verdict on the runtime.
    """
    original = witness.RECOGNISED_UNIQUE_DENIAL_SIGNALS
    witness.RECOGNISED_UNIQUE_DENIAL_SIGNALS = frozenset({name})
    try:
        yield name
    finally:
        witness.RECOGNISED_UNIQUE_DENIAL_SIGNALS = original


def test_a_no_actor_route_denied_is_ambiguous_and_yields_e48_unproven() -> None:
    """RB-3 proof 1, corrected (C2-3). The row that used to BE E48 evidence cannot be.

    `tenant_access_denied` (non-member of a Ready tenant, `tenant_context.py:45`) and
    `tenant_not_ready` (member of a known-but-dormant tenant, `:47`) are different facts, and only
    the first is authorization denial. They reach `control_gateway_audit` as the SAME row:
    `models.py:96-97` gives `not_ready()` the same 403, `http_authenticate_api.py:123-124` collapses
    every non-carrier-mismatch 403 to `forbidden`, `http_authenticator.py:119-124` repeats it, and
    `gateway.py:199-211` emits `RouteDenied` with actor/tenant/carrier all NULL either way.

    So the durable record cannot decide between them, and a witness that reads it as the first one
    files a `tenant_not_ready` denial as genuine authorization denial. This environment provisions a
    dormant tenant on purpose, so that is reachable, not theoretical.
    """
    witness = _witness_module()
    rows = _denial_rows(witness)
    assert rows["tenant_access_denied"] == rows["tenant_not_ready"], (
        "the two upstream reasons must be represented by the SAME durable row here — if they were not, this test "
        "would be checking a distinction the runtime does not actually make"
    )
    reason, detail = witness.classify_denial_reason(rows["tenant_access_denied"])
    assert reason == witness.DENIAL_PRE_AUTH_AMBIGUOUS, (
        f"a RouteDenied row with no actor, tenant or carrier reference must classify as an AMBIGUOUS pre-auth denial, "
        f"got {reason!r}. Naming it tenant_access_denied asserts a fact the record does not carry."
    )
    assert detail and "tenant_not_ready" in detail, "the ambiguity must NAME the other reason the row could be"
    problems = witness.e48_problems(403, b"", rows["tenant_access_denied"])
    assert problems, "an ambiguous pre-auth denial must FAIL the E48 claim"
    assert "E48 NOT AVAILABLE / UNPROVEN" in problems[0], (
        f"the verdict must read as UNPROVEN, not as refuted — the evidence cannot decide, which is a different finding "
        f"from deciding against. Got: {problems[0][:120]!r}"
    )
    assert witness.E48_REQUIRED_DENIAL_REASON == witness.DENIAL_TENANT_ACCESS_DENIED, (
        "E48 itself is unchanged: the claim is still 'ZETA denial is genuine authorization denial'. What changed is "
        "that the harness no longer asserts it from a record that cannot carry it."
    )


def test_tenant_not_ready_cannot_satisfy_e48() -> None:
    """RB-3 proof 1b (C2-3). The fourth reason, stated as its own refusal.

    A member of a known-but-dormant tenant is not denied ACCESS — the tenant is not serving. The
    §28 Definition-of-Done line is about authorization, so this must never satisfy it, and it must
    not do so through the back door of being indistinguishable from the one that would.
    """
    witness = _witness_module()
    rows = _denial_rows(witness)["tenant_not_ready"]
    reason, _detail = witness.classify_denial_reason(rows)
    assert reason != witness.DENIAL_TENANT_ACCESS_DENIED, (
        "a tenant_not_ready denial was classified as genuine authorization denial. It is not one: the principal holds "
        "the membership and the tenant is simply not Ready (auth_router/tenant_context.py:47)."
    )
    assert witness.e48_problems(403, b"", rows), "tenant_not_ready must FAIL the E48 claim"
    # And it must fail for EVERY signal an operator could supply, because none is recognised.
    for supplied in (None, "", "not_ready", "tenant_access_denied", "trust me"):
        assert witness.e48_problems(403, b"", rows, unique_signal=supplied), (
            f"a caller-supplied {supplied!r} must not unlock E48 — only a signal in RECOGNISED_UNIQUE_DENIAL_SIGNALS "
            "can, and that set is empty on this runtime"
        )


def test_only_a_unique_authoritative_signal_can_satisfy_e48() -> None:
    """RB-3 proof 6 (C2-3). The gate is a recognised signal, and there is not one.

    Two things must both be true, and each is worthless without the other: the `tenant_access_denied`
    branch must be REACHABLE (otherwise this is a hard-wired refusal dressed up as a discriminator,
    and it would keep passing if the row shapes changed), and the shipped recognised-signal set must
    be EMPTY (otherwise E48 is being satisfied by something this runtime does not actually emit).
    """
    witness = _witness_module()
    assert witness.RECOGNISED_UNIQUE_DENIAL_SIGNALS == frozenset(), (
        f"the shipped set of authoritative signals that uniquely prove tenant_access_denied must be EMPTY on this "
        f"runtime — nothing separates it from tenant_not_ready by the time the durable row is written. Found: "
        f"{sorted(witness.RECOGNISED_UNIQUE_DENIAL_SIGNALS)}. Adding a name here is a claim that the runtime emits it."
    )
    rows = _denial_rows(witness)["tenant_access_denied"]
    with _a_recognised_signal(witness) as signal:
        reason, _detail = witness.classify_denial_reason(rows, unique_signal=signal)
        assert reason == witness.DENIAL_TENANT_ACCESS_DENIED, (
            "with a RECOGNISED authoritative signal the classifier must be able to reach tenant_access_denied. If it "
            "cannot, the discriminator is a constant refusal and proves nothing about the row it was handed."
        )
        assert witness.e48_problems(403, b"", rows, unique_signal=signal) == [], (
            "a 403, an empty body and a uniquely-proven genuine denial must satisfy E48"
        )
        # An UNRECOGNISED signal must not, even while a recognised one exists.
        assert witness.e48_problems(403, b"", rows, unique_signal="something-else"), (
            "an arbitrary caller-supplied string must not unlock E48; only a recognised signal may"
        )
        # The wire shape stays NECESSARY even when the record would otherwise satisfy the claim.
        assert witness.e48_problems(200, b"", rows, unique_signal=signal), "a 200 is an isolation breach, not a denial"
        assert witness.e48_problems(503, b"", rows, unique_signal=signal), "a 503 is the upstream/audit collapse"
        assert witness.e48_problems(403, b'{"detail": "no"}', rows, unique_signal=signal), "a denial with a body disclosed something"
        # And the other three reasons still fail, signal or not: the signal narrows an ambiguity, it
        # does not override the record.
        for label in ("tenant_context_required", "carrier_mismatch"):
            assert witness.e48_problems(403, b"", _denial_rows(witness)[label], unique_signal=signal), (
                f"{label} must fail E48 regardless of any supplied signal"
            )
    assert witness.RECOGNISED_UNIQUE_DENIAL_SIGNALS == frozenset(), "the probe must restore the shipped (empty) set"
    assert witness.e48_problems(403, b"", rows, unique_signal="e48_probe_signal"), (
        "with the shipped set restored, the same signal must stop working — E48 is UNPROVEN on this runtime"
    )


def test_tenant_context_required_cannot_satisfy_e48() -> None:
    """RB-3 proof 2. The bearer authenticated and simply carried no tenant claim — nobody was denied
    access to ZETA, and the wire response is byte-identical to the one that means they were."""
    witness = _witness_module()
    rows = _denial_rows(witness)[witness.DENIAL_TENANT_CONTEXT_REQUIRED]
    reason, _detail = witness.classify_denial_reason(rows)
    assert reason == witness.DENIAL_TENANT_CONTEXT_REQUIRED, (
        f"a RouteDenied row carrying an actor reference is tenant_context_required, got {reason}"
    )
    problems = witness.e48_problems(403, b"", rows)
    assert problems and "E48 NOT SATISFIED" in problems[0], f"tenant_context_required must FAIL the E48 claim, got {problems}"


def test_carrier_mismatch_cannot_satisfy_e48() -> None:
    """RB-3 proof 3. The request was refused for its CARRIER, not for the principal's authorization."""
    witness = _witness_module()
    rows = _denial_rows(witness)[witness.DENIAL_CARRIER_MISMATCH]
    reason, _detail = witness.classify_denial_reason(rows)
    assert reason == witness.DENIAL_CARRIER_MISMATCH, f"a CarrierMismatch row is carrier_mismatch, got {reason}"
    problems = witness.e48_problems(403, b"", rows)
    assert problems and "E48 NOT SATISFIED" in problems[0], f"carrier_mismatch must FAIL the E48 claim, got {problems}"


def test_a_403_with_an_empty_body_alone_cannot_satisfy_e48() -> None:
    """RB-3 proof 4. The whole defect, stated as a test.

    All FOUR reasons render EXACTLY `403` + empty body. The predecessor asserted only that, so any of
    the four passed — and the three wrong ones were filed as E48 evidence. After C2-3 the durable
    record narrows four to three (`carrier_mismatch` and `tenant_context_required` are separable; the
    other two are not), and **none** of them satisfies E48 on this runtime.
    """
    witness = _witness_module()
    assert witness.e48_problems(403, b"", []) != [], (
        "`403` with an empty body and NO authoritative denial evidence must not satisfy E48 — that is precisely the "
        "assertion that could be silently falsified"
    )
    reasons = _denial_rows(witness)
    assert len(reasons) == 4, f"all four identical-on-the-wire denial reasons must be represented, got {sorted(reasons)}"
    satisfied = [reason for reason, rows in reasons.items() if witness.e48_problems(403, b"", rows) == []]
    assert satisfied == [], (
        f"no durable record shape this runtime produces may satisfy E48, got {satisfied}. Two of the four reasons are "
        "byte-identical in the audit table, and only one of those two is authorization denial."
    )
    # The wire shape stays NECESSARY as well as insufficient — proven where a record COULD satisfy
    # the claim, in test_only_a_unique_authoritative_signal_can_satisfy_e48. Here it is proven that
    # the wire shape alone changes nothing: every non-denial status fails for every reason.
    for reason, rows in reasons.items():
        for status, body in ((200, b""), (503, b""), (403, b'{"detail": "no"}')):
            assert witness.e48_problems(status, body, rows), f"{reason} at status={status} body={body!r} must fail E48"


def test_missing_or_uninterpretable_denial_evidence_fails_closed() -> None:
    """RB-3 proof 5. NOT AVAILABLE / UNPROVEN is a finding, never a pass.

    With the durable sink unselected the Gateway emits to the in-memory no-sink emitter and nothing
    is written at all — so the commonest way to reach this code path is also the one that proves
    least. It must fail, and it must say why.
    """
    witness = _witness_module()
    for label, rows in (
        ("no rows at all (durable sink unselected, or the row did not persist)", []),
        ("rows for the correlation, but none of them a denial", [("tenant_startup_read", "success", True, True, False)]),
        ("a denial row whose outcome is not `rejected`", [(witness.ROUTE_DENIED_ACTION, "observed", False, False, False)]),
    ):
        reason, detail = witness.classify_denial_reason(rows)
        assert reason == witness.DENIAL_EVIDENCE_ABSENT, f"{label}: must report NOT AVAILABLE / UNPROVEN, got {reason}"
        assert detail, f"{label}: the absence must be explained, not merely flagged"
        assert witness.e48_problems(403, b"", rows), f"{label}: missing authoritative evidence must FAIL the E48 claim"
    assert "NOT AVAILABLE" in witness.DENIAL_EVIDENCE_ABSENT and "UNPROVEN" in witness.DENIAL_EVIDENCE_ABSENT, (
        "the absent-evidence verdict must READ as unproven wherever it is printed or recorded — it goes into the "
        "captured artifact and from there into the evidence record"
    )
    # Uninterpretable shapes are not guessed at either.
    for label, rows in (
        (
            "two durable denial rows for one request",
            [_row(witness.ROUTE_DENIED_ACTION), _row(witness.CARRIER_MISMATCH_ACTION, carrier=True)],
        ),
        ("a RouteDenied row carrying a tenant reference", [_row(witness.ROUTE_DENIED_ACTION, actor=True, tenant=True)]),
    ):
        reason, _detail = witness.classify_denial_reason(rows)
        assert reason == witness.DENIAL_INDETERMINATE, f"{label}: must be INDETERMINATE, got {reason}"
        assert witness.e48_problems(403, b"", rows), f"{label}: an uninterpretable record must FAIL the E48 claim"


# A claim about the Control read that was true before `run` acquired one, and is false now. It
# survived in three places: two prose sentences and one PRINTED line in `cmd_status` — and the
# printed one is what an operator actually sees, from the command the launcher's start gate runs.
_RETIRED_READ_CLAIMS = (
    "performs no Control-database read",
    "only Control-database read",
    "only** Control-database read",
    "ONLY Control-database read",
    "ONLY Control-database read the witness performs",
)


def test_no_command_or_document_claims_a_control_read_the_witness_now_performs() -> None:
    """C2-5. `run` performs bounded Control reads; nothing may still say it performs none.

    The stale sentence is not a wording nit: it directly contradicts the same runbook's §2 (the
    Control reference is "REQUIRED by `run`") and §6.1, and it is PRINTED by `cmd_status` — the one
    subcommand the launcher's AW-1-adjacent start gate invokes. An operator reading it would conclude
    the Control DSN is optional and configure a run that fails at its isolation legs.
    """
    for label, body in (
        ("the witness", _text()),
        ("the runbook", _RUNBOOK.read_text(encoding="utf-8")),
        ("the evidence template", _TEMPLATE.read_text(encoding="utf-8")),
    ):
        normalized = " ".join(body.split())
        for retired in _RETIRED_READ_CLAIMS:
            assert retired not in normalized, (
                f"{label} still carries the retired claim {retired!r}. `run` opens a read-only Control connection and "
                "issues one bounded correlation-filtered business read PLUS two metadata statements; describing that "
                "as no read, or as the only read, is false in opposite directions."
            )
        assert "pg_control_system" in normalized, (
            f"{label} must distinguish the bounded business-data read of control_gateway_audit from the "
            "physical-identity METADATA reads (pg_control_system() / current_database()) that run on the same "
            "connection. Collapsing the two is what made the previous wording wrong."
        )
    # And `cmd_status` must positively describe what `run` does, not merely stop denying it.
    status = _source("cmd_status")
    assert "control_gateway_audit" in status or "correlation" in status.lower(), (
        "cmd_status must state what Control read `run` performs; a removed sentence leaves an operator with nothing"
    )


# ---------------------------------------------------------------------------------------------
# F-6: the shipped prose must match `cmd_run`'s ACTUAL control flow.
#
# `cmd_run` asserts on E48 BEFORE it issues the second isolation leg, and `e48_problems` cannot
# return empty on this runtime. Those two facts together make leg 2 UNREACHABLE — so any document
# describing a per-run Control-read count, or a complete two-leg record, as something a current run
# produces is describing a run that cannot happen. That is the same C2-5 defect class the check
# above bars, one document along, and it has to be checked by ORDERING rather than by substring
# presence: the wording is wrong only BECAUSE of where the assert sits, so the guard must see where
# it sits. A `"twice" not in text` check would pass the moment the sentence was reworded and would
# never have noticed the ordering that made it false.
# ---------------------------------------------------------------------------------------------

# Per-`run` leg counts a reader takes as a description of a current run. The per-LEG rule is the true
# one and stays; what is barred is restating it as a per-run total while the abort point precedes
# leg 2.
_RETIRED_PER_RUN_LEG_COUNTS = (
    "twice per run",
    "once per denial leg — twice",
    "once per denial leg - twice",
    "two control-database reads per run",
    "two control reads per run",
)


def _prose(text: str) -> str:
    """Markdown reduced to comparable prose: blockquote markers dropped, emphasis/code ticks removed.

    Anchors are checked against THIS, not against the raw file. A `**` moved one word, a sentence
    rewrapped across a line, or a paragraph re-indented inside a blockquote would each break a raw
    substring match — and a guard that fails on reflow gets weakened rather than fixed. Markup is
    replaced by a space, never elided, so removing it cannot glue two words into a third.
    """
    stripped = "\n".join(re.sub(r"^\s*>+\s?", "", line) for line in text.splitlines())
    for markup in ("**", "`", "*", "#"):
        stripped = stripped.replace(markup, " ")
    return " ".join(stripped.split()).lower()


def _isolation_body() -> List[ast.stmt]:
    """The ONE statement list that carries both isolation legs — `cmd_run`'s try/finally body."""
    tries = [n for n in ast.walk(_func("cmd_run")) if isinstance(n, ast.Try) and n.finalbody]
    assert tries, "cmd_run must run its legs inside a try/finally"
    return tries[0].body


def _stmt_index(body: Sequence[ast.stmt], predicate: Callable[[ast.AST], bool], what: str) -> int:
    """Index of the first TOP-LEVEL statement in `body` containing a node matching `predicate`.

    Deliberately a statement index in one body, not a line number. Line numbers would also be
    satisfied by a leg tucked inside a branch the assert does not dominate; equal membership of the
    same unconditional statement list is what makes "the assert runs first" a fact about execution
    rather than about layout.
    """
    for index, stmt in enumerate(body):
        for node in ast.walk(stmt):
            if predicate(node):
                return index
    raise AssertionError(f"cmd_run's try-body must contain {what}")


def _e48_assert_in(source: str) -> Callable[[ast.AST], bool]:
    """`assert not e48...` — matched on the TESTED expression, never on the message."""

    def predicate(node: ast.AST) -> bool:
        if not isinstance(node, ast.Assert):
            return False
        return re.search(r"\bnot\s+e48\b", ast.get_source_segment(source, node.test) or "") is not None

    return predicate


def _unregistered_carrier_request_in(source: str) -> Callable[[ast.AST], bool]:
    """The second isolation leg's actual request — the `_http` call carrying the unregistered tenant."""

    def predicate(node: ast.AST) -> bool:
        if not isinstance(node, ast.Call) or getattr(node.func, "id", "") != "_http":
            return False
        return "tenant-that-does-not-exist" in (ast.get_source_segment(source, node) or "")

    return predicate


def _is_carrier_audit_read(node: ast.AST) -> bool:
    """The second leg's durable audit read, identified structurally by its own correlation id.

    No source segment needed, so no factory: the call target and the argument name are both AST
    facts. Matching on the correlation-id argument is what separates this call from leg 1's.
    """
    if not isinstance(node, ast.Call) or getattr(node.func, "id", "") != "read_denial_audit":
        return False
    return any(getattr(argument, "id", "") == "carrier_correlation" for argument in node.args)


def test_the_e48_abort_precedes_the_second_isolation_leg_and_every_document_says_so() -> None:
    """F-6. The abort point sits BEFORE leg 2, so no document may present leg 2 as reachable today.

    Three things are established here, in order, because each is worthless without the one before:

    1. **Ordering, from the AST** — the E48 assertion, the unregistered-tenant carrier request and
       that leg's audit read are all top-level statements of the SAME try-body, in that order, and
       `legs_ok = True` comes after all of them. So failing the assertion cannot leave leg 2 partly
       done or the run partly green.
    2. **The assertion cannot pass, EXECUTED** — `e48_problems` is called with the ambiguous durable
       row this runtime actually emits and must return a non-empty problem list, and the recognised
       unique-signal set that could override it must be empty. Ordering alone would only make leg 2
       *conditionally* unreachable; this is what makes it unreachable in fact.
    3. **The documents say exactly that** — no per-run leg count, an explicit statement that the
       second leg is not reached while GBR-4 is unresolved, an explicit statement that the two-leg
       record is therefore unproducible and that a one-leg record is not acceptable as final
       evidence, and the standing pins that GBR-4 is OPEN and router-stage isolation UNPROVEN.

    **This test is MEANT to fail when GBR-4 is resolved.** At that point (2) stops holding, leg 2
    becomes reachable, and every sentence pinned in (3) becomes false in the other direction. The fix
    then is to revise the documents in the same edit — not to delete this guard. That coupling is the
    point: the defect it exists to bar (F-6) was created by changing the code and leaving the prose.
    """
    text = _text()
    body = _isolation_body()
    e48_at = _stmt_index(body, _e48_assert_in(text), "the E48 assertion (`assert not e48, ...`)")
    request_at = _stmt_index(body, _unregistered_carrier_request_in(text), "the unregistered-tenant carrier request")
    audit_at = _stmt_index(body, _is_carrier_audit_read, "the carrier leg's durable audit read")
    assert e48_at < request_at < audit_at, (
        f"cmd_run's statement order is E48-assert={e48_at}, carrier-request={request_at}, carrier-audit-read={audit_at}. "
        "This guard, and the shipped wording it pins, both describe the E48 assertion as the abort point that precedes "
        "the second isolation leg. If the order changed, the documents are now wrong in the opposite direction and must "
        "be revised with the code."
    )
    legs_ok_at = _stmt_index(
        body,
        lambda node: isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "legs_ok" for t in node.targets),
        "the `legs_ok = True` success marker",
    )
    assert audit_at < legs_ok_at, (
        "`legs_ok = True` must come after BOTH legs. Set earlier, a run that aborted at the E48 assertion would still "
        "mark its legs good and exit 0 — which is the failure this whole family of checks exists to prevent."
    )

    # (2) EXECUTED: the assertion cannot pass on this runtime, so the ordering is a real abort.
    witness = _witness_module()
    assert not witness.RECOGNISED_UNIQUE_DENIAL_SIGNALS, (
        "RECOGNISED_UNIQUE_DENIAL_SIGNALS must stay empty until a signal that uniquely separates tenant_access_denied "
        "from tenant_not_ready genuinely exists. Non-empty, E48 could pass and leg 2 would become reachable — at which "
        "point the wording pinned below is false and must be revised in the same edit."
    )
    ambiguous_rows = _denial_rows(witness)["tenant_access_denied"]
    assert witness.e48_problems(403, b"", ambiguous_rows), (
        "e48_problems returned NO problems for the ambiguous pre-auth denial this runtime emits. E48 would then be "
        "provable, the run would not abort, and the documents' 'not reached' wording would be wrong."
    )

    # (3) The documents. Anchors are checked against reduced prose so a reflow cannot break them.
    runbook = _prose(_RUNBOOK.read_text(encoding="utf-8"))
    template = _prose(_TEMPLATE.read_text(encoding="utf-8"))
    for label, prose in (("the runbook", runbook), ("the evidence template", template), ("the witness", _prose(text))):
        for retired in _RETIRED_PER_RUN_LEG_COUNTS:
            assert retired not in prose, (
                f"{label} states a per-run leg count ({retired!r}) while the E48 assertion aborts before leg 2. The "
                "bounded Control read runs once PER LEG, and a current run reaches ONE leg — so a per-run total "
                "describes a run this runtime cannot execute."
            )

    for anchor, why in (
        (
            "cmd_run executes the auth-stage (e48) leg first",
            "the runbook must name which leg runs first — the ordering is the whole reason the count is per-leg",
        ),
        ("e48 resolves to not available / unproven", "the runbook must state the verdict the current runtime produces"),
        ("cmd_run fails at that assertion", "the runbook must state that the run ABORTS there, not merely that E48 is unproven"),
        (
            "the second isolation leg is not reached while gbr-4 remains unresolved",
            "the runbook must state the downstream consequence: leg 2 is unreachable, not merely expected to fail",
        ),
        (
            "once gbr-4 is resolved in a way that lets the auth-stage leg pass",
            "the runbook must state that leg 2 becomes reachable — and its Control read issued — after GBR-4 is resolved",
        ),
        ("still leaves router-stage denial unproven", "router-stage isolation must remain UNPROVEN in the runbook"),
    ):
        assert anchor in runbook, f"the runbook must state {anchor!r}: {why}"

    for anchor, why in (
        (
            "both legs remain mandatory for final acceptance",
            "the two-leg requirement must NOT be weakened by disclosing that it cannot currently be met",
        ),
        (
            "the harness cannot currently produce a complete two-leg isolation record",
            "the template must state that the record it mandates is currently unproducible",
        ),
        (
            "the second isolation leg is not reached while gbr-4 remains unresolved",
            "the template must say WHY it is unproducible — the run aborts before leg 2",
        ),
        (
            "incomplete / not acceptable as final isolation evidence",
            "a one-leg record must be named unacceptable, or it becomes the de-facto complete one",
        ),
        ("does not close gbr-4", "filing an incomplete record must not be readable as closing GBR-4"),
        (
            "may not be marked pass until gbr-4 is resolved and both legs execute",
            "the template must bar a PASS verdict for E48 and for full isolation evidence",
        ),
        (
            "remains unproven, by this leg and by this harness",
            "router-stage isolation must remain UNPROVEN in the template",
        ),
    ):
        assert anchor in template, f"the evidence template must state {anchor!r}: {why}"

    # GBR-4 is the gate every sentence above defers to. It must still be OPEN, and nowhere claimed closed.
    assert re.search(r"gbr-4 —.{0,400}?\bopen\b", runbook), (
        "GBR-4 must remain recorded OPEN in the runbook. Every disclosure above is conditioned on it; if it were closed "
        "the conditions would be stale and the second leg would be reachable."
    )
    assert not re.search(r"gbr-4[^.]{0,200}\bclosed\b", runbook), "GBR-4 must not be recorded CLOSED anywhere in the runbook"

    # Non-vacuity, in-place: the ordering detector must be able to SEE the reversed sequence. A helper
    # that returned 0 for every probe would satisfy `e48_at < request_at` by accident, and the whole
    # check above would be decoration.
    probe_source = (
        "def f():\n"
        "    try:\n"
        "        status, _h, body = _http('GET', url, headers={'X-Tenant-Id': 'tenant-that-does-not-exist'})\n"
        "        carrier_rows = read_denial_audit(control, carrier_correlation)\n"
        "        e48 = e48_problems(status, body, zeta_rows)\n"
        "        assert not e48, 'reversed'\n"
        "    finally:\n"
        "        pass\n"
    )
    probe_body = next(n for n in ast.walk(ast.parse(probe_source)) if isinstance(n, ast.Try) and n.finalbody).body
    assert _stmt_index(probe_body, _e48_assert_in(probe_source), "probe assert") > _stmt_index(
        probe_body, _unregistered_carrier_request_in(probe_source), "probe leg 2"
    ), "the ordering detector must report the LATER index for an assert that follows the leg, or it distinguishes nothing"


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
    # The denial classifier must DISCRIMINATE as far as the record allows, and no further. Four
    # upstream reasons, THREE distinct verdicts: `carrier_mismatch` and `tenant_context_required`
    # resolve to themselves, and the two that share a row resolve to one ambiguous verdict. A
    # classifier returning a single constant would satisfy every individual E48 refusal above.
    witness = _witness_module()
    verdicts = {reason: witness.classify_denial_reason(rows)[0] for reason, rows in _denial_rows(witness).items()}
    assert len(verdicts) == 4 and len(set(verdicts.values())) == 3, (
        f"the classifier must separate what the durable record separates and merge what it merges, got {verdicts}"
    )
    assert verdicts["carrier_mismatch"] == witness.DENIAL_CARRIER_MISMATCH
    assert verdicts["tenant_context_required"] == witness.DENIAL_TENANT_CONTEXT_REQUIRED
    assert verdicts["tenant_access_denied"] == verdicts["tenant_not_ready"] == witness.DENIAL_PRE_AUTH_AMBIGUOUS
    # The recognised-signal probe must actually change the answer, or the contextmanager is inert.
    rows = _denial_rows(witness)["tenant_access_denied"]
    with _a_recognised_signal(witness) as signal:
        assert witness.classify_denial_reason(rows, unique_signal=signal)[0] == witness.DENIAL_TENANT_ACCESS_DENIED
    assert witness.classify_denial_reason(rows, unique_signal="e48_probe_signal")[0] == witness.DENIAL_PRE_AUTH_AMBIGUOUS


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
            test_isolation_legs_are_distinguished_and_neither_claims_router_stage,
            test_the_expected_audit_inventory_includes_the_carrier_mismatch_class,
            test_every_isolation_leg_asserts_and_a_200_breach_fails,
            test_the_auth_stage_isolation_leg_cannot_be_silently_skipped,
            test_finally_cannot_mask_the_real_failure,
            test_the_no_leak_scan_covers_both_bearers,
            test_runtime_posture_is_declared_not_claimed_as_proof,
            test_the_control_database_read_is_bounded_to_an_allow_listed_shape,
            test_a_no_actor_route_denied_is_ambiguous_and_yields_e48_unproven,
            test_tenant_not_ready_cannot_satisfy_e48,
            test_only_a_unique_authoritative_signal_can_satisfy_e48,
            test_tenant_context_required_cannot_satisfy_e48,
            test_carrier_mismatch_cannot_satisfy_e48,
            test_a_403_with_an_empty_body_alone_cannot_satisfy_e48,
            test_missing_or_uninterpretable_denial_evidence_fails_closed,
            test_no_command_or_document_claims_a_control_read_the_witness_now_performs,
            test_the_e48_abort_precedes_the_second_isolation_leg_and_every_document_says_so,
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
