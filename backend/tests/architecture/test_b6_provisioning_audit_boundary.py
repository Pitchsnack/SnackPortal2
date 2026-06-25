"""PRD 06 B-6 — Provisioning Audit Sink BOUNDARY guard (architecture; text-inspection only).

Asserts the B-6 deliverables exist and stay within the reference-only, additive boundary — mirroring the B-5
gate-contract precedent (test_b5_runtime_activation_gate_contract.py). Text-inspection only; no runtime, no
database-driver import (string literals naming paths are not imports). The *_REF reference-only hygiene for the
template is already enforced by test_no_secret_literals.py::test_templates_reference_only over infrastructure/** —
NOT duplicated here. The "audit.py/events.py/main.py unchanged" guarantee is the executor's git scope fence + the
existing EXPECTED_EVENT_ACTIONS guard, NOT an in-pytest assertion. Pure stdlib; standalone-runnable:
  python tests/architecture/test_b6_provisioning_audit_boundary.py
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

_TEMPLATE = _scan.REPO_ROOT / "infrastructure" / "runtime" / "b6_provisioning_audit_sink.template"
_DOCS_DIR = _scan.REPO_ROOT / "docs" / "runtime"
_REQUIRED_DOCS = [
    "b6_provisioning_audit_sink.md",
    "b6_provisioning_audit_events.md",
    "b6_provisioning_audit_evidence_template.md",
    "b6_provisioning_audit_blockers.md",
]
_FORBIDDEN_DIRS = (
    "infrastructure/db/",
    "infrastructure/iac/",
    "infrastructure/docker/",
    "infrastructure/env/",
)
_SANCTIONED_KEYS = {
    "PROVISIONING_AUDIT_REQUIRED",
    "PROVISIONING_AUDIT_SINK_REF",
    "PROVISIONING_AUDIT_RETENTION_POLICY_REF",
    "PROVISIONING_AUDIT_HASH_POLICY_REF",
    "PROVISIONING_AUDIT_REDACTION_POLICY_REF",
}
_DRIVER_TOPLEVEL = {"psycopg", "psycopg2", "asyncpg", "sqlalchemy"}
_B6_TEST_FILES = [
    _scan.BACKEND_ROOT / "tests" / "control_plane" / "test_b6_provisioning_audit_contract.py",
    _scan.BACKEND_ROOT / "tests" / "architecture" / "test_b6_provisioning_audit_boundary.py",
]


def test_sink_template_exists_and_reference_only() -> None:
    assert _TEMPLATE.is_file(), "infrastructure/runtime/b6_provisioning_audit_sink.template must exist"
    text = _TEMPLATE.read_text(encoding="utf-8")
    assert "reference-only" in text.lower(), "template must declare a reference-only posture"
    keys = set()
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        keys.add(s.split("=", 1)[0].strip())
    # only the five sanctioned keys (no rogue / gate-unconstrained additions)
    assert keys == _SANCTIONED_KEYS, f"template keys {sorted(keys)} != sanctioned {sorted(_SANCTIONED_KEYS)}"
    # NOTE: *_REF reference-only hygiene is owned by test_no_secret_literals — not re-checked here.


def test_sink_template_location() -> None:
    rel = _TEMPLATE.relative_to(_scan.REPO_ROOT).as_posix()
    assert rel.startswith("infrastructure/runtime/"), rel
    for forbidden in _FORBIDDEN_DIRS:
        assert not rel.startswith(forbidden), f"B-6 template must not live under {forbidden}"
    assert not rel.endswith(".sql"), "B-6 template must not be a DDL/.sql file"


def test_b6_docs_exist() -> None:
    for name in _REQUIRED_DOCS:
        assert (_DOCS_DIR / name).is_file(), f"missing B-6 doc: docs/runtime/{name}"


def test_blocker_note_keeps_b5_blk_4_open() -> None:
    text = (_DOCS_DIR / "b6_provisioning_audit_blockers.md").read_text(encoding="utf-8")
    assert "B5-BLK-4" in text, "blocker note must reference B5-BLK-4"
    assert "OPEN" in text, "blocker note must keep B5-BLK-4 OPEN"
    assert "b5_activation_blockers.md" in text, "blocker note must cross-reference the B-5 register"


def test_provisioning_audit_distinct_from_lineage() -> None:
    text = (_DOCS_DIR / "b6_provisioning_audit_sink.md").read_text(encoding="utf-8")
    low = text.lower()
    assert "IC-004" in text and "lineage" in low and "distinct" in low, (
        "sink doc must document provisioning-audit (IC-002/D-34) as DISTINCT from lineage (IC-004/D-23)"
    )


def test_no_b6_ddl_added() -> None:
    # no DDL/.sql committed under the B-6 doc/template homes
    for base in (_DOCS_DIR, _TEMPLATE.parent):
        for p in base.glob("b6_*.sql"):
            raise AssertionError(f"B-6 must not add DDL: {p}")


def test_b6_tests_have_no_static_db_driver_import() -> None:
    for p in _B6_TEST_FILES:
        assert p.is_file(), f"expected B-6 test file: {p}"
        for mod in _scan.imported_modules(p):
            top = mod.split(".")[0]
            assert top not in _DRIVER_TOPLEVEL, f"{p.name} statically imports DB driver {mod!r}"


if __name__ == "__main__":
    _scan.run(
        [
            test_sink_template_exists_and_reference_only,
            test_sink_template_location,
            test_b6_docs_exist,
            test_blocker_note_keeps_b5_blk_4_open,
            test_provisioning_audit_distinct_from_lineage,
            test_no_b6_ddl_added,
            test_b6_tests_have_no_static_db_driver_import,
        ]
    )
