"""PRD 06 B-7B — Runtime Audit-Sink Wiring BOUNDARY guard (architecture; text/AST inspection).

Locks the B-7B composition-root invariants without runtime: the Control-Plane composition root
(`main.py`) selects a durable Control-Store by env, but binds NO database driver at module load —
the PostgresControlStore provider is imported FUNCTION-LOCALLY (Driver Containment Standard), and
`main.py` carries no module-level DB-driver import. The B-7B docs exist and keep B5-BLK-4 OPEN with
the Physical Multi-Database MVP mandate intact; the new live-PG runtime-wiring harness binds no
static DB driver. The "off-limits DDL/docs byte-unchanged" guarantee is the executor's git fence,
NOT an in-pytest assertion (B-7 boundary precedent). Pure stdlib; standalone-runnable:
  python tests/architecture/test_b7b_runtime_audit_sink_wiring_boundary.py
"""

from __future__ import annotations

import ast
import pathlib
import sys
from typing import List

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

_MAIN = _scan.BACKEND_ROOT / "control_plane" / "main.py"
_LIVE_TEST = _scan.BACKEND_ROOT / "tests" / "control_plane" / "requires_pg" / "test_pg_control_store_runtime_wiring.py"
_DOCS_DIR = _scan.REPO_ROOT / "docs" / "runtime"
_CONTROL_DDL = _scan.REPO_ROOT / "infrastructure" / "db" / "control"

_DRIVER_TOPLEVEL = {"psycopg", "psycopg2", "asyncpg", "sqlalchemy", "databases", "aiopg"}
_PROVIDER_SUFFIX = "adapters.providers.postgres_store"

_REQUIRED_B7B_DOCS = [
    "b7b_runtime_audit_sink_wiring.md",
    "b7b_runtime_audit_sink_wiring_config.md",
    "b7b_runtime_audit_sink_wiring_fail_closed.md",
    "b7b_runtime_audit_sink_wiring_evidence_template.md",
    "b7b_runtime_audit_sink_wiring_blockers.md",
]


def _module_level_modules(path: pathlib.Path) -> List[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    mods: List[str] = []
    for node in tree.body:  # top-level statements only
        if isinstance(node, ast.Import):
            mods += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            mods.append(node.module or "")
    return mods


def _all_importfrom_modules(path: pathlib.Path) -> List[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            out.append(node.module or "")
        elif isinstance(node, ast.Import):
            out += [a.name for a in node.names]
    return out


def test_main_has_no_module_level_db_driver_or_provider_import() -> None:
    for mod in _module_level_modules(_MAIN):
        top = mod.split(".")[0]
        assert top not in _DRIVER_TOPLEVEL, f"main.py must not statically import DB driver {mod!r}"
        assert not mod.endswith(_PROVIDER_SUFFIX), f"main.py must not import the postgres provider at module level: {mod!r}"


def test_main_imports_postgres_store_function_locally() -> None:
    # present somewhere (the durable branch) but NOT at module level -> function-local containment.
    all_mods = _all_importfrom_modules(_MAIN)
    assert any(m.endswith(_PROVIDER_SUFFIX) for m in all_mods), "main.py must import PostgresControlStore (durable branch)"
    assert all(not m.endswith(_PROVIDER_SUFFIX) for m in _module_level_modules(_MAIN)), (
        "the PostgresControlStore import must be function-local, not module-level"
    )


def test_main_defines_control_store_selector() -> None:
    text = _MAIN.read_text(encoding="utf-8")
    assert "SP2_CP_CONTROL_STORE" in text, "main.py must define the SP2_CP_CONTROL_STORE selector"
    assert '"in_memory"' in text and '"postgres"' in text, "selector must accept 'in_memory' (default) and 'postgres'"


def test_b7b_docs_exist() -> None:
    for name in _REQUIRED_B7B_DOCS:
        assert (_DOCS_DIR / name).is_file(), f"missing B-7B doc: docs/runtime/{name}"


def test_b7b_blockers_keep_b5blk4_open_and_mvp_mandatory() -> None:
    text = (_DOCS_DIR / "b7b_runtime_audit_sink_wiring_blockers.md").read_text(encoding="utf-8")
    assert "B5-BLK-4" in text and "OPEN" in text, "B-7B blockers doc must keep B5-BLK-4 OPEN"
    assert "Physical Multi-Database" in text, "B-7B blockers doc must keep the Physical Multi-Database MVP mandate"


def test_b7b_live_test_has_no_static_db_driver_import() -> None:
    assert _LIVE_TEST.is_file(), f"expected B-7B live-PG harness: {_LIVE_TEST}"
    for mod in _scan.imported_modules(_LIVE_TEST):
        top = mod.split(".")[0]
        assert top not in _DRIVER_TOPLEVEL, f"{_LIVE_TEST.name} statically imports DB driver {mod!r}"


def test_off_limits_b7_b7a_artifacts_present() -> None:
    # existence guard only — byte-unchanged is the executor's git scope fence (B-7 boundary precedent).
    assert (_CONTROL_DDL / "002_provisioning_audit.sql").is_file()
    assert (_CONTROL_DDL / "003_provisioning_audit_append_only.sql").is_file()
    assert (_DOCS_DIR / "b7a_live_pg_control_audit_ddl_exercise.md").is_file()
    assert (_DOCS_DIR / "b7_provisioning_audit_blockers.md").is_file()


if __name__ == "__main__":
    _scan.run(
        [
            test_main_has_no_module_level_db_driver_or_provider_import,
            test_main_imports_postgres_store_function_locally,
            test_main_defines_control_store_selector,
            test_b7b_docs_exist,
            test_b7b_blockers_keep_b5blk4_open_and_mvp_mandatory,
            test_b7b_live_test_has_no_static_db_driver_import,
            test_off_limits_b7_b7a_artifacts_present,
        ]
    )
