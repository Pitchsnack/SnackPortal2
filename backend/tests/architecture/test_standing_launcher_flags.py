"""Architecture guards for the GOVERNED STANDING LAUNCHER (`backend/tools/local/start-sp2-local.ps1`).

Until Gate A the standing topology was started by an out-of-repo PowerShell script under no git
repository at all. Nothing in CI could see it, so nothing could notice that it emitted

    uvicorn <module>:create_app_from_env --factory --port <p>

with **none** of the five canonical flags, that it never set `--host` (leaving uvicorn's
`UVICORN_*` auto-envvar surface live), and that its per-window environment relay was not fail-fast.
Committing the launcher makes the standing posture reviewable; this file is what makes it *pinned*.

What is checked, and why each check exists:

* **The five canonical flags, on one template.** The launcher composes every standing edge through a
  single `Get-StandingUvicornCommand`, so a flag cannot be complete on five edges and short on the
  sixth. The guard asserts the flag census AND that the template is the only uvicorn invocation.
* **The governed standing port map** — 8001 / 8002 / 8003 / 8004 / 8005 / 8820 — bound to the right
  module, with the Gateway on 8820 and **never** 8080. `8080-8088` is the ISOLATED SMOKE /
  VERIFICATION map (`tests/deployment/native_uvicorn_process_smoke.py`); a standing edge in that
  range means two topologies are live and nothing would say so.
* **The three selectors that must stay UNSET** (V7 §24 / E60): `SP2_GW_IMPORT_BASE_URL`,
  `SP2_DBR_ROUTING_AUDIT_BASE_URL`, `SP2_IMPORT_AUDIT_SINK_BASE_URL`. Never assigned — and, stronger,
  swept out of every child so an inherited shell value cannot activate them either.
* **The four activation selectors are never active defaults.** `SP2_CP_CONTROL_STORE`,
  `SP2_CP_CONTROL_STORE_DSN_REF`, `SP2_GW_AUDIT_SINK_BASE_URL`, `SP2_GW_TENANT_STARTUP_BASE_URL` may
  be *present* in the launcher — that is the point, the governed values are pinned so activation is a
  reviewed flip — but each assignment must sit inside an explicit `-Enable*` opt-in block. Running
  with any of them on produces persistent standing state and is Gate-B work.
* **Inherited-environment isolation.** `UVICORN_*` and `SP2_*` are scrubbed in every child before the
  governed values are applied.
* **No foreign-worktree default.** The launcher resolves its backend root from `$PSScriptRoot`, so it
  drives the worktree it is committed in and cannot silently launch a stale or pre-merge tree.
* **No credential material.** References and variable NAMES only.

Pure stdlib; runnable standalone:  python tests/architecture/test_standing_launcher_flags.py
"""

from __future__ import annotations

import pathlib
import re
import sys
from typing import Dict, List, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

LAUNCHER = _scan.BACKEND_ROOT / "tools" / "local" / "start-sp2-local.ps1"

# The governed STANDING map. CLM-SS-1 decision "D-1 gateway port 8820" (that register's D-1 — not
# the repository ADR register's D-01 "Bootstrap Cycle Resolution", a different decision with a
# colliding short identifier).
GOVERNED_STANDING_MAP: Dict[str, int] = {
    "auth_router.adapters.providers.http_authenticate_api": 8001,
    "database_router.adapters.providers.http_dispatch_api": 8002,
    "control_plane.adapters.providers.http_read_api": 8003,
    "database_router.adapters.providers.http_tenant_startup_api": 8004,
    "control_plane.adapters.providers.http_gateway_audit_api": 8005,
    "api_gateway.adapters.providers.http_gateway_edge": 8820,
}

# The five flags that make the native path safe. `--factory` is the application-shape flag; the other
# four are the ONLY thing standing between the standing topology and uvicorn's defaults
# (access_log=True, server_header=True, proxy_headers=True, and more than one worker).
REQUIRED_FLAGS = ("--factory", "--workers 1", "--no-access-log", "--no-server-header", "--no-proxy-headers")

# V7 §24 / E60: these must remain UNSET for the controlled local MVP journey. Import is outside it
# (IMPORT-A / D-3), and neither the routing-audit nor the import-audit durable sink is in scope.
MUST_REMAIN_UNSET = (
    "SP2_GW_IMPORT_BASE_URL",
    "SP2_DBR_ROUTING_AUDIT_BASE_URL",
    "SP2_IMPORT_AUDIT_SINK_BASE_URL",
)

