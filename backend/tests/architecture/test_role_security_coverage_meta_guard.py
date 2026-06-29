"""PRD 06 PMA-AR-2 — cross-family role-security coverage meta-guard (architecture; no PostgreSQL).

Two role-security static least-privilege guards exist — ``test_provisioning_role_static_security.py`` (AT2-AR-1,
``sp2_provisioner``) and ``test_lineage_role_static_security.py`` (PMA-AR-1, ``lineage_writer``/``lineage_reader``).
But nothing asserted, at the PROGRAM level, that *every* security-sensitive role-bearing DDL family stays
represented by a required-suite static role-security guard, and that those guards stay COLLECTED by the required
default suite. A future PR could add role-bearing DDL with no static guard, rename/remove a guard, or de-collect
one from the required suite, while docs still claim coverage.

This guard is the **role-security analogue of PM-AR-1** (``test_required_ci_ddl_coverage_meta_guard.py``, which
does the same for DDL *blob-drift* coverage) — complementary, not a duplicate (different concern). It keeps an
explicit reviewed coverage registry and asserts:

- **INV-A (bidirectional, file-level).** The set of on-disk ``infrastructure/db/**/*.sql`` files that contain an
  executable role-DEFINING statement (or a role-MEMBERSHIP grant) equals the set registered across the coverage
  registry (∪ an explicit excluded-with-reason set). An UNKNOWN role-bearing file (new, unregistered) OR a STALE
  registry/exclusion path (file gone or no longer role-bearing) both FAIL.
- **INV-B (per family).** Each family's static guard exists under ``backend/tests/architecture/``, is named
  ``test_*.py``, has at least one top-level ``def test_`` and no module-level skip, and its source text anchors
  every registered role name AND the DDL path basename (so a guard drifted off its family FAILs).
- **INV-C (collection durability).** A read-only static parse of ``backend/pyproject.toml`` confirms ``testpaths``
  covers ``tests/architecture`` and the ``addopts --ignore`` set does NOT cover ``tests/architecture`` or any
  registry guard path; and the meta-guard itself + every registry guard live under ``tests/architecture`` and are
  ``test_*.py``. (Existence is not collection; this is the recurring required-CI-durability check.)

Detection trigger (PMA-AR-2 §6.3): role-DEFINING (``CREATE``/``ALTER``/``DROP`` ``ROLE``/``USER``) or
role-MEMBERSHIP (``GRANT <role> TO <role>`` — no ``ON``). Table-privilege ``GRANT … ON … TO role`` /
``REVOKE … ON … FROM role`` do NOT trigger a new family (they assign privileges to a role defined elsewhere — the
defining file is already a family). Comments and single-quoted string literals are stripped before detection.

Scope: required-CI coverage/registry/collection-durability ONLY. It does NOT re-assert least-privilege (the
individual guards do that), does NOT do static↔live consistency (PMA-PM-1), and does NOT run live PostgreSQL.
It reads guard SOURCE TEXT only — it never imports/executes the guards or runs DDL, and runs no
``pytest --collect-only`` subprocess. Pure stdlib; imports no database driver; standalone-runnable:

    python tests/architecture/test_role_security_coverage_meta_guard.py
"""

from __future__ import annotations

import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

_DB_DIR = _scan.REPO_ROOT / "infrastructure" / "db"
_ARCH_DIR = pathlib.Path(__file__).resolve().parent  # .../backend/tests/architecture
_PYPROJECT = _scan.BACKEND_ROOT / "pyproject.toml"
_ARCH_RELDIR = "tests/architecture"  # backend-relative posix dir the required suite collects

