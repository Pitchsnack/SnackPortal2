"""CLM tenant data-plane witness — ACME Startup GET/PATCH through the real served path (MANUAL_ONLY).

The chain this exists to prove, and which remains **UNPROVEN**:

    Gateway 8820 -> Tenant Startup 8004 -> Database Router -> Control routing record
                 -> SecretRef -> ACME physical tenant DB -> Startup GET -> Startup PATCH

plus ZETA denial / tenant isolation.

**Under Gate A this harness is BUILT, not run.** `run` performs a real business write to a physical
tenant database (a Gate-B class-M14 act) and refuses without `--confirm-start-gate`. `plan` and
`status` are read-only and safe.

--------------------------------------------------------------------------------------------------
THE PRECONDITION THAT MAKES OR BREAKS THE WHOLE PROOF
--------------------------------------------------------------------------------------------------
With `SP2_GW_TENANT_STARTUP_BASE_URL` unset, `build_tenant_startup_from_env` returns `None` and every
`TENANT_OPERATION` keeps the **pre-CLM router handoff**. The `/tenant/startups/<ref>` routes stay
registered and keep answering — so a witness that does not check first will collect a plausible
response that never touched a tenant database and file it as data-plane evidence.

WHAT EACH CHECK ACTUALLY PROVES — stated exactly, because the difference decides the evidence:

  D-1  DECLARATION, not proof. The tenant-Startup selector is declared and non-blank **in this
       witness's own environment**. The Gateway is a SEPARATE uvicorn process composed from its own
       environment, which this process cannot read; the governed launcher additionally scrubs `SP2_*`
       out of every child, so the operator shell and the Gateway shell are structurally independent.
       D-1 therefore catches the common operator error — running the witness from a shell whose
       posture does not match the launcher's — and makes the operator record what they believe the
       posture is. It is NOT evidence about the running Gateway.
  D-2  DECLARATION, not proof, for the same reason: `SP2_CP_CONTROL_STORE=postgres` is read from this
       process. Whether the running Control Plane serves routing from the durable store is a separate
       Gate-B verification (see UNIMPLEMENTED below).
  P-2  OBSERVED: the declared tenant-Startup edge answers on its own internal surface, recorded at
       the moment of the call, so a later `503` can be attributed instead of guessed.
  A-1  AUTHORITATIVE, edge-observed. The served `GET` returns `200` **and** its body carries EXACTLY
       the field set of the served `TenantStartupDetailDTO` contract. This is the real discriminator:
       the tenant Startup terminal is TYPE-EXACT (`_terminal(..., TenantStartupDetailDTO)`), so with
       the port absent a pre-CLM handoff cannot serve a conforming `200` at all — it collapses to
       `503`. The expected field set is DERIVED from the DTO at call time, never restated here: a
       duplicated literal drifts, and a drifted literal rejects the genuine answer.
  A-2  AUTHORITATIVE, independent. A separate connection to the physical ACME database returns the
       same value. Different process, different connection, different code path — the one thing no
       composition can fake.

UNIMPLEMENTED, and deliberately not claimed: this witness does **not** cross-read the Control
routing row from the Control database. `SNACKPORTAL_SECRET_CONTROL_CONTROL_STORE_DSN_V1` is reported
by `plan` for presence only. Proving that the served routing view came from the durable store rather
than the in-memory one is a separate Gate-B read, and it is recorded as such in the evidence
template. Do not write that this witness performed it.

--------------------------------------------------------------------------------------------------
AMBIGUITIES THAT MUST NOT BE RESOLVED BY GUESSING
--------------------------------------------------------------------------------------------------
* **`503` is four-ways ambiguous** — dead tenant-Startup upstream, dead Auth Router, dead durable
  audit sink, or an unhandled edge exception. Every recorded `503` is paired with an upstream
  liveness census taken at the moment of the call, and no leg may PASS on a `503`.
* **`404` is two-ways ambiguous** — bounded-matcher rejection pre-core vs a genuine unknown
  `startup_ref`. Every `404` is paired with the OBSERVED positive control from the read leg.
* **Audit-coupled fail-closed**: with a durable sink selected, a sink outage turns a legitimate `200`
  into a `503` and a legitimate `403` into a `503`. Evidence collected during a sink outage
  misrepresents the data plane as broken.
* **Isolation has two stages and they prove different things.** The ZETA-claim denial fires in the
  **Auth Router**, before any routing or tenant-DB contact. That is the correct fail-closed posture,
  but it proves *auth-stage* denial — **not** that the Database Router would have refused. The
  router-stage leg is captured separately, labelled separately, and ASSERTED separately: a `200` on
  either leg is an isolation breach and fails the run.
* **A missing VALUE is not a missing ROW.** `short_description` is nullable in the DDL and at the
  edge, so `read_short_description` returning `None` is two different facts. Row presence is asked
  separately (`startup_row_exists`); a present row holding a lawful NULL must never be reported as
  "the row does not exist", and a run that aborted before the write leg must never be reported as a
  failed restore.
* **`://` is LAWFUL inside `short_description`** — the serving edge says so in as many words — so the
  bounded free-text field is scanned under the free-text rule and the rest of the artifact under the
  reference/topology rule. A credential, token or key block in that field still fails the run.

SECRET HYGIENE (D-14). No DSN, password, bearer token or credential value is printed, returned or
written. Every emitted identity is redacted to scheme+host+port+database — TOPOLOGY, never
credentials, and the database name is part of that topology — and every captured artifact is scanned
for leakage, including both bearer tokens, before it is reported. The captured artifacts additionally
bar the physical database name; `plan`'s operator-local redacted connection line does not (runbook §6).

DRIVER CONTAINMENT. No static database-driver import; psycopg is located via importlib at call time.

    python tests/control_plane/requires_pg/test_pg_clm_acme_dataplane_witness.py plan
    python tests/control_plane/requires_pg/test_pg_clm_acme_dataplane_witness.py status
    python tests/control_plane/requires_pg/test_pg_clm_acme_dataplane_witness.py run --confirm-start-gate
"""

