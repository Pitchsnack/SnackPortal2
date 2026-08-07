"""AW-1 — static boundary + BYTE-PIN guard for the least-privilege Gateway-audit writer tooling.

The AW-1 M2 role/grant payload is byte-frozen by the accepted specification, **including its
comments**. This guard is what makes that freeze real in the repository: it pins the embedded block
by SHA-256 and anchors every statement individually, so a governed amendment must move the pin in
lockstep and an ungoverned edit fails the default suite.

**Why the payload is embedded rather than shipped as `infrastructure/db/**/*.sql`.** Two guards would
break if it were a file:

* `test_b5_standing_topology_boundaries.py` asserts a **closed 15-file** on-disk Control-DDL
  inventory — a sixteenth file turns it red;
* the PMA-AR-2 role-security meta-guard (`test_role_security_coverage_meta_guard.py`) globs
  `infrastructure/db/**/*.sql` for role-defining statements and would force a
  `ROLE_SECURITY_COVERAGE` family registration. That registry's INV-A is **structurally bound to
  on-disk SQL**, so a family whose `ddl_path` does not exist FAILS INV-A.

So this file is the meta-guard's *intent* satisfied by other means, and it is deliberately **NOT**
registered in `ROLE_SECURITY_COVERAGE`. Adding it there would be the failure the comment above
describes. The blob-pin idiom is taken from `test_gateway_operational_audit_boundaries.py`.

What is pinned, and why each pin exists:

* **The frozen payload**, by hash and by per-statement anchor. A silent widening — an extra `GRANT`,
  a dropped `REVOKE`, `WITH ADMIN OPTION` on the membership grant — is exactly what a byte pin
  catches and a prose review does not.
* **The database identity assertion happens BEFORE the first statement.** The payload mixes
  cluster-wide statements with database-local ones; run from the maintenance database it strands the
  schema grant somewhere no probe looks.
* **`plan` is read-only** — no bind, no material write, no payload execution. `plan` runs *before*
  Gate B, so a `plan` that could mutate would be a gate bypass.
* **`apply` refuses without its explicit confirmation flag.** Under Gate A this tooling is built and
  not run; nothing may make running it the default.
* **The evidence label `M2 INITIAL CREATION` exists.** On the first-ever apply every branch-2
  conjunct holds, so a three-branch implementation records initial credential creation as recovery
  from a crash that never occurred.
* **No credential material is emitted.** No print of a password, no hash of the secret, no
  credential-bearing DSN literal.
* **The credential material IS persisted, and in the governed order.** §5.5 requires the mutating
  branches to mint, bind, **write the material**, then **re-probe** — and nothing but the applying
  process can do the writing, because the password exists nowhere else. Dropping the last two steps
  is not a partial implementation but an unrecoverable one, and it is invisible until *after* the
  cluster has been mutated. The write is confined to one function, aimed at the §7 file form composed
  exactly as `EnvReferenceSecretStore` composes it, and refused if the sink would land inside a
  repository worktree or be shadowed by the env form.

Pure stdlib; runnable standalone:
    python tests/architecture/test_aw1_gateway_audit_writer_boundaries.py
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import os
import pathlib
import re
import sys
import tempfile
from types import ModuleType
from typing import List
from urllib.parse import urlsplit

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

_TOOL_RELPATH = "tests/control_plane/requires_pg/aw1_gateway_audit_writer.py"
_TOOL = _scan.BACKEND_ROOT / "tests" / "control_plane" / "requires_pg" / "aw1_gateway_audit_writer.py"
_HARNESS = _scan.BACKEND_ROOT / "tests" / "control_plane" / "requires_pg" / "test_pg_aw1_gateway_audit_writer_rehearsal.py"
_COMPLETENESS_GUARD = _scan.BACKEND_ROOT / "tests" / "architecture" / "test_live_pg_workflow_runset_completeness.py"
_COVERAGE_META_GUARD = _scan.BACKEND_ROOT / "tests" / "architecture" / "test_role_security_coverage_meta_guard.py"
_RUNBOOK = _scan.REPO_ROOT / "infrastructure" / "runbooks" / "aw1_gateway_audit_writer.md"

# The LF-normalized SHA-256 of the byte-frozen AW-1 §5.4 payload embedded in the operator tool.
# A governed AW-1 amendment must re-stamp this in the SAME commit as the payload edit.
_FROZEN_PAYLOAD_SHA256 = "05f265c4044ca6414fd27aa9d228bcabe3f2f03c49e777c2e5177ea5c363e4a4"

# Every statement of the frozen block, anchored individually. The hash catches ANY change; these
# catch the specific changes whose absence would be a privilege escalation, and they say so.
_REQUIRED_STATEMENTS = (
    "CREATE ROLE sp2_gateway_audit_writer NOLOGIN;",
    "CREATE ROLE sp2_gateway_audit_ingest LOGIN;",
    "ALTER ROLE sp2_gateway_audit_writer\n    NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;",
    "ALTER ROLE sp2_gateway_audit_ingest\n    NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS INHERIT;",
    "GRANT CONNECT ON DATABASE snackportal2_control_local TO sp2_gateway_audit_writer;",
    "GRANT USAGE  ON SCHEMA  public                       TO sp2_gateway_audit_writer;",
    "GRANT SELECT, INSERT ON public.control_gateway_audit TO sp2_gateway_audit_writer;",
    "REVOKE UPDATE, DELETE, TRUNCATE ON public.control_gateway_audit FROM sp2_gateway_audit_writer;",
    "GRANT sp2_gateway_audit_writer TO sp2_gateway_audit_ingest;",
    "COMMENT ON ROLE sp2_gateway_audit_writer IS",
    "COMMENT ON ROLE sp2_gateway_audit_ingest IS",
)

# Escalation routes the EXECUTABLE payload must never contain. Checked against the comment-stripped
# text: the frozen block's own comments legitimately discuss the separate `ALTER ROLE ... PASSWORD`
# bind, and a naive substring scan over the raw text would flag that explanation as the thing it
# explains.
_FORBIDDEN_IN_EXECUTABLE_PAYLOAD = (
    "WITH ADMIN OPTION",
    "WITH GRANT OPTION",
    "ALL PRIVILEGES",
    "GRANT ALL",
    "ON ALL TABLES",
    "GRANT SET ON PARAMETER",
    "PASSWORD",  # the bind is a SEPARATE client-side-bound statement, never part of the frozen block
)

# Role attributes that must appear ONLY in their negated form. `NOSUPERUSER` contains `SUPERUSER`,
# so the check is per-token, not per-substring.
_NEGATED_ONLY_ATTRIBUTES = ("SUPERUSER", "CREATEDB", "CREATEROLE", "REPLICATION", "BYPASSRLS")


def _tool_text() -> str:
    return _TOOL.read_text(encoding="utf-8")


def _tool_tree() -> ast.Module:
    return ast.parse(_tool_text(), filename=str(_TOOL))


def _module_constant(name: str) -> str:
    for node in ast.walk(_tool_tree()):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name and isinstance(node.value, ast.Constant):
                    return str(node.value.value)
    raise AssertionError(f"{_TOOL.name} must define the module constant {name}")


def _func(name: str) -> ast.FunctionDef:
    for node in ast.walk(_tool_tree()):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{_TOOL.name} must define {name}()")


def _load_tool() -> ModuleType:
    """Load the operator tool by path and execute it.

    Safe under Gate A and in CI: import performs no I/O — argparse, every `connect()` and every
    filesystem touch live inside a command function. Loading it is what lets this guard EXECUTE the
    DSN composer instead of pattern-matching its source.
    """
    spec = importlib.util.spec_from_file_location("_aw1_operator_tool_under_guard", _TOOL)
    assert spec is not None and spec.loader is not None, "the operator tool must be loadable by path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_operator_tool_and_its_companions_exist() -> None:
    assert _TOOL.is_file(), f"the AW-1 operator tool must exist at {_TOOL_RELPATH}"
    assert _HARNESS.is_file(), "the AW-1 Tier-A disposable privilege rehearsal must exist"
    assert _RUNBOOK.is_file(), "the AW-1 environment-contract runbook must exist"


def test_frozen_payload_matches_its_byte_pin() -> None:
    payload = _module_constant("FROZEN_ROLE_GRANT_SQL")
    digest = hashlib.sha256(payload.replace("\r\n", "\n").encode("utf-8")).hexdigest()
    assert digest == _FROZEN_PAYLOAD_SHA256, (
        f"the frozen AW-1 §5.4 payload drifted from its pin.\n  pinned:   {_FROZEN_PAYLOAD_SHA256}\n"
        f"  computed: {digest}\nThe block is byte-frozen by the accepted specification INCLUDING ITS COMMENTS. "
        "A governed amendment must re-stamp this guard in the same commit; an ungoverned edit must fail here."
    )


def test_frozen_payload_contains_every_pinned_statement() -> None:
    payload = _module_constant("FROZEN_ROLE_GRANT_SQL")
    for statement in _REQUIRED_STATEMENTS:
        assert statement in payload, f"the frozen payload must contain, verbatim: {statement!r}"
    # The membership grant must be PLAIN. `GRANT ... WITH ADMIN OPTION` would let the ingest identity
    # hand the writer role to anything else.
    assert "GRANT sp2_gateway_audit_writer TO sp2_gateway_audit_ingest;" in payload


def _executable_payload() -> str:
    """The payload with its `--` comment lines removed (no `--` appears inside a string literal here)."""
    payload = _module_constant("FROZEN_ROLE_GRANT_SQL")
    return "\n".join(line for line in payload.splitlines() if not line.lstrip().startswith("--"))


def test_frozen_payload_grants_nothing_beyond_the_least_privilege_surface() -> None:
    executable = _executable_payload()
    for forbidden in _FORBIDDEN_IN_EXECUTABLE_PAYLOAD:
        assert forbidden not in executable, (
            f"the executable frozen payload must never contain {forbidden!r}. The credential bind in particular is a "
            "SEPARATE client-side-bound statement — a PASSWORD inside the frozen block would put a credential into a "
            "repository file."
        )
    # Attribute tokens may appear only negated. Tokenize so NOSUPERUSER is not read as SUPERUSER.
    tokens = set(re.findall(r"[A-Z][A-Z_]+", executable))
    for attribute in _NEGATED_ONLY_ATTRIBUTES:
        assert attribute not in tokens, f"the payload must never grant {attribute} — only NO{attribute} may appear"
        assert f"NO{attribute}" in tokens, f"the payload must pin NO{attribute} explicitly on the writer role"
    # The writer's table surface is exactly one table, and exactly two verbs on it.
    assert executable.count("GRANT SELECT, INSERT ON") == 1, "the writer's table grant must be a single statement"
    assert "control_gateway_audit" in executable
    for other in ("control_memberships", "control_tenants", "control_audit ", "control_federation", "control_directory"):
        assert other not in executable, f"the payload must not reference {other!r} — the writer reads exactly one table"


def test_apply_asserts_the_database_pin_before_the_first_statement() -> None:
    source = ast.get_source_segment(_tool_text(), _func("cmd_apply")) or ""
    pin_at = source.find("CONTROL_DATABASE")
    exec_at = source.find("FROZEN_ROLE_GRANT_SQL")
    assert pin_at != -1, "apply must assert the pinned control database"
    assert exec_at != -1, "apply must execute the frozen payload"
    assert pin_at < exec_at, (
        "apply must assert current_database() == the pin BEFORE executing the first statement. The payload mixes "
        "cluster-wide statements with database-local ones: run from the maintenance database it strands "
        "GRANT USAGE ON SCHEMA public where no later probe looks, and the table grants fail outright."
    )


def test_plan_is_read_only() -> None:
    """Asserted against the AST, not the prose.

    `plan` legitimately *explains* in its output why a CONFLICTING classification blocks Gate B —
    including a sentence naming the payload's unconditional `ALTER ROLE`s. A raw substring scan would
    flag that explanation as the thing it explains, so the check reads identifiers actually used.
    """
    node = _func("cmd_plan")
    source = ast.get_source_segment(_tool_text(), node) or ""
    assert "read_only = True" in source, "plan must set the connection read-only"
    used = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
    used |= {n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)}
    for mutating in ("FROZEN_ROLE_GRANT_SQL", "_mint_password", "_converge_credential", "_probe_authenticates", "commit", "execute"):
        assert mutating not in used, (
            f"plan must not use {mutating} — plan runs BEFORE Gate B, so a plan that can bind, mint, execute the "
            "payload or commit is a gate bypass, not a convenience"
        )
    # No literal DDL/DCL may be executed from plan either.
    for const in (n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)):
        upper = const.upper()
        assert not (upper.lstrip().startswith(("ALTER ROLE", "CREATE ROLE", "GRANT ", "REVOKE "))), (
            f"plan must not carry an executable DDL/DCL statement literal: {const!r}"
        )


def test_apply_refuses_without_an_explicit_gate_b_confirmation() -> None:
    source = ast.get_source_segment(_tool_text(), _func("cmd_apply")) or ""
    assert "confirm_gate_b_m2" in source, "apply must require an explicit Gate-B confirmation flag"
    guard_at = source.find("confirm_gate_b_m2")
    exec_at = source.find("FROZEN_ROLE_GRANT_SQL")
    assert guard_at < exec_at, "the confirmation check must precede any execution"
    text = _tool_text()
    assert "--confirm-gate-b-m2" in text, "the confirmation must be an explicit CLI flag, not an env var"
    assert 'action="store_true"' in text, "the confirmation flag must default to OFF"


def test_initial_creation_is_distinguished_from_recovery() -> None:
    text = _tool_text()
    assert '"M2 INITIAL CREATION"' in text, (
        "the first-ever credential creation must be recorded as `M2 INITIAL CREATION`. On the first apply every "
        "branch-2 conjunct holds — material absent, role/grant state converged by the payload that just ran, bind "
        "not done — so a three-branch implementation labels initial creation as recovery from a crash that never "
        "occurred, and the evidence pack inherits that falsehood."
    )
    assert '"M2 RECOVERY"' in text, "the bounded recovery branch must still be labelled distinctly"
    source = ast.get_source_segment(text, _func("_converge_credential")) or ""
    assert "roles_were_absent" in source, "the two labels must be discriminated by observed pre-apply state, not by a guess"
    # Branch 1 must SKIP the bind: re-binding an identical password re-salts the SCRAM verifier and
    # mutates pg_authid.rolpassword — a delta, and a de-facto rotation.
    assert "NO_CHANGES" in source and "SKIPPED" in source, "the converged branch must skip both the bind and the material rewrite"


def test_logging_observation_precedes_every_bind() -> None:
    source = ast.get_source_segment(_tool_text(), _func("_converge_credential")) or ""
    observe_at = source.find("logging_observation_problems")
    bind_at = source.find("ALTER ROLE {} PASSWORD")
    assert observe_at != -1, "the §5.6 statement-logging observation must run inside the convergence path"
    assert bind_at != -1, "the bind must be client-side bound via psycopg.sql"
    assert observe_at < bind_at, (
        "the statement-logging observation must happen BEFORE the bind. PostgreSQL performs no password redaction: "
        "log_statement in {ddl,mod,all} writes the full ALTER ROLE ... PASSWORD text to the server log."
    )
    assert "sql.Literal" in source, "the password must be client-side bound (ALTER ROLE accepts no server-side parameters)"


def test_no_credential_material_is_emitted() -> None:
    """No credential VALUE may be printed, hashed, or carried as a literal.

    The tool DOES persist the minted material — §5.5 requires it, and nothing else can (the password
    exists only inside the applying process). What it must never do is emit the value: a
    credential-bearing DSN literal in this file, a `print` of the password, or a hash of the secret.
    """
    text = _tool_text()
    assert not re.search(r"postgres(?:ql)?://[^\s\"']*:[^\s\"']*@", text), "a credential-bearing DSN literal must never appear in this file"
    for leak in ("PGPASSWORD", "-----BEGIN", "eyJ"):
        assert leak not in text, f"the operator tool must carry no credential material ({leak})"
    # Read against the AST, not the prose: `_resolve_writer_material`'s docstring legitimately
    # *explains* that `EnvReferenceSecretStore` indexes `os.environ`, and a substring scan would
    # flag that explanation as the thing it explains.
    for node in ast.walk(_tool_tree()):
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute) and node.value.attr == "environ":
            raise AssertionError(
                "the tool must not index os.environ — it must not persist or mutate any environment variable, and "
                "presence is resolved through `.get()` exactly as the runtime resolver's membership test behaves"
            )
    source = ast.get_source_segment(text, _func("_writer_material")) or ""
    assert "never printed" in source or "Never printed" in source, "the material accessor must state the hygiene rule"

    # No secret-valued name may reach a print(). `password` and `writer_dsn` are the minted secret
    # and the composed material; `dsn` (the EXECUTOR connection string) may be printed only through
    # `redacted()`.
    for call in (n for n in ast.walk(_tool_tree()) if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "print"):
        names = {n.id for n in ast.walk(call) if isinstance(n, ast.Name)}
        for secret_name in ("password", "writer_dsn", "reprobed"):
            assert secret_name not in names, f"`{secret_name}` reaches a print() call — it is a credential value"
        redacted_names = {
            n.id
            for sub in ast.walk(call)
            if isinstance(sub, ast.Call) and getattr(sub.func, "id", "") == "redacted"
            for n in ast.walk(sub)
            if isinstance(n, ast.Name)
        }
        assert "dsn" not in names or "dsn" in redacted_names, "the executor DSN may be printed only through redacted()"


def test_the_material_write_is_confined_to_one_governed_sink() -> None:
    """Persistence is required, but it is a single, named, repository-external act.

    `_write_material` is the ONLY function permitted to touch the filesystem with the credential, its
    destination comes from `_material_file_path()` (composed exactly as `EnvReferenceSecretStore`
    composes it), and the sink is proven to resolve OUTSIDE the repository before anything is
    written. `plan` may not reference any of it.
    """
    tree = _tool_tree()
    write_primitives = ("write_text", "os.replace", "open(")
    writers = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        source = ast.get_source_segment(_tool_text(), node) or ""
        if any(primitive in source for primitive in write_primitives):
            writers.add(node.name)
    assert writers == {"_write_material", "material_sink_problems"}, (
        f"filesystem writes must be confined to `_write_material` (the credential) and `material_sink_problems` "
        f"(a probe file that carries no credential). Found: {sorted(writers)}"
    )
    write_source = ast.get_source_segment(_tool_text(), _func("_write_material")) or ""
    assert "os.replace" in write_source, "the material write must be atomic — a truncated DSN resolves to something else"
    assert "0o600" in write_source, "the material file must be created with restrictive permissions where honoured"

    path_source = ast.get_source_segment(_tool_text(), _func("_material_file_path")) or ""
    assert "SECRET_DIR_ENV" in path_source and "WRITER_SECRET_REF" in path_source and "WRITER_MATERIAL_VERSION" in path_source, (
        "the sink path must be composed exactly as EnvReferenceSecretStore.resolve composes it, or the tool writes "
        "somewhere the runtime never reads"
    )
    blockers = ast.get_source_segment(_tool_text(), _func("material_sink_blockers")) or ""
    assert "repo_root" in blockers and "parents" in blockers, (
        "the sink must be proven OUTSIDE the repository worktree: an operator-local credential written inside a "
        "repository is one `git add -A` from a committed secret"
    )
    plan_source = ast.get_source_segment(_tool_text(), _func("cmd_plan")) or ""
    for forbidden in ("_write_material", "material_sink_problems", "compose_writer_dsn"):
        assert forbidden not in plan_source, f"plan must not reference {forbidden} — plan runs BEFORE Gate B"


def test_a_mutating_branch_persists_and_reprobes_in_the_governed_order() -> None:
    """The exact defect this guard exists to catch.

    A mint + bind with no material write and no re-probe leaves `sp2_gateway_audit_ingest` holding a
    password that existed only in a process that has exited. The operator is told to write a DSN they
    cannot construct; branch 1 becomes permanently unreachable, so every later `apply` mints another
    unknowable password; `status` can never go green; and the launcher's §9 O-6 start gate can
    therefore never open. Escaping needs a superuser `ALTER ROLE` outside AW-1's procedure — the
    class of act AW-1 exists to eliminate. The defect is invisible until AFTER the cluster is mutated.
    """
    source = ast.get_source_segment(_tool_text(), _func("_converge_credential")) or ""
    sink_at = source.find("material_sink_problems()")
    mint_at = source.find("_mint_password()")
    bind_at = source.find("ALTER ROLE {} PASSWORD")
    write_at = source.find("_write_material(")
    reprobe_at = source.rfind("_probe_authenticates(")
    for label, index in (
        ("the sink pre-check", sink_at),
        ("the mint", mint_at),
        ("the bind", bind_at),
        ("the material write", write_at),
        ("the re-probe", reprobe_at),
    ):
        assert index != -1, f"the mutating branch must perform {label}"
    assert sink_at < mint_at, (
        "the sink must be proven writable BEFORE the password is minted. A password minted and bound with nowhere to "
        "go is unrecoverable inside AW-1's own rules."
    )
    assert mint_at < bind_at < write_at < reprobe_at, (
        "§5.5's four steps must run in the governed order: mint -> bind -> write the material -> re-probe. Found "
        f"mint@{mint_at} bind@{bind_at} write@{write_at} re-probe@{reprobe_at}."
    )
    # The re-probe must read the PERSISTED material back through the runtime's own resolution path,
    # not re-use the in-memory string — otherwise it proves the string, not the persistence.
    tail = source[write_at:]
    assert "_resolve_writer_material()" in tail, (
        "the re-probe must RE-RESOLVE the material through the same mechanism the runtime uses, so what is proven is "
        "that the persisted material authenticates"
    )
    assert "RE-PROBE" in tail and "return CONFLICTING" in tail, "a failed re-probe must be fail-closed, not a warning"
    # And a mutating branch may never report success without having reached the re-probe.
    label_return = source.rfind("return label")
    assert label_return > reprobe_at, (
        "`M2 INITIAL CREATION` / `M2 RECOVERY` may only be returned AFTER a successful re-probe — reporting success "
        "without it is reporting a credential nobody has proven usable"
    )


def test_the_material_sink_refuses_a_repository_location_and_a_shadowing_env_form() -> None:
    """EXECUTED, not read. The two refusals that keep the persisted credential reachable and untracked.

    A textual check for the repo-containment logic passes as soon as the identifiers survive, which is
    exactly how a neutered `if` slips through. This calls the function.
    """
    tool = _load_tool()
    saved = {name: os.environ.get(name) for name in (tool.SECRET_DIR_ENV, tool.WRITER_MATERIAL_ENV)}
    try:
        os.environ.pop(tool.WRITER_MATERIAL_ENV, None)

        os.environ.pop(tool.SECRET_DIR_ENV, None)
        undeclared = tool.material_sink_blockers()
        assert any(tool.SECRET_DIR_ENV in blocker for blocker in undeclared), (
            "with no sink directory declared, `apply` must refuse rather than mint a password it cannot persist"
        )

        # Probe with a path inside the repository root the TOOL derives for itself, so the check
        # exercises the tool's own containment logic rather than this guard's copy of it.
        os.environ[tool.SECRET_DIR_ENV] = str(_TOOL.resolve().parents[4] / "backend" / "tests")
        inside = tool.material_sink_blockers()
        assert any("INSIDE the repository" in blocker for blocker in inside), (
            "a sink resolving inside the repository worktree must be refused: an operator-local credential written "
            f"into a repository is one `git add -A` from a committed secret. Got: {inside}"
        )

        outside = pathlib.Path(tempfile.gettempdir()) / "sp2-aw1-sink-shape-probe"
        os.environ[tool.SECRET_DIR_ENV] = str(outside)
        assert tool.material_sink_blockers() == [], (
            f"a declared sink outside every repository must be accepted, got {tool.material_sink_blockers()}"
        )
        assert not outside.exists(), "material_sink_blockers() must create nothing — it is safe for read-only `plan`"

        # A set-but-BLANK env form still shadows the file form in EnvReferenceSecretStore.resolve.
        os.environ[tool.WRITER_MATERIAL_ENV] = "   "
        shadowed = tool.material_sink_blockers()
        assert any(tool.WRITER_MATERIAL_ENV in blocker for blocker in shadowed), (
            "a mutating branch must refuse while the material is held in the env form — a child process cannot "
            "replace its parent shell's variable in place, and the env form shadows the file the tool would write"
        )
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def test_the_material_resolution_mirrors_the_runtime_resolver() -> None:
    """A set-but-EMPTY env var shadows the file form in `EnvReferenceSecretStore.resolve`.

    The resolver returns `os.environ[key]` on MEMBERSHIP, so a blank variable is not "absent" — it is
    an active, empty answer that hides whatever this tool writes to the file form. Collapsing the two
    states would let a successful apply write a file the runtime can never see.
    """
    source = ast.get_source_segment(_tool_text(), _func("_resolve_writer_material")) or ""
    assert "MATERIAL_FORM_ENV" in source and "MATERIAL_FORM_FILE" in source, "resolution must report WHICH form answered"
    assert "raw is not None" in source, (
        "the env form must win by MEMBERSHIP (`os.environ.get(...) is not None`), exactly as the resolver does — not "
        "by truthiness, which would treat a shadowing blank variable as absent"
    )
    blockers = ast.get_source_segment(_tool_text(), _func("material_sink_blockers")) or ""
    assert "MATERIAL_FORM_ENV" in blockers, (
        "a mutating branch must REFUSE when the material is held in the env form: a child process cannot replace its "
        "parent shell's variable in place, and the env form shadows the file the tool would write"
    )
    # The resolver contract this mirrors must still say what the guard assumes it says.
    resolver = (_scan.BACKEND_ROOT / "shared" / "adapters" / "providers" / "env_reference_secret_store.py").read_text(encoding="utf-8")
    assert "if key in os.environ:" in resolver, (
        "EnvReferenceSecretStore resolves the env var by MEMBERSHIP; if that changed, this tool's mirror must change in the same commit"
    )
    assert 'f"{ref.store_ref}@{ref.version}"' in resolver, "the file form path shape must still be <store_ref>@<version>"


def test_the_composed_material_satisfies_the_pinned_dsn_shape() -> None:
    """Executed, not read: compose a synthetic material and run it through the tool's own shape check."""
    tool = _load_tool()
    composed = tool.compose_writer_dsn("postgresql://sp2_local@127.0.0.1:5540/snackportal2_control_local", "A" * 48)
    assert tool.dsn_shape_problems(composed) == [], (
        f"the composed writer material must satisfy the tool's own §5.6/R-9 shape rules, got: {tool.dsn_shape_problems(composed)}"
    )
    parts = urlsplit(composed)
    assert parts.username == tool.INGEST_ROLE, "the material must authenticate as the ingest role"
    assert (parts.path or "").lstrip("/") == tool.CONTROL_DATABASE, "the material must target the pinned control database"
    assert parts.hostname == "127.0.0.1" and parts.port == 5540, "host and port must come from the executor connection"
    assert "options" not in (parts.query or ""), "the material must carry no libpq options keyword"
    # Every character the generator can emit must survive DSN composition unencoded.
    everything = tool.compose_writer_dsn("postgresql://sp2_local@127.0.0.1:5540/x", tool._PASSWORD_ALPHABET)
    assert urlsplit(everything).password == tool._PASSWORD_ALPHABET, (
        "the full password alphabet must round-trip through the composed DSN without percent-encoding"
    )


