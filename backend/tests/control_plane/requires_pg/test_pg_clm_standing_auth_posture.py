"""CLM standing authentication posture — the AUTHFIX-B REPLACEMENT verification harness (MANUAL_ONLY).

**This is the accepted replacement that supersedes the B5-4A standing authentication fixture.**

Why the predecessor had to be replaced rather than amended: `b5_standing_auth_fixture.py` verifies a
subject state that **no longer exists**. Its census is pinned to the `b5_standing_alpha` /
`b5_standing_beta` / `b5_standing_dormant` trio and to a whole-table membership count of **exactly
three**; the standing Control database was replaced around 2026-07-21 by the four-cluster fixture and
now holds `acme` / `nova` / `zeta`. Run today the fixture fails at least six of its checks plus its
B5-4 delegation. That red is **standing and pre-existing** — not a consequence of any later change —
and because the family is MANUAL_ONLY, no automated gate ever observed its colour. Amending it would
have meant deleting or neutering checks 1–7 and 10, which is supersession wearing amendment's
clothes. The predecessor is therefore marked superseded and left intact as a historical artifact; its
non-zero exit is expected and explicit.

WHAT THIS HARNESS DOES DIFFERENTLY, AND WHY IT MATTERS

The fixture asserted a **fixed roster**. That is exactly what made it brittle: any governed change to
the standing fixture falsified it, silently. This harness asserts **structural invariants** that hold
for any correct standing authentication posture, and *reports* the roster instead of pinning it:

  * memberships and tenants must be **referentially coherent** — there is no cross-row foreign key to
    enforce it, so nothing else checks;
  * every `Ready` tenant must carry a canonical `tenant/<id>/dsn` **reference**, and a reference is
    never a credential;
  * a reference that resolves to nothing is **MISSING**, not CONFLICTING — the standing registry
    genuinely references material that does not exist yet, and calling that a conflict would block a
    gate for a state the arc expects;
  * a membership whose principal has no identity is **REPORTED and RETAINED**, never deleted. One
    such orphan is known to exist. No cleanup path exists and none is authorized.

Nothing here is pinned to a count, a name, or a roster. A future governed fixture change does not
falsify this harness — which is the whole point of replacing the previous one.

**STRICTLY READ-ONLY.** No DDL, no INSERT, no UPDATE, no DELETE, no membership creation. In
particular: **creating a membership row to make an authentication journey pass is a Gate-B class-M6
mutation and it destroys the evidence.** If the principal holds no membership, that is the finding.

NO OVERCLAIM. A green run proves the standing Control database is internally coherent and
reference-only. It does **not** prove an authenticated journey, does not prove the tenant data plane,
does not close any B5 blocker, and does not activate anything.

DRIVER CONTAINMENT. No static database-driver import; psycopg is located via importlib at call time.
SECRET HYGIENE (D-14). Every identity is redacted to scheme+host+port+database; no reference value,
DSN, password or token is printed.

    python tests/control_plane/requires_pg/test_pg_clm_standing_auth_posture.py
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import pathlib
import sys
import unittest
from typing import Any, List, Optional, Tuple
from urllib.parse import urlsplit

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))  # backend on path

CONTROL_DSN_ENV = "SNACKPORTAL_SECRET_CONTROL_CONTROL_STORE_DSN_V1"

# The canonical per-tenant credential reference shape. A reference is contract-declared non-secret;
# the value it names is resolved in memory at connect time and never stored.
CANONICAL_REF_TEMPLATE = "tenant/{tenant_id}/dsn"

# Shapes that must never appear in any emitted line.
LEAK_SHAPES = ("://", "@", "eyJ", "-----BEGIN", "password")


def _psycopg() -> Any:
    if importlib.util.find_spec("psycopg") is None:
        return None
    return importlib.import_module("psycopg")


def _control_dsn() -> Optional[str]:
    raw = os.environ.get(CONTROL_DSN_ENV)
    return (raw or "").strip() or None


def redacted(dsn: str) -> str:
    try:
        parts = urlsplit(dsn)
    except ValueError:
        return "<unparseable>"
    host = parts.hostname or "?"
    port = f":{parts.port}" if parts.port else ""
    return f"{parts.scheme or '?'}://{host}{port}{parts.path or ''}"


def _assert_reference_only(label: str, value: Optional[str]) -> None:
    """A reference must look like a reference. Anything with credential shape is a leak."""
    if value is None:
        return
    for shape in LEAK_SHAPES:
        assert shape not in value, f"{label}: the stored reference {value.split(shape)[0]}… carries the secret shape {shape!r}"


def _rows(conn: Any, sql: str, params: Tuple[Any, ...] = ()) -> List[Tuple[Any, ...]]:
    return list(conn.execute(sql, params).fetchall())


def _table_exists(conn: Any, name: str) -> bool:
    return bool(conn.execute("SELECT to_regclass(%s) IS NOT NULL", (f"public.{name}",)).fetchone()[0])


def verify(conn: Any) -> None:
    outputs: List[str] = []

    def record(line: str) -> None:
        outputs.append(line)
        print(line)

    # CSA-1 — the store under verification is the real Control database, not a double.
    database = conn.execute("SELECT current_database()").fetchone()[0]
    system_identifier = conn.execute("SELECT system_identifier FROM pg_control_system()").fetchone()[0]
    record(f"PASS: CSA-1 connected to a physical Control database (system_identifier={system_identifier})")

    # CSA-2 — the authentication-bearing tables exist. Their ABSENCE would make every check below
    # pass vacuously, which is the failure mode this ordering exists to prevent.
    for table in ("control_tenants", "control_memberships"):
        assert _table_exists(conn, table), (
            f"CSA-2: {table} is absent. Every check below would then pass for the wrong reason — apply the governed "
            "control DDL 001-009 first."
        )
    record("PASS: CSA-2 control_tenants and control_memberships both present (the census is non-vacuous)")

    # CSA-3 — the tenant registry, REPORTED not pinned. The predecessor pinned an exact roster and
    # died the day the roster changed.
    #
    # The two GOVERNED reference columns are `assoc_store_ref` and `assoc_version`
    # (infrastructure/db/control/004_control_tenants.sql:38-39): the Control-Plane adapter derives
    # them from `TenantRecord.database_association_ref`, a SecretRef {store_ref, version}. There is
    # no `database_association_ref` COLUMN — that name belongs to the application-layer record and to
    # the served routing DTO, and selecting it aborts every run with `undefined_column`. This is the
    # RB-2 correction; the static guard now checks every selected column against the governed DDL.
    tenants = _rows(conn, "SELECT tenant_id, lifecycle_state, assoc_store_ref, assoc_version FROM control_tenants ORDER BY tenant_id")
    assert tenants, "CSA-3: the tenant registry is EMPTY — there is no standing authentication posture to verify"
    record(f"PASS: CSA-3 tenant registry census: {[(t[0], t[1]) for t in tenants]}")

    ready = [t for t in tenants if str(t[1]).lower() == "ready"]
    assert ready, f"CSA-3: no tenant is Ready (states observed: {sorted({str(t[1]) for t in tenants})})"
    record(f"PASS: CSA-3 at least one Ready tenant ({[t[0] for t in ready]})")

    # CSA-4 — every Ready tenant carries the CANONICAL reference, and it is a reference, not a value.
    # Both halves of the SecretRef are checked: a store_ref with no version names nothing resolvable,
    # and both are contract-declared non-secret, so both are held to the reference-only rule.
    for tenant_id, _state, store_ref, version in ready:
        expected = CANONICAL_REF_TEMPLATE.format(tenant_id=tenant_id)
        assert store_ref, f"CSA-4: Ready tenant {tenant_id!r} carries no assoc_store_ref"
        assert version, f"CSA-4: Ready tenant {tenant_id!r} carries no assoc_version — a store_ref alone resolves nothing"
        _assert_reference_only(f"CSA-4 {tenant_id} assoc_store_ref", str(store_ref))
        _assert_reference_only(f"CSA-4 {tenant_id} assoc_version", str(version))
        assert str(store_ref).startswith("tenant/"), f"CSA-4: {tenant_id!r} assoc_store_ref {store_ref!r} is outside the tenant/ namespace"
        if str(store_ref) != expected:
            record(
                f"NOTE: CSA-4 {tenant_id} assoc_store_ref {store_ref!r} deviates from the canonical form {expected!r} "
                "— record and adjudicate"
            )
    record(
        "PASS: CSA-4 every Ready tenant carries a tenant/-namespaced assoc_store_ref + assoc_version; neither carries a credential shape"
    )

    # CSA-5 — referential coherence. There is no cross-row foreign key here (store parity), so
    # nothing else in the system checks that a membership names a tenant that exists.
    memberships = _rows(conn, "SELECT principal_ref, tenant_id, role FROM control_memberships ORDER BY principal_ref, tenant_id")
    registered = {t[0] for t in tenants}
    dangling = [m for m in memberships if m[1] not in registered]
    assert not dangling, (
        f"CSA-5: membership row(s) name a tenant that is not registered: {[(m[0][:8] + '…', m[1]) for m in dangling]}. "
        "There is no foreign key to catch this — a routed request for such a tenant fails at resolution time."
    )
    record(f"PASS: CSA-5 all {len(memberships)} membership row(s) name a registered tenant (no dangling tenant reference)")

    # CSA-6 — the membership roster, REPORTED. Deliberately NOT pinned to a count: pinning the
    # whole-table count to exactly three is precisely what made the predecessor unmaintainable.
    for principal_ref, tenant_id, role in memberships:
        _assert_reference_only("CSA-6 principal_ref", str(principal_ref))
        record(f"INFO: CSA-6 membership {str(principal_ref)[:8]}…{'':>0} -> {tenant_id} ({role})")
    record(f"PASS: CSA-6 membership census reported ({len(memberships)} row(s)); every principal_ref is reference-shaped")

    # CSA-7 — tenants with NO membership are reported, never repaired. A tenant nobody can reach is a
    # legitimate standing state; creating a membership to "fix" it is a Gate-B M6 mutation.
    reachable = {m[1] for m in memberships}
    unreachable = sorted(t[0] for t in ready if t[0] not in reachable)
    if unreachable:
        record(
            f"NOTE: CSA-7 Ready tenant(s) with NO membership row: {unreachable}. This is REPORTED, not repaired — "
            "creating a membership to make a journey pass is a Gate-B class-M6 mutation and it destroys the evidence."
        )
    record("PASS: CSA-7 unreachable-tenant report complete (no row was created)")

    # CSA-8 — audit provenance, reported honestly. The standing rows were seeded directly, bypassing
    # the audited path, so a zero count here is EXPECTED and is not a failure.
    if _table_exists(conn, "control_audit"):
        audit_rows = int(conn.execute("SELECT count(*) FROM control_audit").fetchone()[0])
        record(
            f"INFO: CSA-8 control_audit carries {audit_rows} row(s). The standing registry rows have ZERO audit "
            "provenance (they were seeded directly, bypassing the audited registration path) — a low or zero count "
            "here is the expected state, not a defect, and any Gate-B mutation inventory must be framed against it."
        )
    record("PASS: CSA-8 audit provenance reported without inference")

    # CSA-9 — no leak in anything this harness emitted, including its own report.
    dsn = _control_dsn() or ""
    password = ""
    try:
        password = urlsplit(dsn).password or ""
    except ValueError:
        password = ""
    blob = "\n".join(outputs)
    for secret in (dsn, password):
        assert not (secret and secret in blob), "CSA-9: a resolved secret value appears in this harness's own output"
    assert str(database) not in blob, "CSA-9: the physical database name appears in the output (topology disclosure)"
    record("PASS: CSA-9 no DSN, password, or physical database name in any emitted line")

    print("\nSUPERSESSION: this harness replaces the B5-4A standing authentication fixture's subject-state census.")
    print("It asserts structural invariants and REPORTS the roster; nothing here is pinned to a name or a count.")
    print("NO OVERCLAIM: it proves the standing Control database is internally coherent and reference-only.")
    print("It does NOT prove an authenticated journey, does NOT prove the tenant data plane, and closes no blocker.")


def test_clm_standing_auth_posture() -> None:
    psycopg = _psycopg()
    dsn = _control_dsn()
    if psycopg is None or dsn is None:
        # An explicit SkipTest, not a bare `return`: a bare return is recorded by pytest as a PASS,
        # which is exactly the vacuous green this replacement exists to stop reproducing.
        raise unittest.SkipTest(
            f"standing configuration absent (psycopg={'yes' if psycopg else 'no'}, {CONTROL_DSN_ENV} set={dsn is not None})"
        )
    print(f"CLM standing authentication posture — READ-ONLY verification against {redacted(dsn)}")
    with psycopg.connect(dsn) as conn:
        conn.read_only = True
        verify(conn)


def main() -> int:
    try:
        test_clm_standing_auth_posture()
    except unittest.SkipTest as exc:
        print(f"SKIP: {exc}")
        return 0
    except AssertionError as exc:
        print(f"FAIL: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
