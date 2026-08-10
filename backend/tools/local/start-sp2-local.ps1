<#
.SYNOPSIS
    Starts the SnackPortal2 local STANDING backend topology - five edges, governed posture.

.DESCRIPTION
    LOCAL / NON-PRODUCTION ONLY. Nothing here authorises a production deployment, a public
    ingress, TLS termination, or a supervisor. `main` is NOT READY / DO-NOT-ACTIVATE.

    This is the GOVERNED, in-repository standing launcher (Gate-A "operator tooling"). It
    supersedes the earlier out-of-repo copy at D:\Pitchsnack\StartupScript\start-sp2-local.ps1,
    which is no longer the durable authoritative source. That file is left in place untouched;
    do not run both.

    What this launcher pins that the ungoverned copy did not:

      1. ALL FIVE canonical uvicorn flags on EVERY standing edge (see $CANONICAL_UVICORN_FLAGS).
         The ungoverned copy emitted `uvicorn <module>:create_app_from_env --factory --port <p>`
         and nothing else, so uvicorn's own defaults (access_log=True, server_header=True,
         proxy_headers=True, host=127.0.0.1-by-default-only-until-an-envvar-says-otherwise) were
         live on the standing topology.
      2. ONE command template. Every edge is emitted from the single line built in
         Get-StandingUvicornCommand, so a flag cannot be present on five edges and missing on the
         sixth. Copy-pasteable per-edge commands live in the runbook, not here.
      3. The STANDING port map, and only it: 8001 / 8003 / 8005 / 8830 / 8831.
         The 8080-8088 map is ISOLATED SMOKE / VERIFICATION ONLY and is never used here.
      4. Fail-fast children. `$ErrorActionPreference = 'Stop'` is the FIRST statement inside each
         child window and every relayed variable is validated non-blank, so a dropped environment
         value aborts the window instead of letting uvicorn start misconfigured.
      5. Inherited-environment isolation. Every child scrubs UVICORN_* and SP2_* before the
         launcher sets the governed values, so nothing in the operator's shell can move the bind
         host, the worker count, the access log, the proxy-header trust, or any SP2 selector.

.NOTES
    Backend worktree: defaults to the repository this script is committed in (derived from
    $PSScriptRoot). It never defaults to a fixed absolute path, so it cannot silently launch a
    stale or pre-merge worktree the way a hard-coded default did.

    Prerequisites, started out of band: Keycloak (sp2_kc_standing) on 8814 and the four PostgreSQL
    containers on 5540-5543. See infrastructure/docker/runbooks/local_start.md.

    GATEWAY-FREE TOPOLOGY. The API Gateway (8820) was deleted, together with the two internal
    transports that existed only to carry a Gateway request into a service: the Database Router
    dispatch edge (8002) and the internal tenant-Startup envelope edge (8004). Each MVP route family
    is now served by the service that owns its records, behind the shared `shared.public_edge`
    boundary linked in-process:

        browser -> tenant Startup edge  8830  (database_router)  -> one tenant database
        browser -> Workspace edge       8831  (control_plane)    -> the Control database

    Both public edges still bind 127.0.0.1. Exposure is a deliberate act at a reverse proxy, never
    the consequence of an unset variable, and TLS terminates there.

    Governed posture reference: docs/runbooks/backend_service_startup_fastapi.md (standing map,
    canonical flags, the selectors this launcher deliberately leaves UNSET by default).

.EXAMPLE
    .\start-sp2-local.ps1

.EXAMPLE
    .\start-sp2-local.ps1 -SkipChecks
#>