def test_password_alphabet_cannot_break_dsn_composition() -> None:
    alphabet = _module_constant("_PASSWORD_ALPHABET")
    for reserved in ":/?#[]@!$&'()*+,;=%\" ":
        assert reserved not in alphabet, (
            f"the generated password alphabet must exclude the URI-reserved character {reserved!r}. Such a character "
            "binds successfully and then fails to compose a parseable DSN — landing in the conflicting branch with "
            "the credential already changed and no material bound, the one unrecoverable ordering in the arc."
        )
    assert len(set(alphabet)) == len(alphabet), "the alphabet must carry no duplicate characters"


def test_dsn_shape_check_pins_application_name_and_bans_options() -> None:
    source = ast.get_source_segment(_tool_text(), _func("dsn_shape_problems")) or ""
    assert '"options"' in source, (
        "the DSN-shape check must ban the libpq `options` keyword. Both adapter statements use the BARE table name, "
        "so resolution to `public` rests on the default search_path — and `options=-c search_path=...` is a "
        "documented, test-exercised mechanism for this DSN class."
    )
    assert "application_name" in source, "the DSN-shape check must require the pinned application_name"
    assert _module_constant("INGEST_APPLICATION_NAME") == "sp2-gateway-audit-ingest"


def test_status_declares_a_fixed_pass_count() -> None:
    text = _tool_text()
    assert "STATUS_DECLARED_CHECKS" in text, "status must declare its pass count (V-13)"
    source = ast.get_source_segment(text, _func("cmd_status")) or ""
    assert "len(checks) == STATUS_DECLARED_CHECKS" in source, (
        "the declared and executed check counts must be asserted equal, or a silently-skipped check reads as success"
    )
    assert "STATUS OK" in source and "return 1" in source, "status must be fail-closed"


