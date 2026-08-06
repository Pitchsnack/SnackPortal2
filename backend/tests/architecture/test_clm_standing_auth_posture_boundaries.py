"""Static guard for the AUTHFIX-B replacement standing authentication verification harness.

AUTHFIX-B requires the B5-4A standing auth fixture family to be superseded **by an accepted
replacement** — a new standing verification harness, not an annotation. This guard pins the
replacement's defining properties, because the ways it could quietly stop being a replacement are
specific and recognisable:

* **It must be read-only.** The predecessor's successor verifies a live standing database. A harness
  that can write is one membership INSERT away from manufacturing the state it claims to observe —
  and creating a membership row to make a journey pass is a Gate-B class-M6 mutation that destroys
  the evidence rather than producing it.
* **It must not pin a roster.** The predecessor pinned `b5_standing_alpha` / `b5_standing_beta` /
  `b5_standing_dormant` and a whole-table membership count of exactly three. The standing fixture was
  replaced; the pins survived; the harness went red and, being MANUAL_ONLY, nobody saw it. A
  replacement that re-pins a roster reproduces that failure with new names.
* **It must fail closed on an absent census.** If `control_tenants` / `control_memberships` are
  missing, every downstream check passes for the wrong reason.
* **It must skip explicitly.** A bare `return` on an unconfigured machine is recorded by pytest as a
  PASS — the vacuous green this whole exercise exists to eliminate.
* **It must state the supersession and its non-claims.** The evidence chain depends on nobody reading
  a coherence check as an authenticated-journey proof.

Pure stdlib; runnable standalone:
    python tests/architecture/test_clm_standing_auth_posture_boundaries.py
"""

from __future__ import annotations

import ast
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

_REPLACEMENT = _scan.BACKEND_ROOT / "tests" / "control_plane" / "requires_pg" / "test_pg_clm_standing_auth_posture.py"
_PREDECESSOR = _scan.BACKEND_ROOT / "tests" / "control_plane" / "requires_pg" / "b5_standing_auth_fixture.py"
_PREDECESSOR_RUNBOOK = _scan.REPO_ROOT / "infrastructure" / "runbooks" / "b5_standing_auth_fixture.md"
_COMPLETENESS_GUARD = _scan.BACKEND_ROOT / "tests" / "architecture" / "test_live_pg_workflow_runset_completeness.py"

# The roster the predecessor pinned. None of it may reappear as an assertion in the replacement.
_RETIRED_SUBJECT_STATE = ("b5_standing_alpha", "b5_standing_beta", "b5_standing_dormant", "b5_standing_member")


def _text() -> str:
    return _REPLACEMENT.read_text(encoding="utf-8")


def _tree() -> ast.Module:
    return ast.parse(_text(), filename=str(_REPLACEMENT))


def test_replacement_exists_and_is_registered() -> None:
    assert _REPLACEMENT.is_file(), (
        "AUTHFIX-B requires supersession BY AN ACCEPTED REPLACEMENT — a new standing verification harness delivered "
        "under Gate A. An annotation-only disposition is a narrowing of that requirement, not a satisfaction of it."
    )
    guard = _COMPLETENESS_GUARD.read_text(encoding="utf-8")
    assert f"tests/control_plane/requires_pg/{_REPLACEMENT.name}" in guard, (
        "the replacement must carry a justified MANUAL_ONLY_EXCEPTIONS key in the same commit as the file"
    )


def test_replacement_is_strictly_read_only() -> None:
    text = _text()
    for write in ("INSERT INTO", "UPDATE ", "DELETE FROM", "TRUNCATE", "CREATE TABLE", "DROP ", "ALTER TABLE", "commit("):
        assert write not in text, f"the replacement must be strictly read-only (found {write!r})"
    assert "read_only = True" in text, "the verification connection must be set read-only"
    assert "class-M6" in text, (
        "the harness must state, in its own text, that creating a membership row to make a journey pass is a Gate-B "
        "M6 mutation that destroys the evidence — the single most tempting wrong move on this surface"
    )


def test_replacement_does_not_re_pin_a_roster() -> None:
    """The specific failure being replaced, asserted so it cannot be reintroduced under new names."""
    tree = _tree()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assert):
            continue
        source = ast.get_source_segment(_text(), node) or ""
        for retired in _RETIRED_SUBJECT_STATE:
            assert retired not in source, (
                f"the replacement asserts on the RETIRED subject state {retired!r}. That roster no longer exists — "
                "re-pinning it is how the predecessor died."
            )
        # A whole-table count equality is the other half of the predecessor's brittleness.
        assert "len(memberships) ==" not in source, (
            "the replacement must not pin the membership count. The predecessor pinned it at exactly three; the "
            "standing fixture changed; the harness went red and, being MANUAL_ONLY, nobody observed it."
        )
    assert "REPORTED, not pinned" in _text() or "REPORTS the roster" in _text() or "reported, never pinned" in _text().lower(), (
        "the harness must say which invariants it asserts and which state it merely reports"
    )