[CmdletBinding()]
param(
    # Empty by default: resolved from $PSScriptRoot below. Pass a path only to launch a DIFFERENT
    # worktree deliberately, and expect the banner to say so.
    [string]$BackendPath = "",

    [string]$KeycloakBase   = "http://127.0.0.1:8814",
    [string]$Realm          = "sp2-local",
    [string]$ClientId       = "snackportal2-clm",
    [string]$FrontendOrigin = "http://127.0.0.1:5173",

    # ---------------------------------------------------------------- Gate-B opt-in switches ----
    # See the "ACTIVATION SELECTORS" block below. All three default to OFF. Turning any of them on
    # produces persistent standing state (durable reads, durable audit rows, tenant business
    # writes) and is Gate-B work - it is NOT authorised by the presence of the switch here.
    [switch]$EnableDurableControlStore,
    [switch]$EnableDurableEdgeAudit,
    # Gateway-free consequence, stated plainly: the public tenant Startup edge holds
    # TenantStartupOperations IN-PROCESS, so there is no longer a separate "wire the data plane"
    # selector to leave unset - composing the edge IS the tenant data plane. This switch therefore
    # gates whether that edge STARTS AT ALL, which keeps the Gate-A default posture exactly what it
    # was: no process able to write tenant business data.
    [switch]$EnableTenantDataPlane,

    # Reference NAMES only. Never a DSN, never a password, never a token. The value behind a
    # reference is resolved by the process from SNACKPORTAL_SECRET_<REF>_V1 (or the file form) and
    # never transits this script.
    # SecretRef NAMES are frozen by AW-1 and are NOT renamed by the Gateway removal: the durable
    # audit store is the Control-DB table `control_gateway_audit` (DDL 012/013), whose name and
    # `source_service = 'api_gateway'` CHECK are separately governed and untouched here.
    [string]$ControlStoreDsnRef     = "control/control-store-dsn",
    [string]$EdgeAuditWriterDsnRef  = "control/gateway-audit-writer-dsn",

    # The single SNACKPORTAL_SECRET_* variable the operational-audit ingest edge is permitted to
    # keep (AW-1 Q8 ingest-process environment whitelist). Name only; the launcher never reads its
    # value, and the AW-1 SecretRef name is frozen.
    [string]$EdgeAuditWriterSecretVar = "SNACKPORTAL_SECRET_CONTROL_GATEWAY_AUDIT_WRITER_DSN_V1",

    [switch]$SkipChecks
)

$ErrorActionPreference = "Stop"

# ============================================================================ GOVERNED POSTURE ==
# Everything in this region is the governed standing posture. The architecture guard
# backend/tests/architecture/test_standing_launcher_flags.py parses this file and pins it. Change
# a value here and that guard must be updated in the same commit, deliberately.

# The five canonical uvicorn flags. On the native path the uvicorn CLI builds its OWN server
# configuration and never executes shared/adapters/providers/asgi_runtime.py, where these
# properties are otherwise pinned. Omitting one silently restores uvicorn's default:
#   --factory           the application is a no-argument factory, not a module-level app object
#   --workers 1         one OS process per edge (AT-D15T1-10 authorized process model)
#   --no-access-log     no request line - targets, tenant references, query strings - on stderr
#   --no-server-header  no `Server: uvicorn` disclosure on every response
#   --no-proxy-headers  X-Forwarded-* is not trusted from any caller
$CANONICAL_UVICORN_FLAGS = @("--factory", "--workers 1", "--no-access-log", "--no-server-header", "--no-proxy-headers")

# Eight of the nine edges are internal-only (IC-010 sec.R/sec.M) and the ninth terminates behind a
# reverse proxy in deployment scope. On the native path the bind address comes from the command
# line, so the command line is the ONLY place loopback is enforced.
$STANDING_BIND_HOST = "127.0.0.1"

# ------------------------------------------------------------------------ STANDING PORT MAP ----
# The Gateway-free standing map. CLM-SS-1 decision "D-1 gateway port 8820" assigned the single
# northbound Gateway surface; that component is deleted, so 8820 is RETIRED and is never bound by
# this launcher. 8002 (dispatch) and 8004 (internal tenant-Startup envelope) went with it - both
# existed only to carry a Gateway request into a service.
#
# The two PUBLIC edges take 8830 / 8831: outside 8080-8088 (the isolated smoke map) and outside
# 8001-8005 (the internal map), so a public port can never be confused with an internal one.
$PORT_AUTH              = 8001
$PORT_CONTROL_READ      = 8003
$PORT_EDGE_AUDIT        = 8005
$PORT_PUBLIC_STARTUP    = 8830
$PORT_PUBLIC_WORKSPACE  = 8831

# Ports this launcher binds. Busy => refuse to start (a second copy of an edge is never wanted).
# The public Startup edge is listed unconditionally: if something is already on 8830 the launcher
# must refuse whether or not this run intends to start that edge.
$STANDING_PORTS = @($PORT_AUTH, $PORT_CONTROL_READ, $PORT_EDGE_AUDIT, $PORT_PUBLIC_STARTUP, $PORT_PUBLIC_WORKSPACE)

# Ports this launcher does NOT bind but MUST look at. 8820 was the standing API Gateway port and
# 8080 the port the repository's historical operator documentation used for it; a listener on
# either after the Gateway was deleted means a stale Gateway process from a pre-removal worktree is
# still up, and the frontend may be talking to it instead of the public edges. 8002 / 8004 are the
# two deleted internal transports, for the same reason. 8000 is uvicorn's own CLI default and
# catches a hand-started edge that forgot --port. Advisory, not fatal: none of these ports belongs
# to this topology, so refusing to start would be a false blocker (8080 is also an ordinary
# dev-server port).
$COLLISION_ADVISORY_PORTS = @(8820, 8080, 8002, 8004, 8000)