def test_tool_is_glob_invisible_to_the_harness_census() -> None:
    # The completeness meta-guard discovers `*/requires_pg/test_*.py`. The operator MODULE must not
    # match (six such non-`test_`-prefixed operator modules already live there); the thin wrapper
    # harness must, and must therefore carry its MANUAL_ONLY exception key.
    assert not _TOOL.name.startswith("test_"), "the operator module must stay outside the test_*.py harness census"
    assert _HARNESS.name.startswith("test_"), "the Tier-A rehearsal wrapper must be discoverable as a harness"
    guard = _COMPLETENESS_GUARD.read_text(encoding="utf-8")
    key = f"tests/control_plane/requires_pg/{_HARNESS.name}"
    assert key in guard, (
        f"{_HARNESS.name} must be registered in MANUAL_ONLY_EXCEPTIONS in the SAME commit as the harness file. "
        "INV-A fails without the key and INV-C fails without the file — the two land together or the default suite "
        "goes red either way."
    )


def test_the_hosted_loop_lockstep_is_deliberately_untouched() -> None:
    """V2-C1: the Tier-A harness is MANUAL_ONLY and NON-loop-enrolled. Nothing in the lockstep moves.

    The instruction AW-1 V2 carried — "+ F22 lockstep updates (EXPECTED_HARNESS_COUNT, b7c2 doc)" —
    is wrong for a harness that is deliberately not enrolled, and following it is actively harmful:
    all four EXPECTED_HARNESS_COUNT sites parse the WORKFLOW LOOP TEXT and compare `len(entries)`,
    so bumping 14→15 while the loop stays 14 turns five assertions red, takes the default suite down,
    and blocks the "default suite green" Gate-B precondition.
    """
    sites = {
        "test_dbr_ar_2d_live_proof_boundaries.py": 14,
        "test_dbr_ar_2d_standing_witness_boundaries.py": 14,
        "test_dbr_ar_2e_activation_evidence_boundaries.py": 14,
        "test_live_pg_docs_workflow_consistency.py": 14,
    }
    for name, expected in sites.items():
        path = _scan.BACKEND_ROOT / "tests" / "architecture" / name
        assert path.is_file(), f"{name} must exist"
        match = re.search(r"EXPECTED_HARNESS_COUNT\s*=\s*(\d+)", path.read_text(encoding="utf-8"))
        assert match and int(match.group(1)) == expected, (
            f"{name}: EXPECTED_HARNESS_COUNT must remain {expected}. The AW-1 Tier-A harness is deliberately "
            "MANUAL_ONLY and non-loop-enrolled; the F22 lockstep does NOT apply and must not be touched."
        )
    doc = _scan.REPO_ROOT / "docs" / "runtime" / "b7c2_live_pg_durable_path_ci.md"
    assert "Run set (14 harnesses)" in doc.read_text(encoding="utf-8"), "the b7c2 run-set doc must remain at 14 harnesses"
    workflow = (_scan.REPO_ROOT / ".github" / "workflows" / "live-pg-durable-path.yml").read_text(encoding="utf-8")
    loop = re.search(r"for\s+h\s+in\s+(?P<loop>.+?);\s*do", workflow, re.DOTALL)
    assert loop and len(re.findall(r"\S+\.py", loop.group("loop"))) == 14, "the hosted live-PG loop must remain 14 explicit entries"


