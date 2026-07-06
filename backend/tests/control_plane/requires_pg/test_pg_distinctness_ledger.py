"""Durable Distinctness Ledger — live-PostgreSQL exercise (standalone-only; SNACKPORTAL_TEST_DSN).

The B-4 live exercise for the PRD 06 B-2 durable ledger: against a real Control database it
applies the additive ledger DDL (infrastructure/db/control/001_distinctness_ledger.sql), then
proves the durable `PostgresDistinctnessLedger` record_evidence / evidence_excluding / remove
behave as the gate requires — latest-per-tenant upsert, inventory-minus-self, drop — and
reconstruct reference-only `DistinctnessEvidence` faithfully. Applies and drops a throwaway
ledger table (controlled non-production only); the database driver stays confined to the adapter
(no `psycopg` import here — Driver Containment Standard).

This file is IGNORED by the default test run (pyproject `addopts --ignore=tests/control_plane/
requires_pg`); B-2 runs no live PostgreSQL. Run it in B-4:
set SNACKPORTAL_TEST_DSN to an admin DSN for a non-production Control database, then
`python tests/control_plane/requires_pg/test_pg_distinctness_ledger.py`.
"""

from __future__ import annotations

import hashlib
import os
import pathlib
import sys
import threading
import time
from dataclasses import replace
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _pg  # noqa: E402

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))  # backend on path

from control_plane.adapters.providers import postgres_distinctness_ledger as ledger_mod  # noqa: E402
from control_plane.adapters.providers.postgres_distinctness_ledger import PostgresDistinctnessLedger  # noqa: E402
from control_plane.distinctness import DistinctnessCollisionError, DistinctnessEvidence  # noqa: E402
from shared.secrets import SecretRef, SecretStore, SecretValue  # noqa: E402

_DDL = pathlib.Path(__file__).resolve().parents[4] / "infrastructure" / "db" / "control" / "001_distinctness_ledger.sql"
_DDL_008 = pathlib.Path(__file__).resolve().parents[4] / "infrastructure" / "db" / "control" / "008_distinctness_fingerprint_unique.sql"
_CONTROL_REF = SecretRef(store_ref="control_secret", version="1")


class MapSecretStore(SecretStore):
    """Maps a secret reference store_ref directly to a DSN (test-only)."""

    def __init__(self, mapping: dict) -> None:
        self._m = mapping

    def resolve(self, ref: SecretRef) -> SecretValue:
        return SecretValue(self._m[ref.store_ref])

    def current_version(self, store_ref: str) -> str:
        return "1"


def _evidence(tenant_id: str) -> DistinctnessEvidence:
    return DistinctnessEvidence(
        system_identifier="sp2_nonprod_control_cluster",
        database_identity=f"{tenant_id}:42",
        observed_target=f"sp2_tenant_{tenant_id}",
        secret_ref_key=f"sp2_tenant_{tenant_id}",
        sentinel_namespace=f"dv_sentinel_{tenant_id}",
        sentinel_token=f"tok_{tenant_id}",
        sentinel_written=True,
    )


def _exec(ledger: PostgresDistinctnessLedger, statement: str) -> None:
    conn = ledger._connect()  # driver confined to the adapter
    try:
        with conn.cursor() as cur:
            cur.execute(statement)
        conn.commit()
    finally:
        conn.close()


def test_durable_ledger_roundtrip(admin_dsn: str) -> None:
    secrets = MapSecretStore({"control_secret": admin_dsn})
    ledger = PostgresDistinctnessLedger(secrets, _CONTROL_REF)
    _exec(ledger, _DDL.read_text(encoding="utf-8"))  # apply the additive DDL (B-4 only)
    try:
        _exec(ledger, "DELETE FROM control_distinctness_ledger")  # clean slate

        ledger.record_evidence("t1", _evidence("t1"))
        ledger.record_evidence("t2", _evidence("t2"))

        inv = ledger.evidence_excluding("t1")
        assert set(inv.keys()) == {"t2"}, f"inventory-minus-self must exclude the subject: {set(inv.keys())}"
        assert inv["t2"].database_identity == "t2:42", "reference-only evidence must reconstruct faithfully"
        assert inv["t2"].sentinel_written is True and inv["t2"].sentinel_token == "tok_t2"

        # upsert-latest (one row per tenant)
        ledger.record_evidence("t2", replace(_evidence("t2"), database_identity="t2:99"))
        assert ledger.evidence_excluding("t1")["t2"].database_identity == "t2:99", "record_evidence must upsert latest"

        ledger.remove("t2")
        assert set(ledger.evidence_excluding("t1").keys()) == set(), "remove must drop the tenant's evidence"
    finally:
        _exec(ledger, "DROP TABLE IF EXISTS control_distinctness_ledger")  # throwaway cleanup


