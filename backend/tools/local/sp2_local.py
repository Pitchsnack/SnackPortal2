"""SnackPortal2 local-development operator command (Stage 6).

    python -m tools.local.sp2_local <command>

The supported command set for running the Option A rebuild locally from a fresh checkout:

    init-env    generate an untracked env file with fresh local throwaway values
    migrate     apply the accepted migration chains to the four local databases
    seed        write the minimum Control-database rows a real request needs
    bootstrap   migrate, then seed
    idp-up      start the local identity provider and pin its realm key as the trust anchor
    verify      prove all fourteen services are up and that only the BFF is published
    smoke       run one real authenticated Startup flow and prove physical tenant isolation

**Why this exists.** Before Stage 6 the only code that applied the migration chains was a pytest
helper inside the Stage 4 live-PostgreSQL harness, and the only code that created a Control tenant
row was a single live test module. A developer with a fresh checkout had nothing to run — and
requiring them to invoke a test harness to create their databases makes the test harness load
bearing for operations, which is how a harness stops being free to change.

**What it is not.** Not a migration framework, not a second source of DDL, and not a runtime
component. It applies the SAME files, in the SAME order, that the Stage 4 harness proved; the
order is derived here by the same globbing rule rather than by a hand-written list, so a migration
added later is picked up instead of being silently skipped by a stale constant.

**Secret handling.** A DSN is assembled, handed to the driver, and never printed. Every
diagnostic names a *target* (``control``, ``acme``) and never a connection string; ``redact()``
exists for the cases where a scheme and database name genuinely help.

Pure stdlib plus the PostgreSQL driver. No service module is imported: the tool is a database and
process operator, and giving it a service import would make the service graph depend on which
tools happen to exist.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import http.cookiejar
import json
import os
import re
import secrets
import subprocess
import sys
import textwrap
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple
from urllib.parse import parse_qs, urlencode, urlparse, urlsplit, urlunsplit

# --- repository geography --------------------------------------------------------------------

#: ``backend/tools/local/sp2_local.py`` -> the repository root.
REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = REPO_ROOT / "backend"
DOCKER_DIR = REPO_ROOT / "infrastructure" / "docker"

COMPOSE_FILE = DOCKER_DIR / "docker-compose.rebuild.yml"
ENV_TEMPLATE = DOCKER_DIR / ".env.rebuild.template"
ENV_FILE = DOCKER_DIR / ".env.rebuild"

#: The compose project name, declared by the manifest's own ``name:`` key. Named volumes are
#: prefixed with it, so removing one by name needs this to be right; a test asserts it matches.
COMPOSE_PROJECT = "snackportal2-rebuild-local"

#: The legacy DDL corpus, reused unchanged by the rebuild (``backend/migrations/README.md``).
INFRA_DB = REPO_ROOT / "infrastructure" / "db"

#: The rebuild's own migrations. Migration M-1 lives here.
REBUILD_MIGRATIONS = BACKEND_ROOT / "migrations"

# --- the local topology ----------------------------------------------------------------------

#: Tenant reference -> the local database name. The tenant reference is the signed claim's value
#: and the registry key; the database name is a local fact and appears nowhere in a contract.
TENANTS: Mapping[str, str] = {
    "acme": "snackportal2_tenant_acme",
    "zeta": "snackportal2_tenant_zeta",
    "nova": "snackportal2_tenant_nova",
}

CONTROL_DATABASE = "snackportal2_control"

#: Host-side port variables, with the defaults the compose file publishes.
PORT_VARIABLES: Mapping[str, Tuple[str, int]] = {
    "control": ("SP2_LOCAL_PG_PORT_CONTROL", 5550),
    "acme": ("SP2_LOCAL_PG_PORT_ACME", 5551),
    "zeta": ("SP2_LOCAL_PG_PORT_ZETA", 5552),
    "nova": ("SP2_LOCAL_PG_PORT_NOVA", 5553),
}

#: The fourteen services, their compose service names, and their container ports. Kept here rather
#: than imported from ``snackportal2.shared.config`` so this tool has no service dependency;
#: ``tests/snackportal2/test_stage6_local_launch.py`` asserts the two agree, which is the check
#: that makes the duplication safe rather than merely tolerated.
SERVICES: Sequence[Tuple[str, int]] = (
    ("bff", 8000),
    ("authentication", 8001),
    ("access-control", 8002),
    ("control-plane", 8003),
    ("database-router", 8004),
    ("startups", 8005),
    ("investors", 8006),
    ("deals", 8007),
    ("sharing", 8008),
    ("import-service", 8009),
    ("lineage", 8010),
    ("contacts", 8011),
    ("ai-agents", 8012),
    ("audit", 8013),
)

#: The one service that may be published (IC-013 §21.1 E-1).
PUBLIC_SERVICE = "bff"

BFF_BASE_URL = "http://127.0.0.1:8000"

#: Compose service names that are databases rather than application services. The exposure rule
#: speaks of a public *application* ingress; a loopback-published local PostgreSQL is neither.
INFRASTRUCTURE_SERVICE = re.compile(r"(postgres|redis|minio|mailhog|keycloak|jaeger|prometheus)", re.IGNORECASE)

# --- the seed ----------------------------------------------------------------------------------

#: The secret-store reference registered for each tenant's database association (D-14: a
#: reference, never a credential). The Database Router turns this pair into the environment
#: variable name it looks the DSN up under, so these values and the compose file's
#: ``SP2_TENANT_DSN_ASSOC_<TENANT>_1`` entries are two halves of one fact.
ASSOCIATION_VERSION = "1"

#: The tenant schema version the provisioning chain records in ``schema_version``.
EXPECTED_SCHEMA_VERSION = "1"

#: The synthetic local principals. Clearly local, clearly not people: no name, no email, no PII,
#: and no resemblance to a production identity. Each is bound to exactly one tenant, so the ACME
#: principal cannot reach ZETA and the isolation check has something real to prove.
SEED_MEMBERSHIPS: Sequence[Tuple[str, str, str]] = (
    ("local-agent-acme", "acme", "TENANT_AGENT"),
    ("local-agent-zeta", "zeta", "TENANT_AGENT"),
    ("local-agent-nova", "nova", "TENANT_AGENT"),
)

#: Two global directory records, so the Control-resident directory reads and the Import operation
#: have something to return. Deliberately fictional companies.
SEED_DIRECTORY: Sequence[Tuple[str, str, str]] = (
    ("GlobalStartupDirectory", "gs-local-001", "Northwind Analytics"),
    ("GlobalStartupDirectory", "gs-local-002", "Harbourline Robotics"),
    ("GlobalInvestorDirectory", "gi-local-001", "Fenwick Ventures"),
)

#: Local development token variables -> the principal each is bound to, for `init-env` and for the
#: runbook. The binding itself is made in the compose file, which assembles the verifier map.
TOKEN_VARIABLES: Mapping[str, str] = {
    "SP2_LOCAL_TOKEN_ACME_AGENT": "local-agent-acme",
    "SP2_LOCAL_TOKEN_ZETA_AGENT": "local-agent-zeta",
    "SP2_LOCAL_TOKEN_NOVA_AGENT": "local-agent-nova",
    "SP2_LOCAL_TOKEN_CONTROL": "local-operator-control",
}

# --- the local identity provider (Stage 6A) ----------------------------------------------------
#
# These are FACTS about the local realm, not knobs. Each one also appears in the committed realm
# template, and `tests/snackportal2/test_stage6_local_launch.py` asserts the two agree — the same
# "duplication made safe by a check" arrangement the service list above uses. A knob would invite
# a value to be changed in one place and not the other, and the failure mode is a browser that
# authenticates and a backend that rejects, with nothing in either log saying why.

#: The committed realm template, and the generated file the container actually imports.
KEYCLOAK_DIR = DOCKER_DIR / "keycloak"
REALM_TEMPLATE = KEYCLOAK_DIR / "realm-sp2-local.template.json"
REALM_IMPORT_DIR = KEYCLOAK_DIR / "import"
REALM_FILE = REALM_IMPORT_DIR / "realm-sp2-local.json"

IDP_SERVICE = "keycloak"
IDP_REALM = "sp2-local"
IDP_CLIENT_ID = "sp2-local-web"

#: The audience the realm stamps into every access token, and the one the pinned anchor requires.
IDP_AUDIENCE = "snackportal2-bff"

#: The frontend dev server's origin, and the exact registered callback. Byte-equality matters:
#: an authorization request whose `redirect_uri` differs by one character is refused by the IdP.
FRONTEND_ORIGIN = "http://localhost:5173"
IDP_REDIRECT_URI = FRONTEND_ORIGIN + "/sp2-gateway/callback"

#: The optional client scope that mints a tenant-scoped token. Requesting one is not permission to
#: use it: the claim is a routing input, and membership is decided by Access Control.
IDP_TENANT_SCOPE_PREFIX = "sp2:tenant:"

#: Only RS256 is enabled on the realm, and the verifier accepts asymmetric algorithms only.
IDP_ALGORITHM = "RS256"

#: Placeholder in the committed realm template -> the env variable that replaces it. The template
#: is committed and therefore carries no usable credential; `init-env` renders the real file.
IDP_PASSWORD_PLACEHOLDERS: Mapping[str, str] = {
    "__SP2_LOCAL_IDP_PASSWORD_ACME__": "SP2_LOCAL_IDP_PASSWORD_ACME",
    "__SP2_LOCAL_IDP_PASSWORD_ZETA__": "SP2_LOCAL_IDP_PASSWORD_ZETA",
    "__SP2_LOCAL_IDP_PASSWORD_NOVA__": "SP2_LOCAL_IDP_PASSWORD_NOVA",
    "__SP2_LOCAL_IDP_PASSWORD_CONTROL__": "SP2_LOCAL_IDP_PASSWORD_CONTROL",
}

#: Login name -> (principal reference == Keycloak user id == `sub`, password variable, tenant).
#: The Keycloak user id is pinned to the principal reference in the realm template, which is what
#: makes the OIDC identity and the seeded Control-database membership the same principal without
#: changing the seed. `None` marks the tenantless CONTROL operator, which holds no membership.
IDP_IDENTITIES: Mapping[str, Tuple[str, str, Optional[str]]] = {
    "acme-agent": ("local-agent-acme", "SP2_LOCAL_IDP_PASSWORD_ACME", "acme"),
    "zeta-agent": ("local-agent-zeta", "SP2_LOCAL_IDP_PASSWORD_ZETA", "zeta"),
    "nova-agent": ("local-agent-nova", "SP2_LOCAL_IDP_PASSWORD_NOVA", "nova"),
    "control-operator": ("local-operator-control", "SP2_LOCAL_IDP_PASSWORD_CONTROL", None),
}

#: The Authentication Service's pinned-issuer variable. Written by `idp-up`, never by hand.
ENV_AUTHENTICATION_ISSUERS = "SP2_AUTHENTICATION_ISSUERS"

#: Variables `init-env` fills with freshly generated local throwaway values.
GENERATED_VARIABLES: Sequence[str] = (
    "SP2_LOCAL_PG_PASSWORD",
    "SP2_INTERNAL_SERVICE_CREDENTIAL",
    "SP2_STARTUPS_SERVICE_CREDENTIAL",
    "SP2_INVESTORS_SERVICE_CREDENTIAL",
    "SP2_DEALS_SERVICE_CREDENTIAL",
    "SP2_LINEAGE_SERVICE_CREDENTIAL",
    "SP2_IMPORT_SERVICE_SERVICE_CREDENTIAL",
    "SP2_LINEAGE_KEY_ACME",
    "SP2_LINEAGE_KEY_ZETA",
    "SP2_LINEAGE_KEY_NOVA",
    "SP2_LOCAL_TOKEN_ACME_AGENT",
    "SP2_LOCAL_TOKEN_ZETA_AGENT",
    "SP2_LOCAL_TOKEN_NOVA_AGENT",
    "SP2_LOCAL_TOKEN_CONTROL",
    "SP2_LOCAL_IDP_ADMIN_PASSWORD",
    "SP2_LOCAL_IDP_PASSWORD_ACME",
    "SP2_LOCAL_IDP_PASSWORD_ZETA",
    "SP2_LOCAL_IDP_PASSWORD_NOVA",
    "SP2_LOCAL_IDP_PASSWORD_CONTROL",
)


class LocalError(RuntimeError):
    """A failure a developer can act on. Never carries a DSN, a password or a token."""


# --- output --------------------------------------------------------------------------------


def say(message: str) -> None:
    print(message, flush=True)


def step(message: str) -> None:
    say("  -> " + message)


def redact(value: str) -> str:
    """A DSN reduced to something safe to print: scheme and database path only."""
    parts = urlsplit(value)
    return urlunsplit((parts.scheme, "<redacted>", parts.path, "", ""))


# --- environment ------------------------------------------------------------------------------


def parse_env_file(text: str) -> Dict[str, str]:
    """Parse ``KEY=VALUE`` lines. Comments and blanks ignored; no interpolation, no export."""
    values: Dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def load_env(path: Path = ENV_FILE) -> Dict[str, str]:
    """The local env file, with real environment variables taking precedence.

    Precedence matters for CI and for one-off overrides: an exported value should win over a file
    a developer edited three weeks ago, not the other way round.
    """
    if not path.exists():
        raise LocalError("no local environment file at " + str(path) + "\n     Create one with:  python -m tools.local.sp2_local init-env")
    values = parse_env_file(path.read_text(encoding="utf-8"))
    for key in list(values):
        override = os.environ.get(key)
        if override is not None and override != "":
            values[key] = override
    return values


def require(env: Mapping[str, str], key: str) -> str:
    value = env.get(key, "").strip()
    if not value:
        raise LocalError(key + " is not set in " + str(ENV_FILE))
    return value


def host_dsn(env: Mapping[str, str], target: str) -> str:
    """The host-side DSN for one target. Assembled here; never stored, never printed."""
    if target != "control" and target not in TENANTS:
        raise LocalError("unknown target " + repr(target))
    variable, default_port = PORT_VARIABLES[target]
    user = env.get("SP2_LOCAL_PG_USER", "").strip() or "sp2_local"
    password = require(env, "SP2_LOCAL_PG_PASSWORD")
    host = env.get("SP2_LOCAL_PG_HOST", "").strip() or "127.0.0.1"
    port = env.get(variable, "").strip() or str(default_port)
    database = CONTROL_DATABASE if target == "control" else TENANTS[target]
    return "postgresql://" + user + ":" + password + "@" + host + ":" + port + "/" + database


# --- the driver ---------------------------------------------------------------------------------


def _driver() -> Any:
    """The PostgreSQL driver, resolved at call time.

    Located at call time rather than imported at module scope so that ``init-env`` — the one
    command a developer runs before anything is installed or running — works without it.
    """
    try:
        import psycopg
    except ImportError as exc:  # pragma: no cover - environment failure, not logic
        raise LocalError("the PostgreSQL driver is not installed. Run:  pip install -e .[dev]  from backend/") from exc
    return psycopg


def connect(dsn: str, *, autocommit: bool = False) -> Any:
    """Open one connection. The DSN enters here and does not leave."""
    connection = _driver().connect(dsn, connect_timeout=10)
    if autocommit:
        connection.autocommit = True
    return connection


def execute(dsn: str, statement: str, params: Tuple[object, ...] = ()) -> None:
    with connect(dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(statement, params)


def query(dsn: str, statement: str, params: Tuple[object, ...] = ()) -> List[Tuple[Any, ...]]:
    with connect(dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(statement, params)
            return [tuple(row) for row in cursor.fetchall()]


# --- migration chains ------------------------------------------------------------------------


def _sorted_sql(directory: Path) -> List[Path]:
    return sorted(directory.glob("*.sql")) if directory.is_dir() else []


def control_chain() -> List[Path]:
    """The Control-database chain: the legacy corpus first, then the rebuild's own (M-1).

    Built by globbing rather than by a hand-written list so a migration added later is picked up
    automatically instead of being silently skipped by a stale constant. This is the same rule the
    accepted Stage 4 harness uses, and a test asserts the two produce the identical list.
    """
    return _sorted_sql(INFRA_DB / "control") + _sorted_sql(REBUILD_MIGRATIONS / "control")


def tenant_chain() -> List[Path]:
    """The tenant-database chain.

    Order matters and is not alphabetical across directories: provisioning bootstraps the
    schema-version marker the Control Plane's readiness concept reads, the tenant business tables
    come next, and lineage last because the lineage and import bookkeeping tables are what the
    Import and Lineage services read. ``deals`` carries an intra-tenant foreign key to ``startups``
    and ``investors``, so 005 must not precede 003/004 — the numeric sort within each directory
    already guarantees that.
    """
    return (
        _sorted_sql(INFRA_DB / "provisioning")
        + _sorted_sql(INFRA_DB / "tenant")
        + _sorted_sql(REBUILD_MIGRATIONS / "tenant")
        + _sorted_sql(INFRA_DB / "lineage")
    )


def apply_chain(dsn: str, files: Sequence[Path], label: str) -> List[str]:
    """Apply one chain, one transaction per file.

    One transaction per file rather than one for the whole chain: that is how a real migration
    runner behaves, and it means a mid-chain failure names the file that failed instead of rolling
    back the evidence of the files that succeeded.

    Fails closed and names the database and the file — never the DSN.
    """
    applied: List[str] = []
    for path in files:
        try:
            with connect(dsn) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise LocalError(
                "migration FAILED on database '" + label + "' at file " + path.name + "\n     " + str(exc).strip().splitlines()[0]
            ) from None
        applied.append(path.name)
    return applied


def reset_database(dsn: str, label: str) -> None:
    """Return one database to zero so a chain application is genuinely from scratch.

    ``DROP SCHEMA ... CASCADE`` removes tables, triggers and functions together. The append-only
    triggers guard UPDATE/DELETE/TRUNCATE, not DROP, so this is not a way to mutate an audit trail
    — it destroys a whole disposable local database's schema, and is only ever pointed at one.
    """
    try:
        with connect(dsn, autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute("DROP SCHEMA IF EXISTS public CASCADE")
                cursor.execute("DROP SCHEMA IF EXISTS dv_sentinel CASCADE")
                cursor.execute("CREATE SCHEMA public")
    except Exception as exc:
        raise LocalError("reset FAILED on database '" + label + "'\n     " + str(exc).strip().splitlines()[0]) from None


# --- the local identity provider (Stage 6A) -----------------------------------------------------


def idp_origin(env: Mapping[str, str]) -> str:
    """The origin the identity provider is published on, and stamps into every ``iss``."""
    return (env.get("SP2_LOCAL_IDP_ISSUER_ORIGIN", "").strip() or "http://localhost:8090").rstrip("/")


def idp_issuer(env: Mapping[str, str]) -> str:
    """The exact `iss` claim value. This string is the key of the pinned trust anchor."""
    return idp_origin(env) + "/realms/" + IDP_REALM


def render_realm_file(env: Mapping[str, str]) -> Path:
    """Render the committed realm template into the untracked file the container imports.

    The template is committed and carries password PLACEHOLDERS, for the same reason the env
    template's secret lines are empty: a placeholder that works is a credential in the repository.
    Rendering fails closed — a missing placeholder means the template and this tool have drifted,
    and an unset password means ``init-env`` has not run.
    """
    if not REALM_TEMPLATE.exists():
        raise LocalError("the committed realm template is missing at " + str(REALM_TEMPLATE))

    text = REALM_TEMPLATE.read_text(encoding="utf-8")
    for placeholder, variable in IDP_PASSWORD_PLACEHOLDERS.items():
        if placeholder not in text:
            raise LocalError("the realm template no longer carries " + placeholder + " — template and tool have drifted")
        value = env.get(variable, "").strip()
        if not value:
            raise LocalError(variable + " is not set in " + str(ENV_FILE) + "\n     Run:  python -m tools.local.sp2_local init-env")
        # JSON-escaped, so a password containing a quote or a backslash cannot break the document.
        text = text.replace(placeholder, json.dumps(value)[1:-1])

    leftover = sorted(set(re.findall(r"__SP2_[A-Z0-9_]+__", text)))
    if leftover:
        raise LocalError("the rendered realm still holds unresolved placeholders: " + ", ".join(leftover))
    try:
        json.loads(text)
    except Exception as exc:
        raise LocalError("the rendered realm file is not valid JSON: " + str(exc).splitlines()[0]) from None

    REALM_IMPORT_DIR.mkdir(parents=True, exist_ok=True)
    REALM_FILE.write_text(text, encoding="utf-8")
    return REALM_FILE


def _http_text(url: str, timeout: int = 15) -> Tuple[int, str]:
    """One GET against the identity provider's public endpoints. stdlib only."""
    request = urllib.request.Request(url, method="GET")
    request.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed loopback URL
            return int(response.status), response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read().decode("utf-8", "replace")
    except urllib.error.URLError as exc:
        raise LocalError("cannot reach " + url + " (" + str(exc.reason) + ")") from None