def test_this_guard_is_not_registered_in_the_role_security_meta_guard() -> None:
    """Deliberate NON-registration, asserted so a future editor cannot 'helpfully' add it.

    PMA-AR-2's INV-A is structurally bound to on-disk `infrastructure/db/**/*.sql`. A registered
    family whose `ddl_path` does not exist FAILS INV-A — and the AW-1 payload is deliberately
    embedded, not shipped as SQL, because a sixteenth on-disk Control DDL file would additionally
    turn the closed-inventory guard red.
    """
    coverage = _COVERAGE_META_GUARD.read_text(encoding="utf-8")
    for token in ("sp2_gateway_audit_writer", "sp2_gateway_audit_ingest", "aw1_gateway_audit_writer"):
        assert token not in coverage, (
            f"{token} must NOT appear in the PMA-AR-2 role-security coverage registry: its INV-A globs on-disk "
            "infrastructure/db/**/*.sql, and a family with a non-existent ddl_path fails INV-A. This byte-pin guard "
            "is the intended substitute."
        )
    db_dir = _scan.REPO_ROOT / "infrastructure" / "db"
    for sql in db_dir.rglob("*.sql"):
        text = sql.read_text(encoding="utf-8")
        assert "sp2_gateway_audit_writer" not in text and "sp2_gateway_audit_ingest" not in text, (
            f"{sql.name} carries an AW-1 role name. The AW-1 SQL must stay EMBEDDED in the operator tooling: as an "
            "on-disk file it would break the closed 15-file Control-DDL inventory guard AND force a PMA-AR-2 family."
        )