# ------------------------------------------------------------------------ ACTIVATION SELECTORS --
# The four selectors below are DELIBERATELY NOT SET in the default standing profile. They are
# present here as pinned, reviewed, one-switch-away configuration - which is the whole point: the
# governed values are recorded so activation is a reviewed flip, not an invention.
#
#   SP2_CP_CONTROL_STORE=postgres                       -> Control Plane reads the real Control DB
#   SP2_CP_CONTROL_STORE_DSN_REF=<reference name only>  -> which secret REFERENCE that store binds
#   SP2_EDGE_AUDIT_SINK_BASE_URL=http://127.0.0.1:8005  -> public edges write durable audit rows
#
# There is deliberately NO fourth selector. Under the Gateway the tenant data plane was wired by
# SP2_GW_TENANT_STARTUP_BASE_URL; the public Startup edge holds the executor in-process, so the
# equivalent control is whether that edge is started at all (-EnableTenantDataPlane).
#
# Running a process with any of them active produces persistent standing state and is GATE-B work
# (classes M11 / M12 / M14). Gate A authorises this file to CONTAIN them; it does not authorise
# running with them on. Each is behind an explicit -Enable* switch that defaults to off, and the
# banner states which posture is live.
#
# NO RAW DSN, PASSWORD, TOKEN OR CREDENTIAL VALUE MAY EVER BE ADDED TO THIS FILE. References and
# variable NAMES only.
$SELECTOR_CONTROL_STORE_VALUE = "postgres"
$SELECTOR_AUDIT_SINK_URL      = "http://127.0.0.1:$PORT_EDGE_AUDIT"

# ============================================================================= WORKTREE PINNING ==
if ([string]::IsNullOrWhiteSpace($BackendPath)) {
    # backend/tools/local/ -> backend/. Resolved from THIS file, so the launcher always drives the
    # worktree it is committed in.
    $BackendPath = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
} else {
    $BackendPath = (Resolve-Path $BackendPath).Path
}

$VenvActivate = Join-Path $BackendPath ".venv\Scripts\Activate.ps1"
$Issuer       = "$KeycloakBase/realms/$Realm"
$CertsUrl     = "$Issuer/protocol/openid-connect/certs"
$Aw1Tool      = Join-Path $BackendPath "tests\control_plane\requires_pg\aw1_gateway_audit_writer.py"

function Test-Port {
    param([int]$Port)
    (Test-NetConnection 127.0.0.1 -Port $Port -WarningAction SilentlyContinue).TcpTestSucceeded
}

Write-Host ""
Write-Host "SnackPortal2 standing backend - LOCAL / NON-PRODUCTION" -ForegroundColor Cyan
Write-Host "  backend worktree : $BackendPath"
try {
    $sha = (& git -C $BackendPath rev-parse HEAD 2>$null)
    $ref = (& git -C $BackendPath rev-parse --abbrev-ref HEAD 2>$null)
    if ($sha) { Write-Host "  git              : $ref @ $sha" }
} catch {
    Write-Host "  git              : (not a git worktree)" -ForegroundColor Yellow
}