# Present-but-gated. Each is a Gate-B act the moment a process runs with it active
# (M12 durable reads / M12 ref binding / M11 durable audit rows / M14 tenant writes).
GATED_ACTIVATION_SELECTORS = (
    "SP2_CP_CONTROL_STORE",
    "SP2_CP_CONTROL_STORE_DSN_REF",
    "SP2_GW_AUDIT_SINK_BASE_URL",
    "SP2_GW_TENANT_STARTUP_BASE_URL",
)

# The isolated smoke / verification map. No standing edge may live here.
SMOKE_ONLY_PORT_RANGE = range(8080, 8089)

_START_EDGE_RE = re.compile(
    r"Start-StandingEdge\b(?P<body>.*?)(?=\n\s*\n|\nStart-|\Z)",
    re.DOTALL,
)
_MODULE_RE = re.compile(r'-Module\s+"([^"]+)"')
_PORT_RE = re.compile(r"-Port\s+(\$[A-Za-z_][A-Za-z0-9_]*|\d+)")
_PORT_CONST_RE = re.compile(r"^\s*\$(PORT_[A-Z_]+)\s*=\s*(\d+)\s*$", re.MULTILINE)
_FLAG_ARRAY_RE = re.compile(r"\$CANONICAL_UVICORN_FLAGS\s*=\s*@\((?P<items>[^)]*)\)")
_UVICORN_LINE_RE = re.compile(r'"uvicorn [^"]*"')


def _text() -> str:
    return LAUNCHER.read_text(encoding="utf-8")


def _code_lines(text: str) -> List[Tuple[int, str]]:
    """Numbered lines with pure-comment lines and the `<# .. #>` help block removed.

    Comment text deliberately NAMES the selectors it forbids (that is how an operator learns what
    the posture is), so every "must not appear" assertion has to read code only.
    """
    out: List[Tuple[int, str]] = []
    in_block = False
    for i, raw in enumerate(text.splitlines(), 1):
        s = raw.strip()
        if s.startswith("<#"):
            in_block = True
        if in_block:
            if "#>" in s:
                in_block = False
            continue
        if s.startswith("#"):
            continue
        code = raw.split("#", 1)[0] if "#" in raw and '"' not in raw.split("#", 1)[0] else raw
        out.append((i, code))
    return out


def _port_constants(text: str) -> Dict[str, int]:
    return {name: int(value) for name, value in _PORT_CONST_RE.findall(text)}


def _standing_edges(text: str) -> Dict[str, int]:
    """The composed (module -> port) census, resolved through the `$PORT_*` constants."""
    consts = _port_constants(text)
    edges: Dict[str, int] = {}
    for match in _START_EDGE_RE.finditer(text):
        body = match.group("body")
        module = _MODULE_RE.search(body)
        port = _PORT_RE.search(body)
        if not module or not port:
            continue
        token = port.group(1)
        resolved = consts[token[1:]] if token.startswith("$") else int(token)
        edges[module.group(1)] = resolved
    return edges


def test_launcher_is_committed() -> None:
    assert LAUNCHER.is_file(), (
        f"the governed standing launcher must be committed at {LAUNCHER.relative_to(_scan.REPO_ROOT)} — "
        "an out-of-repo launcher is invisible to review and to CI, which is how the standing topology "
        "ran for weeks with none of the five canonical flags"
    )


def test_canonical_flag_census_is_exactly_the_five() -> None:
    match = _FLAG_ARRAY_RE.search(_text())
    assert match, "the launcher must declare $CANONICAL_UVICORN_FLAGS as a single reviewable array"
    declared = tuple(item.strip().strip('"').strip("'") for item in match.group("items").split(",") if item.strip())
    assert declared == REQUIRED_FLAGS, (
        f"the canonical flag census must be exactly {REQUIRED_FLAGS} in order, got {declared}. "
        "Each omission silently restores a uvicorn default on the standing topology."
    )


def test_one_uvicorn_command_template_carrying_every_flag() -> None:
    text = _text()
    templates = _UVICORN_LINE_RE.findall(text)
    assert len(templates) == 1, (
        f"the launcher must compose uvicorn in exactly ONE place (found {len(templates)}). More than one "
        "template is how a flag ends up present on five edges and missing on the sixth."
    )
    template = templates[0]
    assert "create_app_from_env" in template, "the standing path must use the no-argument native application factory"
    assert "$flags" in template, "the single template must interpolate $CANONICAL_UVICORN_FLAGS, not restate the flags"
    assert "--host $STANDING_BIND_HOST" in template, (
        "the template must pin the bind host from the command line — on the native path the CLI is the ONLY "
        "place loopback is enforced (IC-010 §R/§M)"
    )
    assert "--port $Port" in template, "the template must take the port from the governed per-edge assignment"
    assert re.search(r'\$STANDING_BIND_HOST\s*=\s*"127\.0\.0\.1"', text), "the governed standing bind host must be 127.0.0.1"