# ---------------------------------------------------------------------------------------------
# RB-1 — V-12 must be ONE predicate, evaluated on the EFFECTIVE rule for the tool's own connection.
#
# The defect: `apply` tested `'trust' in <the auth_method of EVERY type='host' rule>` while
# `classify()` — what `plan` reports — never read the key at all. On the standing control cluster
# that made `plan` exit 0 `MISSING` while `apply` was guaranteed to refuse before minting: a false
# green on the §6.3 pre-grant condition, produced by a predicate that answered a question nobody
# asked (a `host all all 127.0.0.1/32 trust` line does not govern a connection arriving from a
# container-network address).
#
# These checks EXECUTE the tool's own functions. A structural check cannot establish either half:
# the matcher's correctness is a property of its arithmetic, and "plan and apply agree" is a
# property of them consuming one value.
# ---------------------------------------------------------------------------------------------
def _hba(order: int, rule_type: str, address: object, netmask: object, method: str, **overrides: object) -> dict:
    rule = {
        "order": order,
        "type": rule_type,
        "database": ["all"],
        "user_name": ["all"],
        "address": address,
        "netmask": netmask,
        "auth_method": method,
        "error": None,
    }
    rule.update(overrides)
    return rule


# The stock PostgreSQL rule table, in file order: a loopback `trust` line ABOVE the catch-all that
# actually governs a connection arriving from anywhere else. This exact shape is what the whole-file
# membership test got wrong.
def _stock_rules() -> list:
    return [
        _hba(1, "local", None, None, "trust"),
        _hba(2, "host", "127.0.0.1", "255.255.255.255", "trust"),
        _hba(3, "host", "::1", "ffff:ffff:ffff:ffff:ffff:ffff:ffff:ffff", "trust"),
        _hba(4, "local", None, None, "trust", database=["replication"]),
        _hba(5, "host", "127.0.0.1", "255.255.255.255", "trust", database=["replication"]),
        _hba(6, "host", "all", None, "scram-sha-256"),
    ]


# The fall-through hazard, as a MULTI-RULE table. Entry #1 cannot be decided from what this tool
# observes (a `+group` token needs catalog state) and its declared method is `trust`; entry #2 is a
# permissive, password-discriminating catch-all that WOULD match. In a first-match table the scan
# must stop at #1 and report UNDETERMINABLE. A scan that skipped #1 would report `scram-sha-256` and
# let `apply` proceed on a cluster whose governing rule may accept unconditionally — the RB-1
# false-green class, re-entered through the matcher instead of through `classify()`.
def _fall_through_rules() -> list:
    return [
        _hba(1, "host", "all", None, "trust", user_name=["+operators"]),
        _hba(2, "host", "all", None, "scram-sha-256"),
    ]


# The MX8 hazard, as a multi-rule table. Entry #1 is password-discriminating but names a DIFFERENT
# role, so it is a DEFINITE non-match and the governing entry is the `trust` catch-all below it. A
# token matcher that answered "match" (or "undecidable") for a token set it never matched would pick
# entry #1 and report a clean `plan` on a cluster whose real rule is `trust`.
def _non_matching_user_rules() -> list:
    return [
        _hba(1, "host", "all", None, "scram-sha-256", user_name=["postgres"]),
        _hba(2, "host", "all", None, "trust"),
    ]


def _connection(tool: ModuleType, client_address: object) -> dict:
    return {
        "local": client_address is None,
        "ssl": False,
        "client_address": client_address,
        "database": tool.CONTROL_DATABASE,
        "user": "sp2_local",
    }


def _environment(tool: ModuleType, effective: dict) -> dict:
    """A Tier-B environment in which EVERYTHING except V-12 is clean, so a CONFLICTING verdict can
    only have come from V-12."""
    return {
        "database": tool.CONTROL_DATABASE,
        "server_version_num": tool.MIN_SERVER_VERSION_NUM,
        "triggers": dict.fromkeys(tool.EXPECTED_TRIGGERS, "O"),
        "tenant_databases_on_control_cluster": [],
        "log_gucs": {},
        "effective_host_auth": effective,
    }


_EMPTY_STATE = {"roles": {}, "memberships": [], "comments": {}, "owned_objects": {}}
_EMPTY_PRIVILEGES: dict = {"positive": {}, "negative": {}, "unrelated": {}}


def test_an_unrelated_trust_rule_does_not_create_a_false_v12_conflict() -> None:
    """RB-1 proof 1. EXECUTED.

    A `trust` line the executor connection never reaches must not block. This is the case the
    predecessor got wrong in the blocking direction, and it is the standing cluster's actual shape:
    the Docker userland port proxy presents a container-network client address, so the loopback
    `trust` entry is not the governing rule.
    """
    tool = _load_tool()
    rules = _stock_rules()
    assert "trust" in [rule["auth_method"] for rule in rules], "the fixture must contain the trust rules that misled the predecessor"

    effective = tool.effective_host_auth(rules, _connection(tool, "172.17.0.1"))
    assert effective["undeterminable"] is None, f"the governing entry must be determinable: {effective}"
    assert effective["method"] == "scram-sha-256", f"the catch-all entry governs this connection, not a loopback trust line: {effective}"
    assert effective["order"] == 6, "the FIRST matching entry is the governing one"
    assert tool.v12_problems(_environment(tool, effective)) == [], "an unreached trust rule must not block V-12"
    verdict, findings = tool.classify(_EMPTY_STATE, _EMPTY_PRIVILEGES, _environment(tool, effective))
    assert (verdict, findings) == (tool.MISSING, []), f"plan must stay MISSING when V-12 is satisfied, got {verdict} {findings}"


def test_an_effective_trust_rule_for_this_connection_yields_conflicting() -> None:
    """RB-1 proof 2. EXECUTED. The same table, a loopback client — now the trust line DOES govern."""
    tool = _load_tool()
    effective = tool.effective_host_auth(_stock_rules(), _connection(tool, "127.0.0.1"))
    assert effective["undeterminable"] is None and effective["method"] == "trust", f"the loopback entry must govern: {effective}"
    assert effective["order"] == 2, "the first matching entry — not the catch-all below it — is the governing one"
    problems = tool.v12_problems(_environment(tool, effective))
    assert problems and "trust" in problems[0], f"an effective trust rule must block V-12, got {problems}"
    verdict, findings = tool.classify(_EMPTY_STATE, _EMPTY_PRIVILEGES, _environment(tool, effective))
    assert verdict == tool.CONFLICTING, "plan must report CONFLICTING when the effective method is non-discriminating"
    assert any("V-12" in finding for finding in findings), f"the finding must name V-12: {findings}"