# --- PRD 06 B-4 live additions (cross-instance durability, fail-closed matrix, raw-row, NULL, idempotency) ---
# The reviewed Control-DB DDL artifact's git blob hash (EXEC-B4 R1 WP-B4-3 pin). Computed over the
# LF-normalized bytes (git autocrlf normalization), so it matches regardless of working-tree EOL.
_REVIEWED_DDL_BLOB = "30956ff1e85e8dab1c9f55cbfc121ee9212f3ca0"


class _ResolveError(RuntimeError):
    """Unique sentinel raised by the SecretStore.resolve() failure path (distinct from any DB error)."""


class _RaisingResolveStore(SecretStore):
    """A SecretStore whose resolve() always raises _ResolveError (the D-14 resolve-failure path)."""

    def resolve(self, ref: SecretRef) -> SecretValue:
        raise _ResolveError("control-db secret reference unresolvable")

    def current_version(self, store_ref: str) -> str:
        return "1"


def _ledger(admin_dsn: str) -> PostgresDistinctnessLedger:
    """A fresh, independent durable ledger instance (its own SecretStore; connections are per-op)."""
    return PostgresDistinctnessLedger(MapSecretStore({"control_secret": admin_dsn}), _CONTROL_REF)


def _git_blob_sha1(path: pathlib.Path) -> str:
    data = path.read_bytes().replace(b"\r\n", b"\n")  # autocrlf normalization (the git blob is LF)
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def _fresh_table(ledger: PostgresDistinctnessLedger) -> None:
    _exec(ledger, "DROP TABLE IF EXISTS control_distinctness_ledger")
    _exec(ledger, _DDL.read_text(encoding="utf-8"))  # apply the reviewed static DDL (B-4 only)


def _drop_table(ledger: PostgresDistinctnessLedger) -> None:
    _exec(ledger, "DROP TABLE IF EXISTS control_distinctness_ledger")


def _raw_rows(ledger: PostgresDistinctnessLedger):
    """Raw SELECT of the stored rows via the adapter's own connection (driver stays confined)."""
    conn = ledger._connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT tenant_id, system_identifier, database_identity, observed_target, secret_ref_key, "
                "sentinel_namespace, sentinel_token, sentinel_written, recorded_at "
                "FROM control_distinctness_ledger ORDER BY tenant_id"
            )
            return cur.fetchall()
    finally:
        conn.close()


def test_b4_ddl_pin_and_idempotency(admin_dsn: str) -> None:
    # WP-B4-3: the applied DDL is byte-identical to the reviewed artifact (git blob pin), and the DDL
    # is additive/idempotent — applying CREATE TABLE IF NOT EXISTS twice preserves existing rows.
    assert _git_blob_sha1(_DDL) == _REVIEWED_DDL_BLOB, f"DDL must equal the reviewed blob {_REVIEWED_DDL_BLOB}"
    ledger = _ledger(admin_dsn)
    _fresh_table(ledger)
    try:
        ledger.record_evidence("t1", _evidence("t1"))
        _exec(ledger, _DDL.read_text(encoding="utf-8"))  # apply again — must not error, must preserve rows
        assert "t1" in ledger.evidence_excluding("other"), "apply-twice must preserve existing rows (idempotent)"
    finally:
        _drop_table(ledger)


