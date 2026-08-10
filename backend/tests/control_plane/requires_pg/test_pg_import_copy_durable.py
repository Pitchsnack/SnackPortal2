"""W1a composed-core import copy + durable Import Audit — DISPOSABLE live-PostgreSQL proof (standalone-only).

The MANUAL_ONLY disposable proof of the W1a composed-core persistent import path and its durable Import
operational audit. Against three real, proof-owned PostgreSQL databases it applies the reviewed, blob-pinned
control Import-audit DDL (infrastructure/db/control/014_import_operational_audit.sql then
015_import_operational_audit_append_only.sql — exact paths, exact order, each exactly once, never a wildcard)
plus control 001-009 (unpinned) and the enrolled 14-file tenant template (including tenant 008), and proves the
REAL composed path end-to-end:

    Gateway.handle(/import/<ref>)  -> HttpImportInitiation -> served internal Import edge
      -> ImportService.start_import -> PgRoutedSessionProvider -> DatabaseRouter.route() (BULK)
         -> exactly one physical tenant database (sp2_w1a_import_proof_t1)
      -> startups upsert (ON CONFLICT global_startup_id) + atomic tenant-resident lineage + checkpoint
      -> BoundedImportAuditPolicy -> DurableImportAuditEmitter -> Import-audit ingest edge
         -> PostgresImportAuditStore -> control_import_audit (sp2_w1a_import_proof_control)

Proof set (phases W1A-0..W1A-12): reviewed-blob STOP-before-connect; three disposable databases created fresh;
live schema evidence (control_import_audit 12 cols, identity PK, unique audit_id, DB-default recorded_at, the
five-action / source_service / event_version CHECKs, both append-only triggers; the plain non-partial
startups_global_startup_id_key on each tenant DB); a fresh composed journey -> 200 ``created`` with the t1
startups row + lineage row read back and exactly three durable audit rows; idempotent replay -> 200
``replayed`` with row/lineage counts unchanged and exactly two more audit rows; a noop journey; physical
isolation (t2 untouched; a dual-carrier straddle -> 403 with zero rows and zero audit); DB-authority negatives
(a duplicate global_startup_id direct INSERT -> unique violation; UPDATE/DELETE/TRUNCATE on control_import_audit
each rejected); a post-commit audit-failure drill (ingest stopped -> 503, key preserved; restored -> replay
confirms exactly once); and guaranteed teardown of all three disposable databases.

ISOLATION & SAFETY. Everything runs in the proof-owned scratch databases sp2_w1a_import_proof_control /
sp2_w1a_import_proof_t1 / sp2_w1a_import_proof_t2 created from the SNACKPORTAL_TEST_DSN admin connection at
start and DROPPED in a ``finally`` — the proof owns the full lifecycle. The DSN must point ONLY at a disposable,
non-production instance; it must NEVER point at production, shared staging, the standing Control database, or any
tenant database. The repo DDL files are read + blob-pinned only, never modified. No standing SnackPortal2
database is named, read, or touched by this file.

SECRET HYGIENE (D-14). SNACKPORTAL_TEST_DSN is used through the ``_pg`` runner ONLY; no descriptor value is
printed, logged, or written, and the tenant descriptors are resolved in-memory through a proof-local
``SecretStore``. Stored rows are asserted to contain no descriptor/password substring.

DRIVER CONTAINMENT. This file imports NO database driver at module scope. PostgreSQL is reached only through the
sanctioned provider adapters, imported lazily inside the exercise so the module clean-skips without psycopg. The
served edges are hosted on test-owned daemon threads (production servers stay single-threaded and thread-free).

DEFAULT SUITE. IGNORED by the default test run (pyproject addopts ``--ignore=tests/control_plane/requires_pg``).
Run it standalone against a disposable instance:
  python backend/tests/control_plane/requires_pg/test_pg_import_copy_durable.py
With SNACKPORTAL_TEST_DSN unset (or psycopg absent) it clean-skips (exit 0, no DB touched).

NO OVERCLAIM. This proof is DISPOSABLE-ONLY: it does not touch the retained standing topology, does not
standing-enroll DDL 014/015, does not deliver operator retrieval, does not close any B5 blocker, and does not
change the activation gate. The routing view/secret resolution is proof-local (a disposable composition of the
REAL DatabaseRouter, PsycopgConnectionFactory, ImportService, LineageEmit, edges and stores).
"""

from __future__ import annotations

import hashlib
import pathlib
import sys
import threading
from typing import Any, Optional, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _pg  # noqa: E402  (standalone live-PG runner: SNACKPORTAL_TEST_DSN, available()/run()/swap_db())

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))  # backend on path

# The three proof-owned scratch databases: created and dropped by THIS file only. Collision-free vs every
# standing Control/tenant database name and every sibling harness scratch family.
_PROOF_CTL = "sp2_w1a_import_proof_control"
_PROOF_T1 = "sp2_w1a_import_proof_t1"
_PROOF_T2 = "sp2_w1a_import_proof_t2"

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
_CONTROL = _REPO_ROOT / "infrastructure" / "db" / "control"
_DDL_014 = _CONTROL / "014_import_operational_audit.sql"
_DDL_015 = _CONTROL / "015_import_operational_audit_append_only.sql"