from __future__ import annotations

import argparse
import dataclasses
import importlib
import importlib.util
import json
import os
import pathlib
import re
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, FrozenSet, List, Optional, Sequence, Tuple
from urllib.parse import urlsplit

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))  # backend on path

# ------------------------------------------------------------------- governed standing values ----
GATEWAY_BASE_URL = "http://127.0.0.1:8820"
TENANT_STARTUP_BASE_URL = "http://127.0.0.1:8004"

# The composition selector whose absence silently disables the whole data plane.
TENANT_STARTUP_SELECTOR = "SP2_GW_TENANT_STARTUP_BASE_URL"
CONTROL_STORE_SELECTOR = "SP2_CP_CONTROL_STORE"

ACME_TENANT_ID = "acme"
ZETA_TENANT_ID = "zeta"

# Existing reference conventions — no new secret machinery. Values are resolved in memory and never
# printed; only the NAMES appear here and in the runbook.
ACME_DSN_ENV = "SNACKPORTAL_TENANT_SECRET_TENANT_ACME_DSN_V1"
ZETA_DSN_ENV = "SNACKPORTAL_TENANT_SECRET_TENANT_ZETA_DSN_V1"
# Reported for PRESENCE ONLY by `plan`. This witness performs NO Control-database read; the durable
# routing cross-read is a separate Gate-B verification step (see the module docstring).
CONTROL_DSN_ENV = "SNACKPORTAL_SECRET_CONTROL_CONTROL_STORE_DSN_V1"

# Operator-local, never committed, never printed. Both are REQUIRED for the `run` leg: the ZETA
# bearer drives the auth-stage isolation leg, and a witness that can silently skip a required
# isolation leg and still exit 0 produces an incomplete record that reads as a complete one.
BEARER_ENV = "SP2_CLM_WITNESS_BEARER"
ZETA_BEARER_ENV = "SP2_CLM_WITNESS_ZETA_CLAIM_BEARER"

# The ONE allow-listed content field the served PATCH may change (IC-010 CLM).
PATCH_FIELD = "short_description"
PATCH_FIELD_MAX_CHARS = 500

# The statuses a denial leg may legitimately carry. `503` is deliberately EXCLUDED: it is the
# audit-coupled / upstream-down collapse, so a `503` proves nothing about isolation and must fail
# rather than read as a denial. `0` (transport failure) is excluded for the same reason.
DENIAL_STATUSES = (401, 403, 404)

# The durably-homed action classes this journey should produce when Gate B enables the sink.
EXPECTED_AUDIT_ACTIONS = ("tenant_startup_read", "tenant_startup_update", "RouteDenied")

# Shapes that must never appear in the REFERENCE / topology / status text of any captured artifact.
LEAK_SHAPES = ("://", "eyJ", "-----BEGIN", "AKIA", "ghp_", "xox", "password=", "PGPASSWORD")