def realm_public_key_pem(env: Mapping[str, str], attempts: int = 60, delay: float = 2.0) -> str:
    """Wait for the realm, then return its signing public key as a PEM.

    The key is read from the identity provider itself rather than generated here, so the anchor
    the backend pins cannot drift from the key that actually signs the tokens. It is regenerated
    whenever the provider's volume is destroyed, which is why this is a command and not a constant.
    """
    url = idp_issuer(env)
    last = ""
    for _attempt in range(attempts):
        try:
            status, body = _http_text(url)
        except LocalError as exc:
            last = str(exc)
            status, body = 0, ""
        if status == 200:
            try:
                realm = json.loads(body)
            except Exception:
                raise LocalError("the realm endpoint returned something that is not JSON") from None
            if realm.get("realm") != IDP_REALM:
                raise LocalError("the issuer serves realm " + repr(realm.get("realm")) + ", expected " + repr(IDP_REALM))
            key = str(realm.get("public_key", ""))
            if not key:
                raise LocalError("the realm published no public key")
            return "-----BEGIN PUBLIC KEY-----\n" + "\n".join(textwrap.wrap(key, 64)) + "\n-----END PUBLIC KEY-----\n"
        last = "HTTP " + str(status) if status else last
        time.sleep(delay)
    raise LocalError("the identity provider never served realm '" + IDP_REALM + "' at " + url + " (" + last + ")")


