"""PRD Smoke C V2 — integrated live proof, live on PostgreSQL (standalone-only; standing-fixture-bound).

Drives the Smoke C V2 operator (``smoke_c_integrated_live_proof.py``, same directory) end-to-end against
the REAL standing B5-4/B5-4A fixture and INDEPENDENTLY verifies every obligation: the full ``plan`` ->
``run`` -> ``status`` arc, all nine binding SMOKE-C-SPEC-01 scenarios, the alpha/beta physical database
identities, the binding internal denial codes, zero tenant dispatch on every denial, service shutdown and
port release, environment restoration, zero repository artifacts, and the exact before == after
zero-mutation contract. The proof creates nothing and deletes nothing — the standing environment is left
exactly unchanged.

CHECKS (PRD Smoke C V2 §12):
  SCV2-1  standing configuration resolves fully (else CLEAN-SKIP, exit 0, when NOTHING is configured;
          a PARTIAL configuration fails closed — never a silent skip over a half-configured fixture).
  SCV2-2  BEFORE state independently captured (Control DB rows, audit totals, pg_database census,
          tenant-DB invariants, secret-root inventory, touched env keys, repo file inventory).
  SCV2-3  operator ``plan`` exits 0 and is read-only (zero state delta).
  SCV2-4  operator ``run`` exits 0; the in-process evidence record is COMPLETE (nine scenarios).
  SCV2-5  independent scenario verification: every gateway envelope, internal denial code, dispatch
          census, and success-row database identity matches the binding SMOKE-C-SPEC-01 row — including
          alpha -> sp2_tenant_b5_standing_alpha ONLY, beta -> sp2_tenant_b5_standing_beta ONLY,
          dormant -> tenant_not_ready, unknown -> tenant_access_denied (never 503).
  SCV2-6  independent shutdown verification: no in-process server remains registered; every recorded
          loopback ephemeral service port refuses connections.
  SCV2-7  independent zero-mutation verification: the test's OWN after-state equals its OWN before-state
          exactly, and the operator's evidence agrees.
  SCV2-8  environment restored: every touched key equals its pre-run value.
  SCV2-9  zero repository artifacts: the repo file inventory (``.git``/``__pycache__`` excluded) is
          byte-identical before and after.
  SCV2-10 secret/token hygiene: no resolved DSN, password, token-shaped string, or PEM header appears in
          ANY captured command output.
  SCV2-11 operator ``status`` exits 0 afterwards and reports the completed in-process evidence.

DRIVER CONTAINMENT. No static database-driver import (psycopg is located via importlib after the skip
check). No JWT/crypto vendor import (tokens exist only inside the operator's run, minted by the blessed
B5-5 fixture). No ``subprocess`` import — only the operator holds that seam (status-only delegation).

DEFAULT SUITE. IGNORED by the default run (pyproject addopts ``--ignore=tests/control_plane/requires_pg``).
Standing-fixture-bound: run it from ``backend/`` with the SAME configuration as the runbooks
(``infrastructure/runbooks/smoke_c_integrated_live_proof.md`` §3 — DSNs by reference + the external
tenant-secret root) and the B5-4/B5-4A standing fixture established:
  python tests/control_plane/requires_pg/test_pg_smoke_c_integrated_live_proof.py
Registered as a justified MANUAL_ONLY exception of the live-PG run-set completeness guard
(standing-fixture-bound — not runnable on the single ephemeral CI service; loop enrollment is a
``.github`` edit outside this slice's authorized surface).

SECRET HYGIENE (D-14). DSNs are resolved by reference, used in-memory, and never printed. This test runs
serially (one function, one process, single-threaded servers hosted by the operator). B5-BLK-4 remains
OPEN; the Physical Multi-Database MVP remains mandatory and is NOT completed by this test — a green run
is the Smoke C V2 proof executed in the implementation environment, nothing more.
"""

from __future__ import annotations

import contextlib
import importlib
import io
import os
import pathlib
import sys
from typing import Any, Dict, List, Set, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import smoke_c_integrated_live_proof as ops  # noqa: E402  (the operator module under test; import is inert)

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))  # backend on path

_REPO_SKIP_PARTS = {".git", "__pycache__"}
_TOKEN_NEEDLE = "e" + "yJ"  # the base64 JWT prefix (built dynamically; never a committed literal)
_PEM_NEEDLE = "-----BE" + "GIN"