# ------------------------------------------------------------------------------------ checks ----
if (-not $SkipChecks) {
    Write-Host "`nChecking prerequisites..." -ForegroundColor Cyan

    if (-not (Test-Path $VenvActivate)) {
        throw "Virtual environment not found at $VenvActivate. Run: pip install -e `".[dev]`" from $BackendPath"
    }
    Write-Host "  [ok] venv found in the target worktree"

    if (-not (Test-Port 8814)) {
        throw "Keycloak is not listening on 8814. Start the sp2_kc_standing container first."
    }
    Write-Host "  [ok] Keycloak on 8814"

    foreach ($p in 5540, 5541, 5542, 5543) {
        if (-not (Test-Port $p)) {
            throw "PostgreSQL not listening on $p. Start the docker compose topology first."
        }
    }
    Write-Host "  [ok] PostgreSQL on 5540-5543"

    $busy = @($STANDING_PORTS | Where-Object { Test-Port $_ })
    if ($busy) {
        throw "Standing ports already in use: $($busy -join ', '). Stop those processes first."
    }
    Write-Host "  [ok] standing ports free ($($STANDING_PORTS -join ', '))"

    foreach ($p in $COLLISION_ADVISORY_PORTS) {
        if (Test-Port $p) {
            Write-Host "  [WARN] something is listening on $p." -ForegroundColor Yellow
            if ($p -eq 8820 -or $p -eq 8080) {
                Write-Host "         This was an API Gateway port (8820 standing, 8080 in historical operator docs)." -ForegroundColor Yellow
                Write-Host "         The API Gateway has been DELETED. A listener here is a STALE process started from" -ForegroundColor Yellow
                Write-Host "         a pre-removal worktree - and the frontend may be talking to it instead of the two" -ForegroundColor Yellow
                Write-Host "         public edges. Stop it before trusting anything this topology serves." -ForegroundColor Yellow
            } elseif ($p -eq 8002 -or $p -eq 8004) {
                Write-Host "         This was an internal Gateway-facing transport (8002 dispatch, 8004 tenant-Startup" -ForegroundColor Yellow
                Write-Host "         envelope). Both modules are DELETED, so a listener here is a stale pre-removal" -ForegroundColor Yellow
                Write-Host "         process - and 8004 in particular served an UNAUTHENTICATED envelope edge." -ForegroundColor Yellow
            } else {
                Write-Host "         8000 is uvicorn's own CLI default - a hand-started edge that omitted --port." -ForegroundColor Yellow
            }
        }
    }
    Write-Host "  [ok] collision advisory ports checked ($($COLLISION_ADVISORY_PORTS -join ', '))"
}

# ------------------------------------------------------------------------------ issuer config ----
# CRITICAL: jwks must be a dict KEYED BY kid. auth_router/jwt_validation.py does
# `issuer_cfg.jwks.get(kid)` - passing the raw {"keys":[...]} document makes every lookup miss and
# every token is rejected with unknown_kid. The composition-time validator does NOT catch this: a
# raw JWKS document passes its "non-empty object" check and only fails later at verify time, as a
# 401 with no explanation. JWKS is PUBLIC key material; no private key or secret is handled here.
Write-Host "`nFetching JWKS from Keycloak..." -ForegroundColor Cyan
$rawJwks = curl.exe -s $CertsUrl | ConvertFrom-Json
if (-not $rawJwks.keys) { throw "No keys returned from $CertsUrl" }

$jwks = @{}
foreach ($k in $rawJwks.keys) { $jwks[$k.kid] = $k }
Write-Host "  [ok] $($jwks.Count) key(s) indexed by kid"

# audience: the token carries aud as an ARRAY ["snackportal2-clm","account"]. _audience_ok handles
# the array form, so the client id is the correct value. tenant_claim: tokens from this realm carry
# NO tenant claim - tenant_context.py treats an absent claim as a control-plane-scoped principal
# with no active tenant, not as a rejection.
$issuers = @{
    $Issuer = @{
        issuer       = $Issuer
        audience     = $ClientId
        allowed_algs = @("RS256")
        jwks         = $jwks
        tenant_claim = "tenant"
    }
}
$issuersJson = ($issuers | ConvertTo-Json -Depth 20 -Compress)

# ================================================================================== THE LAUNCHER ==

function Get-StandingUvicornCommand {
    <#
      The ONE place a standing uvicorn command is composed. Every edge goes through here, so the
      canonical flag set cannot be complete on five edges and short on the sixth.
    #>
    param(
        [Parameter(Mandatory)][string]$Module,
        [Parameter(Mandatory)][int]$Port
    )
    $flags = $CANONICAL_UVICORN_FLAGS -join " "
    return "uvicorn ${Module}:create_app_from_env $flags --host $STANDING_BIND_HOST --port $Port"
}

function Start-StandingEdge {
    param(
        [Parameter(Mandatory)][string]$Title,
        [Parameter(Mandatory)][string]$Module,
        [Parameter(Mandatory)][int]$Port,
        [hashtable]$EnvVars = @{},
        # AW-1 Q8: extra wildcard patterns the child removes from its own environment before the
        # governed values are applied. Used by the Gateway-audit ingest edge only.
        [string[]]$ExtraScrubPatterns = @(),
        # Names that survive $ExtraScrubPatterns (the ingest edge's own writer secret, when the
        # durable-audit opt-in is active). Names only - the launcher never reads the value.
        [string[]]$KeepEnvNames = @()
    )

    # $ErrorActionPreference FIRST: the child's whole command string is one `;`-joined sequence, so
    # a terminating error anywhere before the uvicorn line prevents the uvicorn line running. The
    # ungoverned copy set this in the PARENT only, which is why a failed value relay there left the
    # variable unset and started uvicorn anyway.
    $lines = @(
        "`$ErrorActionPreference = 'Stop'"
        "Set-Location '$BackendPath'"
        ". '$VenvActivate'"
        "`$host.UI.RawUI.WindowTitle = '$Title'"
    )

    # ---- inherited-environment isolation -------------------------------------------------------
    # uvicorn's CLI is @click.command(context_settings={'auto_envvar_prefix': 'UVICORN'}). Click
    # resolves an explicit CLI option before its envvar, so the five flags above already win - but
    # the surface is wider than the flags: UVICORN_RELOAD, UVICORN_APP_DIR, UVICORN_INTERFACE,
    # UVICORN_LIFESPAN, UVICORN_SSL_*, UVICORN_LIMIT_* and friends have no CLI counterpart here and
    # would take effect silently. Removing the whole prefix is the only complete answer.
    #
    # SP2_* is scrubbed for the same reason and one more: it is how the standing profile guarantees
    # that SP2_DBR_ROUTING_AUDIT_BASE_URL, SP2_IMPORT_AUDIT_SINK_BASE_URL and every SP2_EDGE_* value
    # the launcher does not itself set are UNSET on every edge regardless of what the operator's
    # shell holds. Merely not assigning them would leave an inherited value live - and for
    # SP2_EDGE_AUDIT_SINK_BASE_URL an inherited value would silently activate a DURABLE transport.
    # The sweep is unconditional and nothing is ever exempted from it.
    #
    # NOTE ON MECHANISM: `Start-Process -UseNewEnvironment` is the textbook answer and is NOT used.
    # On this host (Windows PowerShell 5.1.19041) it fails the child outright with
    # "Internal Windows PowerShell error. Loading managed Windows PowerShell failed with error
    # 8009001d" - the stripped environment is missing what the CLR needs to load. Explicit,
    # enumerated scrubbing is used instead: it works, and unlike -UseNewEnvironment it is visible in
    # this file and therefore machine-checkable by the architecture guard.
    # The keep-list applies to the per-edge extra patterns only: the governed UVICORN_* / SP2_*
    # sweep is unconditional and nothing is ever exempted from it.
    $keepClause = ""
    if ($KeepEnvNames.Count -gt 0) {
        $keepList = ($KeepEnvNames | ForEach-Object { "'" + $_ + "'" }) -join ","
        $keepClause = " -and (@($keepList) -notcontains `$_.Name)"
    }
    foreach ($pattern in @("UVICORN_*", "SP2_*")) {
        $lines += "Get-ChildItem Env: | Where-Object { `$_.Name -like '$pattern' } | ForEach-Object { Remove-Item ('Env:' + `$_.Name) -Force }"
    }
    foreach ($pattern in $ExtraScrubPatterns) {
        $lines += "Get-ChildItem Env: | Where-Object { `$_.Name -like '$pattern'$keepClause } | ForEach-Object { Remove-Item ('Env:' + `$_.Name) -Force }"
    }

    # ---- governed values -----------------------------------------------------------------------
    # Values are relayed through temp files rather than the command line: PowerShell strips double
    # quotes out of a JSON string when it crosses a Start-Process boundary, which turns
    # SP2_AR_ISSUERS into invalid JSON and the edge rejects it. Short URL values survive inline, but
    # one mechanism for everything avoids the trap. Every relayed value is validated non-blank in
    # the child, so a dropped relay aborts the window instead of starting a misconfigured edge.
    foreach ($k in $EnvVars.Keys) {
        $tmp = Join-Path $env:TEMP "sp2_$($Title -replace '\W','_')_$k.txt"
        Set-Content -Path $tmp -Value $EnvVars[$k] -NoNewline -Encoding UTF8
        $lines += "`$env:$k = (Get-Content '$tmp' -Raw)"
        $lines += "Remove-Item '$tmp' -Force -ErrorAction SilentlyContinue"
        $lines += "if ([string]::IsNullOrWhiteSpace(`$env:$k)) { throw 'sp2-launcher: $k relayed BLANK for $Title - refusing to start a misconfigured edge' }"
    }

    $lines += (Get-StandingUvicornCommand -Module $Module -Port $Port)

    Start-Process powershell -ArgumentList @(
        "-NoExit", "-Command", ($lines -join "; ")
    )
    Write-Host "  starting $Title on $Port" -ForegroundColor DarkGray
}

# ============================================================================ POSTURE RESOLUTION ==

$controlUrl = "http://127.0.0.1:$PORT_CONTROL_READ"

# Control Plane read edge. Gate-A default: NO SP2_CP_CONTROL_STORE at all, which composes the
# documented in-memory, TEST-ONLY store. A listening socket on 8003 is therefore NOT evidence that
# the physical Control database is the authority behind it - verify the posture before treating any
# read as authoritative.
$controlReadEnv = @{}
if ($EnableDurableControlStore) {
    $controlReadEnv["SP2_CP_CONTROL_STORE"]         = $SELECTOR_CONTROL_STORE_VALUE
    $controlReadEnv["SP2_CP_CONTROL_STORE_DSN_REF"] = $ControlStoreDsnRef
}

# Operational-audit ingest edge (AW-1), still named for the frozen Control-DB table it writes
# (control_gateway_audit, DDL 012/013 - separately governed, not renamed here). This edge is
# durable BY CONSTRUCTION -
# build_gateway_audit_store_from_env has no in-memory branch and never consults
# SP2_CP_CONTROL_STORE. With no reference set it binds the DEFAULT ref control/control-store-dsn,
# which by standing convention resolves to the sp2_local SUPERUSER DSN - so an ordinary operator
# session that exported the superuser material made a superuser audit-write path live rather than
# theoretical. That is exactly the condition AW-1 exists to eliminate.
#
# Gate-A posture, deliberate and a behavioural change from the ungoverned copy: the ingest edge
# starts with an AW-1 Q8-scoped environment carrying NO SNACKPORTAL_SECRET_* material, no
# SNACKPORTAL_SECRET_DIR, no SNACKPORTAL_TENANT_SECRET_*, and no libpq PG* variable. Composition is
# lazy, so the edge binds 8005 and then FAILS CLOSED at first store use. It cannot write with the
# superuser credential. Nothing routes to it under Gate A anyway (the public edges'
# SP2_EDGE_AUDIT_SINK_BASE_URL is unset), so no journey regresses.
$ingestScrub = @("SNACKPORTAL_SECRET_*", "SNACKPORTAL_TENANT_SECRET*", "PG*")
$ingestKeep  = @()
$ingestEnv   = @{}
if ($EnableDurableEdgeAudit) {
    # AW-1 sec.11 S-3(a) PRIMARY control, checked FIRST because it needs no database at all.
    # psycopg.connect("") does NOT fail - it falls back to libpq connection defaults: the PG*
    # environment variables, then localhost:5432, the OS user's name as the role, and a ~/.pgpass
    # lookup. env_reference_secret_store.py returns the variable's value with no strip and no blank
    # check, so a set-but-empty writer variable resolves to "" and connects SOMEWHERE, chosen by
    # nobody, as an identity nobody reviewed. Unset, empty and whitespace-only are all refusals.
    #
    # PRESENCE ONLY. The value is tested for blankness in place and is never read into a variable,
    # never printed, never relayed to a child, and never written anywhere. The ingest child inherits
    # it directly through $ingestKeep / -KeepEnvNames; it does not transit this script.
    if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($EdgeAuditWriterSecretVar))) {
        throw "AW-1 S-3(a): $EdgeAuditWriterSecretVar is unset, empty or whitespace-only - refusing to start the operational-audit ingest edge on $PORT_EDGE_AUDIT. A blank credential does not fail closed at psycopg: it falls back to libpq defaults and connects somewhere nobody chose. (Presence only - no value was read out or printed.)"
    }
    Write-Host "`nAW-1 S-3(a): writer secret MATERIAL present and non-blank (presence only)" -ForegroundColor Cyan

    # AW-1 sec.9 O-6 -> O-7 start gate: the writer role/grant/credential state must be confirmed
    # BEFORE the ingest edge starts. A red status means the least-privilege writer is not in the
    # state AW-1 requires, and starting anyway is how an ungoverned identity ends up writing.
    if (-not (Test-Path $Aw1Tool)) {
        throw "AW-1 start gate: operator tool not found at $Aw1Tool - refusing to start the ingest edge."
    }
    Write-Host "`nAW-1 start gate (sec.9 O-6): checking the least-privilege writer state..." -ForegroundColor Cyan
    & (Join-Path $BackendPath ".venv\Scripts\python.exe") $Aw1Tool status
    if ($LASTEXITCODE -ne 0) {
        throw "AW-1 start gate FAILED (exit $LASTEXITCODE): refusing to start the operational-audit ingest edge on 8005."
    }
    Write-Host "  [ok] AW-1 status reports the writer state is as required"

    $ingestKeep = @($EdgeAuditWriterSecretVar)
    $ingestEnv["SP2_CP_CONTROL_STORE_DSN_REF"] = $EdgeAuditWriterDsnRef
}

