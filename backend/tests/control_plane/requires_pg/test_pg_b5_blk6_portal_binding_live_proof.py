"""B5-BLK-6C-C — real Control-DB portal-composition disposable proof (standalone wrapper; MANUAL_ONLY).

Drives ``b5_blk6_portal_binding_live_proof.run_proof`` against a fresh DISPOSABLE local PostgreSQL
Control database and independently verifies the proof-complete claim:

  6CC-1  configuration gate: CLEAN-SKIP (exit 0) only when NOTHING is configured; a PARTIAL
         configuration (DSN without psycopg, or psycopg without DSN) FAILS CLOSED — never a
         silent skip that could be mistaken for a green proof.
  6CC-2  scenario census: every label in ``SCENARIO_LABELS`` executed — a skipped or hollow run
         can never claim proof completion.
  6CC-3  zero retained artifact: the disposable database datname count is exactly 0 after the
         mandatory ``finally`` teardown.
  6CC-4  secret/token hygiene: no raw DSN, password, token-shaped string, or PEM header appears
         in any transcript line.

DEFAULT SUITE. IGNORED by the default run (pyproject addopts ``--ignore=tests/control_plane/requires_pg``)
and registered as a justified MANUAL_ONLY exception of the live-PG run-set completeness guard; the
hosted live-pg workflow is deliberately NOT edited by this slice. Operator command (from ``backend/``,
with SNACKPORTAL_TEST_DSN set to a DISPOSABLE local admin DSN permitted to CREATE/DROP DATABASE):

  python tests/control_plane/requires_pg/test_pg_b5_blk6_portal_binding_live_proof.py

NON-CLAIMS. A green run proves the composed CONTROL portal read against a fresh disposable Control DB
and nothing more: no durable audit persistence (in-memory recorder), no served northbound ingress, no
Lovable cutover, no tenant-DB routing, no cross-cluster distinctness, no production database identity,
no pagination support, no real import/tenant-operation business result, no blocker closure. B5-BLK-6
remains OPEN; production remains NOT READY / DO-NOT-ACTIVATE.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
from typing import List, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _pg  # noqa: E402  (SNACKPORTAL_TEST_DSN accessor + swap_db; used by NAME only, never printed)
import b5_blk6_portal_binding_live_proof as ops  # noqa: E402  (the operator module under proof; import is inert)

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))  # backend on path

_TOKEN_NEEDLE = "e" + "yJ"  # the base64 JWT prefix (built dynamically; never a committed literal)
_PEM_NEEDLE = "-----BE" + "GIN"


def _configuration_pieces() -> Tuple[List[str], List[str]]:
    """(present, absent) configuration pieces — the clean-skip vs fail-closed discriminator."""
    present: List[str] = []
    absent: List[str] = []
    if _pg.dsn():
        present.append("SNACKPORTAL_TEST_DSN")
    else:
        absent.append("SNACKPORTAL_TEST_DSN")
    if importlib.util.find_spec("psycopg") is not None:
        present.append("psycopg")
    else:
        absent.append("psycopg")
    return present, absent


def test_pg_b5_blk6_portal_binding_live_proof() -> None:
    # 6CC-1 — clean-skip only when NOTHING is configured; a partial configuration fails closed.
    present, absent = _configuration_pieces()
    if not present:
        print(f"SKIP: disposable-proof configuration absent — {absent}")
        return
    assert not absent, f"6CC-1: PARTIAL configuration (present={present}, absent={absent}) — fail closed, never a silent skip"
    admin_dsn = _pg.dsn()
    print("PASS: 6CC-1 configuration fully resolves (disposable local admin DSN + psycopg)")

    evidence = ops.run_proof(admin_dsn)

    # 6CC-2 — the proof-complete claim requires EVERY scenario label executed (never a subset).
    executed = {label for label, row in evidence["scenarios"].items() if row.get("executed") is True}
    assert executed == set(ops.SCENARIO_LABELS), (
        f"6CC-2: scenario census incomplete — missing {sorted(set(ops.SCENARIO_LABELS) - executed)}, "
        f"unexpected {sorted(executed - set(ops.SCENARIO_LABELS))}"
    )
    print(f"PASS: 6CC-2 scenario census complete ({len(executed)}/{len(ops.SCENARIO_LABELS)})")

    # 6CC-3 — zero retained PostgreSQL artifact.
    assert evidence["datname_count"] == 0, "6CC-3: the disposable Control DB was retained (datname count != 0)"
    print("PASS: 6CC-3 zero retained artifact (disposable database datname count == 0)")

    # 6CC-4 — secret/token hygiene across the full transcript.
    password = ""
    if "@" in admin_dsn and "://" in admin_dsn:
        userinfo = admin_dsn.split("://", 1)[1].split("@", 1)[0]
        password = userinfo.split(":", 1)[1] if ":" in userinfo else ""
    for line in evidence["transcript"]:
        assert admin_dsn not in line, "6CC-4: a raw DSN leaked into the proof transcript"
        if password:
            assert password not in line, "6CC-4: a password leaked into the proof transcript"
        assert _TOKEN_NEEDLE not in line, "6CC-4: a token-shaped string leaked into the proof transcript"
        assert _PEM_NEEDLE not in line, "6CC-4: a PEM header leaked into the proof transcript"
    print("PASS: 6CC-4 no DSN/password/token/PEM in any transcript line")
    print("NOTE: proof executed with an IN-MEMORY audit recorder; no durable audit persistence is claimed.")
    print("      B5-BLK-6 remains OPEN; production remains NOT READY / DO-NOT-ACTIVATE.")


def main() -> int:
    try:
        test_pg_b5_blk6_portal_binding_live_proof()
    except AssertionError as exc:
        print(f"FAIL: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