def _configuration_pieces() -> Tuple[List[str], List[str]]:
    """(present, absent) standing-configuration pieces — the clean-skip vs fail-closed discriminator."""
    present: List[str] = []
    absent: List[str] = []
    try:
        importlib.import_module("psycopg")
        present.append("psycopg")
    except ModuleNotFoundError:
        absent.append("psycopg")
    try:
        ops._resolve_dsns()
        present.append("dsn-references")
    except ops.OpsConfigError:
        absent.append("dsn-references")
    try:
        ops._validated_secret_dir()
        present.append("tenant-secret-root")
    except ops.OpsConfigError:
        absent.append("tenant-secret-root")
    return present, absent


def _run(argv: List[str]) -> Tuple[int, str]:
    """Run one operator command in-process, capturing stdout (the B5-4A proof idiom)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = ops.main(argv)
    return code, buf.getvalue()


def _repo_inventory() -> Set[str]:
    """Every repository file path (relative, posix), ``.git``/``__pycache__`` excluded — artifact census."""
    root = ops._REPO_ROOT
    return {
        p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() and not (_REPO_SKIP_PARTS & set(p.relative_to(root).parts))
    }


def test_smoke_c_integrated_live_proof() -> None:
    # SCV2-1 — clean-skip only when NOTHING is configured; a partial configuration fails closed.
    present, absent = _configuration_pieces()
    if not present:
        print(f"SKIP: standing configuration absent — {absent}")
        return
    assert not absent, f"SCV2-1: PARTIAL standing configuration (present={present}, absent={absent}) — fail closed, never a silent skip"
    control_dsn, admin_dsn = ops._resolve_dsns()
    print("PASS: SCV2-1 standing configuration fully resolves")

    outputs: List[str] = []

    # SCV2-2 — independent BEFORE state.
    env_before = {key: os.environ.get(key) for key in (*ops._ENV_TOUCHED_KEYS, ops._SECRET_DIR_ENV)}
    repo_before = _repo_inventory()
    state_before = ops._snapshot_state()
    assert state_before["tenant_ids"] == sorted([ops.TENANT_ALPHA, ops.TENANT_BETA, ops.TENANT_DORMANT]), (
        f"SCV2-2: standing tenant registry is {state_before['tenant_ids']!r} — refusing to run over drift"
    )
    assert state_before["residue"] == 0, "SCV2-2: pre-existing residue rows — refusing to run over drift"
    print("PASS: SCV2-2 before-state captured independently (standing registry exact; zero residue)")

    # SCV2-3 — plan is read-only.
    code, out = _run(["plan"])
    outputs.append(out)
    assert code == 0, f"SCV2-3: plan exited {code}:\n{out}"
    assert ops._snapshot_state() == state_before, "SCV2-3: plan mutated observable state"
    print("PASS: SCV2-3 plan read-only")

    # SCV2-4 — run exits 0 with COMPLETE in-process evidence.
    code, out = _run(["run"])
    outputs.append(out)
    assert code == 0, f"SCV2-4: run exited {code}:\n{out}"
    evidence: Dict[str, Any] = dict(ops._LAST_PROOF)
    assert evidence, "SCV2-4: run left no in-process evidence"
    assert ops.proof_complete(evidence), "SCV2-4: the in-process evidence record is incomplete"
    assert set(evidence["scenarios"].keys()) == {s["label"] for s in ops.SCENARIOS}, "SCV2-4: scenario census drifted"
    print(f"PASS: SCV2-4 run green with complete evidence (commit {evidence['commit']})")

    # SCV2-5 — independent scenario verification against the binding rows.
    for expected in ops.SCENARIOS:
        label = str(expected["label"])
        observed = evidence["scenarios"][label]
        assert observed["executed"] is True, f"SCV2-5 {label}: not executed"
        triple = (observed["status"], observed["public_code"], observed["dispatched"])
        assert triple == (expected["status"], expected["public_code"], expected["dispatched"]), (
            f"SCV2-5 {label}: gateway envelope {triple!r} != binding row"
        )
        if expected["internal_code"] is None:
            assert observed["category"] == "TENANT_OPERATION", f"SCV2-5 {label}: category {observed['category']!r}"
            assert observed["database"] == expected["database"], f"SCV2-5 {label}: routed db {observed['database']!r}"
            assert observed["readback_reused"] is True, f"SCV2-5 {label}: identity readback minted a NEW connection"
            assert observed["route_events"] == 1, f"SCV2-5 {label}: {observed['route_events']} Route event(s)"
            assert observed["other_pool_delta"] == 0, f"SCV2-5 {label}: the OTHER tenant's pool changed"
        else:
            assert observed["internal_code"] == expected["internal_code"], (
                f"SCV2-5 {label}: internal code {observed['internal_code']!r} != {expected['internal_code']!r}"
            )
            assert observed["route_events"] == 0, f"SCV2-5 {label}: a denied request reached the router"
            assert observed["pool_delta"] == 0 and observed["new_pool_keys"] == 0, f"SCV2-5 {label}: denial touched a tenant pool"
    alpha_db = evidence["scenarios"]["alpha-success"]["database"]
    beta_db = evidence["scenarios"]["beta-success"]["database"]
    assert (alpha_db, beta_db) == (ops.ALPHA_DB, ops.BETA_DB) and alpha_db != beta_db, (
        f"SCV2-5: database identities ({alpha_db!r}, {beta_db!r}) are not the two distinct standing targets"
    )
    print("PASS: SCV2-5 all nine binding scenarios independently verified (identities distinct and correct)")

    # SCV2-6 — shutdown and port release, independently probed.
    assert ops._ACTIVE_SERVERS == [], "SCV2-6: in-process server registry is not empty"
    assert evidence["shutdown_problems"] == [], f"SCV2-6: shutdown problems recorded: {evidence['shutdown_problems']}"
    assert evidence["pools_drained"] is True, "SCV2-6: tenant pools were not drained"
    services: Dict[str, str] = evidence["services"]
    assert set(services.keys()) == {"control_plane_read_edge", "auth_router_authenticate", "database_router_dispatch"}, (
        f"SCV2-6: service census drifted: {sorted(services)}"
    )
    for name, base_url in services.items():
        assert base_url.startswith(f"http://{ops.LOOPBACK_HOST}:"), f"SCV2-6: {name} bound off-loopback: {base_url}"
        assert ops._port_refused(base_url), f"SCV2-6: {name} port still accepting connections: {base_url}"
    print("PASS: SCV2-6 all services stopped; loopback ephemeral ports refused after the run")

    # SCV2-7 — independent zero-mutation verification.
    state_after = ops._snapshot_state()
    diff = sorted(key for key in state_before if state_before[key] != state_after.get(key))
    assert state_after == state_before, f"SCV2-7: before-state != after-state (differing keys: {diff})"
    assert evidence["before_equals_after"] is True, "SCV2-7: the operator's own before/after comparison disagrees"
    print("PASS: SCV2-7 zero mutation (independent before == after; operator evidence agrees)")

    # SCV2-8 — environment restored.
    env_after = {key: os.environ.get(key) for key in (*ops._ENV_TOUCHED_KEYS, ops._SECRET_DIR_ENV)}
    assert env_after == env_before, "SCV2-8: touched environment keys were not restored"
    assert evidence["env_restored"] is True, "SCV2-8: the operator's own env-restoration witness disagrees"
    print("PASS: SCV2-8 environment restored exactly")

    # SCV2-9 — zero repository artifacts.
    repo_after = _repo_inventory()
    created = sorted(repo_after - repo_before)
    removed = sorted(repo_before - repo_after)
    assert not created and not removed, f"SCV2-9: repository inventory changed (created={created}, removed={removed})"
    print("PASS: SCV2-9 zero repository artifacts created or removed")

    # SCV2-11 (status) is captured BEFORE the hygiene sweep so its output is swept too.
    code, out = _run(["status"])
    outputs.append(out)
    assert code == 0, f"SCV2-11: status exited {code}:\n{out}"
    assert "last in-process proof evidence complete" in out, "SCV2-11: status does not report the completed evidence"

    # SCV2-10 — secret/token hygiene across every captured output.
    for dsn in (control_dsn, admin_dsn):
        password = ""
        if "@" in dsn and "://" in dsn:
            userinfo = dsn.split("://", 1)[1].split("@", 1)[0]
            password = userinfo.split(":", 1)[1] if ":" in userinfo else ""
        for captured in outputs:
            assert dsn not in captured, "SCV2-10: a raw DSN leaked into command output"
            if password:
                assert password not in captured, "SCV2-10: a password leaked into command output"
    for captured in outputs:
        assert _TOKEN_NEEDLE not in captured, "SCV2-10: a token-shaped string leaked into command output"
        assert _PEM_NEEDLE not in captured, "SCV2-10: a PEM header leaked into command output"
    print("PASS: SCV2-10 no DSN/password/token/PEM in any captured output")
    print("PASS: SCV2-11 status green with completed in-process evidence")
    print("NOTE: Smoke C V2 proof executed in the implementation environment. B5-BLK-4 remains OPEN;")
    print("      the Physical Multi-Database MVP remains mandatory and NOT complete.")


def main() -> int:
    try:
        test_smoke_c_integrated_live_proof()
    except AssertionError as exc:
        print(f"FAIL: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