# The two PUBLIC edges. Both consume the SAME IC-005 authenticate base URL - deliberately one name
# for one thing - and the SAME exact-origin CORS allowlist. Neither has a loopback default for the
# audit sink: a default would silently activate a durable transport.
#
# SP2_EDGE_ALLOWED_ORIGINS is REQUIRED for any browser client. Unset means an EMPTY allowlist and
# every cross-origin request is denied. The failure mode is silent: the edge answers the CORS
# preflight OPTIONS with 204, the browser then never sends the real request, and nothing appears in
# any server log. Exact match - the "localhost" spelling fails against a "127.0.0.1" origin.
$publicEdgeEnv = @{
    SP2_EDGE_AUTH_ROUTER_BASE_URL = "http://127.0.0.1:$PORT_AUTH"
    SP2_EDGE_ALLOWED_ORIGINS      = $FrontendOrigin
}
if ($EnableDurableEdgeAudit) { $publicEdgeEnv["SP2_EDGE_AUDIT_SINK_BASE_URL"] = $SELECTOR_AUDIT_SINK_URL }

# The Startup edge additionally needs the routing-association read (the Database Router's own
# pre-existing selector). It is the ROUTER gate: with it set, the edge composes
# TenantStartupOperations in-process, which IS the tenant data plane.
$startupEdgeEnv = $publicEdgeEnv.Clone()
$startupEdgeEnv["SP2_DBR_ROUTING_READ_BASE_URL"] = $controlUrl