def test_b4_write_and_reference_only_row(admin_dsn: str) -> None:
    # WP-B4-4: recorded_at is populated (UTC) and refreshes on upsert; the stored row holds only
    # reference-safe values — never the admin DSN or password (D-14).
    ledger = _ledger(admin_dsn)
    _fresh_table(ledger)
    try:
        ledger.record_evidence("t1", _evidence("t1"))
        row1 = _raw_rows(ledger)
        assert len(row1) == 1
        rec1 = row1[0][8]  # recorded_at (timestamptz -> tz-aware datetime, in the session timezone)
        assert rec1 is not None, "recorded_at must be populated"
        assert rec1.tzinfo is not None, "recorded_at must be a timezone-aware (timestamptz) value"
        # timestamptz is stored as UTC; the adapter sets it via now_iso() at record time — assert the
        # instant is ~now (aware subtraction normalizes across timezones).
        assert abs((datetime.now(timezone.utc) - rec1).total_seconds()) < 300, "recorded_at must be set at record time"
        ledger.record_evidence("t1", replace(_evidence("t1"), database_identity="t1:zzz"))  # upsert
        row2 = _raw_rows(ledger)
        assert row2[0][2] == "t1:zzz", "upsert must refresh the row"
        assert row2[0][8] >= rec1, "recorded_at must refresh (>= prior) on upsert"
        p = urlsplit(admin_dsn)
        leak = [s for s in (admin_dsn, p.password or "") if s]
        for row in row2:
            for cell in row:
                for secret in leak:
                    assert secret not in str(cell), "stored row must not contain the DSN/secret (reference-only)"
    finally:
        _drop_table(ledger)


def test_b4_read_and_null_token(admin_dsn: str) -> None:
    # WP-B4-5: read excludes the subject + reconstructs faithfully; a NULL sentinel_token round-trips
    # to the None singleton (not the string "None"); a falsey sentinel_written -> False.
    ledger = _ledger(admin_dsn)
    _fresh_table(ledger)
    try:
        ledger.record_evidence("t1", _evidence("t1"))
        ledger.record_evidence("t2", replace(_evidence("t2"), sentinel_token=None, sentinel_written=False))
        inv = ledger.evidence_excluding("t1")
        assert set(inv.keys()) == {"t2"}
        assert inv["t2"].sentinel_token is None, "NULL sentinel_token must decode to None, not 'None'"
        assert inv["t2"].sentinel_written is False
        t1 = ledger.evidence_excluding("t2")["t1"]
        assert t1.database_identity == "t1:42" and t1.observed_target == "sp2_tenant_t1" and t1.sentinel_token == "tok_t1"
    finally:
        _drop_table(ledger)


def test_b4_cross_instance_durability(admin_dsn: str) -> None:
    # WP-B4-5a (keystone): evidence written by adapter instance A is read back by a FRESH, wholly
    # independent instance B — proving persistence survives adapter-instance teardown (restart/multi-node).
    writer = _ledger(admin_dsn)
    _fresh_table(writer)
    try:
        writer.record_evidence("t1", _evidence("t1"))
        del writer  # discard the writing instance (its per-op connections are already closed)
        reader = _ledger(admin_dsn)  # wholly independent instance B (fresh SecretStore + connection)
        inv = reader.evidence_excluding("other")
        assert "t1" in inv, "a fresh adapter instance must read persisted evidence (durability)"
        assert inv["t1"].database_identity == "t1:42" and inv["t1"].sentinel_token == "tok_t1"
    finally:
        _drop_table(_ledger(admin_dsn))


def test_b4_remove_cross_instance(admin_dsn: str) -> None:
    # WP-B4-6: remove drops only the named tenant and the removal PERSISTS — a fresh instance does
    # not see the removed tenant.
    a = _ledger(admin_dsn)
    _fresh_table(a)
    try:
        a.record_evidence("t1", _evidence("t1"))
        a.record_evidence("t2", _evidence("t2"))
        a.remove("t1")
        b = _ledger(admin_dsn)  # fresh instance
        assert set(b.evidence_excluding("other").keys()) == {"t2"}, "remove must persist across instances"
    finally:
        _drop_table(a)


