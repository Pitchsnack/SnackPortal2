"""PRD DBR-AR-2D V3 — standing witnesses, read-only verification on PostgreSQL (standalone-only; standing-bound).

Verifies the DELIVERED DBR-AR-2D V3 standing witnesses against the REAL retained standing topology —
STRICTLY READ-ONLY plus two refusal probes: this test never applies DDL, never creates a backup, never
starts the evidence-generating ``run``, never writes any row, and leaves the standing environment
byte-identical. It exists so the delivered standing evidence can be independently re-verified at any
later time WITHOUT re-running the exactly-once witness (PRD DBR-AR-2D V3 §6.3: the evidence-generating
run happens exactly once; re-verification is read-only).

CHECKS (PRD DBR-AR-2D V3 §12/§15):
  V3W-1  standing configuration resolves (else CLEAN-SKIP, exit 0: refs/secret-dir/psycopg absent).
  V3W-2  BEFORE state independently captured (full snapshot families through the operator's own
         read-only snapshot seam).
  V3W-3  operator ``plan`` exits 0 in the COMPLETE stage and is read-only (zero snapshot delta;
         it must state that apply and run are both refused).
  V3W-4  operator ``status`` exits 0; the B5-4 6/6 + B5-4A 12/12 delegations PASS; every named
         standing check PASSes; no FAIL line.
  V3W-5  independent evidence verification: exactly the four predeclared durable rows in identity
         order (Route alpha / Route beta / RouteDenied dormant not_ready / IsolationAnomaly
         alpha->beta), the S3 auth-edge correlation ABSENT, unique event_ids, tz-aware DB-assigned
         recorded_at, NULL trace_ref, and a references-only content scan.
  V3W-6  independent schema verification: the exact 20-column contract, identity PK, unique
         event_id, the EXACT CHECK set, the EXACT trigger set, and the append-only function.
  V3W-7  rerun refusal, live: ``run`` exits non-zero BEFORE composing anything (its refusal path),
         and ``apply --backup-dir <tmp>`` exits non-zero; both with ZERO standing-state delta and
         ZERO backup artifact.
  V3W-8  append-only preservation: the operator carries no mutation surface; the four rows are
         still byte-identical after every probe above.
  V3W-9  automatic standing apply order remains exactly 001-009 (010/011 not enrolled).
  V3W-10 secret hygiene: no resolved DSN (nor its password) appears in ANY captured command output.

DRIVER CONTAINMENT. No static database-driver import; the operator module (same directory) is
imported — its import is inert by contract — and psycopg is located via importlib only after the
skip check. No ``subprocess`` import here (only the operator holds that seam).

DEFAULT SUITE. IGNORED by the default run (pyproject addopts ``--ignore=tests/control_plane/requires_pg``).
Standing-bound: run it from ``backend/`` with the SAME configuration as the runbook
(``infrastructure/runbooks/dbr_ar_2_durable_routing_audit.md`` — DSNs by reference + the external
tenant-secret root) AFTER the Dan-authorized V3 apply+run delivered the standing evidence:
  python tests/control_plane/requires_pg/test_pg_dbr_ar_2d_standing_witnesses.py
Without that configuration (or without psycopg) it clean-skips (exit 0). Registered as a justified
MANUAL_ONLY exception of the live-PG run-set completeness guard (standing-bound — not runnable on the
single ephemeral CI service; the hosted 14-harness loop is deliberately unchanged by this slice).

SECRET HYGIENE (D-14). DSNs are resolved by reference, used in-memory, and never printed. NO OVERCLAIM:
a green run re-verifies the delivered LOCAL standing witnesses only; DBR-AR-2 remains OPEN, DBR-AR-2E
remains not started, and production activation remains NOT READY / DO-NOT-ACTIVATE.
"""

from __future__ import annotations

import contextlib
import importlib
import io
import pathlib
import sys
import tempfile
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import dbr_ar_2d_standing_witnesses as ops  # noqa: E402  (the operator module under test; import is inert)

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))  # backend on path


def _available() -> Optional[str]:
    """None iff the standing configuration is fully present; else the (non-sensitive) skip reason."""
    try:
        importlib.import_module("psycopg")
    except ModuleNotFoundError:
        return "psycopg not installed"
    try:
        ops._resolve_dsns()
        ops._validated_secret_dir()
    except ops.OpsConfigError as exc:
        return str(exc)
    return None