def test_standing_port_map_is_the_governed_map() -> None:
    edges = _standing_edges(_text())
    assert edges == GOVERNED_STANDING_MAP, (
        "the launcher's (module -> port) census must be exactly the governed standing map.\n"
        f"  expected: {GOVERNED_STANDING_MAP}\n  found:    {edges}"
    )


def test_gateway_is_8820_and_no_standing_edge_lands_in_the_smoke_range() -> None:
    edges = _standing_edges(_text())
    gateway = edges["api_gateway.adapters.providers.http_gateway_edge"]
    assert gateway == 8820, f"the standing API Gateway must bind 8820, found {gateway}"
    for module, port in edges.items():
        assert port not in SMOKE_ONLY_PORT_RANGE, (
            f"{module} is assigned standing port {port}, which is inside the ISOLATED SMOKE / VERIFICATION "
            "range 8080-8088. A standing edge in that range means two topologies are live at once."
        )
    consts = _port_constants(_text())
    for name, value in consts.items():
        assert value not in SMOKE_ONLY_PORT_RANGE, f"${name} = {value} collides with the isolated smoke map"


def test_no_unauthorized_serving_mode_in_the_launcher() -> None:
    code = "\n".join(line for _n, line in _code_lines(_text()))
    for unauthorized in ("--host 0.0.0.0", "--reload", "gunicorn", "--workers 2", "--workers 4"):
        assert unauthorized not in code, f"{unauthorized} must never appear in the standing launcher"


def test_the_three_e60_selectors_are_never_set() -> None:
    # Not merely absent: the launcher must actively sweep SP2_* out of every child, so an inherited
    # value in the operator's shell cannot activate them either.
    for line_no, line in _code_lines(_text()):
        for name in MUST_REMAIN_UNSET:
            assert name not in line, (
                f"{LAUNCHER.name}:{line_no} references {name} in code. It must remain UNSET for the controlled "
                "local MVP journey (V7 §24 / E60): Import is outside the journey (IMPORT-A / D-3) and neither "
                "the routing-audit nor the import-audit durable sink is in scope."
            )


def test_inherited_environment_is_scrubbed_in_every_child() -> None:
    code = "\n".join(line for _n, line in _code_lines(_text()))
    sweep = re.search(r"foreach\s*\(\$pattern\s+in\s+@\((?P<items>[^)]*)\)\)", code)
    assert sweep, "the launcher must sweep a declared prefix list out of every child window"
    swept = tuple(item.strip().strip('"').strip("'") for item in sweep.group("items").split(",") if item.strip())
    assert swept == ("UVICORN_*", "SP2_*"), (
        f"the unconditional child sweep must be exactly ('UVICORN_*', 'SP2_*'), got {swept}. uvicorn's CLI is "
        "@click.command(auto_envvar_prefix='UVICORN'): UVICORN_RELOAD, UVICORN_APP_DIR, UVICORN_INTERFACE and "
        "friends have no CLI counterpart here and would take effect silently. Sweeping SP2_* is additionally what "
        "guarantees the three E60 selectors are UNSET even when the operator's shell holds a value for them."
    )
    assert "-like '$pattern'" in code, "the sweep must apply the declared prefixes to the child's own environment"
    # The emitted child line escapes `$_` with a backtick so the PARENT does not interpolate it.
    assert re.search(r"Remove-Item \('Env:' \+ `?\$_\.Name\) -Force", code), "the sweep must actually remove the variables"
    # The unconditional sweep must be exempt-free: a keep-list may narrow the per-edge EXTRA patterns
    # (AW-1 Q8 keeps the ingest edge's own writer variable) but never the governed UVICORN_*/SP2_* pass.
    unconditional = re.search(r"foreach\s*\(\$pattern\s+in\s+@\(\"UVICORN_\*\".*?\n(?P<body>.*?)\n\s*\}", code, re.DOTALL)
    assert unconditional and "$keepClause" not in unconditional.group("body"), (
        "nothing may be exempted from the governed UVICORN_*/SP2_* sweep"
    )