def _b4_permission_denied_optional(admin_dsn: str) -> None:
    # WP-B4-7(d): conditionally-optional. If a restricted login role can be provisioned, prove that a
    # role without privileges on the ledger table fails closed (raises) on evidence_excluding. If the
    # test role cannot create roles, record a non-blocking OBSERVATION and skip (does not block PASS).
    role = "sp2_b4_norights"
    pw = "b4_" + os.urandom(8).hex()  # ephemeral; dropped in cleanup; never reported
    setup = _ledger(admin_dsn)
    _fresh_table(setup)
    created = False
    try:
        setup.record_evidence("t1", _evidence("t1"))
        try:
            _exec(setup, f"DROP ROLE IF EXISTS {role}")
            _exec(setup, f"CREATE ROLE {role} LOGIN PASSWORD '{pw}'")
            _exec(setup, f"REVOKE ALL ON control_distinctness_ledger FROM {role}")
            created = True
        except Exception as exc:
            print(f"OBS: (d) permission-denied SKIPPED — cannot provision a restricted role ({type(exc).__name__}); non-blocking")
            return
        parts = urlsplit(admin_dsn)
        restricted_dsn = urlunsplit(
            (parts.scheme, f"{role}:{pw}@{parts.hostname}:{parts.port or 5432}", parts.path, parts.query, parts.fragment)
        )
        restricted = PostgresDistinctnessLedger(MapSecretStore({"control_secret": restricted_dsn}), _CONTROL_REF)
        raised = False
        try:
            restricted.evidence_excluding("t1")
        except Exception:
            raised = True
        assert raised, "(d) a permission-denied role must fail closed (raise)"
        print("PASS: (d) permission-denied fails closed")
    finally:
        try:
            if created:
                _exec(setup, f"DROP ROLE IF EXISTS {role}")
        except Exception:
            pass
        _drop_table(setup)


def test_b4_fail_closed_matrix(admin_dsn: str) -> None:
    # WP-B4-7 (primary delta): live fail-closed for the full fault matrix. Each method RAISES (caught
    # broadly) and evidence_excluding NEVER returns {} (an empty inventory would hide a tenant-vs-tenant
    # collision = fail-open). Adapter-direct; the driver is reached only via the adapter (no static import).
    from control_plane.adapters.providers import postgres_distinctness_ledger as _Lmod

    # (a) SecretStore.resolve() raises -> propagate, and psycopg.connect is NEVER reached.
    connect_calls = []
    orig_connect = _Lmod.psycopg.connect
    _Lmod.psycopg.connect = lambda *a, **k: connect_calls.append((a, k))
    try:
        bad = PostgresDistinctnessLedger(_RaisingResolveStore(), _CONTROL_REF)
        for op in (
            lambda: bad.record_evidence("t1", _evidence("t1")),
            lambda: bad.evidence_excluding("t1"),
            lambda: bad.remove("t1"),
        ):
            raised = False
            try:
                op()
            except Exception as exc:
                raised = isinstance(exc, _ResolveError)
            assert raised, "(a) resolve() failure must propagate"
        assert connect_calls == [], "(a) connect must not be reached when resolve() fails"
    finally:
        _Lmod.psycopg.connect = orig_connect

    # (b) unreachable/closed DSN (connect-time) -> every method raises.
    unreachable = PostgresDistinctnessLedger(
        MapSecretStore({"control_secret": "postgresql://u:p@127.0.0.1:1/none"}), _CONTROL_REF, timeout=2.0
    )
    for op in (
        lambda: unreachable.record_evidence("t1", _evidence("t1")),
        lambda: unreachable.evidence_excluding("t1"),
        lambda: unreachable.remove("t1"),
    ):
        raised = False
        try:
            op()
        except Exception:
            raised = True
        assert raised, "(b) unreachable DSN must fail closed (raise)"

    # (c) missing table -> evidence_excluding RAISES, never returns {}.
    ledger = _ledger(admin_dsn)
    _drop_table(ledger)  # ensure the table is absent
    got_empty, raised = False, False
    try:
        got_empty = ledger.evidence_excluding("t1") == {}
    except Exception:
        raised = True
    assert raised and not got_empty, "(c) missing table must RAISE, never return {} (fail-open)"

    # (e) in-flight error (NOT NULL violation) -> no partial commit (a fresh instance sees no row).
    writer = _ledger(admin_dsn)
    _fresh_table(writer)
    try:
        raised = False
        try:
            writer.record_evidence("tbad", replace(_evidence("tbad"), system_identifier=None))  # NULL into NOT NULL
        except Exception:
            raised = True
        assert raised, "(e) a NOT NULL violation must propagate"
        assert "tbad" not in _ledger(admin_dsn).evidence_excluding("other"), "(e) failed write must not partially commit"
    finally:
        _drop_table(writer)

    # (d) permission-denied -> conditionally-optional (best-effort; non-blocking observation if infeasible).
    _b4_permission_denied_optional(admin_dsn)


