"""Regression guard for the secret-scan CI workflow configuration.

Asserts that ``.github/workflows/ci.yml`` (and ``.gitleaks.toml``) retain the
secret-scan protections. Implements PRD-CI-SECSCAN-REGRESSION-GUARD-01-R1 = addendum
ATR-R1 (the guard) + ATR-R2 (the fail-closed meta-test), plus the currently-true static
invariants ATR-S4/S5/S7/S8/S9.

ATR-S1/S2/S3 (validate-job + top-level least-privilege, and the gitleaks-action SHA-pin)
were deferred to PRD-CI-HARDEN-01 and are now ALSO asserted here, landed in the SAME PR
that hardened ci.yml (PRD-CI-HARDEN-01-R1):
  * ATR-S1 — validate job has a block-style permissions: { contents: read }, no write grant.
  * ATR-S2 — a top-level (indent 0) permissions: default with contents: read, no write grant.
  * ATR-S3 — the gitleaks action ref is EXACTLY 40 lowercase hex chars (a pinned commit SHA),
             not the moving @v2 tag, not short, not non-hex.

Design (per the R1 PRDs):
  * Pure stdlib, no dependency. The structural parse is indentation-aware and strips YAML
    comments, so comment prose that mentions gitleaks-action@v2 / pull-requests:read /
    pull_request (ci.yml comments) is never mistaken for structure.
  * Each check is a pure function over file CONTENT (a string) and fails closed via
    AssertionError -- the only exception ``_scan.run()`` catches. A missing / empty /
    unparseable file, or an unlocatable secret-scan job / gitleaks step, raises
    AssertionError rather than passing silently.
  * The gitleaks step is located by the org-qualified action repo
    ``gitleaks/gitleaks-action`` independent of the ``@ref``, so the SHA-pin does not break
    location; meta-tests anchor on the live uses-line (ref-agnostic), never on a literal @v2.
  * Every ``contents: read`` mutation anchors on a BLOCK-UNIQUE substring (the MUT-2
    discipline): after ATR-S1 there are three ``contents: read`` lines (top-level indent 2,
    validate indent 6, secret-scan indent 6) and ``_must_replace`` mutates only the first.
  * The negative meta-tests exercise the checks against IN-MEMORY mutated copies; the live
    ci.yml is NEVER edited. The new validate/top-level no-write checks use a NEW scoped helper
    (``_assert_no_write_in``); the secret-scan-bound ``assert_no_write_grant`` is unchanged.
  * The new S1/S2 checks adopt the block-style-only convention and fail closed on unrecognized
    encodings; tolerance of flow-style / anchors / quoted scalars is out of scope here and is
    owned by PRD-CI-SECSCAN-REGRESSION-GUARD-02.

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
HEXDIGITS = "0123456789abcdef"


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


def _parse_kv(child_strings):
    kv = {}
    for s in child_strings:
        if ":" in s:
            key, _, value = s.partition(":")
            kv[key.strip()] = value.strip()
    return kv


def _assert_no_write_in(child_strings):
    """Scoped no-write check over a list of stripped 'k: v' permission children.

    Distinct from assert_no_write_grant (which is BOUND to the secret-scan job); this is
    used for the validate-job and top-level permission blocks (ATR-S1 / ATR-S2).
    """
    for s in child_strings:
        assert "write-all" not in s, "permissions must not grant write-all: " + repr(s)
        if ":" in s:
            _, _, value = s.partition(":")
            assert value.strip() != "write", "permissions must not grant a write scope: " + repr(s)


def _top_level_permissions_children(ci_text):
    """Indent-2 children of a top-level (indent-0) ``permissions:`` stanza, or None.

    The job-relative _find_key(body, "permissions", 4) cannot see a top-level stanza, so
    this scans the raw lines for an indent-0 ``permissions:`` (mirroring the indent-0 ``on:``
    scan in assert_trigger_coverage) and returns its indent-2 children.
    """
    lines = _lines(ci_text)
    pi = None
    for i, raw in enumerate(lines):
        if _is_comment_or_blank(raw):
            continue
        s = _strip_inline(raw)
        if _indent(s) == 0 and s.strip() == "permissions:":
            pi = i
            break
    if pi is None:
        return None
    kids = []
    for raw in lines[pi + 1 :]:
        if _is_comment_or_blank(raw):
            continue
        s = _strip_inline(raw)
        if _indent(s) == 0:
            break
        kids.append(s.strip())
    return kids


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


def _gitleaks_uses_line(ci_text):
    """The active gitleaks ``uses:`` line (comment-stripped, indentation preserved).

    Located ref-agnostically (by org repo, not @ref); used as a stable mutation anchor that
    survives the SHA-pin instead of the literal '@v2'. Fail-closed if absent.
    """
    body = _job_block(ci_text, "secret-scan")
    chunk = _gitleaks_step(body)
    assert chunk is not None, "secret-scan job has no active " + GITLEAKS_REPO + " step"
    for raw in chunk:
        if _uses_repo(raw) == GITLEAKS_REPO:
            return _strip_inline(raw)
    assert False, "secret-scan job has no gitleaks uses: line"


def _gitleaks_ref(ci_text):
    """The ref token after '@' on the gitleaks ``uses:`` line (comment-stripped)."""
    value = _gitleaks_uses_line(ci_text).strip()
    if value.startswith("- "):
        value = value[2:].strip()
    value = value[len("uses:") :].strip()  # 'gitleaks/gitleaks-action@<ref>'
    parts = value.split("@", 1)
    assert len(parts) == 2, "gitleaks uses: has no @ref: " + repr(value)
    return parts[1].strip()


# --- guard checks: pure functions over file CONTENT, fail-closed via assert ----


def assert_secret_scan_job_present(ci_text):
    _job_block(ci_text, "secret-scan")


def assert_read_only_permissions(ci_text):
    body = _job_block(ci_text, "secret-scan")
    i = _find_key(body, "permissions", 4)
    assert i is not None, "secret-scan job has no permissions: block"
    kv = _parse_kv(_children(body, i, 4))
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


# --- new ATR-S1/S2/S3 checks (landed with PRD-CI-HARDEN-01-R1) -----------------


def assert_validate_least_privilege(ci_text):
    """ATR-S1: validate job has a block-style permissions: { contents: read }, no write."""
    body = _job_block(ci_text, "validate")  # job-isolated: never asserts against secret-scan
    i = _find_key(body, "permissions", 4)
    assert i is not None, "validate job has no permissions: block (ATR-S1)"
    kids = _children(body, i, 4)
    kv = _parse_kv(kids)
    assert kv.get("contents") == "read", "validate permissions.contents must be 'read' (ATR-S1)"
    _assert_no_write_in(kids)


def assert_top_level_permissions_default(ci_text):
    """ATR-S2: a top-level (indent 0) permissions default with contents: read, no write."""
    kids = _top_level_permissions_children(ci_text)
    assert kids is not None, "ci.yml has no top-level permissions: default (ATR-S2)"
    kv = _parse_kv(kids)
    assert kv.get("contents") == "read", "top-level permissions.contents must be 'read' (ATR-S2)"
    _assert_no_write_in(kids)


def assert_gitleaks_pinned_sha(ci_text):
    """ATR-S3: the gitleaks action ref is exactly 40 lowercase hex chars (a commit SHA)."""
    ref = _gitleaks_ref(ci_text)
    assert len(ref) == 40, "gitleaks ref must be a 40-char commit SHA (not @v2/short), got len " + str(len(ref)) + ": " + repr(ref)
    assert all(c in HEXDIGITS for c in ref), "gitleaks ref must be 40 LOWERCASE HEX chars, got: " + repr(ref)


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


def test_validate_least_privilege() -> None:  # ATR-S1 positive
    assert_validate_least_privilege(_ci_text())


def test_top_level_permissions_default() -> None:  # ATR-S2 positive
    assert_top_level_permissions_default(_ci_text())


def test_gitleaks_pinned_sha() -> None:  # ATR-S3 positive
    assert_gitleaks_pinned_sha(_ci_text())


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


def test_meta_permissions_removed() -> None:  # MUT-1 (secret-scan-unique 3-line anchor; verified still unique)
    m = _must_replace(_norm(_ci_text()), "    permissions:\n      contents: read\n      pull-requests: read\n", "")
    _expect_fail(assert_read_only_permissions, m, "MUT-1 permissions block removed")


def test_meta_write_grant_added() -> None:  # MUT-2 (re-anchored to the secret-scan-unique 2-line literal)
    m = _must_replace(
        _norm(_ci_text()),
        "      contents: read\n      pull-requests: read",
        "      contents: write\n      pull-requests: read",
    )
    _expect_fail(assert_no_write_grant, m, "MUT-2 contents: write added to secret-scan")


def test_meta_token_removed() -> None:  # MUT-3
    m = _must_replace(_norm(_ci_text()), "          " + TOKEN_PLACEHOLDER + "\n", "")
    _expect_fail(assert_token_passthrough, m, "MUT-3 GITHUB_TOKEN passthrough removed")


def test_meta_continue_on_error_added() -> None:  # MUT-4 (re-anchored off @v2 to the live uses-line)
    ci = _norm(_ci_text())
    old = _gitleaks_uses_line(ci) + "\n"
    new = old + "        continue-on-error: true\n"
    m = _must_replace(ci, old, new)
    _expect_fail(assert_no_fail_open, m, "MUT-4 continue-on-error: true added to gitleaks step")


def test_meta_gitleaks_commented_out() -> None:  # MUT-5 (re-anchored)
    ci = _norm(_ci_text())
    uses_line = _gitleaks_uses_line(ci)
    m = _must_replace(ci, uses_line, "        # " + uses_line.lstrip())
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


def test_meta_decoy_comment_not_counted() -> None:  # MUT-13 (re-anchored; decoy keeps @v2 as PROSE)
    ci = _norm(_ci_text())
    base = _must_replace(ci, _gitleaks_uses_line(ci), "        uses: actions/checkout@v4")
    decoy = "  # uses: " + GITLEAKS_REPO + "@v2  (comment only -- NOT a real step)\n"
    _expect_fail(assert_gitleaks_step_present, decoy + base, "MUT-13 decoy comment must not count as the gitleaks step")


def test_meta_trigger_narrowed() -> None:  # MUT-14
    m = _must_replace(_norm(_ci_text()), "  pull_request:\n", "")
    _expect_fail(assert_trigger_coverage, m, "MUT-14 pull_request trigger removed")


def test_meta_pos_sha_forward_compat() -> None:  # POS-SHA (re-anchored: live + synthetic, ref-agnostic)
    # (a) LIVE: the ref-agnostic locator + token check pass on the real SHA-pinned ci.yml.
    assert_gitleaks_step_present(_ci_text())
    assert_token_passthrough(_ci_text())
    # (b) SYNTHETIC forward-compat: a 40-hex value DECOUPLED from the live pin, in the trailing
    #     inline-comment form, exercising _strip_inline. Proves ref-agnosticism (not a duplicate
    #     of the two live positives above).
    ci = _norm(_ci_text())
    synth = "b" * 40
    m = _must_replace(ci, _gitleaks_uses_line(ci), "        uses: " + GITLEAKS_REPO + "@" + synth + "  # v9.9.9")
    assert_gitleaks_step_present(m)
    assert_token_passthrough(m)


def test_meta_s1_validate_perms_removed() -> None:  # ATR-S1 negative (block-unique validate anchor)
    m = _must_replace(
        _norm(_ci_text()),
        "  validate:\n    runs-on: ubuntu-latest\n    permissions:\n      contents: read\n",
        "  validate:\n    runs-on: ubuntu-latest\n",
    )
    _expect_fail(assert_validate_least_privilege, m, "ATR-S1 validate permissions block removed")


def test_meta_s1_validate_write_grant() -> None:  # ATR-S1 negative (block-unique validate anchor)
    m = _must_replace(
        _norm(_ci_text()),
        "  validate:\n    runs-on: ubuntu-latest\n    permissions:\n      contents: read",
        "  validate:\n    runs-on: ubuntu-latest\n    permissions:\n      contents: write",
    )
    _expect_fail(assert_validate_least_privilege, m, "ATR-S1 validate contents: write grant")


def test_meta_s2_top_level_removed() -> None:  # ATR-S2 negative (indent-0 block-unique anchor)
    m = _must_replace(_norm(_ci_text()), "permissions:\n  contents: read\n\njobs:", "jobs:")
    _expect_fail(assert_top_level_permissions_default, m, "ATR-S2 top-level permissions default removed")


def test_meta_s2_top_level_write_grant() -> None:  # ATR-S2 negative (indent-0 block-unique anchor)
    m = _must_replace(_norm(_ci_text()), "permissions:\n  contents: read", "permissions:\n  contents: write")
    _expect_fail(assert_top_level_permissions_default, m, "ATR-S2 top-level contents: write grant")


def test_meta_s3_reverted_to_v2() -> None:  # ATR-S3 negative
    ci = _norm(_ci_text())
    m = _must_replace(ci, _gitleaks_uses_line(ci), "        uses: " + GITLEAKS_REPO + "@v2")
    _expect_fail(assert_gitleaks_pinned_sha, m, "ATR-S3 gitleaks reverted to @v2")


def test_meta_s3_short_sha() -> None:  # ATR-S3 negative
    ci = _norm(_ci_text())
    m = _must_replace(ci, _gitleaks_uses_line(ci), "        uses: " + GITLEAKS_REPO + "@ff98106")
    _expect_fail(assert_gitleaks_pinned_sha, m, "ATR-S3 gitleaks short SHA")


def test_meta_s3_non_hex() -> None:  # ATR-S3 negative (concretely non-hex 40-char string)
    ci = _norm(_ci_text())
    m = _must_replace(ci, _gitleaks_uses_line(ci), "        uses: " + GITLEAKS_REPO + "@" + ("g" * 40))
    _expect_fail(assert_gitleaks_pinned_sha, m, "ATR-S3 gitleaks non-hex 40-char ref")


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
            test_validate_least_privilege,
            test_top_level_permissions_default,
            test_gitleaks_pinned_sha,
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
            test_meta_s1_validate_perms_removed,
            test_meta_s1_validate_write_grant,
            test_meta_s2_top_level_removed,
            test_meta_s2_top_level_write_grant,
            test_meta_s3_reverted_to_v2,
            test_meta_s3_short_sha,
            test_meta_s3_non_hex,
        ]
    )