# Explicit, reviewed role-security coverage registry (authored from the live PMA-AR-2 pins). A new role family MUST
# be added here (with its static guard) in lockstep; an intentionally-unguarded role-bearing DDL would need a
# NAMED, reasoned entry in _ROLE_DDL_EXCLUSIONS — never a silent omission.
ROLE_SECURITY_COVERAGE: dict[str, dict[str, tuple[str, ...]]] = {
    "provisioning": {
        "ddl_paths": ("infrastructure/db/provisioning/003_provisioning_role.sql",),
        "roles": ("sp2_provisioner",),
        "static_guard": ("test_provisioning_role_static_security.py",),
    },
    "lineage": {
        "ddl_paths": ("infrastructure/db/lineage/003_roles.sql",),
        "roles": ("lineage_writer", "lineage_reader"),
        "static_guard": ("test_lineage_role_static_security.py",),
    },
}
# Role-bearing DDL deliberately NOT requiring an individual static guard — each value is a tested reason. EMPTY
# today (no such DDL exists); kept present so INV-A's excluded-with-reason path is real and exercised.
_ROLE_DDL_EXCLUSIONS: dict[str, str] = {}

# --- detection (role-DEFINING + role-MEMBERSHIP only; comments + string literals stripped) --------
_ROLE_DEFINING_RE = re.compile(r"(?is)\b(?:CREATE|ALTER|DROP)\s+(?:ROLE|USER)\b")
# GRANT <role> TO <role> — membership. A table-privilege grant ("GRANT SELECT ON t TO r") never matches: the word
# right after GRANT must be immediately followed by TO, but a privilege is followed by ',' or 'ON'.
_ROLE_MEMBERSHIP_RE = re.compile(r"(?is)\bGRANT\s+\w+\s+TO\s+\w+\b")
_TOP_LEVEL_TEST_RE = re.compile(r"(?m)^\s*def\s+(test_\w+)\s*\(")
_MODULE_SKIP_RE = re.compile(r"(?m)^\s*pytestmark\s*=.*\bskip\b|allow_module_level\s*=\s*True")


def _strip(sql: str) -> str:
    """Remove ``/* … */`` and ``--`` comments and blank single-quoted literals (prose must not be read as DDL)."""
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    sql = re.sub(r"--[^\n]*", " ", sql)
    sql = re.sub(r"'[^']*'", "''", sql)
    return sql


def _is_role_bearing(clean_sql: str) -> bool:
    """True iff comment/literal-stripped SQL contains a role-DEFINING or role-MEMBERSHIP statement."""
    return bool(_ROLE_DEFINING_RE.search(clean_sql) or _ROLE_MEMBERSHIP_RE.search(clean_sql))


def _detected_role_bearing_files() -> set[str]:
    """Repo-relative posix paths of every ``infrastructure/db/**/*.sql`` that is role-bearing."""
    out: set[str] = set()
    for path in _DB_DIR.rglob("*.sql"):
        if _is_role_bearing(_strip(path.read_text(encoding="utf-8"))):
            out.add(path.relative_to(_scan.REPO_ROOT).as_posix())
    return out


def _registered_ddl_paths() -> set[str]:
    paths: set[str] = set()
    for fam in ROLE_SECURITY_COVERAGE.values():
        paths.update(fam["ddl_paths"])
    return paths


def _top_level_test_defs(src: str) -> list[str]:
    return _TOP_LEVEL_TEST_RE.findall(src)


def _module_skipped(src: str) -> bool:
    return _MODULE_SKIP_RE.search(src) is not None


def _pytest_testpaths(pyproject_text: str) -> list[str]:
    m = re.search(r"(?ms)^\s*testpaths\s*=\s*\[(.*?)\]", pyproject_text)
    return re.findall(r"""['"]([^'"]+)['"]""", m.group(1)) if m else []


def _addopts_ignores(pyproject_text: str) -> list[str]:
    m = re.search(r"""(?m)^\s*addopts\s*=\s*['"](.*?)['"]\s*$""", pyproject_text)
    return re.findall(r"--ignore=(\S+)", m.group(1)) if m else []


def _covers(prefix: str, target: str) -> bool:
    """True iff a pytest path/ignore `prefix` covers `target` (equal or a parent dir)."""
    p = prefix.strip().rstrip("/")
    return target == p or target.startswith(p + "/")


