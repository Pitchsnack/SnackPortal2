"""PRD 06 B-5 — activation-gate CONTRACT guard (text-inspection only; no runtime, no driver import).

Asserts the B-5 gate ARTIFACTS exist and commit to a fail-closed, references-only posture. B-5-specific only: secret /
*_REF hygiene for the .template is ALREADY enforced by test_no_secret_literals (test_templates_reference_only + the
pattern scan over infrastructure/**), so this test does not duplicate it. Text inspection only — no static
database-driver import (string literals naming paths are not imports). Pure stdlib; standalone-runnable:
  python tests/architecture/test_b5_runtime_activation_gate_contract.py
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

_TEMPLATE = _scan.REPO_ROOT / "infrastructure" / "runtime" / "b5_activation_gate.template"
_DOCS = [
    "b5_production_runtime_activation_gate.md",
    "b5_activation_blockers.md",
    "b5_activation_evidence_template.md",
    "b5_runtime_readiness_matrix.md",
]
_BLOCKER_IDS = [f"B5-BLK-{i}" for i in range(1, 10)]
_FORBIDDEN_DIRS = (
    "infrastructure/db/",
    "infrastructure/iac/",
    "infrastructure/docker/",
    "infrastructure/env/",
)


def test_activation_gate_template_exists_and_disabled_by_default() -> None:
    assert _TEMPLATE.is_file(), "infrastructure/runtime/b5_activation_gate.template must exist"
    text = _TEMPLATE.read_text(encoding="utf-8")
    assert "RUNTIME_ACTIVATION_ENABLED=false" in text, "activation switch must be present and false by default"


def test_activation_gate_template_location() -> None:
    rel = _TEMPLATE.relative_to(_scan.REPO_ROOT).as_posix()
    assert rel.startswith("infrastructure/runtime/"), rel
    for forbidden in _FORBIDDEN_DIRS:
        assert not rel.startswith(forbidden), f"runtime template must not live under {forbidden}"


def test_b5_runtime_docs_exist() -> None:
    base = _scan.REPO_ROOT / "docs" / "runtime"
    for name in _DOCS:
        assert (base / name).is_file(), f"missing B-5 doc: docs/runtime/{name}"


def test_blocker_register_is_not_ready_by_default() -> None:
    reg = (_scan.REPO_ROOT / "docs" / "runtime" / "b5_activation_blockers.md").read_text(encoding="utf-8")
    assert "NOT READY" in reg, "blocker register must commit a NOT READY posture"
    for blocker_id in _BLOCKER_IDS:
        assert blocker_id in reg, f"blocker register must list {blocker_id}"


if __name__ == "__main__":
    _scan.run(
        [
            test_activation_gate_template_exists_and_disabled_by_default,
            test_activation_gate_template_location,
            test_b5_runtime_docs_exist,
            test_blocker_register_is_not_ready_by_default,
        ]
    )