# The ONE bounded free-text field the served contract carries is scanned under a DIFFERENT rule, and
# the difference is not an invention: it mirrors a distinction this repository already makes at the
# edge that admits the field. `database_router/adapters/providers/http_tenant_startup_api.py` splits
# `_REF_SECRET_SHAPES` (which contains `://`) from `_TEXT_SECRET_SHAPES` (which does not) because
# "`://` is lawful inside business free text; a credential or key block never is". A URL in a startup's
# `short_description` is therefore a LAWFUL fixture value, and scanning it against the URI shape would
# abort a CORRECT run — the same class of defect as a drifted key-set literal, one field along.
# Credential/token/PEM detection is NOT weakened: every one of those shapes still applies to the free
# text, plus a credential-bearing-URI pattern that no plain `https://…` link can match.
TEXT_LEAK_SHAPES = tuple(shape for shape in LEAK_SHAPES if shape != "://")
CREDENTIAL_URI = re.compile(r"[A-Za-z][A-Za-z0-9+.\-]*://[^\s/@]*:[^\s/@]*@")


# ------------------------------------------------------------------------------------ helpers ----
def _psycopg() -> Any:
    if importlib.util.find_spec("psycopg") is None:
        raise SystemExit("psycopg is not installed; this witness requires it.")
    return importlib.import_module("psycopg")


def served_record_fields() -> FrozenSet[str]:
    """The EXACT key set the served `GET /tenant/startups/<ref>` body can carry, DERIVED from the
    authoritative contract rather than restated here.

    `serialize_portal_dto` emits `json.dumps(dataclasses.asdict(dto))`, so the served key set is
    exactly the dataclass field set of `TenantStartupDetailDTO` — including the nullable fields,
    which `asdict` renders as `null` rather than omitting. Deriving it is not a stylistic choice: a
    duplicated literal in this file drifts from the contract silently, and a drifted literal rejects
    the GENUINE answer, aborting every run including a correct one on a live Gate-B data plane.

    Resolved at call time (the module performs no I/O at import, and `plan`/`status` never need it).
    """
    portal = importlib.import_module("api_gateway.portal")
    return frozenset(field.name for field in dataclasses.fields(portal.TenantStartupDetailDTO))


def redacted(dsn: str) -> str:
    """scheme+host+port+database only. Never userinfo, never a query string."""
    try:
        parts = urlsplit(dsn)
    except ValueError:
        return "<unparseable>"
    host = parts.hostname or "?"
    port = f":{parts.port}" if parts.port else ""
    return f"{parts.scheme or '?'}://{host}{port}{parts.path or ''}"


def _env(name: str) -> Optional[str]:
    raw = os.environ.get(name)
    if raw is None:
        return None
    return raw.strip() or None


_BODY_MARKER = "body="
_FREE_TEXT_PLACEHOLDER = "<bounded free text, scanned separately>"


def _partition_artifact(blob: str) -> Tuple[str, List[str]]:
    """Split a captured artifact into (reference/topology/status text, bounded free-text values).

    The served body is `serialize_portal_dto(...)` — a JSON object — and exactly ONE of its fields,
    `PATCH_FIELD`, is bounded business free text. Only that value is partitioned out. Everything else
    stays under the FULL shape census: the status line, every reference field, every non-record body
    (a `{"version", "result"}` envelope, an empty denial body) and every body that does not parse.
    Fail-closed by construction — anything this function cannot positively identify as the free-text
    value is scanned strictly.
    """
    marker = blob.find(_BODY_MARKER)
    if marker == -1:
        return blob, []
    head = blob[: marker + len(_BODY_MARKER)]
    try:
        parsed = json.loads(blob[marker + len(_BODY_MARKER) :])
    except ValueError:
        return blob, []
    if not isinstance(parsed, dict) or not isinstance(parsed.get(PATCH_FIELD), str):
        return blob, []
    remainder = dict(parsed)
    remainder[PATCH_FIELD] = _FREE_TEXT_PLACEHOLDER
    return head + json.dumps(remainder), [str(parsed[PATCH_FIELD])]