def _run(argv: List[str]) -> Tuple[int, str]:
    """Run one operator command in-process, capturing stdout."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = ops.main(argv)
    return code, buf.getvalue()


def _rows() -> List[Tuple[Any, ...]]:
    control_dsn, _admin = ops._resolve_dsns()
    conn = ops._connect(control_dsn)
    try:
        with conn.cursor() as cur:
            return ops._routing_rows(cur)
    finally:
        conn.close()


def _census() -> Optional[Dict[str, Any]]:
    control_dsn, _admin = ops._resolve_dsns()
    conn = ops._connect(control_dsn)
    try:
        with conn.cursor() as cur:
            return ops._routing_schema_census(cur)
    finally:
        conn.close()


def test_dbr_ar_2d_standing_witnesses_readonly() -> None:
    skip = _available()
    if skip is not None:
        print(f"SKIP: standing configuration absent — {skip}")
        return
    control_dsn, admin_dsn = ops._resolve_dsns()
    outputs: List[str] = []

    # V3W-2 — BEFORE state (full families through the operator's own read-only snapshot seam).
    before = ops._snapshot_state()
    stage, _live_census, live_rows = ops._live_stage(control_dsn)
    assert stage == ops.STAGE_COMPLETE, (
        f"V3W-2: stage is {stage!r} — this read-only verifier requires the DELIVERED standing witness state"
        " (the Dan-authorized apply+run must have executed exactly once)"
    )
    print("PASS: V3W-2 before-state captured (COMPLETE stage)")

    # V3W-3 — plan is read-only and states the exactly-once refusal posture.
    code, out = _run(["plan"])
    outputs.append(out)
    assert code == 0, f"V3W-3: plan exited {code}:\n{out}"
    assert "apply and run are both REFUSED (exactly-once)" in out, "V3W-3: plan must state the COMPLETE refusal posture"
    after_plan = ops._snapshot_state()
    assert after_plan == before, "V3W-3: plan mutated standing state"
    print("PASS: V3W-3 plan read-only (COMPLETE stage; refusal posture stated)")

    # V3W-4 — status green: delegations + every named standing check.
    code, out = _run(["status"])
    outputs.append(out)
    assert code == 0, f"V3W-4: status failed (exit {code}):\n{out}"
    assert "FAIL" not in out, f"V3W-4: status carries FAIL line(s):\n{out}"
    for needle in (
        "PASS: B5-4 standing topology 6/6",
        "PASS: B5-4A standing auth fixture 12/12",
        "PASS: exact routing-audit schema on the standing Control DB",
        "PASS: exactly the four predeclared evidence rows in emission order (no fifth row)",
        "PASS: automatic standing apply order remains exactly 001-009 (010/011 not enrolled)",
        "PASS: dormant preserved: Registered membership-only; no secret, no database, no schema",
        "PASS: alpha/beta preserved: Ready on their own distinct physical databases",
        "PASS: locked activation posture intact (NOT READY; DBR-AR-2 OPEN; DBR-AR-2E not started)",
    ):
        assert needle in out, f"V3W-4: status output omits {needle!r}"
    print("PASS: V3W-4 status green (delegations + named standing checks)")

    # V3W-5 — independent evidence verification (this test's OWN reads, not the operator's verdict).
    rows = _rows()
    problem = ops.evaluate_evidence_rows(rows)
    assert problem is None, f"V3W-5: {problem}"
    assert rows == live_rows, "V3W-5: evidence rows changed between reads"
    password = ""
    if "@" in control_dsn and "://" in control_dsn:
        userinfo = control_dsn.split("://", 1)[1].split("@", 1)[0]
        password = userinfo.split(":", 1)[1] if ":" in userinfo else ""
    leak = ops._leak_scan_rows(rows, [control_dsn, admin_dsn, password])
    assert leak is None, f"V3W-5: {leak}"
    print(f"PASS: V3W-5 exactly {len(rows)} predeclared evidence rows; S3 absent; references only")

    # V3W-6 — independent schema verification (exact sets — OBS-2D-1 posture).
    census = _census()
    schema_problem = ops._routing_schema_problem(census)
    assert schema_problem is None, f"V3W-6: {schema_problem}"
    assert census is not None and census["checks"] == ops._EXPECTED_CHECKS, "V3W-6: exact CHECK set violated"
    assert census["triggers"] == ops._EXPECTED_TRIGGERS, "V3W-6: exact trigger set violated"
    print("PASS: V3W-6 exact schema (20 columns; exact CHECK set; exact trigger set; append-only function)")

    # V3W-7 — rerun refusal, live: run and apply both refuse with ZERO delta and ZERO artifact.
    code, out = _run(["run"])
    outputs.append(out)
    assert code != 0, "V3W-7: a second evidence-generating run must be REFUSED"
    assert "REFUSED" in out, f"V3W-7: run refusal must be explicit:\n{out}"
    assert _rows() == rows, "V3W-7: the refused run changed the evidence rows"
    with tempfile.TemporaryDirectory() as tmp:
        code, out = _run(["apply", "--backup-dir", tmp])
        outputs.append(out)
        assert code != 0, "V3W-7: a second apply must be REFUSED"
        assert "REFUSED" in out, f"V3W-7: apply refusal must be explicit:\n{out}"
        leftover = [p.name for p in pathlib.Path(tmp).rglob("*") if p.is_file()]
        assert leftover == [], f"V3W-7: the refused apply left backup artifact(s): {leftover}"
    after_refusals = ops._snapshot_state()
    assert after_refusals == before, "V3W-7: the refusal probes changed standing state"
    print("PASS: V3W-7 rerun refusal live (run refused; apply refused; zero delta; zero artifact)")

    # V3W-8 — rows still byte-identical after every probe above (append-only preservation).
    assert _rows() == rows, "V3W-8: the evidence rows drifted during read-only verification"
    print("PASS: V3W-8 evidence rows byte-identical after all probes")

    # V3W-9 — the automatic standing apply order stays 001-009 (never an enrollment).
    ops._assert_auto_apply_order_unchanged()
    print("PASS: V3W-9 automatic standing apply order remains exactly 001-009")

    # V3W-10 — secret hygiene across every captured output.
    for captured in outputs:
        assert control_dsn not in captured, "V3W-10: a raw DSN leaked into command output"
        assert admin_dsn not in captured, "V3W-10: a raw DSN leaked into command output"
        if password:
            assert password not in captured, "V3W-10: a password leaked into command output"
    print("PASS: V3W-10 no DSN/password in any captured output")


def main() -> int:
    try:
        test_dbr_ar_2d_standing_witnesses_readonly()
    except AssertionError as exc:
        print(f"FAIL: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
