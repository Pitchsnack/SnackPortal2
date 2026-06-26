"""PRD 06 B-7 — Provisioning Audit Durable Store BOUNDARY guard (architecture; text-inspection only).

Asserts the B-7 deliverables exist and stay within the created-not-applied, additive boundary — mirroring the B-6
gate-contract precedent. Text-inspection only; no runtime, no database-driver import. The "off-limits source unchanged"
guarantee is the executor's git scope fence, NOT an in-pytest assertion. Pure stdlib; standalone-runnable:
  python tests/architecture/test_b7_provisioning_audit_durable_store_boundary.py
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

_CONTROL = _scan.REPO_ROOT / "infrastructure" / "db" / "control"
_DDL = _CONTROL / "002_provisioning_audit.sql"
_DOCS_DIR = _scan.REPO_ROOT / "docs" / "runtime"
_RUNTIME_DIR = _scan.REPO_ROOT / "infrastructure" / "runtime"
_REQUIRED_DOCS = [
    "b7_provisioning_audit_durable_store.md",
    "b7_provisioning_audit_schema.md",
    "b7_provisioning_audit_policy.md",
    "b7_provisioning_audit_evidence_template.md",
    "b7_provisioning_audit_blockers.md",
]
_DRIVER_TOPLEVEL = {"psycopg", "psycopg2", "asyncpg", "sqlalchemy"}
_B7_TEST_FILES = [
    _scan.BACKEND_ROOT / "tests" / "control_plane" / "test_b7_provisioning_audit_durable_store_contract.py",
    _scan.BACKEND_ROOT / "tests" / "architecture" / "test_b7_provisioning_audit_durable_store_boundary.py",
    # PRD 06 B-7A: the live-PG harness reaches the driver only via the adapter — no static driver import (defense-in-depth).
    _scan.BACKEND_ROOT / "tests" / "control_plane" / "requires_pg" / "test_pg_control_audit_ddl.py",
]


def test_ddl_exists_under_db_control_only() -> None:
    assert _DDL.is_file(), "infrastructure/db/control/002_provisioning_audit.sql must exist"
    rel = _DDL.relative_to(_scan.REPO_ROOT).as_posix()
    assert rel.startswith("infrastructure/db/control/"), rel
    low = _DDL.read_text(encoding="utf-8").lower()
    assert "not applied" in low, "the DDL must be created-not-applied"


def test_no_ddl_under_docs_or_infra_runtime() -> None:
    # B-7 DDL lives ONLY under infrastructure/db/control/ — never under docs/runtime or infrastructure/runtime
    for base in (_DOCS_DIR, _RUNTIME_DIR):
        sqls = [p.relative_to(_scan.REPO_ROOT).as_posix() for p in base.rglob("*.sql")]
        assert not sqls, f".sql must not live under {base.relative_to(_scan.REPO_ROOT).as_posix()}: {sqls}"


def test_b7_docs_exist() -> None:
    for name in _REQUIRED_DOCS:
        assert (_DOCS_DIR / name).is_file(), f"missing B-7 doc: docs/runtime/{name}"


def test_blocker_note_keeps_b5_blk_4_open() -> None:
    text = (_DOCS_DIR / "b7_provisioning_audit_blockers.md").read_text(encoding="utf-8")
    assert "B5-BLK-4" in text, "blocker note must reference B5-BLK-4"
    assert "OPEN" in text, "blocker note must keep B5-BLK-4 OPEN"
    assert "B6-BLK-2" in text, "blocker note must name the B6-BLK-2 sub-blocker B-7 reduces"


def test_b7_tests_have_no_static_db_driver_import() -> None:
    for p in _B7_TEST_FILES:
        assert p.is_file(), f"expected B-7 test file: {p}"
        for mod in _scan.imported_modules(p):
            top = mod.split(".")[0]
            assert top not in _DRIVER_TOPLEVEL, f"{p.name} statically imports DB driver {mod!r}"


if __name__ == "__main__":
    _scan.run(
        [
            test_ddl_exists_under_db_control_only,
            test_no_ddl_under_docs_or_infra_runtime,
            test_b7_docs_exist,
            test_blocker_note_keeps_b5_blk_4_open,
            test_b7_tests_have_no_static_db_driver_import,
        ]
    )