# --- INV-A: every role-bearing DDL file is registered (bidirectional) ----------------------------
def test_inv_a_role_bearing_ddl_coverage_completeness_bidirectional() -> None:
    detected = _detected_role_bearing_files()
    registered = _registered_ddl_paths() | set(_ROLE_DDL_EXCLUSIONS)
    unknown = detected - registered
    assert not unknown, (
        f"role-bearing DDL with NO role-security coverage registry entry: {sorted(unknown)}. Add the family (and "
        f"its static role-security guard) to ROLE_SECURITY_COVERAGE — or _ROLE_DDL_EXCLUSIONS with a reason — before merge."
    )
    stale = registered - detected
    assert not stale, (
        f"registry/exclusion pins role-bearing DDL not detected on disk: {sorted(stale)}. A role DDL file was "
        f"deleted/renamed or no longer contains a role-defining/membership statement — repair the registry."
    )
    # Each registered COVERAGE ddl_path must exist and actually be role-bearing (no vacuous registry entry).
    for fam, spec in ROLE_SECURITY_COVERAGE.items():
        for rel in spec["ddl_paths"]:
            p = _scan.REPO_ROOT / rel
            assert p.is_file(), f"{fam}: registered DDL path missing on disk: {rel}"
            assert _is_role_bearing(_strip(p.read_text(encoding="utf-8"))), (
                f"{fam}: registered DDL path {rel} contains no role-defining/membership statement"
            )


# --- INV-B: each family guard exists, is located/named/collectable, and anchors roles + DDL ------
def test_inv_b_each_family_guard_exists_located_named_anchors() -> None:
    for fam, spec in ROLE_SECURITY_COVERAGE.items():
        guards = spec["static_guard"]
        assert guards, f"family {fam!r} has no static_guard in the registry"
        for guard_name in guards:
            assert re.fullmatch(r"test_.*\.py", guard_name), f"{fam}: static_guard not named test_*.py: {guard_name}"
            guard_path = _ARCH_DIR / guard_name
            assert guard_path.is_file(), f"{fam}: static role-security guard missing under {_ARCH_RELDIR}/: {guard_name}"
            src = guard_path.read_text(encoding="utf-8")
            assert _top_level_test_defs(src), f"{fam}: guard {guard_name} has no top-level def test_ (not collectable)"
            assert not _module_skipped(src), f"{fam}: guard {guard_name} is module-level skipped (not collected)"
            for role in spec["roles"]:
                assert role in src, f"{fam}: guard {guard_name} does not reference registered role {role!r} (drifted off family)"
            for rel in spec["ddl_paths"]:
                base = rel.rsplit("/", 1)[-1]
                assert base in src, f"{fam}: guard {guard_name} does not reference its DDL {base!r} (drifted off family)"


# --- INV-C: guards (and this meta-guard) stay collected by the required default suite ------------
def test_inv_c_guards_collected_by_required_suite() -> None:
    text = _PYPROJECT.read_text(encoding="utf-8")
    testpaths = _pytest_testpaths(text)
    ignores = _addopts_ignores(text)
    assert any(_covers(tp, _ARCH_RELDIR) for tp in testpaths), (
        f"pyproject testpaths {testpaths} does not cover {_ARCH_RELDIR} — role-security guards would not be collected"
    )
    # every registry guard + this meta-guard: under tests/architecture, test_*.py, not under any --ignore.
    guard_relpaths = [f"{_ARCH_RELDIR}/{g}" for spec in ROLE_SECURITY_COVERAGE.values() for g in spec["static_guard"]]
    guard_relpaths.append(f"{_ARCH_RELDIR}/{pathlib.Path(__file__).name}")
    for rel in guard_relpaths:
        assert rel.startswith(_ARCH_RELDIR + "/") and rel.endswith(".py"), f"guard not under {_ARCH_RELDIR}/: {rel}"
        covering = [ig for ig in ignores if _covers(ig, rel) or _covers(ig, _ARCH_RELDIR)]
        assert not covering, f"pyproject addopts --ignore {covering} would de-collect required role-security guard {rel}"