# The Workspace edge reads the Control DB through the SAME posture the read edge uses.
$workspaceEdgeEnv = $publicEdgeEnv.Clone()
if ($EnableDurableControlStore) {
    $workspaceEdgeEnv["SP2_CP_CONTROL_STORE"]         = $SELECTOR_CONTROL_STORE_VALUE
    $workspaceEdgeEnv["SP2_CP_CONTROL_STORE_DSN_REF"] = $ControlStoreDsnRef
}

Write-Host "`nStanding posture for this run:" -ForegroundColor Cyan
Write-Host ("  Control store        : {0}" -f $(if ($EnableDurableControlStore) { "postgres (DURABLE - Gate-B class M12)" } else { "UNSET -> in-memory, TEST-ONLY" }))
Write-Host ("  Durable edge audit   : {0}" -f $(if ($EnableDurableEdgeAudit) { "ON (DURABLE WRITES - Gate-B class M11)" } else { "OFF - sink unwired, ingest edge fails closed" }))
Write-Host ("  Tenant data plane    : {0}" -f $(if ($EnableTenantDataPlane) { "ON (public Startup edge STARTED - Gate-B class M14)" } else { "OFF - public Startup edge NOT started" }))
if ($EnableDurableControlStore -or $EnableDurableEdgeAudit -or $EnableTenantDataPlane) {
    Write-Host "  >> At least one activation selector is ON. This produces PERSISTENT STANDING STATE." -ForegroundColor Yellow
    Write-Host "  >> That is Gate-B work. Confirm you hold that authorization before continuing." -ForegroundColor Yellow
}