def test_activation_selectors_are_gated_behind_an_explicit_opt_in() -> None:
    """Present is fine. Active-by-default is not."""
    text = _text()
    for switch in ("EnableDurableControlStore", "EnableDurableGatewayAudit", "EnableTenantDataPlane"):
        assert re.search(rf"\[switch\]\${switch}\b", text), f"the launcher must expose -{switch} as an off-by-default switch"
        assert not re.search(rf"\[switch\]\${switch}\s*=", text), f"-{switch} must have no default value — a switch defaults to off"

    depth_of_gate: List[int] = []
    depth = 0
    for line_no, line in _code_lines(text):
        opens_gate = bool(re.search(r"^\s*if\s*\(.*\$Enable[A-Za-z]+", line))
        for name in GATED_ACTIVATION_SELECTORS:
            # An assignment form: `["NAME"] = ...`, `NAME = ...` or `NAME=...` inside a hashtable.
            if re.search(rf'(\["{name}"\]|\b{name}\b)\s*=[^=]', line):
                assert depth_of_gate or opens_gate, (
                    f"{LAUNCHER.name}:{line_no} assigns {name} outside an -Enable* opt-in block. Gate A authorises "
                    "the launcher to CONTAIN the activation selectors so their governed values are pinned and a "
                    "future activation is a reviewed one-line flip. It does NOT authorise shipping them active: "
                    "running a process with any of them on produces persistent standing state (M11 / M12 / M14) "
                    "and is Gate-B work."
                )
        if opens_gate:
            depth_of_gate.append(depth)
        depth += line.count("{") - line.count("}")
        while depth_of_gate and depth <= depth_of_gate[-1]:
            depth_of_gate.pop()


def test_launcher_resolves_its_own_worktree() -> None:
    text = _text()
    assert re.search(r'\[string\]\$BackendPath\s*=\s*""', text), (
        "the launcher must NOT default $BackendPath to an absolute path — a hard-coded default is how the "
        "standing topology kept launching a pre-merge worktree after the merge landed"
    )
    assert "$PSScriptRoot" in text, "the backend root must be derived from $PSScriptRoot so the launcher drives its own worktree"
    assert not re.search(r'=\s*"[A-Za-z]:\\\\?Pitchsnack', text), "no absolute developer path may be hard-coded as a default"


def test_launcher_carries_no_credential_material() -> None:
    code = "\n".join(line for _n, line in _code_lines(_text()))
    # Reference NAMES and variable NAMES only — never a resolved value.
    for shape in ("password=", "PGPASSWORD=", "postgresql://", "postgres://", "-----BEGIN", "eyJ"):
        assert shape not in code, f"the launcher must carry no credential material (found {shape!r})"
    for ref_default in ('"control/control-store-dsn"', '"control/gateway-audit-writer-dsn"'):
        assert ref_default in code, f"the governed secret REFERENCE {ref_default} must be pinned by name"


def test_aw1_start_gate_precedes_the_ingest_edge() -> None:
    """AW-1 §9 O-6 → O-7: confirm the least-privilege writer state BEFORE starting the ingest edge."""
    code = "\n".join(line for _n, line in _code_lines(_text()))
    assert "aw1_gateway_audit_writer.py" in code, "the launcher must know the AW-1 operator tool's path"
    assert "$LASTEXITCODE -ne 0" in code, "a red AW-1 status must be observed, not merely printed"
    assert "refusing to start the Gateway-audit ingest edge" in code, (
        "a failed AW-1 start gate must REFUSE to start the ingest edge — starting anyway is how an ungoverned "
        "identity ends up writing durable audit rows"
    )