# --- non-vacuity (synthetic strings / tempfile ONLY; never mutate tracked files) -----------------
def test_nv_inva_unknown_and_stale_detected() -> None:  # RED-PMA-AR2-1/2/3
    detected = {"infrastructure/db/provisioning/003_provisioning_role.sql", "infrastructure/db/lineage/003_roles.sql"}
    registered_full = detected
    assert (detected - registered_full) == set() and (registered_full - detected) == set()  # aligned -> pass
    registered_missing = {"infrastructure/db/lineage/003_roles.sql"}  # provisioning dropped (RED-2)
    assert detected - registered_missing == {"infrastructure/db/provisioning/003_provisioning_role.sql"}  # unknown -> INV-A fails
    detected_missing = {"infrastructure/db/provisioning/003_provisioning_role.sql"}  # lineage file gone
    assert registered_full - detected_missing == {"infrastructure/db/lineage/003_roles.sql"}  # stale -> INV-A fails
    extra = detected | {"infrastructure/db/control/099_new_roles.sql"}  # new unregistered role DDL (RED-1)
    assert extra - registered_full == {"infrastructure/db/control/099_new_roles.sql"}


def test_nv_invb_guard_missing_detected() -> None:  # RED-PMA-AR2-4
    assert not (_ARCH_DIR / "test_does_not_exist_role_guard.py").is_file()


def test_nv_invb_structural_rejections() -> None:  # RED-PMA-AR2-5/6/7
    assert not "some/other/dir/test_x.py".startswith(_ARCH_RELDIR + "/")  # RED-5 path outside tests/architecture
    assert re.fullmatch(r"test_.*\.py", "guard_helpers.py") is None  # RED-6 filename not test_*.py
    assert _top_level_test_defs("def _helper():\n    return 1\n") == []  # RED-7 no top-level def test_


def test_nv_invb_anchor_rejections() -> None:  # RED-PMA-AR2-8/9
    src = "ROLES = ('other_role',)\n_DDL = '.../999_other.sql'\n"
    assert "sp2_provisioner" not in src  # RED-8 registered role missing from guard text
    assert "003_provisioning_role.sql" not in src  # RED-9 registered DDL basename missing from guard text


def test_nv_detection_negatives() -> None:  # RED-PMA-AR2-10/11/13
    assert not _is_role_bearing(_strip("-- CREATE ROLE shadow NOLOGIN;\n"))  # RED-10 comment-only CREATE ROLE
    assert not _is_role_bearing(_strip("COMMENT ON ROLE x IS 'CREATE ROLE y; GRANT z TO w';\n"))  # RED-11 prose literal
    assert not _is_role_bearing(_strip("GRANT SELECT, INSERT ON lineage TO lineage_writer;\n"))  # RED-13 table grant
    assert not _is_role_bearing(_strip("REVOKE UPDATE, DELETE, TRUNCATE ON lineage FROM lineage_writer;\n"))  # table revoke
    # positive controls: real role-defining / membership ARE detected
    assert _is_role_bearing(_strip("CREATE ROLE sp2_provisioner NOLOGIN;\n"))
    assert _is_role_bearing(_strip("GRANT lineage_writer TO sp2_provisioner;\n"))  # membership (no ON)


def test_nv_invc_ignore_covering_arch_detected() -> None:  # RED-PMA-AR2-12
    bad = _addopts_ignores('addopts = "--ignore=tests/architecture"')
    assert bad == ["tests/architecture"]
    assert _covers("tests/architecture", f"{_ARCH_RELDIR}/test_role_security_coverage_meta_guard.py")  # would de-collect -> INV-C fails
    good = _addopts_ignores('addopts = "--ignore=tests/lineage_service/requires_pg --ignore=tests/control_plane/requires_pg"')
    assert all(not _covers(ig, _ARCH_RELDIR) for ig in good)  # the real ignores do NOT cover tests/architecture
    assert _pytest_testpaths('testpaths = ["tests"]') == ["tests"] and _covers("tests", _ARCH_RELDIR)


if __name__ == "__main__":
    _scan.run(
        [
            test_inv_a_role_bearing_ddl_coverage_completeness_bidirectional,
            test_inv_b_each_family_guard_exists_located_named_anchors,
            test_inv_c_guards_collected_by_required_suite,
            test_nv_inva_unknown_and_stale_detected,
            test_nv_invb_guard_missing_detected,
            test_nv_invb_structural_rejections,
            test_nv_invb_anchor_rejections,
            test_nv_detection_negatives,
            test_nv_invc_ignore_covering_arch_detected,
        ]
    )