# --- PRD 07D-2c live additions (008 fingerprint uniqueness + the two-writer interleave, L-3) ---
# The reviewed 008 DDL artifact's git blob hash (07D-2c D-1 pin; LF-normalized, matching the
# default-suite blob guard's _PIN_008 in lockstep — b7c1r2 INV-A/INV-B).
_REVIEWED_008_BLOB = "c510ebbaa881e3fc325dbb8ee8bf49b114e522ab"


def _fresh_table_2c(ledger: PostgresDistinctnessLedger) -> None:
    """Fresh ledger table WITH the 07D-2c fingerprint-uniqueness constraint applied (001 + 008)."""
    _exec(ledger, "DROP TABLE IF EXISTS control_distinctness_ledger")
    _exec(ledger, _DDL.read_text(encoding="utf-8"))
    _exec(ledger, _DDL_008.read_text(encoding="utf-8"))


def test_2c_008_pin_and_idempotent_apply(admin_dsn: str) -> None:
    # D-1: the applied 008 is byte-identical to the reviewed artifact (git blob pin), and the
    # DDL is additive/idempotent — re-applying IF NOT EXISTS over live rows preserves them.
    assert _git_blob_sha1(_DDL_008) == _REVIEWED_008_BLOB, f"008 DDL must equal the reviewed blob {_REVIEWED_008_BLOB}"
    ledger = _ledger(admin_dsn)
    _fresh_table_2c(ledger)
    try:
        ledger.record_evidence("t1", _evidence("t1"))
        _exec(ledger, _DDL_008.read_text(encoding="utf-8"))  # apply again — must not error, rows preserved
        assert "t1" in ledger.evidence_excluding("other"), "008 re-apply must preserve existing rows (idempotent)"
    finally:
        _drop_table(ledger)


def test_2c_cross_tenant_fingerprint_collision_sequential(admin_dsn: str) -> None:
    # §9 check 2 (MC-1 kill site, live leg): a SECOND tenant recording the SAME fingerprint is
    # refused with the typed collision (23505 mapped); the ledger still holds only the winner.
    ledger = _ledger(admin_dsn)
    _fresh_table_2c(ledger)
    try:
        ev_win = _evidence("t_win")
        ledger.record_evidence("t_win", ev_win)
        loser = replace(
            _evidence("t_lose"),
            system_identifier=ev_win.system_identifier,
            database_identity=ev_win.database_identity,  # same fingerprint, different tenant
        )
        raised = False
        try:
            _ledger(admin_dsn).record_evidence("t_lose", loser)
        except DistinctnessCollisionError:
            raised = True
        assert raised, "a cross-tenant same-fingerprint insert must surface DistinctnessCollisionError"
        rows = _raw_rows(ledger)
        assert len(rows) == 1 and rows[0][0] == "t_win", f"exactly the winner's row must survive: {rows}"
    finally:
        _drop_table(ledger)


def test_2c_same_tenant_upsert_legal_and_remove_frees_fingerprint(admin_dsn: str) -> None:
    # §9 check 3: same-tenant re-record (upsert) stays legal; a fingerprint change onto a value
    # another tenant holds is refused; remove() frees the fingerprint for a new claimant.
    ledger = _ledger(admin_dsn)
    _fresh_table_2c(ledger)
    try:
        ev1 = _evidence("t1")
        ledger.record_evidence("t1", ev1)
        ledger.record_evidence("t1", ev1)  # same-tenant re-record of the SAME fingerprint: legal
        ledger.record_evidence("t2", _evidence("t2"))  # distinct fingerprint: legal
        colliding = replace(
            _evidence("t2"),
            system_identifier=ev1.system_identifier,
            database_identity=ev1.database_identity,  # t2 changing onto t1's fingerprint
        )
        raised = False
        try:
            ledger.record_evidence("t2", colliding)
        except DistinctnessCollisionError:
            raised = True
        assert raised, "a fingerprint change onto another tenant's value must be refused"
        assert ledger.evidence_excluding("t1")["t2"].database_identity == "t2:42", "the refused change must not land"
        ledger.remove("t1")  # frees the fingerprint
        ledger.record_evidence("t2", colliding)  # the freed fingerprint is claimable again
        assert ledger.evidence_excluding("t1")["t2"].database_identity == ev1.database_identity
    finally:
        _drop_table(ledger)


