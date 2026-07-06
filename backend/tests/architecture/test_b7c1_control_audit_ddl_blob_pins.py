"""PRD 06 B-7C-1 (+ B-7C-1R) — reviewed Control-DB DDL blob-drift guard (architecture; no PostgreSQL).

The live-PG harnesses pin their reviewed Control-DB DDL by LF-normalized git-blob SHA-1 and STOP if the
applied bytes drift: the B-7A/B-7B control_audit harnesses pin 002 (887d0cbc…) and 003 (c787c537…); the
B-4 distinctness-ledger harness (test_pg_distinctness_ledger.py) pins 001 (30956ff1…) via the variable
``_REVIEWED_DDL_BLOB``. Those harnesses are ``--ignore``'d by the default suite, so DDL/pin drift would
otherwise surface only on a manual live run. This default-suite guard is the SINGLE SOURCE OF TRUTH: it
recomputes the blob SHA-1 of the DDL files and asserts (a) each DDL matches its known pin, and (b) every
requires_pg harness that pins a DDL pins the SAME current value. A DDL revision therefore fails CI here
until the harness pin(s) are updated in lockstep — no live database required, and the harnesses are
read-only (never applied/modified).

B-7C-1R (B7C1-AR-1) extended this guard from 002/003 (control_audit) to also cover 001
(001_distinctness_ledger.sql), which test_pg_distinctness_ledger.py pins under ``_REVIEWED_DDL_BLOB`` —
a different variable name than the control_audit harnesses' ``_REVIEWED_002_BLOB``/``_REVIEWED_003_BLOB``,
so 001 has its own check (it is NOT folded into the 002/003 harness loop).

MCC (Control DB Schema) extended it again to cover the Control-DB registry DDL 004-007
(control_tenants / control_memberships / control_federation / control_directory — the wired-but-previously-
DDL-less tables postgres_store.py already targets), pinned in lockstep with the MCC live-PG harness
``test_pg_control_schema_mcc.py`` (``_REVIEWED_004_BLOB``..``_REVIEWED_007_BLOB``; Option P).

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

# PRD 06 B-7C-1R (B7C1-AR-1): also pin 001_distinctness_ledger.sql. The B-4 distinctness-ledger live-PG
# harness pins it by the SAME LF-normalized git-blob SHA-1, but under the variable name _REVIEWED_DDL_BLOB
# (NOT _REVIEWED_001_BLOB / _REVIEWED_002_BLOB) — so it gets its own check below, not the 002/003 loop.
_DDL_001 = _CONTROL / "001_distinctness_ledger.sql"
_PIN_001 = "30956ff1e85e8dab1c9f55cbfc121ee9212f3ca0"
_DISTINCTNESS_HARNESS = _scan.BACKEND_ROOT / "tests" / "control_plane" / "requires_pg" / "test_pg_distinctness_ledger.py"

# PRD 07D-2c: pin 008_distinctness_fingerprint_unique.sql — the unique fingerprint constraint
# (system_identifier, database_identity) that serializes the D15 gate's CHECK->ACT window. The same
# distinctness-ledger harness applies it live and pins the same blob under _REVIEWED_008_BLOB
# (b7c1r2 INV-A/INV-B lockstep: guard pin + harness pin must move together with the DDL bytes).
_DDL_008 = _CONTROL / "008_distinctness_fingerprint_unique.sql"
_PIN_008 = "c510ebbaa881e3fc325dbb8ee8bf49b114e522ab"

# MCC (Control DB Schema): pin the Control-DB registry DDL 004-007 — control_tenants / control_memberships /
# control_federation / control_directory, the wired-but-previously-DDL-less tables postgres_store.py already
# targets. The MCC live-PG harness (test_pg_control_schema_mcc.py) pins the same blobs under
# _REVIEWED_004_BLOB / _REVIEWED_005_BLOB / _REVIEWED_006_BLOB / _REVIEWED_007_BLOB (Option P; MCC exec-auth
# V2 §15) — cross-checked below so a DDL revision fails CI here until guard + harness pins move in lockstep.
_DDL_004 = _CONTROL / "004_control_tenants.sql"
_DDL_005 = _CONTROL / "005_control_memberships.sql"
_DDL_006 = _CONTROL / "006_control_federation.sql"
_DDL_007 = _CONTROL / "007_control_directory.sql"
_PIN_004 = "8194408e62f08533e649612981f10089b8a3b1b0"
_PIN_005 = "a0df9ec58b6825aa298b1b9656cc0028d9831c14"
_PIN_006 = "c929af89da85ec7614b716bdb40af611da9613f2"
_PIN_007 = "aa6066a7398cfb81e8e96067927023c3f11bb391"
_MCC_HARNESS = _scan.BACKEND_ROOT / "tests" / "control_plane" / "requires_pg" / "test_pg_control_schema_mcc.py"
# (harness var name, guard pin, DDL path) — var names are LITERAL so the b7c1r2 meta-guard's pin-var scan sees them.
_MCC_PINS = [
    ("_REVIEWED_004_BLOB", _PIN_004, _DDL_004),
    ("_REVIEWED_005_BLOB", _PIN_005, _DDL_005),
    ("_REVIEWED_006_BLOB", _PIN_006, _DDL_006),
    ("_REVIEWED_007_BLOB", _PIN_007, _DDL_007),
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


def test_distinctness_ledger_ddl_blob_matches_pin() -> None:
    # B-7C-1R: 001 distinctness-ledger DDL (separate from the control_audit 002/003 pins).
    assert _git_blob_sha1(_DDL_001) == _PIN_001, (
        f"001_distinctness_ledger.sql drifted from pin {_PIN_001}; a governed DDL change must update this guard "
        f"and the test_pg_distinctness_ledger.py _REVIEWED_DDL_BLOB pin in lockstep"
    )


def test_distinctness_harness_pin_matches_current_ddl() -> None:
    # B-7C-1R: the B-4 harness pins 001 under _REVIEWED_DDL_BLOB (a different variable name than the
    # control_audit harnesses' _REVIEWED_002_BLOB/_REVIEWED_003_BLOB) — so this is a separate check.
    computed_001 = _git_blob_sha1(_DDL_001)
    text = _DISTINCTNESS_HARNESS.read_text(encoding="utf-8")
    m001 = re.search(r'_REVIEWED_DDL_BLOB\s*=\s*"([0-9a-f]{40})"', text)
    assert m001, "test_pg_distinctness_ledger.py must pin _REVIEWED_DDL_BLOB (001 distinctness-ledger DDL)"
    assert m001.group(1) == computed_001, "test_pg_distinctness_ledger.py _REVIEWED_DDL_BLOB diverges from the current 001 DDL blob"


def test_distinctness_fingerprint_008_ddl_blob_matches_pin() -> None:
    # PRD 07D-2c: 008 fingerprint-uniqueness DDL (separate pin variable in the same harness).
    assert _git_blob_sha1(_DDL_008) == _PIN_008, (
        f"008_distinctness_fingerprint_unique.sql drifted from pin {_PIN_008}; a governed DDL change must "
        f"update this guard and the test_pg_distinctness_ledger.py _REVIEWED_008_BLOB pin in lockstep"
    )


def test_distinctness_harness_008_pin_matches_current_ddl() -> None:
    # PRD 07D-2c: the distinctness-ledger harness pins 008 under _REVIEWED_008_BLOB; the harness
    # pin must equal the CURRENT blob of the DDL (single source of truth = the DDL bytes).
    computed_008 = _git_blob_sha1(_DDL_008)
    text = _DISTINCTNESS_HARNESS.read_text(encoding="utf-8")
    m008 = re.search(r'_REVIEWED_008_BLOB\s*=\s*"([0-9a-f]{40})"', text)
    assert m008, "test_pg_distinctness_ledger.py must pin _REVIEWED_008_BLOB (008 fingerprint-uniqueness DDL)"
    assert m008.group(1) == computed_008, "test_pg_distinctness_ledger.py _REVIEWED_008_BLOB diverges from the current 008 DDL blob"


def test_mcc_control_registry_ddl_blobs_match_known_pins() -> None:
    # MCC: 004-007 Control-DB registry DDL (control_tenants/memberships/federation/directory).
    for _var, pin, ddl in _MCC_PINS:
        assert _git_blob_sha1(ddl) == pin, (
            f"{ddl.name} drifted from pin {pin}; a governed DDL change must update this guard "
            f"and the test_pg_control_schema_mcc.py harness pin in lockstep"
        )


def test_mcc_harness_pins_match_current_ddl() -> None:
    # MCC Option P lockstep: the live-PG harness pins 004-007 under _REVIEWED_004_BLOB.._REVIEWED_007_BLOB;
    # each harness pin must equal the CURRENT blob of its DDL (single source of truth = the DDL bytes).
    text = _MCC_HARNESS.read_text(encoding="utf-8")
    for var, _pin, ddl in _MCC_PINS:
        m = re.search(var + r'\s*=\s*"([0-9a-f]{40})"', text)
        assert m, f"test_pg_control_schema_mcc.py must pin {var} ({ddl.name})"
        assert m.group(1) == _git_blob_sha1(ddl), f"test_pg_control_schema_mcc.py {var} diverges from the current {ddl.name} blob"


if __name__ == "__main__":
    _scan.run(
        [
            test_control_audit_ddl_blobs_match_known_pins,
            test_requires_pg_harness_pins_match_current_ddl,
            test_distinctness_ledger_ddl_blob_matches_pin,
            test_distinctness_harness_pin_matches_current_ddl,
            test_distinctness_fingerprint_008_ddl_blob_matches_pin,
            test_distinctness_harness_008_pin_matches_current_ddl,
            test_mcc_control_registry_ddl_blobs_match_known_pins,
            test_mcc_harness_pins_match_current_ddl,
        ]
    )