def assert_no_leak(artifacts: Dict[str, str], secrets_in_play: Sequence[str], databases: Sequence[str]) -> None:
    """Scan EVERY captured artifact for raw-secret leakage. Called before anything is reported.

    `secrets_in_play` must carry BOTH bearer tokens: the auth-stage artifact captures the response to
    a request that carried the ZETA bearer, so an echo of it would otherwise be caught only by the
    generic `eyJ` shape — which a non-JWT bearer form does not have.

    TWO shape censuses, one artifact, nothing exempted. The resolved-secret, password-substring and
    physical-database scans run over the WHOLE artifact and are not partitioned at all. Only the SHAPE
    census splits: `LEAK_SHAPES` over the reference/topology/status text, and `TEXT_LEAK_SHAPES` plus
    `CREDENTIAL_URI` over the one bounded free-text field — mirroring `_REF_SECRET_SHAPES` /
    `_TEXT_SECRET_SHAPES` at the edge that admits it. A lawful URL in a fixture's `short_description`
    therefore cannot abort a correct run, while a credential, token or key block in the same field
    still fails it.
    """
    problems: List[str] = []
    for label, blob in artifacts.items():
        reference_text, free_text_values = _partition_artifact(blob)
        for secret in secrets_in_play:
            if secret and secret in blob:
                problems.append(f"{label}: a resolved secret value appears verbatim")
            password = _password_of(secret)
            if password and password in blob:
                problems.append(f"{label}: a credential password substring appears")
        for shape in LEAK_SHAPES:
            if shape in reference_text:
                problems.append(f"{label}: contains the secret-shaped token {shape!r}")
        for value in free_text_values:
            for shape in TEXT_LEAK_SHAPES:
                if shape in value:
                    problems.append(f"{label}: the bounded {PATCH_FIELD} free text contains the secret-shaped token {shape!r}")
            if CREDENTIAL_URI.search(value):
                problems.append(f"{label}: the bounded {PATCH_FIELD} free text contains a credential-bearing URI")
        for database in databases:
            if database and database in blob:
                problems.append(f"{label}: names the physical database {database!r} (topology disclosure)")
    assert not problems, "NO-LEAK SCAN FAILED:\n  " + "\n  ".join(problems)


def _password_of(dsn: str) -> str:
    try:
        return urlsplit(dsn).password or ""
    except ValueError:
        return ""


def _http(
    method: str, url: str, *, bearer: Optional[str], body: Optional[bytes], headers: Optional[Dict[str, str]] = None
) -> Tuple[int, Dict[str, str], bytes]:
    """One bounded HTTP call. Never logs the bearer; returns status, headers and the raw body."""
    request = urllib.request.Request(url, data=body, method=method)
    if bearer:
        request.add_header("Authorization", f"Bearer {bearer}")
    if body is not None:
        request.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers or {}), exc.read()
    except urllib.error.URLError as exc:
        return 0, {}, str(exc.reason).encode("utf-8")


def _live(url: str) -> bool:
    status, _headers, _body = _http("GET", url, bearer=None, body=None)
    return status != 0


def physical_identity(conn: Any) -> Tuple[str, str]:
    """The ACME identity-proof pair. `system_identifier` ALONE is insufficient — two databases on the
    same cluster share it — so the pair is what is recorded."""
    system_identifier = conn.execute("SELECT system_identifier FROM pg_control_system()").fetchone()[0]
    database = conn.execute("SELECT current_database()").fetchone()[0]
    return str(system_identifier), str(database)


def startups_digest(conn: Any) -> str:
    """An order-stable digest of the tenant `startups` table, for the before==after restore proof."""
    row = conn.execute(
        "SELECT coalesce(md5(string_agg(rowhash, ',' ORDER BY global_startup_id)), 'EMPTY') FROM ("
        "SELECT global_startup_id, md5(concat(quote_nullable(global_startup_id::text),'|',"
        "quote_nullable(short_description))) AS rowhash FROM startups) t"
    ).fetchone()[0]
    return str(row)


def startup_row_exists(conn: Any, startup_ref: str) -> bool:
    """Row PRESENCE, asked as its own question and answered by its own probe.

    `short_description` is NULLABLE — by DDL (`infrastructure/db/tenant/003_startups.sql`) and at the
    edge (`_bounded_short_description` returns `None` for a JSON `null`) — so a `None` from
    `read_short_description` is two different facts: no such row, or a present row holding a lawful
    NULL. The positive control needs the first one only. Conflating them aborts a CORRECT run and
    blames it on a row that is, in fact, there.
    """
    return conn.execute("SELECT 1 FROM startups WHERE global_startup_id = %s", (startup_ref,)).fetchone() is not None


def read_short_description(conn: Any, startup_ref: str) -> Optional[str]:
    """The stored value, which may lawfully be `None`. Row presence is `startup_row_exists`, not this."""
    row = conn.execute("SELECT short_description FROM startups WHERE global_startup_id = %s", (startup_ref,)).fetchone()
    return None if row is None else row[0]