def issuer_anchor_json(env: Mapping[str, str], public_key_pem: str) -> str:
    """The single-line ``SP2_AUTHENTICATION_ISSUERS`` value, exactly as the env file holds it.

    Single line on purpose: an env file has no multi-line value, so the PEM's newlines travel as
    JSON ``\\n`` escapes and become real newlines again when the service parses the JSON.
    """
    return json.dumps(
        {
            idp_issuer(env): {
                "audience": IDP_AUDIENCE,
                "algorithms": [IDP_ALGORITHM],
                "public_key_pem": public_key_pem,
            }
        }
    )


def write_env_value(key: str, value: str, path: Path = ENV_FILE) -> None:
    """Replace exactly one ``KEY=`` line in the untracked env file, preserving everything else.

    Rewriting the whole file from the template would discard the generated secrets; appending
    would leave two lines for one key and let the later one win silently.
    """
    if not path.exists():
        raise LocalError("no local environment file at " + str(path) + "\n     Create one with:  python -m tools.local.sp2_local init-env")
    lines = path.read_text(encoding="utf-8").splitlines()
    replaced = 0
    for index, raw in enumerate(lines):
        stripped = raw.strip()
        if stripped.startswith("#") or "=" not in stripped:
            continue
        if stripped.split("=", 1)[0].strip() == key:
            lines[index] = key + "=" + value
            replaced += 1
    if replaced == 0:
        raise LocalError(key + " is not declared in " + str(path) + "; the template and the tool have drifted")
    if replaced > 1:
        raise LocalError(key + " is declared " + str(replaced) + " times in " + str(path) + "; remove the duplicates")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def key_fingerprint(public_key_pem: str) -> str:
    """A short, non-secret identity for a PUBLIC key, so a change is visible without printing it."""
    body = "".join(line for line in public_key_pem.splitlines() if "-----" not in line)
    return hashlib.sha256(base64.b64decode(body)).hexdigest()[:16]