# =================================================================================== START ORDER ==
# A service's bound URL becomes the next service's selector value. Control Plane read first, since
# the Auth Router and the public Startup edge both point at it; the two PUBLIC edges last, since
# each needs the Auth Router bound.

Write-Host "`nStarting standing edges..." -ForegroundColor Cyan

Start-StandingEdge -Title "control_plane $PORT_CONTROL_READ" `
    -Module "control_plane.adapters.providers.http_read_api" `
    -Port $PORT_CONTROL_READ `
    -EnvVars $controlReadEnv

Start-Sleep -Seconds 3
if (-not (Test-Port $PORT_CONTROL_READ)) {
    throw "control_plane failed to start on $PORT_CONTROL_READ. Check its window."
}

Start-StandingEdge -Title "edge_audit $PORT_EDGE_AUDIT" `
    -Module "control_plane.adapters.providers.http_gateway_audit_api" `
    -Port $PORT_EDGE_AUDIT `
    -EnvVars $ingestEnv `
    -ExtraScrubPatterns $ingestScrub `
    -KeepEnvNames $ingestKeep

Start-StandingEdge -Title "auth_router $PORT_AUTH" `
    -Module "auth_router.adapters.providers.http_authenticate_api" `
    -Port $PORT_AUTH `
    -EnvVars @{
        SP2_AR_CONTROL_PLANE_READ_BASE_URL = $controlUrl
        SP2_AR_ISSUERS                     = $issuersJson
    }

Start-Sleep -Seconds 3

# --- the PUBLIC edges -------------------------------------------------------------------------
# 127.0.0.1 by construction (Get-StandingUvicornCommand pins --host $STANDING_BIND_HOST). Exposure
# is a deliberate act at a reverse proxy; nothing here opens one.
Start-StandingEdge -Title "public_workspace $PORT_PUBLIC_WORKSPACE" `
    -Module "control_plane.adapters.providers.http_public_workspace_edge" `
    -Port $PORT_PUBLIC_WORKSPACE `
    -EnvVars $workspaceEdgeEnv