def test_2c_two_writer_interleave(admin_dsn: str) -> None:
    # L-3 discharge (D-9 recipe; the C19 precedent): writer A INSERTs the fingerprint and holds
    # it UNCOMMITTED; writer B — the REAL adapter record_evidence on its own thread — INSERTs
    # the SAME fingerprint under another tenant and is observed LOCK-waiting on the in-doubt
    # unique key via pg_stat_activity; A commits PROMPTLY (CI PGOPTIONS lock_timeout=5000 kills
    # a blocked INSERT at 5 s); B surfaces the unique violation mapped to the typed collision;
    # exactly one surviving row. All connections come from the adapter (driver stays confined).
    ledger = _ledger(admin_dsn)
    _fresh_table_2c(ledger)
    winner_conn = None
    try:
        ev_w = _evidence("t_win")
        ev_l = replace(
            _evidence("t_lose"),
            system_identifier=ev_w.system_identifier,
            database_identity=ev_w.database_identity,  # the SAME fingerprint
        )
        # Writer A: the winner's recording — the adapter's own upsert statement, executed on a
        # held-open connection and NOT yet committed (the overlap window the gate cannot see).
        winner_conn = ledger._connect()
        with winner_conn.cursor() as cur:
            cur.execute(
                ledger_mod._UPSERT,
                (
                    "t_win",
                    ev_w.system_identifier,
                    ev_w.database_identity,
                    ev_w.observed_target,
                    ev_w.secret_ref_key,
                    ev_w.sentinel_namespace,
                    ev_w.sentinel_token,
                    ev_w.sentinel_written,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
        # Writer B: the REAL adapter path on its own thread (its INSERT blocks on the in-doubt
        # unique key until A's transaction resolves). Outcome captured; failures assertion-shaped.
        outcome: dict = {}

        def _loser() -> None:
            try:
                _ledger(admin_dsn).record_evidence("t_lose", ev_l)
                outcome["result"] = "no-error"
            except DistinctnessCollisionError:
                outcome["result"] = "collision"  # mapped + typed — NOT a raw driver exception
            except Exception as exc:  # a raw driver error leaking past the adapter = FAIL
                outcome["result"] = f"raw:{type(exc).__name__}"

        loser_thread = threading.Thread(target=_loser)
        loser_thread.start()

        # Deterministic overlap proof: poll until B is visibly LOCK-blocked on A's transaction.
        mon = ledger._connect()
        try:
            deadline = time.time() + 30
            blocked = False
            while time.time() < deadline:
                with mon.cursor() as cur:
                    cur.execute("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() AND wait_event_type = 'Lock'")
                    n = cur.fetchone()[0]
                mon.rollback()  # end the read txn so each poll observes fresh activity
                if n and n >= 1:
                    blocked = True
                    break
                time.sleep(0.05)
            assert blocked, "the losing writer never LOCK-blocked on the winner's uncommitted row — overlap not established"
        finally:
            mon.close()
        print("PASS: 2c overlap established (loser LOCK-blocked while the winner's insert is uncommitted)")

        winner_conn.commit()  # winner commits -> B's INSERT surfaces the unique violation
        loser_thread.join(timeout=30)
        assert not loser_thread.is_alive(), "loser thread must finish after the winner commits"
        assert outcome.get("result") == "collision", (
            f"the lost race must surface as the mapped DistinctnessCollisionError, got: {outcome.get('result')}"
        )
        rows = _raw_rows(ledger)
        assert len(rows) == 1 and rows[0][0] == "t_win", f"exactly the winner's row must survive: {rows}"
    finally:
        if winner_conn is not None:
            try:
                winner_conn.close()  # close BEFORE the drop so an aborted winner txn cannot block it
            except Exception:
                pass
        _drop_table(_ledger(admin_dsn))


if __name__ == "__main__":
    _pg.run(
        [
            test_durable_ledger_roundtrip,
            test_b4_ddl_pin_and_idempotency,
            test_b4_write_and_reference_only_row,
            test_b4_read_and_null_token,
            test_b4_cross_instance_durability,
            test_b4_remove_cross_instance,
            test_b4_fail_closed_matrix,
            test_2c_008_pin_and_idempotent_apply,
            test_2c_cross_tenant_fingerprint_collision_sequential,
            test_2c_same_tenant_upsert_legal_and_remove_frees_fingerprint,
            test_2c_two_writer_interleave,
        ]
    )