# --- the browser's own login flow, driven headlessly --------------------------------------------
#
# Authorization Code + PKCE S256, exactly as the frontend adapter performs it: the same client,
# the same redirect URI, the same code challenge, the same token exchange. Nothing here is a
# shortcut around authentication — there is no password grant, no client secret, no admin API and
# no minted token. It exists so `smoke` can keep proving the request path once the pinned-issuer
# posture is active, and so the claim contract can be checked without a human at a keyboard.


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Stop urllib following the authorization redirect: the redirect IS the result."""

    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None


class _LoopbackCookiePolicy(http.cookiejar.DefaultCookiePolicy):
    """Send Keycloak's ``SameSite=None; Secure`` session cookies over loopback HTTP.

    A browser does this already: ``http://localhost`` is a secure context, so a ``Secure`` cookie
    is accepted and returned there. ``http.cookiejar`` has no notion of secure contexts and would
    silently withhold the authentication-session cookie, which arrives as a bare 400 from the
    login POST. This restores the browser's behaviour for loopback only.
    """

    def return_ok_secure(self, cookie: Any, request: Any) -> bool:
        host = (urlparse(request.full_url).hostname or "").lower()
        return host in {"localhost", "127.0.0.1", "::1"}


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def oidc_access_token(env: Mapping[str, str], username: str, scope: str) -> str:
    """Obtain one real access token through Authorization Code + PKCE. Never prints it."""
    if username not in IDP_IDENTITIES:
        raise LocalError("unknown local identity " + repr(username))
    _principal, password_variable, _tenant = IDP_IDENTITIES[username]
    password = require(env, password_variable)
    issuer = idp_issuer(env)

    jar = http.cookiejar.CookieJar(_LoopbackCookiePolicy())
    follow = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    halt = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar), _NoRedirect)

    verifier = _b64url(secrets.token_bytes(32))
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    state = _b64url(secrets.token_bytes(16))
    authorize = (
        issuer
        + "/protocol/openid-connect/auth?"
        + urlencode(
            {
                "response_type": "code",
                "client_id": IDP_CLIENT_ID,
                "redirect_uri": IDP_REDIRECT_URI,
                "scope": scope,
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )
    )

    location: Optional[str] = None
    try:
        with halt.open(authorize, timeout=20) as response:  # noqa: S310 - fixed loopback URL
            page = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        if exc.code not in (301, 302, 303, 307, 308):
            raise LocalError("the authorization endpoint answered " + str(exc.code)) from None
        # An existing single sign-on session: no login form, straight back to the callback.
        location, page = exc.headers.get("Location"), ""

    if location is None:
        form = re.search(r'<form[^>]*id="kc-form-login"[^>]*action="([^"]+)"', page)
        if form is None:
            raise LocalError("the identity provider did not render the expected login form")
        action = form.group(1).replace("&amp;", "&")
        body = urlencode({"username": username, "password": password, "credentialId": ""}).encode("utf-8")
        request = urllib.request.Request(action, data=body, method="POST")
        request.add_header("Content-Type", "application/x-www-form-urlencoded")
        try:
            with halt.open(request, timeout=20) as response:  # noqa: S310 - fixed loopback URL
                raise LocalError("the login did not redirect (HTTP " + str(response.status) + "); the credentials were rejected")
        except urllib.error.HTTPError as exc:
            if exc.code not in (301, 302, 303, 307, 308):
                raise LocalError("the login was refused (HTTP " + str(exc.code) + ") for " + username) from None
            location = exc.headers.get("Location")

    parameters = parse_qs(urlparse(location or "").query)
    if parameters.get("state", [""])[0] != state:
        raise LocalError("the authorization response carried the wrong state")
    if "code" not in parameters:
        raise LocalError("no authorization code was returned for " + username)

    exchange = urlencode(
        {
            "grant_type": "authorization_code",
            "client_id": IDP_CLIENT_ID,
            "code": parameters["code"][0],
            "redirect_uri": IDP_REDIRECT_URI,
            "code_verifier": verifier,
        }
    ).encode("utf-8")
    request = urllib.request.Request(issuer + "/protocol/openid-connect/token", data=exchange, method="POST")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with follow.open(request, timeout=20) as response:  # noqa: S310 - fixed loopback URL
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise LocalError("the token exchange failed (HTTP " + str(exc.code) + ")") from None

    token = payload.get("access_token")
    if not isinstance(token, str) or not token:
        raise LocalError("the token response carried no access token")
    if str(payload.get("token_type", "")).lower() != "bearer":
        raise LocalError("the token response was not a bearer token")
    return token


def token_claims(token: str) -> Dict[str, Any]:
    """The token's claims, decoded STRUCTURALLY and without verifying anything.

    Used only to report the claim CONTRACT — which names are present and what shape they have.
    The signature authority is the Authentication Service; nothing here is a verification, and
    no claim read here is ever treated as permission.
    """
    parts = token.split(".")
    if len(parts) != 3:
        raise LocalError("the credential is not a three-part JWT")
    body = parts[1] + "=" * (-len(parts[1]) % 4)
    return dict(json.loads(base64.urlsafe_b64decode(body)))


# --- commands ------------------------------------------------------------------------------------


def command_init_env(force: bool) -> int:
    """Write an untracked env file with freshly generated local throwaway values.

    The committed template holds empty secret lines on purpose: a placeholder long enough to
    satisfy the 32-character lineage-key floor is a placeholder that works, and would end up
    left in place. Generating instead means every developer's local stack has distinct values and
    the repository has none.
    """
    if ENV_FILE.exists() and not force:
        say("An env file already exists at " + str(ENV_FILE))
        say("Nothing was changed. Pass --force to regenerate it (this invalidates existing lineage rows).")
        return 1
    if not ENV_TEMPLATE.exists():
        raise LocalError("the committed template is missing at " + str(ENV_TEMPLATE))

    generated = {name: secrets.token_urlsafe(32) for name in GENERATED_VARIABLES}

    lines: List[str] = []
    filled: List[str] = []
    for raw in ENV_TEMPLATE.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in generated:
                lines.append(key + "=" + generated[key])
                filled.append(key)
                continue
        lines.append(raw)

    missing = sorted(set(GENERATED_VARIABLES) - set(filled))
    if missing:
        raise LocalError("the template no longer declares: " + ", ".join(missing) + " — template and tool have drifted")

    banner = [
        "# GENERATED, UNTRACKED, LOCAL THROWAWAY VALUES — do not commit, do not reuse anywhere else.",
        "# Written by: python -m tools.local.sp2_local init-env",
        "# Regenerating invalidates verification of lineage rows written under the previous keys;",
        "# reset the databases too:  python -m tools.local.sp2_local bootstrap --reset",
        "",
    ]
    ENV_FILE.write_text("\n".join(banner + lines) + "\n", encoding="utf-8")

    say("Wrote " + str(ENV_FILE))
    say("  " + str(len(filled)) + " values generated (" + str(len(GENERATED_VARIABLES)) + " expected). No value is printed here.")
    say("  This file is gitignored. It contains local throwaway secrets and must never be committed.")

    # The identity provider's realm is configuration, and configuration a developer has to click
    # through an admin console is configuration a fresh checkout does not reproduce. Rendered here
    # from the committed template so `docker compose up` imports it declaratively.
    realm = render_realm_file(parse_env_file(ENV_FILE.read_text(encoding="utf-8")))
    say("Wrote " + str(realm))
    say("  The local Keycloak realm, rendered from " + REALM_TEMPLATE.name + " with the generated passwords.")
    say("  Also gitignored. The committed template carries placeholders and no usable credential.")
    return 0


def command_migrate(reset: bool) -> int:
    """Apply the accepted chains to the Control database and all three tenant databases."""
    env = load_env()
    control = control_chain()
    tenant = tenant_chain()

    if not control or not tenant:
        raise LocalError("no migration files found; the chains would apply nothing")

    say("Applying migrations (" + str(len(control)) + " Control files, " + str(len(tenant)) + " tenant files x " + str(len(TENANTS)) + ")")

    targets: Sequence[Tuple[str, Sequence[Path]]] = [("control", control)] + [(name, tenant) for name in TENANTS]
    for label, files in targets:
        dsn = host_dsn(env, label)
        if reset:
            step(label + ": reset to an empty schema")
            reset_database(dsn, label)
        applied = apply_chain(dsn, files, label)
        step(label + ": applied " + str(len(applied)) + " files, " + applied[0] + " .. " + applied[-1])

    say("Migrations applied.")
    return 0


def command_seed() -> int:
    """Write the minimum Control-database rows a real authenticated request needs.

    Three record classes and nothing more: the tenant registry entries the Database Router
    resolves against, the memberships the Access Control Service reads, and a few global directory
    records so a directory read and an import have something to return.

    Every statement upserts, so the command is safe to rerun. Nothing is written to a tenant
    database: tenant business records are created through the BFF, by a request, which is the only
    path that proves the request path works.
    """
    env = load_env()
    dsn = host_dsn(env, "control")
    now = datetime.now(timezone.utc).isoformat()

    say("Seeding the Control database (local development identities only)")

    for tenant_ref in TENANTS:
        # Column list and conflict behaviour match PostgresControlStore.put_tenant exactly, so a
        # seeded row and a service-written row are the same row. `created_at` is deliberately
        # absent from the update list: a rerun must not restamp when the tenant was registered.
        execute(
            dsn,
            "INSERT INTO control_tenants (tenant_id, organization_ref, lifecycle_state, expected_schema_version, "
            "assoc_store_ref, assoc_version, federation_config_ref, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (tenant_id) DO UPDATE SET organization_ref = EXCLUDED.organization_ref, "
            "lifecycle_state = EXCLUDED.lifecycle_state, expected_schema_version = EXCLUDED.expected_schema_version, "
            "assoc_store_ref = EXCLUDED.assoc_store_ref, assoc_version = EXCLUDED.assoc_version, "
            "updated_at = EXCLUDED.updated_at",
            (
                tenant_ref,
                "org-local-" + tenant_ref,
                "ACTIVE",
                EXPECTED_SCHEMA_VERSION,
                "assoc/" + tenant_ref,
                ASSOCIATION_VERSION,
                "",  # federation_config_ref is NOT NULL; empty is the honest "none recorded"
                now,
                now,
            ),
        )
    step(str(len(TENANTS)) + " tenant registry rows (lifecycle ACTIVE, association assoc/<tenant> v1)")

    for principal_ref, tenant_ref, role in SEED_MEMBERSHIPS:
        execute(
            dsn,
            "INSERT INTO control_memberships (principal_ref, tenant_id, role) VALUES (%s, %s, %s) "
            "ON CONFLICT (principal_ref, tenant_id) DO UPDATE SET role = EXCLUDED.role",
            (principal_ref, tenant_ref, role),
        )
    step(str(len(SEED_MEMBERSHIPS)) + " memberships, one principal per tenant and no principal in two")

    for directory, record_ref, display_name in SEED_DIRECTORY:
        execute(
            dsn,
            "INSERT INTO control_directory (directory, record_id, display_name, attributes) VALUES (%s, %s, %s, %s::jsonb) "
            "ON CONFLICT (directory, record_id) DO UPDATE SET display_name = EXCLUDED.display_name, "
            "attributes = EXCLUDED.attributes",
            (directory, record_ref, display_name, json.dumps({"residency": "global", "source": "local-development-seed"})),
        )
    step(str(len(SEED_DIRECTORY)) + " global directory records (fictional; no real company, no PII)")

    say("Seed complete. No tenant database was written to.")
    return 0


def command_bootstrap(reset: bool) -> int:
    result = command_migrate(reset)
    if result != 0:
        return result
    return command_seed()


def command_idp_up(reset: bool) -> int:
    """Start the local identity provider and pin its realm key as the Authentication trust anchor.

    Two halves, and the order is the point. The realm is imported from a file this command
    renders, so a fresh checkout reproduces the whole identity configuration; then the realm's own
    PUBLIC key is read back from the provider and written into the untracked env file. Pinning a
    key we asked the provider for — rather than one this repository generated — is what makes it
    impossible for the anchor and the signer to disagree.

    From this point the four opaque local tokens authenticate nobody: a pinned issuer WINS over
    the static development map, deliberately, so a deployment never holds two live trust anchors.
    """
    env = load_env()
    issuer = idp_issuer(env)

    say("1. Realm configuration")
    realm_path = render_realm_file(env)
    step("rendered " + realm_path.name + " from the committed template (passwords substituted, none printed)")

    if reset:
        say("2. Reset — remove the identity provider and its data")
        _run(_compose_command() + ["rm", "--stop", "--force", "--volumes", IDP_SERVICE], timeout=180)
        volume = COMPOSE_PROJECT + "_sp2_rebuild_keycloak_data"
        code, output = _run(["docker", "volume", "rm", volume], timeout=120)
        step(("removed volume " + volume) if code == 0 else ("volume " + volume + " was not present"))
        del output
    else:
        say("2. Reset — not requested (an already-imported realm keeps its existing passwords)")

    say("3. Start the identity provider")
    code, output = _run(_compose_command() + ["up", "-d", "--wait", IDP_SERVICE], timeout=600)
    if code != 0:
        raise LocalError("could not start the identity provider.\n     " + output.strip()[-500:])
    step("compose service '" + IDP_SERVICE + "' is up and its realm health check passes")

    say("4. Read the realm signing key and pin it")
    public_key_pem = realm_public_key_pem(env)
    step("realm '" + IDP_REALM + "' served at " + issuer)
    step("RS256 public key fingerprint " + key_fingerprint(public_key_pem) + " (PUBLIC; the private half never leaves the provider)")
    write_env_value(ENV_AUTHENTICATION_ISSUERS, issuer_anchor_json(env, public_key_pem))
    step("wrote " + ENV_AUTHENTICATION_ISSUERS + " into " + ENV_FILE.name + ": issuer, audience " + IDP_AUDIENCE + ", " + IDP_ALGORITHM)

    say("5. Apply it to the Authentication Service")
    running = _compose_service_names()
    if "authentication" in running:
        code, output = _run(_compose_command() + ["up", "-d", "--wait", "authentication"], timeout=600)
        if code != 0:
            raise LocalError("the Authentication Service did not come back up with the new anchor.\n     " + output.strip()[-500:])
        step("recreated the Authentication Service; the verifier is resolved once, at import, so a restart is required")
    else:
        step("the Authentication Service is not running yet — it will pick the anchor up when you start the stack")

    say("")
    say("IDP: READY — " + issuer)
    say("        client " + IDP_CLIENT_ID + " (public, Authorization Code + PKCE S256), audience " + IDP_AUDIENCE)
    say("        redirect " + IDP_REDIRECT_URI)
    say("        sign in as: " + ", ".join(sorted(IDP_IDENTITIES)) + "  (passwords are in " + ENV_FILE.name + ", never printed)")
    say("")
    say("Next:   docker compose -f " + str(COMPOSE_FILE.relative_to(REPO_ROOT)).replace(chr(92), "/") + " --env-file ... up -d --wait")
    return 0


# --- verification ----------------------------------------------------------------------------


def _compose_command() -> List[str]:
    return ["docker", "compose", "-f", str(COMPOSE_FILE), "--env-file", str(ENV_FILE)]


def _run(argv: Sequence[str], timeout: int = 120) -> Tuple[int, str]:
    try:
        completed = subprocess.run(list(argv), capture_output=True, text=True, timeout=timeout, check=False)
    except FileNotFoundError as exc:
        raise LocalError("command not found: " + argv[0]) from exc
    except subprocess.TimeoutExpired as exc:
        raise LocalError("command timed out: " + " ".join(argv[:3])) from exc
    return completed.returncode, (completed.stdout or "") + (completed.stderr or "")


def _http_json(
    url: str,
    *,
    token: Optional[str] = None,
    method: str = "GET",
    body: Optional[Mapping[str, Any]] = None,
    tenant: Optional[str] = None,
) -> Tuple[int, Any]:
    """One HTTP call against the BFF's published loopback port. stdlib only."""
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Accept", "application/json")
    if data is not None:
        request.add_header("Content-Type", "application/json")
    if token is not None:
        request.add_header("Authorization", "Bearer " + token)
    if tenant is not None:
        # The one recognized carrier header (IC-013 §5), sent exactly as the browser sends it.
        # A carrier is match-or-reject only: it never grants tenant access and never selects a
        # database, so sending it exercises the comparison rather than obtaining anything.
        request.add_header("X-Tenant-Id", tenant)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310 - fixed loopback URL
            payload = response.read().decode("utf-8")
            return int(response.status), (json.loads(payload) if payload else None)
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8")
        return int(exc.code), (json.loads(payload) if payload else None)
    except urllib.error.URLError as exc:
        raise LocalError("the BFF is not reachable at " + url + " (" + str(exc.reason) + "). Is the stack up?") from None


