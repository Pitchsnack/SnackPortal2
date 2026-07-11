"""PRD B5-4A V2 — standing auth fixture extension, live on PostgreSQL (standalone-only; standing-fixture-bound).

Proves the B5-4A V2 operator (``b5_standing_auth_fixture.py``, same directory) against the REAL standing
Control DB — ADDITIVELY. The four intended rows are PERMANENT by design, so unlike the disposable B5-4
proof this test creates no scratch database, drops nothing, and removes no row: it drives the operator's
plan -> apply -> apply -> status arc, verifies every acceptance obligation, and leaves the standing fixture
exactly in its intended permanent state. The ONLY induced-and-restored negative leg is a dormant secret
FILE under the (outside-repo) secret root — pure file-system, zero Control-DB mutation, removed afterwards.

CHECKS (PRD B5-4A V2 §11):
  B54A-1  standing configuration resolves (else CLEAN-SKIP, exit 0: refs/secret-dir/psycopg absent).
  B54A-2  BEFORE state: original B5-4 status 6/6; alpha/beta registry rows snapshotted; every intended
          row preflights ABSENT or EXACT (a CONFLICTING row is a hard fail — nothing is written over drift);
          baseline tenant/membership/audit counts captured.
  B54A-3  plan is read-only: exit 0 on a clean/exact preflight, and ZERO count deltas.
  B54A-4  first apply: exit 0; creates ONLY the absent intended rows — afterwards exactly three
          memberships (all TENANT_AGENT for the fixture principal), exactly one dormant tenant row
          (Registered, canonical dangling association), tenant registry == exactly the three standing ids,
          RegisterTenant audit provenance for the dormant tenant == exactly one row, total audit rows grew
          by exactly the number of newly created tenants (1 on a fresh run, 0 on an idempotent re-run),
          and the alpha/beta registry rows are IDENTICAL to their pre-apply snapshots.
  B54A-5  second apply is a no-op: exit 0; 0 new tenant rows, 0 new membership rows, 0 new audit rows.
  B54A-6  status: exit 0; reports the original 'B5-4 STATUS = 6/6 PASS' FIRST and every extension PASS
          line with no FAIL line.
  B54A-7  non-Ready semantics through the REAL read edge: the dormant tenant is visible, ready=false,
          lifecycle 'Registered', AND the fixture principal is a member — the exact membership-gated
          precondition under which the live Auth Router resolver emits tenant_not_ready (a non-member
          would be denied tenant_access_denied first).
  B54A-8  reference-only proof: no dormant secret file, no dormant secret env key, BOTH secret-store
          twins fail closed (LookupError) for the dormant reference, and the would-be dormant database is
          ABSENT from pg_database (schema trivially absent with it).
  B54A-9  negative leg (restored): materializing a dormant secret FILE makes status fail closed on the
          exact 'no dormant secret material' check; removing it restores green.  [mutation-10 live leg]
  B54A-10 secret hygiene: no resolved DSN (nor its password) appears in ANY captured command output.
  B54A-11 original B5-4 status is 6/6 again at the very end — the extension preserved the topology.

DRIVER CONTAINMENT. No static database-driver import: psycopg is located via importlib after the skip
check. The original B5-4 harness is NEVER imported (the operator under test reaches it subprocess-only).

DEFAULT SUITE. IGNORED by the default run (pyproject addopts --ignore=tests/control_plane/requires_pg).
Standing-fixture-bound: run it from ``backend/`` with the SAME configuration as the runbooks
(``infrastructure/runbooks/b5_standing_auth_fixture.md`` §3 — DSNs by reference + the external
tenant-secret root) and the B5-4 standing topology established:
  python tests/control_plane/requires_pg/test_pg_b5_standing_auth_fixture.py
Without that configuration (or without psycopg) it clean-skips (exit 0). Registered as a justified
MANUAL_ONLY exception of the live-PG run-set completeness guard (standing-fixture-bound — not runnable on
the single ephemeral CI service; loop enrollment is a .github edit outside this slice's surface).

SECRET HYGIENE (D-14). DSNs are resolved by reference, used in-memory, and never printed; the negative-leg
file content is a placeholder marker, not a credential. B5-BLK-4 remains OPEN; the Physical Multi-Database
MVP remains mandatory and is NOT completed by this test. Smoke C is NOT executed here.
"""

from __future__ import annotations

import contextlib
import importlib
import io
import pathlib
import sys
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import b5_standing_auth_fixture as ops  # noqa: E402  (the operator module under test; import is inert)

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


