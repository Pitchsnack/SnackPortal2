"""Regression guard for the secret-scan CI workflow configuration.

Asserts that ``.github/workflows/ci.yml`` (and ``.gitleaks.toml``) retain the
secret-scan protections that are true on ``main`` today. Implements
PRD-CI-SECSCAN-REGRESSION-GUARD-01-R1 = addendum ATR-R1 (the guard) + ATR-R2 (the
fail-closed meta-test), plus the currently-true static invariants ATR-S4/S5/S7/S8/S9.

The deferred invariants ATR-S1/S2/S3 (validate-job and top-level least-privilege, and
the gitleaks-action SHA-pin) are deliberately NOT asserted here -- they are false on main
today and would turn the build red; they land via PRD-CI-HARDEN-01, which adds them to
this guard afterwards.

Design (per the R1 PRD):
  * Pure stdlib, no dependency. The structural parse is indentation-aware and strips YAML
    comments, so comment prose that mentions gitleaks-action@v2 / pull-requests:read /
    pull_request (ci.yml comments) is never mistaken for structure.
  * Each check is a pure function over file CONTENT (a string) and fails closed via
    AssertionError -- the only exception ``_scan.run()`` catches. A missing / empty /
    unparseable file, or an unlocatable secret-scan job / gitleaks step, raises
    AssertionError rather than passing silently.
  * The gitleaks step is located by the org-qualified action repo
    ``gitleaks/gitleaks-action`` independent of the ``@ref``, so a future SHA-pin
    (PRD-CI-HARDEN-01) does not break the guard.
  * The negative meta-tests exercise the checks against IN-MEMORY mutated copies; the live
    ci.yml is NEVER edited.

Runs under pytest (``pytest tests/architecture``) and standalone
(``python tests/architecture/test_secret_scan_workflow_guard.py``).
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

GITLEAKS_REPO = "gitleaks/gitleaks-action"
TOKEN_PLACEHOLDER = "GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}"


# --- low-level line helpers (comment-stripped, indentation-aware) --------------


def _lines(text):
    # splitlines() is newline-agnostic (handles the CRLF ci.yml).
    return text.splitlines()


def _is_comment_or_blank(raw):
    s = raw.strip()
    return (not s) or s.startswith("#")


def _strip_inline(raw):
    # Drop a trailing " #..." comment; preserve leading whitespace for indent depth.
    i = raw.find(" #")
    if i != -1:
        raw = raw[:i]
    return raw.rstrip()


def _indent(raw):
    return len(raw) - len(raw.lstrip(" "))


def _uses_repo(raw):
    """Org-qualified action repo of an ACTIVE ``uses:`` line (ref-agnostic), else None."""
    if _is_comment_or_blank(raw):
        return None
    s = _strip_inline(raw).strip()
    if s.startswith("- "):
        s = s[2:].strip()
    if not s.startswith("uses:"):
        return None
    value = s[len("uses:") :].strip()
    return value.split("@", 1)[0].strip()


def _job_block(ci_text, job_name):
    """Lines of the named job body (indent > 2). Fail closed (AssertionError) if absent."""
    lines = _lines(ci_text)
    start = None
    for idx, raw in enumerate(lines):
        if _is_comment_or_blank(raw):
            continue
        s = _strip_inline(raw)
        if _indent(s) == 2 and s.strip() == job_name + ":":
            start = idx
            break
    assert start is not None, "ci.yml: job '" + job_name + "' not found"
    body = []
    for raw in lines[start + 1 :]:
        if _is_comment_or_blank(raw):
            body.append(raw)
            continue
        if _indent(_strip_inline(raw)) <= 2:
            break
        body.append(raw)
    assert body, "ci.yml: job '" + job_name + "' has an empty body"
    return body


def _find_key(block, key, indent):
    for i, raw in enumerate(block):
        if _is_comment_or_blank(raw):
            continue
        s = _strip_inline(raw)
        if _indent(s) == indent and s.strip() == key + ":":
            return i
    return None


def _children(block, start_i, parent_indent):
    out = []
    for raw in block[start_i + 1 :]:
        if _is_comment_or_blank(raw):
            continue
        s = _strip_inline(raw)
        if _indent(s) <= parent_indent:
            break
        out.append(s.strip())
    return out


def _steps(body):
    si = _find_key(body, "steps", 4)
    assert si is not None, "secret-scan job has no steps: block"
    chunks = []
    cur = None
    for raw in body[si + 1 :]:
        if _is_comment_or_blank(raw):
            if cur is not None:
                cur.append(raw)
            continue
        s = _strip_inline(raw)
        ind = _indent(s)
        if ind <= 4:
            break
        if ind == 6 and s.strip().startswith("- "):
            if cur is not None:
                chunks.append(cur)
            cur = [raw]
        elif cur is not None:
            cur.append(raw)
    if cur is not None:
        chunks.append(cur)
    return chunks


def _gitleaks_step(body):
    for chunk in _steps(body):
        for raw in chunk:
            if _uses_repo(raw) == GITLEAKS_REPO:
                return chunk
    return None


# --- guard checks: pure functions over file CONTENT, fail-closed via assert ----


def assert_secret_scan_job_present(ci_text):
    _job_block(ci_text, "secret-scan")


def assert_read_only_permissions(ci_text):
    body = _job_block(ci_text, "secret-scan")
    i = _find_key(body, "permissions", 4)
    assert i is not None, "secret-scan job has no permissions: block"
    kv = {}
    for s in _children(body, i, 4):
        if ":" in s:
            key, _, value = s.partition(":")
            kv[key.strip()] = value.strip()
    assert kv.get("contents") == "read", "secret-scan permissions.contents must be 'read'"
    assert kv.get("pull-requests") == "read", "secret-scan permissions.pull-requests must be 'read'"


def assert_no_write_grant(ci_text):
    body = _job_block(ci_text, "secret-scan")
    for raw in body:
        if _is_comment_or_blank(raw):
            continue
        s = _strip_inline(raw).strip()
        assert "write-all" not in s, "secret-scan job must not grant write-all: " + repr(s)
        if ":" in s:
            _, _, value = s.partition(":")
            assert value.strip() != "write", "secret-scan job must not grant a write permission: " + repr(s)


def assert_gitleaks_step_present(ci_text):
    body = _job_block(ci_text, "secret-scan")
    msg = "secret-scan job has no active " + GITLEAKS_REPO + " step (ref-agnostic match)"
    assert _gitleaks_step(body) is not None, msg


def assert_token_passthrough(ci_text):
    body = _job_block(ci_text, "secret-scan")
    chunk = _gitleaks_step(body)
    assert chunk is not None, "secret-scan job has no active " + GITLEAKS_REPO + " step"
    want = TOKEN_PLACEHOLDER.replace(" ", "")
    found = False
    for raw in chunk:
        if _is_comment_or_blank(raw):
            continue
        if _strip_inline(raw).strip().replace(" ", "") == want:
            found = True
    assert found, "gitleaks step must pass " + TOKEN_PLACEHOLDER


def assert_fetch_depth_zero(ci_text):
    body = _job_block(ci_text, "secret-scan")
    value = None
    for raw in body:
        if _is_comment_or_blank(raw):
            continue
        s = _strip_inline(raw).strip()
        if s.startswith("fetch-depth:"):
            value = s.partition(":")[2].strip()
    assert value is not None, "secret-scan checkout must set fetch-depth: 0 (none found)"
    assert value == "0", "secret-scan checkout fetch-depth must be 0, got " + repr(value)


def assert_no_fail_open(ci_text):
    body = _job_block(ci_text, "secret-scan")
    for raw in body:
        if _is_comment_or_blank(raw):
            continue
        norm = _strip_inline(raw).strip().replace(" ", "")
        assert "continue-on-error:true" not in norm, "secret-scan must not set continue-on-error: true"
        assert norm not in ("if:false", "if:${{false}}"), "secret-scan must not be disabled with if: false"
        assert "if:always()" not in norm, "secret-scan must not mask its result with if: always()"
        assert "||true" not in norm, "secret-scan must not discard the gitleaks exit code with '|| true'"


def assert_no_pull_request_target(workflow_texts):
    for name, text in workflow_texts:
        for raw in _lines(text):
            if _is_comment_or_blank(raw):
                continue
            assert "pull_request_target" not in _strip_inline(raw), name + ": pull_request_target trigger is forbidden"


def assert_trigger_coverage(ci_text):
    lines = _lines(ci_text)
    on_i = None
    for i, raw in enumerate(lines):
        if _is_comment_or_blank(raw):
            continue
        s = _strip_inline(raw)
        if _indent(s) == 0 and s.strip() == "on:":
            on_i = i
            break
    assert on_i is not None, "ci.yml has no top-level on: trigger block"
    triggers = []
    for raw in lines[on_i + 1 :]:
        if _is_comment_or_blank(raw):
            continue
        s = _strip_inline(raw)
        if _indent(s) == 0:
            break
        key = s.strip()
        key = key[:-1] if key.endswith(":") else key.partition(":")[0]
        triggers.append(key.strip())
    assert "push" in triggers, "on: must include push, got " + repr(triggers)
    assert "pull_request" in triggers, "on: must include pull_request, got " + repr(triggers)
    narrowed = ("branches" in triggers) or ("paths" in triggers)
    assert not narrowed, "on: must not narrow coverage with branches:/paths:, got " + repr(triggers)


def assert_gitleaks_config_unweakened(toml_text):
    has_usedefault = False
    for raw in _lines(toml_text):
        if _is_comment_or_blank(raw):
            continue
        s = _strip_inline(raw).strip()
        low = s.lower()
        norm = s.replace(" ", "")
        if norm == "useDefault=true":
            has_usedefault = True
        assert "allowlist" not in low, ".gitleaks.toml must not add an allowlist: " + repr(s)
        assert "stopwords" not in low, ".gitleaks.toml must not add stopwords: " + repr(s)
        assert ".*" not in norm, ".gitleaks.toml must not add a catch-all glob/regex: " + repr(s)
    assert has_usedefault, ".gitleaks.toml must retain [extend] useDefault = true"


# --- read the real files (read-only) via REPO_ROOT; fail-closed on I/O errors --


def _read(path):
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:  # fail closed as AssertionError (B011)
        assert False, "required file unreadable: " + str(path) + " (" + str(exc) + ")"


def _ci_text():
    return _read(_scan.REPO_ROOT / ".github" / "workflows" / "ci.yml")


def _gitleaks_text():
    return _read(_scan.REPO_ROOT / ".gitleaks.toml")


def _workflow_texts():
    wf_dir = _scan.REPO_ROOT / ".github" / "workflows"
    items = []
    for p in sorted(wf_dir.glob("*.yml")) + sorted(wf_dir.glob("*.yaml")):
        items.append((p.name, _read(p)))
    assert items, "no workflow files found under .github/workflows/"
    return items


# --- positive tests: every guarded invariant is TRUE on main today ------------


def test_secret_scan_job_exists() -> None:
    assert_secret_scan_job_present(_ci_text())


def test_secret_scan_read_only_permissions() -> None:
    assert_read_only_permissions(_ci_text())


def test_secret_scan_no_write_grant() -> None:
    assert_no_write_grant(_ci_text())


def test_gitleaks_step_present() -> None:
    assert_gitleaks_step_present(_ci_text())


def test_github_token_passthrough() -> None:
    assert_token_passthrough(_ci_text())


def test_fetch_depth_zero() -> None:
    assert_fetch_depth_zero(_ci_text())


def test_no_fail_open() -> None:
    assert_no_fail_open(_ci_text())


def test_no_pull_request_target() -> None:
    assert_no_pull_request_target(_workflow_texts())


def test_trigger_coverage() -> None:
    assert_trigger_coverage(_ci_text())


def test_gitleaks_config_unweakened() -> None:
    assert_gitleaks_config_unweakened(_gitleaks_text())


# --- ATR-R2 fail-closed meta-tests: mutate IN-MEMORY copies; never touch disk --


def _norm(text):
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _must_replace(text, old, new):
    assert old in text, "meta-test setup: expected substring not present: " + repr(old)
    return text.replace(old, new, 1)


def _expect_fail(fn, arg, label):
    try:
        fn(arg)
    except AssertionError:
        return
    assert False, "guard did not fail-closed for " + label


def test_meta_permissions_removed() -> None:  # MUT-1
    m = _must_replace(_norm(_ci_text()), "    permissions:\n      contents: read\n      pull-requests: read\n", "")
    _expect_fail(assert_read_only_permissions, m, "MUT-1 permissions block removed")


def test_meta_write_grant_added() -> None:  # MUT-2
    m = _must_replace(_norm(_ci_text()), "      contents: read", "      contents: write")
    _expect_fail(assert_no_write_grant, m, "MUT-2 contents: write added")


def test_meta_token_removed() -> None:  # MUT-3
    m = _must_replace(_norm(_ci_text()), "          " + TOKEN_PLACEHOLDER + "\n", "")
    _expect_fail(assert_token_passthrough, m, "MUT-3 GITHUB_TOKEN passthrough removed")


def test_meta_continue_on_error_added() -> None:  # MUT-4
    old = "        uses: " + GITLEAKS_REPO + "@v2\n"
    new = old + "        continue-on-error: true\n"
    m = _must_replace(_norm(_ci_text()), old, new)
    _expect_fail(assert_no_fail_open, m, "MUT-4 continue-on-error: true added to gitleaks step")


def test_meta_gitleaks_commented_out() -> None:  # MUT-5
    m = _must_replace(_norm(_ci_text()), "        uses: " + GITLEAKS_REPO + "@v2", "        # uses: " + GITLEAKS_REPO + "@v2")
    _expect_fail(assert_gitleaks_step_present, m, "MUT-5 gitleaks step commented out")


def test_meta_job_renamed() -> None:  # MUT-6
    m = _must_replace(_norm(_ci_text()), "  secret-scan:", "  secret-scon:")
    _expect_fail(assert_secret_scan_job_present, m, "MUT-6 secret-scan job renamed (fail-closed)")


def test_meta_fetch_depth_shallow() -> None:  # MUT-7
    m = _must_replace(_norm(_ci_text()), "          fetch-depth: 0", "          fetch-depth: 1")
    _expect_fail(assert_fetch_depth_zero, m, "MUT-7 fetch-depth made shallow")


def test_meta_pull_request_target_in_collection() -> None:  # MUT-8
    clean = _norm(_ci_text())
    mutated = _must_replace(clean, "  pull_request:", "  pull_request_target:")
    _expect_fail(
        assert_no_pull_request_target, [("ci.yml", clean), ("evil.yml", mutated)], "MUT-8 pull_request_target in a multi-file collection"
    )


def test_meta_empty_content() -> None:  # MUT-9
    _expect_fail(assert_secret_scan_job_present, "   \n\t\n   ", "MUT-9 empty/whitespace ci.yml (fail-closed)")


def test_meta_garbled_content() -> None:  # MUT-10
    _expect_fail(assert_secret_scan_job_present, "not yaml at all <<< %%% >>>", "MUT-10 unparseable ci.yml (fail-closed)")


def test_meta_gitleaks_usedefault_false() -> None:  # MUT-11
    m = _must_replace(_norm(_gitleaks_text()), "useDefault = true", "useDefault = false")
    _expect_fail(assert_gitleaks_config_unweakened, m, "MUT-11 .gitleaks.toml useDefault flipped to false")


def test_meta_gitleaks_broad_allowlist() -> None:  # MUT-12
    m = _norm(_gitleaks_text()) + "\n[allowlist]\npaths = ['.*']\n"
    _expect_fail(assert_gitleaks_config_unweakened, m, "MUT-12 .gitleaks.toml broad [allowlist] added")


def test_meta_decoy_comment_not_counted() -> None:  # MUT-13
    base = _must_replace(_norm(_ci_text()), "        uses: " + GITLEAKS_REPO + "@v2", "        uses: actions/checkout@v4")
    decoy = "  # uses: " + GITLEAKS_REPO + "@v2  (comment only -- NOT a real step)\n"
    _expect_fail(assert_gitleaks_step_present, decoy + base, "MUT-13 decoy comment must not count as the gitleaks step")


def test_meta_trigger_narrowed() -> None:  # MUT-14
    m = _must_replace(_norm(_ci_text()), "  pull_request:\n", "")
    _expect_fail(assert_trigger_coverage, m, "MUT-14 pull_request trigger removed")


def test_meta_pos_sha_forward_compat() -> None:  # POS-SHA
    sha = "a" * 40
    m = _must_replace(_norm(_ci_text()), GITLEAKS_REPO + "@v2", GITLEAKS_REPO + "@" + sha)
    # Forward-compat: after PRD-CI-HARDEN-01 pins the action to a SHA, the guard MUST
    # still locate the step and still pass the token check (ref-agnostic locator).
    assert_gitleaks_step_present(m)
    assert_token_passthrough(m)


if __name__ == "__main__":
    _scan.run(
        [
            test_secret_scan_job_exists,
            test_secret_scan_read_only_permissions,
            test_secret_scan_no_write_grant,
            test_gitleaks_step_present,
            test_github_token_passthrough,
            test_fetch_depth_zero,
            test_no_fail_open,
            test_no_pull_request_target,
            test_trigger_coverage,
            test_gitleaks_config_unweakened,
            test_meta_permissions_removed,
            test_meta_write_grant_added,
            test_meta_token_removed,
            test_meta_continue_on_error_added,
            test_meta_gitleaks_commented_out,
            test_meta_job_renamed,
            test_meta_fetch_depth_shallow,
            test_meta_pull_request_target_in_collection,
            test_meta_empty_content,
            test_meta_garbled_content,
            test_meta_gitleaks_usedefault_false,
            test_meta_gitleaks_broad_allowlist,
            test_meta_decoy_comment_not_counted,
            test_meta_trigger_narrowed,
            test_meta_pos_sha_forward_compat,
        ]
    )