def test_v12_fails_closed_when_the_governing_rule_cannot_be_determined() -> None:
    """An unreadable rule table, an unparsed entry, and an undecidable entry all BLOCK.

    pg_hba is a first-match table: an entry that can be neither matched nor excluded might be the
    governing one, so no later entry may be assumed to govern instead. Fail-closed is the only
    honest reading — V-12 exists to establish that a credential probe MEANS something.
    """
    tool = _load_tool()
    for label, effective in (
        ("unreadable rule table", tool.effective_host_auth(None, _connection(tool, "127.0.0.1"))),
        (
            "an entry that did not parse",
            tool.effective_host_auth(
                [_hba(1, "host", "all", None, "scram-sha-256", error="invalid connection type")], _connection(tool, "10.0.0.5")
            ),
        ),
        (
            "a hostname address that is not an IP literal",
            tool.effective_host_auth([_hba(1, "host", "some-host.internal", None, "scram-sha-256")], _connection(tool, "10.0.0.5")),
        ),
        (
            "a group token needing catalog state",
            tool.effective_host_auth(
                [_hba(1, "host", "all", None, "scram-sha-256", user_name=["+operators"])], _connection(tool, "10.0.0.5")
            ),
        ),
        (
            "an unobserved SSL state against a hostssl entry",
            tool.effective_host_auth([_hba(1, "hostssl", "all", None, "scram-sha-256")], {**_connection(tool, "10.0.0.5"), "ssl": None}),
        ),
        (
            # MULTI-RULE. Every fixture above is a single-entry table, in which "stop at the
            # undecidable entry" and "run off the end of the table" reach the same blocking answer —
            # so none of them can tell the two apart. This one can: there IS a later entry, and it is
            # both safe and password-discriminating.
            "an undecidable entry ABOVE a permissive catch-all (the fall-through hazard)",
            tool.effective_host_auth(_fall_through_rules(), _connection(tool, "10.0.0.5")),
        ),
    ):
        assert effective["undeterminable"], f"{label}: must be reported UNDETERMINABLE, got {effective}"
        assert effective["method"] is None, f"{label}: no method may be claimed when the governing entry is unknown"
        assert tool.v12_problems(_environment(tool, effective)), f"{label}: an undeterminable effective method must BLOCK"
        verdict, _findings = tool.classify(_EMPTY_STATE, _EMPTY_PRIVILEGES, _environment(tool, effective))
        assert verdict == tool.CONFLICTING, f"{label}: plan must report CONFLICTING"
    # And a missing observation entirely — the key absent from the environment — must also block.
    assert tool.v12_problems({}), "an environment carrying no effective-host-auth observation must block"


def test_an_undecidable_rule_above_a_permissive_catch_all_stops_the_scan() -> None:
    """The fall-through mutation, stated as its own proof — MULTI-RULE, because it has to be.

    The fixtures in the test above are single-entry tables. In a single-entry table "stop at the
    undecidable entry" and "run off the end of the table" produce the SAME blocking answer, so a
    matcher that skipped undecidable entries would still pass every one of them. That is not a
    hypothetical: with `effective_host_auth`'s undecidable branch changed from `return` to
    `continue`, the whole architecture suite stayed green while V-12 had become fail-OPEN.

    Here there is a later entry, and it is safe and password-discriminating. Only a scan that
    genuinely stops can produce UNDETERMINABLE.
    """
    tool = _load_tool()
    rules = _fall_through_rules()
    assert len(rules) >= 2, "the fixture must have a LATER entry, or it cannot exercise fall-through at all"
    # The later entry must be one V-12 would accept, so the mutant's answer is a GREEN one.
    assert rules[-1]["auth_method"] in tool.PASSWORD_DISCRIMINATING_AUTH_METHODS, (
        "the later entry must be a method V-12 accepts; otherwise a fall-through would block anyway and this fixture would prove nothing"
    )
    connection = _connection(tool, "10.0.0.5")

    # The later entry DOES match this connection — established independently, so the assertions below
    # are about the scan stopping, not about the fixture failing to match.
    assert tool.effective_host_auth([rules[-1]], connection) == {"method": "scram-sha-256", "order": 2, "undeterminable": None}, (
        "the catch-all must match this connection on its own; otherwise the fall-through case is unreachable"
    )

    effective = tool.effective_host_auth(rules, connection)
    assert effective["method"] is None, (
        f"the scan reached the LATER entry and reported {effective['method']!r}. pg_hba is a FIRST-MATCH table: an entry "
        "that can be neither matched nor excluded might be the governing one, and here its declared method is `trust` — "
        "so assuming the entry below it governs converts a fail-closed V-12 into a fail-OPEN one."
    )
    assert effective["order"] == rules[0]["order"], (
        f"the scan must stop AT the undecidable entry (#{rules[0]['order']}), got #{effective['order']}"
    )
    assert effective["undeterminable"], "the reason the governing entry is unknowable must be reported, not implied"
    assert tool.v12_problems(_environment(tool, effective)), "an undeterminable governing entry must BLOCK V-12"
    verdict, findings = tool.classify(_EMPTY_STATE, _EMPTY_PRIVILEGES, _environment(tool, effective))
    assert verdict == tool.CONFLICTING and any("V-12" in finding for finding in findings), (
        f"plan must report CONFLICTING naming V-12, got {verdict} {findings}"
    )


def test_hba_token_matching_decides_in_both_directions() -> None:
    """`_hba_tokens_match` is pinned in BOTH directions — match and definite non-match.

    A three-valued matcher has two ways to be wrong, and only one of them is visible from the tests
    that exercise matching. If a token set that matched NOTHING returned `True` (or `None`), a rule
    naming a different database or a different role would be treated as governing — so a stricter,
    password-discriminating entry above a permissive `trust` catch-all would be reported as the
    governing rule and `plan` would go green on a cluster that accepts unconditionally. That is the
    RB-1 false green re-entered one function lower down, and only the negative direction catches it.
    """
    tool = _load_tool()
    # MATCH.
    assert tool._hba_tokens_match(["all"], "sp2_local") is True, "`all` matches every value"
    assert tool._hba_tokens_match(["sp2_local"], "sp2_local") is True, "an exact name matches"
    assert tool._hba_tokens_match(["postgres", "sp2_local"], "sp2_local") is True, "any token in the array may match"
    # DEFINITE NON-MATCH — the direction MX8 inverts.
    assert tool._hba_tokens_match(["postgres"], "sp2_local") is False, (
        "a token set naming only OTHER values is a DEFINITE non-match. Returning True or None here makes a rule that "
        "does not apply look like the governing one."
    )
    assert tool._hba_tokens_match(["replication"], "sp2_local") is False, (
        "a replication-only entry cannot govern this ordinary connection — and it must decide FALSE rather than stall "
        "the scan, because the stock pg_hba.conf puts replication lines above the catch-all"
    )
    assert tool._hba_tokens_match(["postgres", "replication"], "sp2_local") is False, "still a definite non-match"
    # UNDECIDABLE — needs catalog or filesystem state this tool does not read.
    for undecidable in (["+operators"], ["@dbs.conf"], ["sameuser"], ["samerole"], ["postgres", "+operators"]):
        assert tool._hba_tokens_match(undecidable, "sp2_local") is None, f"{undecidable} must decide NOTHING"
    assert tool._hba_tokens_match(None, "sp2_local") is None, "an unobserved token array decides nothing"
    assert tool._hba_tokens_match(["all"], None) is None, "an unobserved connection value decides nothing"

    # The address matcher is pinned in both directions for the same reason.
    assert tool._hba_address_matches("all", None, "10.0.0.5") is True
    assert tool._hba_address_matches("127.0.0.1", "255.255.255.255", "172.17.0.1") is False, (
        "a loopback CIDR is a DEFINITE non-match for a container-network client — this is the RB-1 case itself"
    )
    assert tool._hba_address_matches("some-host.internal", None, "10.0.0.5") is None, "a hostname is not resolved here"

    # END TO END: the definite non-match must actually move the governing entry.
    effective = tool.effective_host_auth(_non_matching_user_rules(), _connection(tool, "10.0.0.5"))
    assert (effective["method"], effective["order"]) == ("trust", 2), (
        f"the entry naming a different role must be SKIPPED and the trust catch-all below it must govern, got {effective}"
    )
    assert tool.v12_problems(_environment(tool, effective)), "the effective trust rule must block V-12"