# ----------------------------------------------------------------------------- precondition gate --
def evaluate_preconditions(gateway_base_url: str, tenant_startup_base_url: str) -> Tuple[bool, List[str], Dict[str, Any]]:
    """D-1 / D-2 declarations plus the P-2 upstream-liveness census. Read-only; no auth, no writes.

    D-1 and D-2 read THIS process's environment. The Gateway and the Control Plane are separate
    uvicorn processes composed from their own environments, and the governed launcher scrubs `SP2_*`
    out of every child — so these are declarations about the operator's shell, not observations of
    the running services. They gate the run because a mismatch is the commonest way an operator
    collects a plausible non-answer; they are not the evidence. A-1 (the type-exact served body) and
    A-2 (the independent physical read) are.
    """
    findings: List[str] = []
    observed: Dict[str, Any] = {}

    selector = _env(TENANT_STARTUP_SELECTOR)
    observed[TENANT_STARTUP_SELECTOR] = "SET" if selector else "UNSET/BLANK"
    if not selector:
        findings.append(
            f"D-1 FAILED: {TENANT_STARTUP_SELECTOR} is unset or blank in THIS process's environment. Declared unset, "
            "the Gateway keeps the pre-CLM router handoff: /tenant/startups/<ref> still answers, and the answer is NOT "
            "data-plane evidence. (This is a declaration about the operator shell, not a read of the Gateway process.)"
        )
    elif selector.rstrip("/") != tenant_startup_base_url.rstrip("/"):
        findings.append(f"D-1 WARNING: {TENANT_STARTUP_SELECTOR} points at {selector!r}, not the governed {tenant_startup_base_url!r}")

    store = _env(CONTROL_STORE_SELECTOR)
    observed[CONTROL_STORE_SELECTOR] = store or "UNSET"
    if store != "postgres":
        findings.append(
            f"D-2 FAILED: {CONTROL_STORE_SELECTOR}={store!r} in THIS process's environment. A routing view served from "
            "the in-memory store would let this witness pass with NO physical ACME database involved at all. Proving "
            "which store the RUNNING Control Plane used is a separate Gate-B read; this check does not perform it."
        )

    # Upstream liveness census, taken now, so any later 503 can be attributed instead of guessed.
    census = {
        "gateway": _live(f"{gateway_base_url}/health"),
        "tenant_startup": _live(f"{tenant_startup_base_url}/health") or _live(tenant_startup_base_url),
    }
    observed["upstream_census"] = census
    if not census["gateway"]:
        findings.append(f"the Gateway is not answering on {gateway_base_url}")
    if not census["tenant_startup"]:
        findings.append(
            f"P-2 FAILED: the tenant-Startup edge is not answering on {tenant_startup_base_url}. Any 503 from the "
            "Gateway would be indistinguishable from three other causes."
        )
    return (not findings), findings, observed


# ------------------------------------------------------------------------------------ commands ----
def cmd_plan(args: argparse.Namespace) -> int:
    """READ-ONLY. Resolves configuration completeness and prints redacted identities only."""
    print("CLM ACME tenant data-plane witness — PLAN (read-only; no auth, no write, no standing mutation)")
    ok, findings, observed = evaluate_preconditions(args.gateway_base_url, args.tenant_startup_base_url)
    print(f"  gateway             : {args.gateway_base_url}")
    print(f"  tenant startup      : {args.tenant_startup_base_url}")
    for key, value in observed.items():
        print(f"  {key:20s}: {value}")

    configured: Dict[str, bool] = {}
    for name in (ACME_DSN_ENV, ZETA_DSN_ENV, CONTROL_DSN_ENV, BEARER_ENV, ZETA_BEARER_ENV):
        configured[name] = _env(name) is not None
        print(f"  {name:52s}: {'PRESENT' if configured[name] else 'ABSENT'} (presence only)")

    acme_dsn = _env(ACME_DSN_ENV)
    if acme_dsn:
        psycopg = _psycopg()
        with psycopg.connect(acme_dsn) as conn:
            conn.read_only = True
            system_identifier, database = physical_identity(conn)
        # The identity pair is the DV-C1/DV-C2 fingerprint. `system_identifier` alone is insufficient.
        print(f"  ACME physical id    : system_identifier={system_identifier} database=<redacted>")
        print(f"  ACME connection     : {redacted(acme_dsn)}")

    # The A-1 discriminator, resolved from the contract so the operator can see what `run` will
    # require. Field NAMES of a public response contract; no value of any kind.
    print(f"  served DTO fields   : {sorted(served_record_fields())}")

    print(f"\n  PRECONDITIONS: {'SATISFIED' if ok else 'NOT SATISFIED'}")
    for finding in findings:
        print(f"    - {finding}")
    print("\n  `plan` proves nothing about the data plane. It only establishes whether a `run` could.")
    return 0 if ok else 2


def cmd_status(args: argparse.Namespace) -> int:
    """READ-ONLY, fail-closed. The same preconditions, plus an explicit statement of what is unproven."""
    print("CLM ACME tenant data-plane witness — STATUS (read-only)")
    ok, findings, observed = evaluate_preconditions(args.gateway_base_url, args.tenant_startup_base_url)
    for key, value in observed.items():
        print(f"  {key:20s}: {value}")
    for finding in findings:
        print(f"  FAIL: {finding}")
    print("\n  UNPROVEN (and not proven by this command): Database Router -> SecretRef -> ACME physical tenant")
    print("  database -> Startup GET/PATCH. Only a `run` under an explicit START-GATE establishes that, and")
    print("  running it is a Gate-B class-M14 act.")
    print("  ALSO UNPROVEN BY ANY COMMAND HERE: that the RUNNING Control Plane served routing from the durable")
    print("  store. This witness performs no Control-database read; that cross-check is a separate Gate-B step.")
    return 0 if ok else 1