def test_blank_writer_material_refuses_before_the_ingest_edge_starts() -> None:
    """AW-1 §11 S-3(a), the PRIMARY control — and the one the runbook already promises.

    `psycopg.connect("")` does not fail. It falls back to libpq connection defaults: the `PG*`
    environment variables, then `localhost:5432`, the OS user's name as the role, and a `~/.pgpass`
    lookup. `env_reference_secret_store.py` returns the variable's value with no strip and no blank
    check, so a set-but-empty writer variable resolves to `""` and the ingest edge connects
    somewhere nobody chose, as an identity nobody reviewed — the silent alternate-source path.

    The check must be inside the durable-audit opt-in block (it is meaningless when the ingest edge
    holds no material at all) and must precede the start of that edge.
    """
    code_lines = _code_lines(_text())
    code = "\n".join(line for _n, line in code_lines)
    assert "IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($GatewayAuditWriterSecretVar))" in code, (
        "the launcher must refuse when the SELECTED writer secret-material variable is unset, empty, OR "
        "whitespace-only after stripping. Reading it through the parameter (not a hard-coded name) is what keeps the "
        "check aimed at the variable the launcher actually keeps in the ingest window."
    )
    assert "AW-1 S-3(a)" in code, "the refusal must name the control it discharges"

    def _line_of(needle: str) -> int:
        for number, line in code_lines:
            if needle in line:
                return number
        raise AssertionError(f"expected {needle!r} in the launcher's code")

    gate_line = _line_of("IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($GatewayAuditWriterSecretVar))")
    opt_in_line = _line_of("if ($EnableDurableGatewayAudit) {")
    keep_line = _line_of("$ingestKeep = @($GatewayAuditWriterSecretVar)")
    start_line = _line_of('-Title "gateway_audit $PORT_GATEWAY_AUDIT"')
    assert opt_in_line < gate_line < keep_line < start_line, (
        "the blank-material refusal must sit inside the -EnableDurableGatewayAudit opt-in block and run BEFORE the "
        f"ingest edge is started (opt-in@{opt_in_line} check@{gate_line} keep@{keep_line} start@{start_line})"
    )
    # Presence only: the value must never be captured, printed, or relayed.
    assert not re.search(r"\$\w+\s*=\s*\[Environment\]::GetEnvironmentVariable\(\$GatewayAuditWriterSecretVar\)", code), (
        "the writer material must be tested for blankness IN PLACE. Capturing it into a variable is the first step "
        "toward printing or relaying a credential the launcher has no reason to hold."
    )
    for emitter in ("Write-Host $env:", "Write-Output $env:"):
        assert emitter not in code, f"the launcher must never emit an environment value ({emitter})"


def test_ingest_edge_gets_the_aw1_q8_environment_whitelist() -> None:
    code = "\n".join(line for _n, line in _code_lines(_text()))
    for pattern in ("SNACKPORTAL_SECRET_*", "SNACKPORTAL_TENANT_SECRET*", "PG*"):
        assert f'"{pattern}"' in code, (
            f"the Gateway-audit ingest edge must scrub {pattern} (AW-1 Q8). The ingest edge is durable BY "
            "CONSTRUCTION and, with no reference set, binds the DEFAULT ref control/control-store-dsn — which by "
            "standing convention resolves to the sp2_local SUPERUSER DSN. An unscoped operator session therefore "
            "makes a superuser audit-write path live, which is the condition AW-1 exists to eliminate."
        )


def test_guard_is_non_vacuous() -> None:
    # Every detector must be able to see its violation.
    assert _standing_edges('Start-StandingEdge -Title "x" `\n    -Module "a.b.c" `\n    -Port 8080\n') == {"a.b.c": 8080}
    assert _port_constants("$PORT_GATEWAY        = 8820\n") == {"PORT_GATEWAY": 8820}
    assert _FLAG_ARRAY_RE.search('$CANONICAL_UVICORN_FLAGS = @("--factory")'), "the flag census must be detectable"
    assert _UVICORN_LINE_RE.findall('return "uvicorn ${Module}:create_app_from_env --factory"'), "the template must be detectable"
    # The comment stripper must not hide code, and must hide comments.
    stripped = "\n".join(line for _n, line in _code_lines("# SP2_GW_IMPORT_BASE_URL is forbidden\n$x = 1\n"))
    assert "SP2_GW_IMPORT_BASE_URL" not in stripped and "$x = 1" in stripped
    assert len(GOVERNED_STANDING_MAP) == 6, "the standing census must cover exactly the six standing edges"


if __name__ == "__main__":
    _scan.run(
        [
            test_launcher_is_committed,
            test_canonical_flag_census_is_exactly_the_five,
            test_one_uvicorn_command_template_carrying_every_flag,
            test_standing_port_map_is_the_governed_map,
            test_gateway_is_8820_and_no_standing_edge_lands_in_the_smoke_range,
            test_no_unauthorized_serving_mode_in_the_launcher,
            test_the_three_e60_selectors_are_never_set,
            test_inherited_environment_is_scrubbed_in_every_child,
            test_activation_selectors_are_gated_behind_an_explicit_opt_in,
            test_launcher_resolves_its_own_worktree,
            test_launcher_carries_no_credential_material,
            test_aw1_start_gate_precedes_the_ingest_edge,
            test_blank_writer_material_refuses_before_the_ingest_edge_starts,
            test_ingest_edge_gets_the_aw1_q8_environment_whitelist,
            test_guard_is_non_vacuous,
        ]
    )