def test_only_password_discriminating_methods_satisfy_v12() -> None:
    """The allow-list is the point: `peer`, `cert`, `ldap` and friends all authenticate SOMETHING
    other than the password `ALTER ROLE ... PASSWORD` binds, so the probe decides nothing."""
    tool = _load_tool()
    for method in ("scram-sha-256", "md5", "password"):
        assert tool.v12_problems(_environment(tool, {"method": method, "order": 1, "undeterminable": None})) == [], (
            f"{method} verifies the bound password and must satisfy V-12"
        )
    for method in ("trust", "peer", "ident", "cert", "gss", "sspi", "ldap", "radius", "pam", "bsd", "reject", "some-future-method"):
        assert tool.v12_problems(_environment(tool, {"method": method, "order": 1, "undeterminable": None})), (
            f"{method} does not decide the bound password and must BLOCK — an allow-list, so an unknown method blocks too"
        )


def _calls(function: str, callee: str) -> int:
    """How many times `function` CALLS `callee` — read from the AST, never from the text.

    A substring scan is satisfied by the identifier appearing in a comment or docstring, and both of
    these functions legitimately NAME the predicate while explaining why they share it. That is not a
    hypothetical: the first version of this guard used `"v12_problems(" in <source>` and a mutation
    that replaced the real call with `v12 = []` sailed through, because the explanatory comment two
    lines above still carried the token.
    """
    return sum(
        1 for node in ast.walk(_func(function)) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == callee
    )


def test_plan_and_apply_share_one_v12_classification() -> None:
    """RB-1 proof 3. Structural AND executed.

    Both paths must consume the SAME function. A second copy of the logic is how the two drifted
    apart in the first place, so the check is that exactly one predicate exists and both callers CALL
    it — and that `classify()` moves to CONFLICTING for precisely the inputs it rejects.
    """
    text = _tool_text()
    assert _calls("classify", "v12_problems") == 1, (
        "classify() — what `plan` reports — must CALL the V-12 predicate exactly once. Without the call, `plan` exits 0 "
        "MISSING on a cluster where `apply` refuses before minting: a false green on the §6.3 pre-grant condition."
    )
    assert _calls("_converge_credential", "v12_problems") == 1, (
        "the apply convergence path must CALL the SAME predicate. It is defence in depth now that the pre-apply "
        "classify() blocks first, but a guard that claims to check it must actually check it."
    )
    assert _func("v12_problems") is not None, "there must be exactly one V-12 predicate"
    # The predecessor's whole-file membership test must not survive anywhere in a DECISION path.
    for name in ("classify", "v12_problems", "_converge_credential"):
        source = ast.get_source_segment(text, _func(name)) or ""
        assert "host_auth_method_census" not in source, (
            f"{name}() reads the reported-only whole-file census. That census is the PREDECESSOR's predicate: it "
            "answers 'does any host rule anywhere say trust', which is neither this connection's rule nor the hazard."
        )
    # Executed: the two verdicts agree on every input, in both directions.
    tool = _load_tool()
    for effective in (
        tool.effective_host_auth(_stock_rules(), _connection(tool, "172.17.0.1")),
        tool.effective_host_auth(_stock_rules(), _connection(tool, "127.0.0.1")),
        tool.effective_host_auth(None, _connection(tool, "127.0.0.1")),
        {"method": "md5", "order": 1, "undeterminable": None},
        {"method": "cert", "order": 1, "undeterminable": None},
    ):
        environment = _environment(tool, effective)
        apply_blocks = bool(tool.v12_problems(environment))
        plan_verdict, _findings = tool.classify(_EMPTY_STATE, _EMPTY_PRIVILEGES, environment)
        assert apply_blocks == (plan_verdict == tool.CONFLICTING), (
            f"plan and apply disagree on {effective}: apply blocks={apply_blocks}, plan verdict={plan_verdict}. It must "
            "be IMPOSSIBLE for plan to report green where apply would refuse solely on V-12."
        )


def test_a_plan_that_ignored_v12_could_not_pass_this_guard() -> None:
    """RB-1 proof 4. The mutation this guard exists to catch, exercised as a mutation.

    `classify()` is re-run with the V-12 predicate STUBBED OUT — which is exactly what "plan ignores
    V-12" means — and the guard's own assertion is shown to fail on the mutant. Without this, a
    reviewer has to take on faith that the executed checks above are load-bearing.
    """
    tool = _load_tool()
    effective = tool.effective_host_auth(_stock_rules(), _connection(tool, "127.0.0.1"))
    environment = _environment(tool, effective)
    assert tool.classify(_EMPTY_STATE, _EMPTY_PRIVILEGES, environment)[0] == tool.CONFLICTING, "the unmutated tool must block"

    original = tool.v12_problems
    try:
        tool.v12_problems = lambda _environment: []  # the mutation: plan stops consulting V-12
        mutant_verdict, _findings = tool.classify(_EMPTY_STATE, _EMPTY_PRIVILEGES, environment)
    finally:
        tool.v12_problems = original
    assert mutant_verdict == tool.MISSING, (
        "the mutation probe did not change the verdict, so the CONFLICTING above did not come from V-12 and these "
        "checks would pass against a plan that ignores it"
    )
    assert tool.classify(_EMPTY_STATE, _EMPTY_PRIVILEGES, environment)[0] == tool.CONFLICTING, "the mutation must be reverted"


def _conflict_exit_codes() -> List[int]:
    """Every constant `return` reachable inside an `if verdict == CONFLICTING:` branch of `cmd_plan`.

    Read from the AST, never from the text. The predecessor of this check asserted
    `"if verdict == CONFLICTING:" in plan_source and "return 2" in plan_source` against
    `ast.get_source_segment`, which INCLUDES interior comments — so deleting the real gate outright
    while leaving those two token sequences in the surrounding commentary passed the guard with
    `cmd_plan` returning 0 on CONFLICTING. A comment cannot be an `ast.If` and cannot contain an
    `ast.Return`, so this form is not satisfiable by prose.
    """
    codes: List[int] = []
    for node in ast.walk(_func("cmd_plan")):
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if not (
            isinstance(test, ast.Compare)
            and isinstance(test.left, ast.Name)
            and test.left.id == "verdict"
            and len(test.ops) == 1
            and isinstance(test.ops[0], ast.Eq)
            and len(test.comparators) == 1
            and isinstance(test.comparators[0], ast.Name)
            and test.comparators[0].id == "CONFLICTING"
        ):
            continue
        for inner in ast.walk(node):
            if isinstance(inner, ast.Return) and isinstance(inner.value, ast.Constant) and isinstance(inner.value.value, int):
                codes.append(int(inner.value.value))
    return codes


class _NoDatabaseConnection:
    """A `psycopg` connection stand-in for an EXECUTED `cmd_plan`: no driver, no socket, no cluster.

    `cmd_plan` uses it only as a context manager and as the argument of the observation functions,
    every one of which is replaced below. Nothing here can reach a database.
    """

    def __init__(self) -> None:
        self.read_only = False

    def __enter__(self) -> "_NoDatabaseConnection":
        return self

    def __exit__(self, *_exc: object) -> bool:
        return False


class _NoDatabaseDriver:
    def __init__(self, connection: _NoDatabaseConnection) -> None:
        self._connection = connection

    def connect(self, _dsn: str) -> _NoDatabaseConnection:
        return self._connection


