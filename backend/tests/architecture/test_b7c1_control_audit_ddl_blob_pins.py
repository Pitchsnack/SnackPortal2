"""PRD 06 B-7C-1 — control_audit DDL blob-drift guard (architecture; no PostgreSQL).

The B-7A and B-7B live-PG harnesses pin the reviewed control_audit DDL by LF-normalized git-blob SHA-1
(002 = 887d0cbc…, 003 = c787c537…) and STOP if the applied bytes drift. Those harnesses are
``--ignore``'d by the default suite, so DDL/pin drift would otherwise surface only on a manual live run.
This default-suite guard is the SINGLE SOURCE OF TRUTH: it recomputes the blob SHA-1 of the DDL files and
asserts (a) the DDL matches the known pins, and (b) BOTH requires_pg harness files pin the SAME current
value. A DDL revision therefore fails CI here until the harness pins are updated in lockstep — no live
database required, and the harnesses are read-only (never applied/modified).

Pure stdlib (hashlib); imports no database driver; standalone-runnable:
  python tests/architecture/test_b7c1_control_audit_ddl_blob_pins.py
"""

from __future__ import annotations

import hashlib
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

_CONTROL = _scan.REPO_ROOT / "infrastructure" / "db" / "control"
_DDL_002 = _CONTROL / "002_provisioning_audit.sql"
_DDL_003 = _CONTROL / "003_provisioning_audit_append_only.sql"

# Full LF-normalized git-blob SHA-1 pins established by B-7A and re-confirmed in B-7B post-merge
# verification (main de3fe73). A legitimate DDL change must update these AND the two harness pins.
_PIN_002 = "887d0cbce636b7a4610272b584ad0aea61eb2294"
_PIN_003 = "c787c5372c511dc1975d337cdfe871d2d849a2c4"

_HARNESSES = [
    _scan.BACKEND_ROOT / "tests" / "control_plane" / "requires_pg" / "test_pg_control_audit_ddl.py",
    _scan.BACKEND_ROOT / "tests" / "control_plane" / "requires_pg" / "test_pg_control_store_runtime_wiring.py",
]


def _git_blob_sha1(path: pathlib.Path) -> str:
    data = path.read_bytes().replace(b"\r\n", b"\n")  # autocrlf normalization (the git blob is LF)
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def test_control_audit_ddl_blobs_match_known_pins() -> None:
    assert _git_blob_sha1(_DDL_002) == _PIN_002, (
        f"002_provisioning_audit.sql drifted from pin {_PIN_002}; a governed DDL change must update this guard "
        f"and both requires_pg harness pins in lockstep"
    )
    assert _git_blob_sha1(_DDL_003) == _PIN_003, (
        f"003_provisioning_audit_append_only.sql drifted from pin {_PIN_003}; update this guard + both harness pins"
    )


def test_requires_pg_harness_pins_match_current_ddl() -> None:
    computed_002 = _git_blob_sha1(_DDL_002)
    computed_003 = _git_blob_sha1(_DDL_003)
    for harness in _HARNESSES:
        text = harness.read_text(encoding="utf-8")
        m002 = re.search(r'_REVIEWED_002_BLOB\s*=\s*"([0-9a-f]{40})"', text)
        m003 = re.search(r'_REVIEWED_003_BLOB\s*=\s*"([0-9a-f]{40})"', text)
        assert m002 and m003, f"{harness.name} must pin _REVIEWED_002_BLOB and _REVIEWED_003_BLOB"
        assert m002.group(1) == computed_002, f"{harness.name} _REVIEWED_002_BLOB diverges from the current 002 DDL blob"
        assert m003.group(1) == computed_003, f"{harness.name} _REVIEWED_003_BLOB diverges from the current 003 DDL blob"


if __name__ == "__main__":
    _scan.run([test_control_audit_ddl_blobs_match_known_pins, test_requires_pg_harness_pins_match_current_ddl])