def _compose_rows() -> List[Dict[str, Any]]:
    """The RUNNING stack, as compose reports it. Empty when nothing is up."""
    code, output = _run(_compose_command() + ["ps", "--format", "json"])
    if code != 0:
        return []
    rows: List[Dict[str, Any]] = []
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("{"):
            rows.append(json.loads(line))
    return rows


def _compose_service_names() -> Set[str]:
    """Which compose services currently have a container."""
    return {str(row.get("Service", "")) for row in _compose_rows()}


def _published_services() -> Dict[str, List[str]]:
    """Compose service name -> published host ports, read from the RUNNING stack.

    Read from the runtime rather than from the manifest on purpose. The manifest check already
    exists as a static gate; this one answers the different question of what is actually listening,
    which is what a `-p` on a `docker compose run`, a stale container, or a local override would
    change without touching a tracked file.
    """
    rows = _compose_rows()
    if not rows:
        raise LocalError("could not read the running stack. Is it up?")
    published: Dict[str, List[str]] = {}
    for row in rows:
        name = str(row.get("Service", ""))
        ports = str(row.get("Publishers") or row.get("Ports") or "")
        entries: List[str] = []
        if isinstance(row.get("Publishers"), list):
            for publisher in row["Publishers"]:
                if publisher.get("PublishedPort"):
                    entries.append(str(publisher.get("URL") or "") + ":" + str(publisher["PublishedPort"]))
        elif "->" in ports:
            entries = [segment.strip() for segment in ports.split(",") if "->" in segment]
        published[name] = entries
    return published