if ($EnableTenantDataPlane) {
    Start-StandingEdge -Title "public_startup $PORT_PUBLIC_STARTUP" `
        -Module "database_router.adapters.providers.http_public_startup_edge" `
        -Port $PORT_PUBLIC_STARTUP `
        -EnvVars $startupEdgeEnv
} else {
    Write-Host "  SKIPPING public_startup on $PORT_PUBLIC_STARTUP (-EnableTenantDataPlane is off)" -ForegroundColor DarkGray
    Write-Host "  The public Startup edge holds TenantStartupOperations IN-PROCESS: starting it IS the" -ForegroundColor DarkGray
    Write-Host "  tenant data plane (Gate-B class M14). There is no 'started but unwired' posture for it." -ForegroundColor DarkGray
}

# ======================================================================================= VERIFY ==
Write-Host "`nWaiting for services to bind..." -ForegroundColor Cyan
Start-Sleep -Seconds 5

$expected = [ordered]@{
    "auth_router"      = $PORT_AUTH
    "control_plane"    = $PORT_CONTROL_READ
    "edge_audit"       = $PORT_EDGE_AUDIT
    "public_workspace" = $PORT_PUBLIC_WORKSPACE
}
if ($EnableTenantDataPlane) { $expected["public_startup"] = $PORT_PUBLIC_STARTUP }

Write-Host ""
$failed = @()
foreach ($name in $expected.Keys) {
    $port = $expected[$name]
    if (Test-Port $port) {
        Write-Host ("  {0,-18} {1}  UP" -f $name, $port) -ForegroundColor Green
    } else {
        Write-Host ("  {0,-18} {1}  DOWN" -f $name, $port) -ForegroundColor Red
        $failed += $name
    }
}

if ($failed) {
    Write-Host "`nFailed: $($failed -join ', '). Check those windows for the fail-closed message." -ForegroundColor Red
    exit 1
}

# A listening socket proves a bind, not a composition. /health proves the edge composed.
Write-Host ""
try {
    $health = curl.exe -s "http://127.0.0.1:$PORT_PUBLIC_WORKSPACE/health" | ConvertFrom-Json
    Write-Host "  workspace edge health: $($health.status) (build_phase $($health.build_phase))" -ForegroundColor Green
} catch {
    Write-Host "  workspace edge health check failed" -ForegroundColor Yellow
}
if ($EnableTenantDataPlane) {
    try {
        $health = curl.exe -s "http://127.0.0.1:$PORT_PUBLIC_STARTUP/health" | ConvertFrom-Json
        Write-Host "  startup edge health  : $($health.status) (build_phase $($health.build_phase))" -ForegroundColor Green
    } catch {
        Write-Host "  startup edge health check failed" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "  A listening socket is NOT evidence a database is reachable. The Control Plane read" -ForegroundColor DarkGray
Write-Host "  edge and the audit ingest edge bind reference-only secrets and resolve them LAZILY at" -ForegroundColor DarkGray
Write-Host "  first store use - a bad or absent reference surfaces on the first request, not here." -ForegroundColor DarkGray

Write-Host @"

Standing edges running (Gateway-free topology).

  Frontend    cd <frontend worktree>; bun run dev -- --port 5173
  Workspace   http://127.0.0.1:$PORT_PUBLIC_WORKSPACE      GET /memberships
  Startup     http://127.0.0.1:$PORT_PUBLIC_STARTUP      GET|PATCH /tenant/startups/<ref>   (only with -EnableTenantDataPlane)

  Standing map   auth 8001 / control-read 8003 / edge-audit 8005 /
                 PUBLIC startup 8830 / PUBLIC workspace 8831
  RETIRED        8820 (API Gateway), 8002 (dispatch), 8004 (internal tenant-Startup envelope) -
                 all three deleted. A listener on any of them is a STALE pre-removal process.
  NOT this map   8080-8088 is ISOLATED SMOKE / VERIFICATION ONLY (tests/deployment/
                 native_uvicorn_process_smoke.py). Never start a standing edge on 8080.

  TWO public surfaces now, not one: the reverse proxy needs two upstreams, two TLS bindings and
  the same exact-origin CORS allowlist on both.

To stop: close the service windows, or
  Get-Process powershell | Where-Object MainWindowTitle -match '^(auth_router|control_plane|edge_audit|public_startup|public_workspace) ' | Stop-Process

"@ -ForegroundColor Cyan