# Reviewed W1a control-audit DDL blobs (full LF-normalized git-blob SHA-1). A mismatch STOPS the exercise BEFORE
# any connection is opened. Cross-checked in the default suite by test_b7c1_control_audit_ddl_blob_pins.py.
_REVIEWED_014_BLOB = "73436f9681163c8a86ee230f51206062b06735c5"
_REVIEWED_015_BLOB = "ba594e3cd6eb070790bde6015f5225960c0d62ed"

# Control DDL applied UNPINNED beside 014/015 (their blobs are pinned by the b7c1 guard; this proof only needs
# the base control schema present). 001-009, in order.
_CONTROL_DDL_UNPINNED = (
    "001_distinctness_ledger.sql",
    "002_provisioning_audit.sql",
    "003_provisioning_audit_append_only.sql",
    "004_control_tenants.sql",
    "005_control_memberships.sql",
    "006_control_federation.sql",
    "007_control_directory.sql",
    "008_distinctness_fingerprint_unique.sql",
    "009_control_tenants_cas_version.sql",
)

_T1_ID, _T2_ID = "t1", "t2"
_T1_REF, _T2_REF = "tenant/t1/dsn", "tenant/t2/dsn"
_SOURCE_REF = "g1"
_DISPLAY = "Acme Inc"


def _git_blob_sha1(path: pathlib.Path) -> str:
    data = path.read_bytes().replace(b"\r\n", b"\n")  # autocrlf normalization (the git blob is LF)
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def _verify_reviewed_blobs() -> None:
    """Resolve the committed blob IDs and STOP before connecting or applying SQL if either diverges from the
    reviewed pin (pure file I/O — no DB, no socket)."""
    b014, b015 = _git_blob_sha1(_DDL_014), _git_blob_sha1(_DDL_015)
    assert b014 == _REVIEWED_014_BLOB, f"014 blob {b014} != reviewed {_REVIEWED_014_BLOB} — STOP before connect/apply (do not fix DDL here)"
    assert b015 == _REVIEWED_015_BLOB, f"015 blob {b015} != reviewed {_REVIEWED_015_BLOB} — STOP before connect/apply (do not fix DDL here)"
    print(f"PASS: W1A-0 reviewed DDL blob pins verified BEFORE any connection (014={b014[:12]}…, 015={b015[:12]}…)")


def _scalar(conn: Any, sql: str, params: Tuple[Any, ...] = ()) -> Any:
    row = conn.execute(sql, params).fetchone()
    return row[0] if row else None


def _raises(conn: Any, sql: str, params: Tuple[Any, ...] = ()) -> bool:
    try:
        conn.execute(sql, params)
        return False
    except Exception:
        return True


def _serve(server: Any) -> threading.Thread:
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread


def _stop(server: Any, thread: Optional[threading.Thread]) -> None:
    server.shutdown()
    server.server_close()
    if thread is not None:
        thread.join(timeout=5)


# --- the exercise ---------------------------------------------------------------------------------
def test_w1a_import_copy_durable_live_proof(admin_dsn: str) -> None:
    # PROOF W1A-0 — reviewed blob pins verified BEFORE any connection or SQL (STOP rule).
    # ------------------------------------------------------------------------------------------
    # WITHDRAWN WITH THE API GATEWAY — this exercise cannot run and must not pretend to.
    #
    # It drove `Gateway import route -> internal Import edge -> ImportService.start_import -> durable Import audit`.
    # The API Gateway package, its `HttpRouterDispatch` / `HttpImportInitiation` clients, the
    # `POST /internal/dispatch/route` edge and the internal tenant-Startup envelope edge were ALL
    # deleted: each existed only to carry a Gateway request into a service, and the public edges
    # hold their executors in-process instead.
    #
    # Refusing here rather than deleting the file is deliberate, and conservative on both sides:
    #   * the recorded scenario, its ordering rules and its evidence format survive in git for
    #     whoever authors the Gateway-free successor
    #     (`git show 8719f4f3:backend/tests/control_plane/requires_pg/test_pg_import_copy_durable.py`);
    #   * the file surface this harness belongs to is pinned by its own governance guards, which
    #     are about the W1a import write path — not about the Gateway — and deleting the file would break
    #     contracts that have nothing to do with this removal;
    #   * and it can no longer emit evidence. A harness that raises cannot produce a false PASS,
    #     which is the failure mode that matters when a live proof loses its subject.
    #
    # There is therefore currently NO live proof of this property on the Gateway-free topology.
    # Authoring one is a named adoption blocker, not a completed migration.
    raise AssertionError(
        "WITHDRAWN: this live proof drove the API Gateway topology, which has been deleted. "
        "A Gateway-free successor must be authored and executed under a separate live "
        "authorization before any evidence for this property may be cited."
    )


if __name__ == "__main__":
    _pg.run([test_w1a_import_copy_durable_live_proof])