def cmd_run(args: argparse.Namespace) -> int:
    """The evidence-generating leg. Gate-B M14. Refuses without an explicit START-GATE."""
    if not args.confirm_start_gate:
        print("REFUSED: `run` performs a REAL business write (PATCH) to a physical tenant database.")
        print("That is a Gate-B class-M14 act and requires an explicit human START-GATE.")
        print("Re-invoke with --confirm-start-gate only when Gate B is granted and M14 is authorized.")
        return 3

    ok, findings, observed = evaluate_preconditions(args.gateway_base_url, args.tenant_startup_base_url)
    if not ok:
        print("REFUSED: preconditions not satisfied. Nothing collected here could be data-plane evidence.")
        for finding in findings:
            print(f"    - {finding}")
        return 2

    bearer = _env(BEARER_ENV)
    zeta_bearer = _env(ZETA_BEARER_ENV)
    acme_dsn = _env(ACME_DSN_ENV)
    zeta_dsn = _env(ZETA_DSN_ENV)
    # ZETA_BEARER_ENV is MANDATORY, not optional. Instruction §11 requires the witness to separately
    # distinguish auth-stage denial from router-stage isolation; a run that skipped the auth-stage
    # leg and still exited 0 would file an incomplete record as a complete one.
    for name, value in (
        (BEARER_ENV, bearer),
        (ZETA_BEARER_ENV, zeta_bearer),
        (ACME_DSN_ENV, acme_dsn),
        (ZETA_DSN_ENV, zeta_dsn),
    ):
        if not value:
            print(f"REFUSED: {name} is unset or blank.")
            return 2

    expected_fields = served_record_fields()
    psycopg = _psycopg()
    artifacts: Dict[str, str] = {}
    startup_ref = args.startup_ref
    url = f"{args.gateway_base_url}/tenant/startups/{startup_ref}"

    acme = psycopg.connect(acme_dsn, autocommit=True)
    zeta = psycopg.connect(zeta_dsn, autocommit=True)
    # Bound BEFORE the try so the `finally` block can never raise NameError over the real failure.
    # This is the one harness whose premise is that failures must be attributable; masking the
    # original exception with a bookkeeping error defeats exactly that.
    original: Optional[str] = None
    before_digest: Optional[str] = None
    acme_identity: Tuple[str, str] = ("", "")
    zeta_identity: Tuple[str, str] = ("", "")
    legs_ok = False
    restored_ok = False
    no_leak_ok = False
    # Whether the served PATCH was ISSUED. This — not the pre-state value — is the restore's signal:
    # the pre-state value is legitimately NULL for a lawful row, so it cannot mean "nothing to undo".
    write_attempted = False
    try:
        acme_identity = physical_identity(acme)
        zeta_identity = physical_identity(zeta)
        assert acme_identity != zeta_identity, (
            "ACME and ZETA resolve to the SAME (system_identifier, current_database()) pair — this is not a "
            "physically separated topology and no isolation claim may be made from it"
        )
        before_digest = startups_digest(acme)
        zeta_before_digest = startups_digest(zeta)
        # Row PRESENCE first, and as its own question. The pre-state value is read afterwards and may
        # lawfully be NULL — the column is nullable in the DDL and at the edge — so it can never stand
        # in for "the row is missing".
        assert startup_row_exists(acme, startup_ref), (
            f"POSITIVE CONTROL FAILED: no row with global_startup_id={startup_ref!r} exists in the ACME database. "
            f"This is row ABSENCE, established by a separate existence probe: a PRESENT row whose {PATCH_FIELD} is "
            "NULL is lawful and does not reach here."
        )
        original = read_short_description(acme, startup_ref)

        # ---- READ leg (A-1 + A-2) -------------------------------------------------------------
        read_status, _headers, body = _http("GET", url, bearer=bearer, body=None)
        artifacts["served_get"] = f"status={read_status} body={body.decode('utf-8', 'replace')}"
        assert read_status == 200, f"served GET returned {read_status}; upstream census at call time was {observed['upstream_census']}"
        record = json.loads(body)
        assert isinstance(record, dict), "the served GET body must be a JSON object"
        assert set(record) == expected_fields, (
            f"A-1 FAILED: the served GET body carries keys {sorted(record)}, not the served TenantStartupDetailDTO "
            f"contract field set {sorted(expected_fields)}. The tenant Startup terminal is TYPE-EXACT, so a pre-CLM "
            "handoff cannot serve a conforming 200 at all — a shape mismatch here means the served contract and this "
            "witness disagree, and nothing collected is data-plane evidence."
        )
        assert record["record_ref"] == startup_ref, (
            f"A-1 FAILED: the served record_ref {record['record_ref']!r} is not the reference the route addressed "
            f"({startup_ref!r}); a divergent echo is a protocol violation and is never trusted"
        )
        assert record[PATCH_FIELD] == original, (
            "P-4 FAILED: the served GET value does not match an INDEPENDENT read of the physical ACME database"
        )
        print("PASS: READ — served GET 200; body is EXACTLY the served TenantStartupDetailDTO field set;")
        print("      record_ref echoes the addressed reference; value matches an independent ACME read")
        print(f"      ACME identity: system_identifier={acme_identity[0]} (database redacted)")

        # ---- 404 disambiguation: every 404 needs the OBSERVED positive control ----------------
        unknown_status, _h, unknown_body = _http(
            "GET", f"{args.gateway_base_url}/tenant/startups/nonexistent-ref-000", bearer=bearer, body=None
        )
        bare_status, _h, _b = _http("GET", f"{args.gateway_base_url}/tenant/startups", bearer=bearer, body=None)
        assert unknown_status != 200, (
            f"an unknown startup_ref returned 200 — the route answered for a record that does not exist "
            f"(positive control on the same route family was {read_status})"
        )
        assert unknown_status in DENIAL_STATUSES and not unknown_body, (
            f"the unknown-startup_ref leg returned {unknown_status} with body-present={bool(unknown_body)}; a genuine "
            f"not-found must be one of {DENIAL_STATUSES} with an EMPTY body. 503 in particular is the upstream/audit "
            "collapse and proves nothing about the data plane."
        )
        assert bare_status != 200, "the bare /tenant/startups route returned 200; it is not an exposed route"
        print(
            f"PASS: 404 disambiguation — unknown startup_ref={unknown_status}, bare route={bare_status}, "
            f"positive control={read_status} (OBSERVED on the read leg, not assumed)"
        )

        # ---- WRITE leg ----------------------------------------------------------------------
        new_value = args.new_description
        assert len(new_value) <= PATCH_FIELD_MAX_CHARS, f"{PATCH_FIELD} is bounded at {PATCH_FIELD_MAX_CHARS} characters"
        payload = json.dumps({PATCH_FIELD: new_value}).encode("utf-8")
        # Set BEFORE the request, never after: a PATCH that reached the physical database and then
        # failed a later assertion still has to be restored.
        write_attempted = True
        status, _headers, body = _http("PATCH", url, bearer=bearer, body=payload)
        artifacts["served_patch"] = f"status={status} body={body.decode('utf-8', 'replace')}"
        assert status == 200, f"served PATCH returned {status}; upstream census at call time was {observed['upstream_census']}"
        patched = json.loads(body)
        assert set(patched) == expected_fields, (
            f"A-1 FAILED on the write leg: the served PATCH body carries keys {sorted(patched)}, not the served "
            f"TenantStartupDetailDTO contract field set {sorted(expected_fields)}"
        )
        assert patched[PATCH_FIELD] == new_value, "the served PATCH must echo the new value"
        assert read_short_description(acme, startup_ref) == new_value, (
            "the INDEPENDENT ACME read does not show the new value — the write did not reach the physical database"
        )
        assert startups_digest(zeta) == zeta_before_digest, "ZETA changed during an ACME write — isolation is broken"
        print("PASS: WRITE — served PATCH 200; independent ACME read confirms; ZETA byte-identical")

        # ---- ISOLATION: two stages, recorded and ASSERTED separately -------------------------
        status, _headers, body = _http("GET", url, bearer=zeta_bearer, body=None, headers={"X-Tenant-Id": ZETA_TENANT_ID})
        artifacts["isolation_auth_stage"] = f"status={status} body={body.decode('utf-8', 'replace')}"
        assert status == 403 and not body, "an ACME-only principal claiming ZETA must get 403 with an EMPTY body"
        print("PASS: ISOLATION (AUTH STAGE) — 403, empty body, ZETA unchanged")
        print("      SCOPE CAVEAT: this denial fires in the Auth Router, BEFORE any routing or tenant-DB contact.")
        print("      It proves AUTH-STAGE denial. It does NOT prove the Database Router would have refused.")

        status, _headers, body = _http("GET", url, bearer=bearer, body=None, headers={"X-Tenant-Id": "tenant-that-does-not-exist"})
        artifacts["isolation_router_stage"] = f"status={status} body={body.decode('utf-8', 'replace')}"
        assert status != 200, (
            "ISOLATION BREACH (ROUTER STAGE): an unregistered-tenant carrier was answered 200. The record was served "
            "to a request carrying a tenant this topology does not know."
        )
        assert status in DENIAL_STATUSES and not body, (
            f"the router-stage isolation leg returned {status} with body-present={bool(body)}; a real denial must be "
            f"one of {DENIAL_STATUSES} with an EMPTY body. A 503 here is the upstream/audit collapse — it is NOT a "
            "denial and must not be recorded as isolation evidence."
        )
        print(f"PASS: ISOLATION (ROUTER STAGE) — unregistered-tenant carrier denied with {status}, empty body")
        print("      Recorded SEPARATELY from the auth-stage leg: they prove different things.")

        assert startups_digest(zeta) == zeta_before_digest, "ZETA changed during the isolation legs"
        legs_ok = True

    except AssertionError as exc:
        # Recorded here rather than propagating, so the `finally` restore result and the no-leak scan
        # are both reported alongside the real cause instead of behind a traceback.
        print(f"FAIL: {exc}")
    finally:
        # RESTORE, always. The before==after digest is the proof, not the UPDATE's return code.
        # The branch key is `write_attempted` — whether the write leg RAN — and deliberately not the
        # pre-state value: that value is legitimately NULL for a lawful row, and keying on it left a
        # run that wrote nothing in NEITHER branch, printing a restore failure it had not had.
        if write_attempted and before_digest is not None:
            try:
                acme.execute("UPDATE startups SET short_description = %s WHERE global_startup_id = %s", (original, startup_ref))
                restored_ok = startups_digest(acme) == before_digest
            except Exception as exc:  # noqa: BLE001
                print(f"RESTORE FAILED: {exc}")
            print(f"{'PASS' if restored_ok else 'FAIL'}: RESTORE — before == after digest: {restored_ok}")
        elif not write_attempted:
            # The run aborted before the served PATCH was issued, so nothing was written and
            # restoration is vacuously true. Reporting FAIL here blames the restore for an earlier
            # failure and hides the real cause behind a second, invented one.
            restored_ok = True
            print("PASS: RESTORE — vacuous: the run never issued the write, so there is nothing to undo")
        else:
            # Unreachable by construction (`before_digest` is bound before the write leg) and left
            # fail-closed rather than assumed away.
            print("FAIL: RESTORE — the write leg ran with no before-digest; the table cannot be proven restored")
        try:
            assert_no_leak(
                artifacts,
                [acme_dsn or "", zeta_dsn or "", bearer or "", zeta_bearer or ""],
                [acme_identity[1], zeta_identity[1]],
            )
            no_leak_ok = True
            print("PASS: NO-LEAK SCAN — no DSN, password, bearer token, or physical database name in any artifact")
        except AssertionError as exc:
            print(f"FAIL: {exc}")
        acme.close()
        zeta.close()

    print("\n  AUDIT: with the durable sink enabled, this journey should produce the durably-homed classes")
    print(f"  {EXPECTED_AUDIT_ACTIONS} in control_gateway_audit, with the {PATCH_FIELD} VALUE absent from every cell.")
    print("  Verifying that is a separate read of the Control database; it is not inferred from this run.")
    verdict = legs_ok and restored_ok and no_leak_ok
    print(f"\n  RUN VERDICT: {'PASS' if verdict else 'FAIL'} (legs={legs_ok} restore={restored_ok} no_leak={no_leak_ok})")
    return 0 if verdict else 1


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="CLM ACME tenant data-plane witness (operator harness)")
    parser.add_argument("--gateway-base-url", default=GATEWAY_BASE_URL)
    parser.add_argument("--tenant-startup-base-url", default=TENANT_STARTUP_BASE_URL)
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("plan", help="read-only: configuration and precondition completeness")
    sub.add_parser("status", help="read-only, fail-closed precondition report")
    run_parser = sub.add_parser("run", help="GATE-B M14: served GET + PATCH + isolation + restore")
    run_parser.add_argument("--confirm-start-gate", action="store_true", help="required; a real tenant write follows")
    run_parser.add_argument("--startup-ref", default="clm-startup-1")
    run_parser.add_argument("--new-description", default="clm witness value")
    args = parser.parse_args(list(argv) if argv is not None else None)
    # No subcommand => the READ-ONLY status path. The standalone runner must never trip the write leg.
    if not args.command:
        args.command = "status"
    return {"plan": cmd_plan, "status": cmd_status, "run": cmd_run}[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