def _counts() -> Dict[str, Any]:
    """Baseline/delta snapshot through the ControlStore port (read-only)."""
    cp = ops._compose_control_store_standalone_plane()
    try:
        memberships = cp.store.list_memberships()
        audit = cp.store.list_audit()
        return {
            "tenant_ids": sorted(str(t) for t in cp.store.list_tenant_ids()),
            "memberships": sorted((m.principal_ref, m.tenant_id, m.role.value) for m in memberships),
            "audit_total": len(audit),
            "dormant_register_audit": [
                (rec.actor, rec.from_state, rec.to_state)
                for rec in audit
                if rec.tenant_id == ops.DORMANT_TENANT_ID and rec.action == "RegisterTenant"
            ],
            "alpha_beta_rows": {tid: cp.store.get_tenant(tid) for tid in ops.READY_TENANT_IDS},
            "preflight": ops._preflight(cp),
        }
    finally:
        ops._close_plane(cp)


def test_b5_standing_auth_fixture_live() -> None:
    skip = _available()
    if skip is not None:
        print(f"SKIP: standing configuration absent — {skip}")
        return
    psycopg = importlib.import_module("psycopg")
    control_dsn, admin_dsn = ops._resolve_dsns()
    secret_dir = ops._validated_secret_dir()
    outputs: List[str] = []

    # B54A-2 — BEFORE state (original 6/6; clean/exact preflight; baselines).
    code, out = ops._b5_4_status()
    assert ops._b5_4_status_problem(code, out) is None, "B54A-2: the established B5-4 standing topology (6/6) is a hard precondition"
    before = _counts()
    for key, classification in before["preflight"].items():
        assert classification in (ops.ABSENT, ops.EXACT), f"B54A-2: row {key} preflights {classification} — refusing to run over drift"
    fresh_tenant = before["preflight"][f"tenant:{ops.DORMANT_TENANT_ID}"] == ops.ABSENT
    if not fresh_tenant:
        assert len(before["dormant_register_audit"]) == 1, "B54A-2: a pre-existing dormant tenant must carry exactly one provenance row"
    print(f"PASS: B54A-2 before-state clean (dormant tenant {'ABSENT' if fresh_tenant else 'EXACT (authorized prior application)'})")

    # B54A-3 — plan is read-only.
    code, out = _run(["plan"])
    outputs.append(out)
    assert code == 0, f"B54A-3: plan exited {code} on a clean/exact preflight:\n{out}"
    after_plan = _counts()
    assert after_plan["tenant_ids"] == before["tenant_ids"], "B54A-3: plan mutated the tenant registry"
    assert after_plan["memberships"] == before["memberships"], "B54A-3: plan mutated memberships"
    assert after_plan["audit_total"] == before["audit_total"], "B54A-3: plan wrote audit rows"
    print("PASS: B54A-3 plan read-only")

    # B54A-4 — first apply creates ONLY the absent intended rows.
    code, out = _run(["apply"])
    outputs.append(out)
    assert code == 0, f"B54A-4: first apply failed (exit {code}):\n{out}"
    after1 = _counts()
    expected_memberships = sorted((ops.PRINCIPAL, tid, ops._ROLE_VALUE) for tid in ops.MEMBERSHIP_TENANT_IDS)
    assert after1["memberships"] == expected_memberships, f"B54A-4: memberships are {after1['memberships']!r}"
    expected_tenants = sorted((*ops.READY_TENANT_IDS, ops.DORMANT_TENANT_ID))
    assert after1["tenant_ids"] == expected_tenants, f"B54A-4: tenant registry is {after1['tenant_ids']!r}"
    assert after1["dormant_register_audit"] == [(ops._ACTOR, None, "Registered")], (
        f"B54A-4: dormant RegisterTenant provenance is {after1['dormant_register_audit']!r}"
    )
    assert after1["audit_total"] == before["audit_total"] + (1 if fresh_tenant else 0), "B54A-4: unexpected audit-row delta"
    for tid in ops.READY_TENANT_IDS:
        assert after1["alpha_beta_rows"][tid] == before["alpha_beta_rows"][tid], f"B54A-4: standing tenant {tid} row changed"
    print("PASS: B54A-4 first apply (additive-only; alpha/beta untouched)")

    # B54A-5 — second apply is a no-op.
    code, out = _run(["apply"])
    outputs.append(out)
    assert code == 0, f"B54A-5: second apply failed (exit {code}):\n{out}"
    after2 = _counts()
    assert after2["tenant_ids"] == after1["tenant_ids"], "B54A-5: second apply changed the tenant registry"
    assert after2["memberships"] == after1["memberships"], "B54A-5: second apply changed memberships"
    assert after2["audit_total"] == after1["audit_total"], "B54A-5: second apply wrote audit rows"
    assert after2["dormant_register_audit"] == after1["dormant_register_audit"], "B54A-5: duplicate RegisterTenant provenance"
    print("PASS: B54A-5 second apply is a no-op (0 new rows, 0 new audit rows)")

    # B54A-6 — status: original 6/6 FIRST, then every extension PASS line.
    code, out = _run(["status"])
    outputs.append(out)
    assert code == 0, f"B54A-6: status failed (exit {code}):\n{out}"
    assert "B5-4 STATUS = 6/6 PASS" in out, "B54A-6: status must report the original B5-4 6/6 first"
    assert "FAIL" not in out, f"B54A-6: status carries FAIL line(s):\n{out}"
    cp = ops._compose_control_store_standalone_plane()
    try:
        facts = ops._gather_facts(cp, admin_dsn, secret_dir)
    finally:
        ops._close_plane(cp)
    evaluated = ops._evaluate(facts)
    for name, problem in evaluated:
        assert problem is None, f"B54A-6: extension check {name!r}: {problem}"
        assert f"PASS: {name}" in out, f"B54A-6: status output omits the check line {name!r}"
    assert out.index("B5-4 STATUS") < out.index("PASS: alpha membership exact"), "B54A-6: B5-4 delegation must come first"
    print(f"PASS: B54A-6 status green ({len(evaluated)} extension checks after the 6/6 delegation)")

    # B54A-7 — the membership-gated non-Ready precondition through the REAL read edge.
    assert facts["dormant_read_state"] is not None, "B54A-7: dormant tenant not visible at the read edge"
    assert facts["dormant_read_state"]["ready"] is False, "B54A-7: read edge does not serve ready=false"
    assert facts["dormant_read_state"]["lifecycle_state"] == "Registered", "B54A-7: dormant lifecycle drifted"
    assert facts["dormant_member"] is True, "B54A-7: the fixture principal is not a member of the dormant tenant"
    print("PASS: B54A-7 membership-gated non-Ready precondition holds through the real read service")

    # B54A-8 — reference-only: no secret material, no physical database, both adapters fail closed.
    ref = ops._dormant_ref()
    dormant_file = secret_dir / f"{ref.store_ref}@{ref.version}"
    assert not dormant_file.exists(), "B54A-8: a dormant secret file exists"
    assert not facts["dormant_secret_env"], "B54A-8: a dormant secret env key is set"
    assert not facts["cp_adapter_resolves"], "B54A-8: the control-plane secret adapter resolves the dormant reference"
    assert not facts["dbr_adapter_resolves"], "B54A-8: the database-router secret adapter resolves the dormant reference"
    conn = psycopg.connect(admin_dsn, connect_timeout=10)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (ops._dormant_target(),))
            assert cur.fetchone() is None, "B54A-8: the would-be dormant database exists"
    finally:
        conn.close()
    print("PASS: B54A-8 dormant reference is dangling (no secret material, no database, no schema)")

    # B54A-9 — induced-and-restored negative leg: a dormant secret FILE must fail status closed.
    created_dirs: List[pathlib.Path] = []
    parent = dormant_file.parent
    while not parent.exists():
        created_dirs.append(parent)
        parent = parent.parent
    for directory in reversed(created_dirs):
        directory.mkdir()
    try:
        dormant_file.write_text("b5-4a-negative-leg-marker (not a credential)\n", encoding="utf-8")
        code, out = _run(["status"])
        outputs.append(out)
        assert code != 0, "B54A-9: status passed despite dormant secret material"
        assert "FAIL: no dormant secret material" in out, f"B54A-9: wrong check failed:\n{out}"
    finally:
        dormant_file.unlink(missing_ok=True)
        for directory in created_dirs:
            try:
                directory.rmdir()
            except OSError:
                break
    code, out = _run(["status"])
    outputs.append(out)
    assert code == 0, f"B54A-9: status did not recover after restoring the negative leg:\n{out}"
    print("PASS: B54A-9 dormant secret material fails status closed (restored)")

    # B54A-10 — secret hygiene across every captured output.
    for dsn in (control_dsn, admin_dsn):
        password = ""
        if "@" in dsn and "://" in dsn:
            userinfo = dsn.split("://", 1)[1].split("@", 1)[0]
            password = userinfo.split(":", 1)[1] if ":" in userinfo else ""
        for captured in outputs:
            assert dsn not in captured, "B54A-10: a raw DSN leaked into command output"
            if password:
                assert password not in captured, "B54A-10: a password leaked into command output"
    print("PASS: B54A-10 no DSN/password in any captured output")

    # B54A-11 — the original standing topology is intact at the end.
    code, out = ops._b5_4_status()
    assert ops._b5_4_status_problem(code, out) is None, "B54A-11: the original B5-4 topology is no longer 6/6"
    print("PASS: B54A-11 original B5-4 topology preserved (6/6)")


def main() -> int:
    try:
        test_b5_standing_auth_fixture_live()
    except AssertionError as exc:
        print(f"FAIL: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