def command_verify() -> int:
    """Prove the local stack is up, healthy, contract-clean, and exposed only through the BFF."""
    env = load_env()
    failures: List[str] = []

    say("1. Public ingress — the BFF, from the host")
    for route in ("/health", "/readiness"):
        status, body = _http_json(BFF_BASE_URL + route)
        ok = status == 200 and isinstance(body, dict) and body.get("service") == "bff"
        step(route + ": " + str(status) + (" ok" if ok else "  <-- FAIL"))
        if not ok:
            failures.append("bff" + route)

    status, schema = _http_json(BFF_BASE_URL + "/openapi.json")
    if status != 200 or not isinstance(schema, dict):
        failures.append("bff /openapi.json")
        step("/openapi.json: " + str(status) + "  <-- FAIL")
    else:
        step("/openapi.json: OpenAPI " + str(schema.get("openapi")) + ", " + str(len(schema.get("paths", {}))) + " paths")

    say("2. All fourteen services, probed from INSIDE the private network")
    probe = (
        "import json,urllib.request\n"
        "targets=" + repr([(name, port) for name, port in SERVICES]) + "\n"
        "out={}\n"
        "for name,port in targets:\n"
        "    base='http://'+name+':'+str(port)\n"
        "    entry={}\n"
        "    for route in ('/health','/readiness'):\n"
        "        try:\n"
        "            with urllib.request.urlopen(base+route,timeout=10) as r:\n"
        "                entry[route]=[r.status, json.loads(r.read().decode())]\n"
        "        except Exception as exc:\n"
        "            entry[route]=[0, str(exc)]\n"
        "    try:\n"
        "        with urllib.request.urlopen(base+'/openapi.json',timeout=15) as r:\n"
        "            doc=json.loads(r.read().decode())\n"
        "            entry['openapi']=[doc.get('openapi'), len(doc.get('paths',{})), sorted(\n"
        "                op.get('operationId') for path in doc.get('paths',{}).values() for op in path.values() if isinstance(op,dict))]\n"
        "    except Exception as exc:\n"
        "        entry['openapi']=[None,0,str(exc)]\n"
        "    out[name]=entry\n"
        "print('SP2VERIFY'+json.dumps(out))\n"
    )
    code, output = _run(_compose_command() + ["exec", "-T", PUBLIC_SERVICE, "python", "-c", probe], timeout=300)
    marker = [line for line in output.splitlines() if line.startswith("SP2VERIFY")]
    if code != 0 or not marker:
        raise LocalError("could not probe the private network from the BFF container.\n     " + output.strip()[-500:])
    results: Dict[str, Dict[str, Any]] = json.loads(marker[0][len("SP2VERIFY") :])

    all_operation_ids: List[str] = []
    for name, _port in SERVICES:
        entry = results.get(name, {})
        health = entry.get("/health", [0, None])
        readiness = entry.get("/readiness", [0, None])
        version, path_count, operations = (entry.get("openapi") or [None, 0, []])[:3]
        ids = operations if isinstance(operations, list) else []
        all_operation_ids.extend(ids)
        ok = health[0] == 200 and readiness[0] == 200 and str(version).startswith("3.1")
        step(
            name.ljust(16)
            + " health "
            + str(health[0])
            + "  readiness "
            + str(readiness[0])
            + "  OpenAPI "
            + str(version)
            + "  paths "
            + str(path_count)
            + ("" if ok else "   <-- FAIL")
        )
        if not ok:
            failures.append(name)

    duplicates = sorted({op for op in all_operation_ids if all_operation_ids.count(op) > 1})
    step("operationIds across all fourteen: " + str(len(all_operation_ids)) + " total, " + str(len(set(all_operation_ids))) + " unique")
    if duplicates:
        failures.append("duplicate operationIds: " + ", ".join(duplicates))
        step("duplicate operationIds: " + ", ".join(duplicates) + "   <-- FAIL")

    say("3. Exposure — exactly one APPLICATION service publishes a port, and it is the BFF")
    published = _published_services()
    application_publishers = sorted(name for name, ports in published.items() if ports and not INFRASTRUCTURE_SERVICE.search(name))
    database_publishers = sorted(name for name, ports in published.items() if ports and INFRASTRUCTURE_SERVICE.search(name))
    step("application services publishing: " + (", ".join(application_publishers) or "none"))
    step("databases publishing (loopback, not an application ingress): " + (", ".join(database_publishers) or "none"))
    if application_publishers != [PUBLIC_SERVICE]:
        failures.append("public application ingress is " + repr(application_publishers) + ", expected ['bff']")

    say("4. Internal services are NOT reachable from the host")
    import socket

    for name, port in SERVICES:
        if name == PUBLIC_SERVICE:
            continue
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe_socket:
            probe_socket.settimeout(1.0)
            reachable = probe_socket.connect_ex(("127.0.0.1", port)) == 0
        if reachable:
            # Not automatically a failure: 8001-8005 are also the legacy standing topology's ports,
            # so something unrelated may be listening. It IS reported, loudly, because the
            # alternative is a silent pass over a genuinely published internal service.
            step("127.0.0.1:" + str(port) + " (" + name + ") ANSWERED — check what is listening; this manifest publishes nothing there")
    step("checked " + str(len(SERVICES) - 1) + " internal ports on 127.0.0.1")

    say("5. Local identity provider — the browser's login")
    issuer = idp_issuer(env)
    anchor = env.get(ENV_AUTHENTICATION_ISSUERS, "").strip()
    if IDP_SERVICE not in _compose_service_names():
        step("not running. Start it with:  python -m tools.local.sp2_local idp-up   <-- browser login unavailable")
        failures.append("identity provider not running")
    else:
        status, body = _http_text(issuer)
        realm_ok = status == 200 and json.loads(body or "{}").get("realm") == IDP_REALM
        step("realm '" + IDP_REALM + "' at " + issuer + ": " + str(status) + (" ok" if realm_ok else "  <-- FAIL"))
        if not realm_ok:
            failures.append("identity provider realm")

        status, body = _http_text(issuer + "/.well-known/openid-configuration")
        discovery = json.loads(body or "{}") if status == 200 else {}
        pkce = "S256" in (discovery.get("code_challenge_methods_supported") or [])
        stamped = discovery.get("issuer") == issuer
        step("discovery: PKCE S256 " + ("advertised" if pkce else "MISSING") + ", issuer " + ("as pinned" if stamped else "DIFFERENT"))
        if not (pkce and stamped):
            failures.append("identity provider discovery")

        # The anchor is compared, never printed. What matters is that the Authentication Service
        # trusts exactly this issuer: an anchor for a different one authenticates nobody, and the
        # symptom is a 401 that says nothing about why.
        if not anchor:
            step(ENV_AUTHENTICATION_ISSUERS + " is EMPTY — the browser's OIDC tokens will be rejected. Run: idp-up")
            failures.append("no pinned trust anchor")
        else:
            trusted = sorted(json.loads(anchor))
            step("pinned trust anchors: " + ", ".join(trusted) + ("  ok" if trusted == [issuer] else "  <-- FAIL, expected only " + issuer))
            if trusted != [issuer]:
                failures.append("pinned trust anchor does not match the local issuer")

    if failures:
        say("")
        say("VERIFY: FAIL — " + "; ".join(failures))
        return 1
    say("")
    say("VERIFY: PASS — 14/14 services healthy, OpenAPI 3.1, BFF is the only public application ingress,")
    say("        and the local identity provider serves the realm the Authentication Service pins.")
    return 0