def test_replacement_fails_closed_on_a_vacuous_census() -> None:
    text = _text()
    assert "CSA-2" in text and "pass vacuously" in text, (
        "the harness must assert the authentication-bearing tables EXIST before checking anything about their "
        "contents — absent tables make every downstream check pass for the wrong reason"
    )
    assert "assert _table_exists(conn, table)" in text, "table presence must be asserted, not assumed"
    assert "assert tenants," in text, "an empty registry must fail, not pass silently"


def test_replacement_skips_explicitly_rather_than_returning() -> None:
    assert "unittest.SkipTest" in _text(), (
        "an unconfigured run must raise SkipTest. A bare `return` is recorded by pytest as a PASS — the vacuous "
        "green that let the predecessor's red go unobserved."
    )
    node = _skip_branch()
    bare_returns = [n for n in ast.walk(node) if isinstance(n, ast.Return)]
    assert not bare_returns, (
        "the verification entrypoint must contain no `return` statement: an early return on an unconfigured machine "
        "is exactly the vacuous PASS this replacement exists to stop reproducing"
    )
    raises = [n for n in ast.walk(node) if isinstance(n, ast.Raise)]
    assert raises, "the skip path must RAISE, not return"


def _skip_branch() -> ast.AST:
    for node in ast.walk(_tree()):
        if isinstance(node, ast.FunctionDef) and node.name == "test_clm_standing_auth_posture":
            return node
    raise AssertionError("the replacement must expose test_clm_standing_auth_posture()")


def test_replacement_states_supersession_and_non_claims() -> None:
    text = _text()
    assert "SUPERSESSION" in text, "the harness must state that it supersedes the B5-4A fixture's subject-state census"
    assert "NO OVERCLAIM" in text, "the harness must state its non-claims"
    for non_claim in ("does NOT prove an authenticated journey", "does NOT prove the tenant data plane"):
        assert non_claim in text, f"the harness must disclaim: {non_claim}"


def test_predecessor_is_marked_superseded_and_left_intact() -> None:
    """Retirement-by-deletion was NOT chosen, and must not happen by accident."""
    assert _PREDECESSOR.is_file(), (
        "the predecessor must NOT be deleted. Its checks are still referenced by four default-suite guards and by "
        "the MANUAL_ONLY completeness invariants; deleting it turns those red."
    )
    text = _PREDECESSOR.read_text(encoding="utf-8")
    assert "SUPERSEDED" in text, "the predecessor must carry an explicit supersession marking"
    assert _REPLACEMENT.name in text, "the predecessor must name its replacement so a reader can follow the chain"
    # The supersession banner must not break the delegating surfaces' PASS-count arithmetic.
    banner_lines = [line for line in text.splitlines() if "SUPERSEDED" in line]
    for line in banner_lines:
        assert "PASS:" not in line, (
            "a supersession banner containing the substring 'PASS:' silently breaks the delegating operators' exact "
            "PASS-count arithmetic (they count occurrences)"
        )
    runbook = _PREDECESSOR_RUNBOOK.read_text(encoding="utf-8")
    assert "SUPERSEDED" in runbook, "the predecessor's runbook must carry the supersession notice too"
    for banned in ("B5-BLK-4 CLOSED", "MVP COMPLETE", "Smoke C passed", "Smoke C succeeded", "Smoke C has been executed"):
        assert banned not in runbook, f"the supersession notice must not introduce the banned claim {banned!r}"


def test_guard_is_non_vacuous() -> None:
    assert _skip_branch() is not None
    assert len(_RETIRED_SUBJECT_STATE) == 4
    probe = ast.parse("assert 'b5_standing_alpha' in x\n")
    found = [n for n in ast.walk(probe) if isinstance(n, ast.Assert)]
    assert found and "b5_standing_alpha" in (ast.get_source_segment("assert 'b5_standing_alpha' in x\n", found[0]) or ""), (
        "the retired-roster detector must be able to see a violation"
    )


if __name__ == "__main__":
    _scan.run(
        [
            test_replacement_exists_and_is_registered,
            test_replacement_is_strictly_read_only,
            test_replacement_does_not_re_pin_a_roster,
            test_replacement_fails_closed_on_a_vacuous_census,
            test_replacement_skips_explicitly_rather_than_returning,
            test_replacement_states_supersession_and_non_claims,
            test_predecessor_is_marked_superseded_and_left_intact,
            test_guard_is_non_vacuous,
        ]
    )
