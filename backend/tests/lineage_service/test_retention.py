"""Retention framework: safe default retain-all; expiry disabled (PRD-P6-R2 E/F; §14)."""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _doubles  # noqa: E402
import _h  # noqa: E402

from lineage_service.models import RetentionPolicy  # noqa: E402
from lineage_service.retention import RetentionDisabled, RetentionFramework  # noqa: E402


def test_default_retain_all() -> None:
    audit = _doubles.RecordingAudit()
    d = RetentionFramework(audit=audit).evaluate(_doubles.ctx())
    assert d.action == "retain" and d.eligible_count == 0 and d.policy_configured is False
    assert "RetentionEvaluated" in audit.actions()


def test_configured_policy_still_retains_in_phase6() -> None:
    policy = RetentionPolicy(regime_code="SOC2", retention_floor_days=365)
    d = RetentionFramework().evaluate(_doubles.ctx(), policy)
    assert d.action == "retain" and d.eligible_count == 0 and d.policy_configured is True


def test_expiry_and_crypto_erase_disabled() -> None:
    r = RetentionFramework()
    for op in (r.expire, r.crypto_erase, r.delete):
        try:
            op()
            assert False, "expected RetentionDisabled"
        except RetentionDisabled:
            pass


if __name__ == "__main__":
    _h.run([
        test_default_retain_all,
        test_configured_policy_still_retains_in_phase6,
        test_expiry_and_crypto_erase_disabled,
    ])