def _execute_plan(tool: ModuleType, effective: dict) -> int:
    """Run the REAL `cmd_plan` end to end over a synthetic observation and return its EXIT CODE.

    Every function `cmd_plan` calls to reach the outside world is replaced: the driver, the executor
    DSN, all four observation functions, the material resolver and the sink probe. `classify()` and
    the exit-code logic — the two things under test — are the tool's own.
    """
    connection = _NoDatabaseConnection()
    environment = _environment(tool, effective)
    replacements: dict = {
        "_psycopg": lambda: _NoDatabaseDriver(connection),
        "_executor_dsn": lambda: "postgresql://executor@127.0.0.1:1/snackportal2_control_local",
        "observe_environment": lambda _conn: environment,
        "observe_role_state": lambda _conn: dict(_EMPTY_STATE),
        "observe_privileges": lambda _conn: dict(_EMPTY_PRIVILEGES),
        "observe_row_baseline": lambda _conn: None,
        "_resolve_writer_material": lambda: (None, None),
        "material_sink_blockers": lambda: [],
    }
    originals = {name: getattr(tool, name) for name in replacements}
    try:
        for name, replacement in replacements.items():
            setattr(tool, name, replacement)
        return int(tool.cmd_plan(argparse.Namespace()))
    finally:
        for name, original in originals.items():
            setattr(tool, name, original)


def test_a_conflicting_plan_exits_non_zero() -> None:
    """RB-1 proof 5. `plan`'s EXIT CODE, established structurally AND by execution.

    A verdict printed on stdout that leaves the process exiting 0 is not a gate — the false green
    simply moves from the verdict line to the shell. Both halves are here because each catches what
    the other cannot: the AST form pins that the gate exists as control flow (so deleting it and
    leaving explanatory comments behind fails), and the executed form pins the observable behaviour
    (so re-shaping the control flow into something the AST check does not recognise still fails).
    """
    codes = _conflict_exit_codes()
    assert codes, (
        "cmd_plan has no `if verdict == CONFLICTING:` branch containing a constant `return`. plan must EXIT non-zero "
        "on CONFLICTING; a comment mentioning the condition is not a gate."
    )
    assert all(code != 0 for code in codes), f"every CONFLICTING exit from cmd_plan must be non-zero, found {codes}"

    tool = _load_tool()
    conflicting = tool.effective_host_auth(_stock_rules(), _connection(tool, "127.0.0.1"))
    clean = tool.effective_host_auth(_stock_rules(), _connection(tool, "172.17.0.1"))
    assert tool.classify(_EMPTY_STATE, _EMPTY_PRIVILEGES, _environment(tool, conflicting))[0] == tool.CONFLICTING
    assert tool.classify(_EMPTY_STATE, _EMPTY_PRIVILEGES, _environment(tool, clean))[0] == tool.MISSING

    assert _execute_plan(tool, conflicting) != 0, (
        "an EXECUTED `plan` over an effective-`trust` cluster exited 0. The operator's shell — and the start gate that "
        "reads it — sees the exit code, not the printed verdict."
    )
    assert _execute_plan(tool, clean) == 0, (
        "an EXECUTED `plan` over an effective-`scram-sha-256` cluster must exit 0, or the gate blocks the state it exists to permit"
    )


def test_the_operator_runbook_describes_the_effective_rule_predicate() -> None:
    """The operator reads the runbook, not this guard — and it documented the RETIRED predicate.

    V-12's refusal row said "Host auth includes `trust`", which is the whole-file membership test
    RB-1 replaced. An operator following it would look for the wrong thing: they would go hunting for
    any `trust` line in `pg_hba.conf` (and find one on a stock installation) instead of for the entry
    that governs the tool's own connection.
    """
    runbook = _RUNBOOK.read_text(encoding="utf-8")
    assert "Host auth includes `trust`" not in runbook, (
        "the runbook still states V-12 as a whole-file `trust` census. That is the PREDECESSOR's predicate — it answers "
        "'does any host rule anywhere say trust', which is neither this connection's rule nor the hazard."
    )
    for required in ("effective", "first-match", "pg_hba"):
        assert required in runbook.lower(), f"the runbook must describe V-12 as the {required!r} rule for this connection"
    assert "UNPROVEN" in runbook and "P-4" in runbook, (
        "the runbook must state the expected live outcome as UNPROVEN pending the P-4 query. Nobody has read the "
        "standing cluster's rule table, so neither a predicted green nor a predicted red may be presented as a fact."
    )


def test_guard_is_non_vacuous() -> None:
    payload = _module_constant("FROZEN_ROLE_GRANT_SQL")
    assert payload.strip(), "the payload constant must be readable by this guard"
    mutated = payload.replace("GRANT SELECT, INSERT ON", "GRANT SELECT, INSERT, UPDATE ON")
    assert mutated != payload, "the mutation probe must apply"
    assert hashlib.sha256(mutated.encode("utf-8")).hexdigest() != _FROZEN_PAYLOAD_SHA256, "a widened grant must move the pin"
    assert _func("cmd_plan") is not None and _func("cmd_apply") is not None and _func("cmd_status") is not None
    assert len(_REQUIRED_STATEMENTS) == 11, "the frozen payload is eleven statements"
    # The CONFLICTING-exit reader must find control flow, and must NOT be satisfiable by prose. Both
    # halves are probed: the shape it accepts, and the comment-only shape it must reject.
    real = ast.parse("def cmd_plan(a):\n    if verdict == CONFLICTING:\n        return 2\n    return 0\n")
    prose = ast.parse("def cmd_plan(a):\n    # if verdict == CONFLICTING: return 2\n    return 0\n")
    for tree, expected, label in ((real, [2], "a real gate"), (prose, [], "a commented-out gate")):
        function = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef))
        found = [
            int(inner.value.value)
            for node in ast.walk(function)
            if isinstance(node, ast.If)
            and isinstance(node.test, ast.Compare)
            and isinstance(node.test.left, ast.Name)
            and node.test.left.id == "verdict"
            for inner in ast.walk(node)
            if isinstance(inner, ast.Return) and isinstance(inner.value, ast.Constant) and isinstance(inner.value.value, int)
        ]
        assert found == expected, f"the CONFLICTING-exit reader must see {label} as {expected}, got {found}"
    # The fall-through fixture must actually BE multi-rule, or the mutation it exists for is unreachable.
    assert len(_fall_through_rules()) >= 2 and len(_non_matching_user_rules()) >= 2, (
        "both hazard fixtures must carry a LATER entry; a single-rule table cannot distinguish 'stopped' from "
        "'ran off the end', which is exactly how the fall-through mutation survived"
    )


if __name__ == "__main__":
    _scan.run(
        [
            test_operator_tool_and_its_companions_exist,
            test_frozen_payload_matches_its_byte_pin,
            test_frozen_payload_contains_every_pinned_statement,
            test_frozen_payload_grants_nothing_beyond_the_least_privilege_surface,
            test_apply_asserts_the_database_pin_before_the_first_statement,
            test_plan_is_read_only,
            test_apply_refuses_without_an_explicit_gate_b_confirmation,
            test_initial_creation_is_distinguished_from_recovery,
            test_logging_observation_precedes_every_bind,
            test_no_credential_material_is_emitted,
            test_the_material_write_is_confined_to_one_governed_sink,
            test_a_mutating_branch_persists_and_reprobes_in_the_governed_order,
            test_the_material_sink_refuses_a_repository_location_and_a_shadowing_env_form,
            test_the_material_resolution_mirrors_the_runtime_resolver,
            test_the_composed_material_satisfies_the_pinned_dsn_shape,
            test_password_alphabet_cannot_break_dsn_composition,
            test_dsn_shape_check_pins_application_name_and_bans_options,
            test_status_declares_a_fixed_pass_count,
            test_tool_is_glob_invisible_to_the_harness_census,
            test_the_hosted_loop_lockstep_is_deliberately_untouched,
            test_this_guard_is_not_registered_in_the_role_security_meta_guard,
            test_an_unrelated_trust_rule_does_not_create_a_false_v12_conflict,
            test_an_effective_trust_rule_for_this_connection_yields_conflicting,
            test_v12_fails_closed_when_the_governing_rule_cannot_be_determined,
            test_an_undecidable_rule_above_a_permissive_catch_all_stops_the_scan,
            test_hba_token_matching_decides_in_both_directions,
            test_only_password_discriminating_methods_satisfy_v12,
            test_plan_and_apply_share_one_v12_classification,
            test_a_plan_that_ignored_v12_could_not_pass_this_guard,
            test_a_conflicting_plan_exits_non_zero,
            test_the_operator_runbook_describes_the_effective_rule_predicate,
            test_guard_is_non_vacuous,
        ]
    )