def command_smoke() -> int:
    """One real authenticated Startup flow, end to end, plus physical isolation evidence.

    This is deliberately not a unit test. It goes through the published ingress with a real token,
    is authorized by the real Access Control Service, is routed by the real Database Router, and is
    then checked against the tenant databases directly — because "the API said 201" and "the row is
    in the right physical database" are different claims and only the second one is isolation.
    """
    env = load_env()
    failures: List[str] = []

    say("0. Credentials — whichever posture the Authentication Service is actually in")
    if env.get(ENV_AUTHENTICATION_ISSUERS, "").strip():
        # The pinned-issuer posture. Obtain real tokens the way the browser does: Authorization
        # Code + PKCE S256, same public client, same redirect URI, same exchange. No password
        # grant, no client secret, no admin API — there is no shortcut around authentication here.
        step("pinned issuer configured -> obtaining real OIDC tokens (Authorization Code + PKCE S256)")
        acme_token = oidc_access_token(env, "acme-agent", "openid " + IDP_TENANT_SCOPE_PREFIX + "acme")
        zeta_token = oidc_access_token(env, "zeta-agent", "openid " + IDP_TENANT_SCOPE_PREFIX + "zeta")
        tenant_claims = token_claims(acme_token)
        present = [name for name in ("sub", "role", "active_tenant", "aud", "iss", "exp") if name in tenant_claims]
        step("ACME token claim names: " + ", ".join(present))
        step(
            "  sub="
            + str(tenant_claims.get("sub"))
            + "  role="
            + str(tenant_claims.get("role"))
            + "  active_tenant="
            + str(tenant_claims.get("active_tenant"))
        )
        expected_claims = {"sub": "local-agent-acme", "role": "TENANT_AGENT", "active_tenant": "acme"}
        for name, wanted in expected_claims.items():
            if tenant_claims.get(name) != wanted:
                failures.append("the ACME token's " + name + " claim is " + repr(tenant_claims.get(name)) + ", expected " + repr(wanted))
        # A token minted WITHOUT a tenant scope must carry no active tenant. If it did, every
        # principal-level request would silently arrive pre-bound to a tenant database.
        principal_claims = token_claims(oidc_access_token(env, "acme-agent", "openid"))
        step("principal-only token (no tenant scope) carries active_tenant: " + repr(principal_claims.get("active_tenant")))
        if principal_claims.get("active_tenant") is not None:
            failures.append("a token minted without a tenant scope carried an active tenant")
    else:
        step("no pinned issuer -> using the local static development tokens")
        acme_token = require(env, "SP2_LOCAL_TOKEN_ACME_AGENT")
        zeta_token = require(env, "SP2_LOCAL_TOKEN_ZETA_AGENT")

    say("1. Create a Startup in ACME, through the BFF")
    company = "Local Smoke Ltd " + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    status, created = _http_json(
        BFF_BASE_URL + "/tenant/startups",
        token=acme_token,
        tenant="acme",
        method="POST",
        body={
            "display_name": company,
            "short_description": "Created by the Stage 6 local smoke check.",
            "investment_stage": "seed",
            "company_url": "https://www.local-smoke.example/",
            "industry": "software",
            "headquarters_country": "GB",
            "headquarters_city": "London",
        },
    )
    if status == 401:
        raise LocalError(
            "create returned 401 unauthenticated.\n"
            "     The Authentication Service is not accepting this credential. The usual cause is a\n"
            "     pinned trust anchor the running container has not picked up: the verifier is resolved\n"
            "     once, at import, so the container must be recreated after " + ENV_AUTHENTICATION_ISSUERS + " changes.\n"
            "     Run:  python -m tools.local.sp2_local idp-up"
        )
    if status != 201 or not isinstance(created, dict):
        raise LocalError("create returned " + str(status) + ": " + json.dumps(created)[:300])
    record_ref = str(created.get("record_ref", ""))
    step("201 Created, record_ref " + record_ref)
    # The response is the contract-pinned eight-field Startup shape, which deliberately carries no
    # URL: "no ... URL ... may ever join this shape". The website IS accepted, normalized and
    # stored — it is just not surfaced. Checked against the database in step 4, not asserted here,
    # because expecting it in the response would be asserting a contract violation.
    step("response fields: " + ", ".join(sorted(created)))
    if "company_url" in created:
        failures.append("the tenant Startup DTO surfaced a URL; the contract-pinned shape excludes it")

    say("2. Read it back, as the same ACME principal")
    status, read_back = _http_json(BFF_BASE_URL + "/tenant/startups/" + record_ref, token=acme_token, tenant="acme")
    ok = status == 200 and isinstance(read_back, dict) and read_back.get("display_name") == company
    step("GET /tenant/startups/{record_ref}: " + str(status) + (" ok" if ok else "  <-- FAIL"))
    if not ok:
        failures.append("read-back")

    say("3. The SAME record reference, presented by the ZETA principal")
    status, _denied = _http_json(BFF_BASE_URL + "/tenant/startups/" + record_ref, token=zeta_token, tenant="zeta")
    step("GET with the ZETA token: " + str(status) + (" (not found — correct)" if status == 404 else "  <-- FAIL, expected 404"))
    if status != 404:
        failures.append("cross-tenant read returned " + str(status) + ", expected 404")

    say("4. Physical isolation — ask each tenant database directly")
    for tenant_ref in TENANTS:
        rows = query(host_dsn(env, tenant_ref), "SELECT count(*) FROM startups WHERE company_name = %s", (company,))
        count = int(rows[0][0]) if rows else 0
        expected = 1 if tenant_ref == "acme" else 0
        verdict = "ok" if count == expected else "  <-- FAIL, expected " + str(expected)
        step(tenant_ref.ljust(6) + " database: " + str(count) + " matching row(s)  " + verdict)
        if count != expected:
            failures.append(tenant_ref + " holds " + str(count) + " rows, expected " + str(expected))

    stored = query(host_dsn(env, "acme"), "SELECT company_url FROM startups WHERE company_name = %s", (company,))
    website = str(stored[0][0]) if stored and stored[0][0] is not None else ""
    normalized = website == "https://local-smoke.example"
    step("website stored as " + repr(website) + " (www. dropped, trailing slash removed)" + ("" if normalized else "  <-- FAIL"))
    if not normalized:
        failures.append("the website was not normalized on write: " + repr(website))

    say("5. Control database — the record must NOT be there, and the audit event must be")
    control = host_dsn(env, "control")
    tables = [row[0] for row in query(control, "SELECT table_name FROM information_schema.tables WHERE table_schema='public'")]
    if "startups" in tables:
        failures.append("the Control database has a startups table; tenant records must not be Control-resident")
    step("Control database has no tenant 'startups' table: " + ("ok" if "startups" not in tables else "  <-- FAIL"))

    audit_rows = query(control, "SELECT count(*) FROM control_ingress_audit WHERE record_ref = %s", (record_ref,))
    audit_count = int(audit_rows[0][0]) if audit_rows else 0
    step("control_ingress_audit rows for this record: " + str(audit_count) + (" ok" if audit_count >= 1 else "  <-- FAIL, expected >= 1"))
    if audit_count < 1:
        failures.append("no ingress-edge audit event was persisted for the read")

    sources = [row[0] for row in query(control, "SELECT DISTINCT source_service FROM control_ingress_audit")]
    step("audit source_service values present: " + (", ".join(sorted(str(s) for s in sources)) or "none"))

    say("6. Import — a global directory record becomes an INDEPENDENT tenant copy with lineage")
    source_ref = SEED_DIRECTORY[0][1]
    status, first = _http_json(BFF_BASE_URL + "/import/startups/" + source_ref, token=acme_token, tenant="acme", method="POST")
    if status != 201 or not isinstance(first, dict):
        failures.append("import returned " + str(status))
        step("POST /import/startups/" + source_ref + ": " + str(status) + "  <-- FAIL")
    else:
        step("outcome " + str(first.get("outcome")) + ", tenant record " + str(first.get("tenant_record_ref")))
        # Idempotent per source and tenant: a repeat must REPLAY, not make a second copy.
        _status, again = _http_json(BFF_BASE_URL + "/import/startups/" + source_ref, token=acme_token, tenant="acme", method="POST")
        replayed = isinstance(again, dict) and again.get("tenant_record_ref") == first.get("tenant_record_ref")
        step(
            "repeat import: outcome "
            + str((again or {}).get("outcome"))
            + ", same record "
            + str(replayed)
            + (" ok" if replayed else "  <-- FAIL")
        )
        if not replayed:
            failures.append("the import was not idempotent")

    # The lineage row must exist in the tenant database, carry a real keyed marker, and start a
    # chain. A marker column that is present but empty would mean a record was written without
    # provenance, which is the one outcome the fail-closed key resolution exists to prevent.
    lineage = query(
        host_dsn(env, "acme"),
        "SELECT count(*), coalesce(min(length(integrity_marker)), 0), coalesce(min(marker_version), 0) "
        "FROM lineage WHERE event_type = 'import'",
    )
    count, marker_length, marker_version = (int(lineage[0][0]), int(lineage[0][1]), int(lineage[0][2])) if lineage else (0, 0, 0)
    ok_lineage = count >= 1 and marker_length == 64 and marker_version >= 1
    step(
        "ACME lineage import rows: "
        + str(count)
        + ", D-23 marker length "
        + str(marker_length)
        + ", version "
        + str(marker_version)
        + (" ok" if ok_lineage else "  <-- FAIL")
    )
    if not ok_lineage:
        failures.append("the import wrote no verifiable lineage row")

    # Import is not synchronization and not sharing: the same global record imported by another
    # tenant is a separate copy in a separate database with its own chain.
    nova_lineage = int(query(host_dsn(env, "nova"), "SELECT count(*) FROM lineage")[0][0])
    step("NOVA lineage rows (never imported into): " + str(nova_lineage) + (" ok" if nova_lineage == 0 else "  <-- FAIL"))
    if nova_lineage != 0:
        failures.append("NOVA holds lineage rows it was never imported into")

    if failures:
        say("")
        say("SMOKE: FAIL — " + "; ".join(failures))
        return 1
    say("")
    say("SMOKE: PASS — principal -> BFF -> Access Control -> Database Router -> Startup Service -> ACME PostgreSQL.")
    say("        The row exists in ACME only; ZETA and NOVA hold nothing; the Control DB holds the audit event;")
    say("        the import wrote an independent tenant copy with a keyed D-23 lineage marker.")
    return 0


# --- entry point ------------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m tools.local.sp2_local",
        description="SnackPortal2 local-development operator command (LOCAL / NON-PRODUCTION ONLY).",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-env", help="generate an untracked env file with fresh local values").add_argument(
        "--force", action="store_true", help="overwrite an existing env file (invalidates existing lineage rows)"
    )
    subparsers.add_parser("migrate", help="apply the accepted migration chains").add_argument(
        "--reset", action="store_true", help="drop each schema first, so the chain applies from zero"
    )
    subparsers.add_parser("seed", help="write the minimum Control-database rows (idempotent)")
    subparsers.add_parser("bootstrap", help="migrate, then seed").add_argument(
        "--reset", action="store_true", help="drop each schema first, so the chain applies from zero"
    )
    subparsers.add_parser("idp-up", help="start the local identity provider and pin its realm key as the trust anchor").add_argument(
        "--reset", action="store_true", help="destroy the identity provider's data first, so the realm is imported from scratch"
    )
    subparsers.add_parser("verify", help="prove all fourteen services are up and only the BFF is published")
    subparsers.add_parser("smoke", help="run one real authenticated Startup flow and prove physical isolation")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    arguments = build_parser().parse_args(list(argv) if argv is not None else None)
    handlers: Mapping[str, Any] = {
        "init-env": lambda: command_init_env(bool(getattr(arguments, "force", False))),
        "migrate": lambda: command_migrate(bool(getattr(arguments, "reset", False))),
        "seed": command_seed,
        "bootstrap": lambda: command_bootstrap(bool(getattr(arguments, "reset", False))),
        "idp-up": lambda: command_idp_up(bool(getattr(arguments, "reset", False))),
        "verify": command_verify,
        "smoke": command_smoke,
    }
    try:
        return int(handlers[arguments.command]())
    except LocalError as exc:
        say("")
        say("ERROR: " + str(exc))
        return 2


def iter_chain_names(files: Iterable[Path]) -> List[str]:
    """The chain as file names, for the runbook and for the consistency tests."""
    return [path.name for path in files]


if __name__ == "__main__":
    sys.exit(main())
