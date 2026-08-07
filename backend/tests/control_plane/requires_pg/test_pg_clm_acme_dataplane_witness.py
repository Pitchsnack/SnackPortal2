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

  E48  AUTHORITATIVE, the one claim that cannot be made from the wire — and CURRENTLY UNPROVABLE.
       The ZETA-claim denial is correlated with the DURABLE operational-audit record for the same
       request, and only `tenant_access_denied` would satisfy it. FOUR reasons render an identical
       `403` with an identical empty body: `carrier_mismatch`, `tenant_context_required`,
       `tenant_access_denied` and `tenant_not_ready`. The durable record separates the first two. It
       CANNOT separate the last two — `not_ready()` carries the same 403, the Auth Router edge
       collapses every non-carrier-mismatch 403 to `forbidden`, and the Gateway writes a reference-
       free `RouteDenied` row either way — so a no-reference row is classified as an AMBIGUOUS
       PRE-AUTH DENIAL and E48 is reported `NOT AVAILABLE / UNPROVEN`. Missing audit evidence is
       reported the same way. Neither is ever a pass; see runbook GBR-4 for what would close it.

THE CONTROL-DATABASE READS, stated exactly. `run` opens a Control connection with
`read_only = True` and executes two kinds of statement on it. (a) ONE bounded BUSINESS-DATA read —
`read_denial_audit`, a `SELECT` from `control_gateway_audit` filtered to a correlation id **this
witness minted for its own request**, reading the reference columns as `IS NOT NULL` booleans so no
reference VALUE enters this process; it runs once per denial leg. (b) The physical-identity METADATA
pair `pg_control_system()` / `current_database()`, which read no table and no business row and exist
because the no-leak census must bar the Control database's physical name. That is the whole of it.

UNIMPLEMENTED, and deliberately not claimed: this witness does **not** cross-read the Control
routing row. It does not read `control_tenants`, and it makes no claim about which store served the
routing view. Proving that the served routing view came from the durable store rather than the
in-memory one is a separate Gate-B read, and it is recorded as such in the evidence template. Do not
write that this witness performed it.

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
* **Both isolation legs are pre-routing, and neither proves router-stage denial (GBR-1).** The
  ZETA-claim denial fires in the **Auth Router**, before any routing or tenant-DB contact; the
  unregistered-tenant carrier leg is resolved as `carrier_mismatch` in the same Auth Router path. Both
  denials are real, both are captured and ASSERTED separately, and a `200` on either is an isolation
  breach that fails the run — but **whether the Database Router itself would refuse remains UNPROVEN
  by this harness**, and neither leg may be labelled or recorded as router-stage evidence.
* **A `403` with an empty body names no reason.** Three different denials render it identically, so
  every denial leg records the reason OBSERVED in the durable audit rather than the one assumed.
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
import uuid
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
# Reported for PRESENCE ONLY by `plan`; REQUIRED by `run`. `run` opens ONE bounded, read-only
# Control connection for ONE purpose: reading the durable Gateway operational-audit rows that carry
# the denial REASON for the correlation ids this witness itself minted (RB-3 / E48). It still
# performs NO routing cross-read — see the module docstring and runbook §6.1.
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
# GBR-2: `CarrierMismatch` is the FOURTH class this journey actually emits — D-43 durably homes it
# (`control_plane/adapters/providers/http_gateway_audit_api.py:117`) and the unregistered-tenant
# carrier leg produces it. Omitting it made this list read as exhaustive when it under-counted by
# one, so an operator reconciling the Control-DB read against it would have found a row they had no
# entry for. Durable coverage is the FIVE `_CLM_DURABLE_ACTIONS` classes; the fifth,
# `workspace_memberships_read`, belongs to a different journey and is deliberately not listed here.
EXPECTED_AUDIT_ACTIONS = ("tenant_startup_read", "tenant_startup_update", "RouteDenied", "CarrierMismatch")

# ------------------------------------------------------ RB-3: the denial-reason discriminator ----
# The header the Gateway honours when correlating a request with its audit record
# (`api_gateway/gateway.py:53`, lower-cased on read). Without one the Gateway mints its own, which
# this process never sees — and an audit row nobody can find is not evidence.
CORRELATION_HEADER = "X-Correlation-Id"

# The two durably homed DENIAL actions of the Gateway edge (D-42 CLM Stage B + D-43). Both are in
# `_CLM_DURABLE_ACTIONS`, so with the durable sink selected both reach `control_gateway_audit`, and
# both are written BEFORE the denial is handed back (deny-with-evidence: a durable denial record that
# cannot persist collapses the response to 503 instead).
ROUTE_DENIED_ACTION = "RouteDenied"
CARRIER_MISMATCH_ACTION = "CarrierMismatch"
DENIAL_OUTCOME = "rejected"

# The FOUR denial reasons a `403` with an empty body can carry on this route, and how far the
# durable record can separate them. All four are indistinguishable at the wire, which is RB-3.
#
#   carrier_mismatch          the Auth Router rejected because the recognised carrier disagrees with
#                             the signed tenant claim. The Gateway emits action `CarrierMismatch`
#                             with an opaque carrier reference (`gateway.py:200-207`).
#   tenant_context_required   the bearer authenticated but carries no tenant claim, so dispatch
#                             refuses (`dispatch.py:65`). The Gateway emits `RouteDenied` from the
#                             POST-authentication branch, which passes `actor_ref=principal_ref`
#                             (`gateway.py:237`) — so the row DOES carry an actor reference.
#   tenant_access_denied      the token's signed claim IS the target tenant and the principal holds
#                             no membership for it (`auth_router/tenant_context.py:45`). The Gateway
#                             emits `RouteDenied` from the authenticator-rejection branch, which runs
#                             BEFORE any AuthContext exists — so the row carries NO actor, tenant or
#                             carrier reference (`gateway.py:199-211`). This is the ONLY reason that
#                             is genuine authorization denial, i.e. E48.
#   tenant_not_ready          the principal IS a member, but the tenant is known-but-not-Ready
#                             (`auth_router/tenant_context.py:47` raises `not_ready`). It is NOT an
#                             authorization denial at all.
#
# >>> WHY tenant_access_denied AND tenant_not_ready CANNOT BE TOLD APART HERE (the C2-3 finding) <<<
#
# `auth_router/models.py:96-97` gives `not_ready()` the SAME `403` status as `forbidden()`;
# `auth_router/adapters/providers/http_authenticate_api.py:123-124` then collapses every
# non-`carrier_mismatch` 403 to the single public code `forbidden` — its own docstring says the
# granular reasons "never leak past the status bucket" — and
# `api_gateway/adapters/providers/http_authenticator.py:119-124` repeats the collapse Gateway-side.
# By the time `gateway.py:199-211` emits the audit event, both reasons produce a BYTE-IDENTICAL
# durable row: action `RouteDenied`, outcome `rejected`, actor/tenant/carrier all NULL.
#
# So a no-reference `RouteDenied` row is an AMBIGUOUS PRE-AUTH DENIAL. It is not evidence of genuine
# authorization denial, and this witness must not file it as such — the standing local fixture
# deliberately provisions a dormant tenant, so `tenant_not_ready` is reachable here, not theoretical.
# Narrowing the ambiguity is a PRODUCTION change (a distinct status, public code, or audit action)
# and is explicitly out of scope; the honest reading is UNPROVEN, and that is what is reported.
DENIAL_TENANT_ACCESS_DENIED = "tenant_access_denied"
DENIAL_TENANT_CONTEXT_REQUIRED = "tenant_context_required"
DENIAL_CARRIER_MISMATCH = "carrier_mismatch"
DENIAL_TENANT_NOT_READY = "tenant_not_ready"
DENIAL_PRE_AUTH_AMBIGUOUS = "AMBIGUOUS PRE-AUTH DENIAL (tenant_access_denied OR tenant_not_ready)"
DENIAL_EVIDENCE_ABSENT = "NOT AVAILABLE / UNPROVEN"
DENIAL_INDETERMINATE = "INDETERMINATE"

# The authoritative signals that would UNIQUELY prove `tenant_access_denied` rather than
# `tenant_not_ready` for a no-reference `RouteDenied` row.
#
# It is EMPTY, and the emptiness is a fact about the runtime, not a gap in this harness: the chain
# above erases the distinction before anything durable is written, and manufacturing a substitute
# (a fabricated bearer, a new Keycloak scope, a changed public code) is exactly what this arc
# forbids. While it is empty, E48 is UNPROVABLE from the durable record and every no-reference
# `RouteDenied` row classifies as AMBIGUOUS. If the runtime later emits a genuinely distinguishing
# signal, adding its name here — and passing it to `classify_denial_reason` — is the whole change.
RECOGNISED_UNIQUE_DENIAL_SIGNALS: FrozenSet[str] = frozenset()

# E48 — the §28 Definition-of-Done line "ZETA denial is genuine authorization denial". Exactly one
# of the reasons above satisfies it, and reaching that reason requires a recognised signal above.
E48_REQUIRED_DENIAL_REASON = DENIAL_TENANT_ACCESS_DENIED

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


def read_denial_audit(conn: Any, correlation_id: str) -> List[Tuple[Any, ...]]:
    """The durable Gateway-edge audit rows for ONE correlation id, in store order.

    STRICTLY READ-ONLY and STRICTLY BOUNDED: one `SELECT`, one correlation id — the one this witness
    minted for its own request — and only what the denial-reason derivation needs. It reads the
    reference columns as `IS NOT NULL` BOOLEANS, never as values, so no actor, tenant or carrier
    reference can enter this process at all, let alone an artifact.

    This is the witness's ONE bounded read of Control BUSINESS DATA — the single statement that reads
    a row of a Control table. It is not the only statement executed on that connection, and saying so
    would be false: `physical_identity` issues `pg_control_system()` and `current_database()`, which
    are cluster/session METADATA (no table, no business row) and are required by the no-leak census,
    and this function itself runs once per denial leg. It does not read `control_tenants`, it does
    not read a routing row, and it does not scan the audit table. The durable routing cross-read
    remains a separate Gate-B operator step (module docstring; runbook §6.1).
    """
    return list(
        conn.execute(
            "SELECT action, outcome, actor_ref IS NOT NULL, tenant_ref IS NOT NULL, carrier_ref IS NOT NULL "
            "FROM control_gateway_audit WHERE correlation_id = %s ORDER BY id",
            (correlation_id,),
        ).fetchall()
    )


def classify_denial_reason(rows: Sequence[Sequence[Any]], *, unique_signal: Optional[str] = None) -> Tuple[str, str]:
    """`(reason, detail)` — which denial the Gateway actually made, from the durable record alone.

    Pure: rows in, verdict out. That is what lets the static guard EXECUTE every branch without a
    database, and what keeps the derivation reviewable next to the emitter it mirrors.

    Fail-closed in every direction. No durable denial row => `NOT AVAILABLE / UNPROVEN` (the sink is
    off, the row did not persist, or the correlation never reached the Gateway) — never a pass. A row
    shape the derivation above does not cover => `INDETERMINATE` — never a guess. A row shape TWO
    different upstream reasons produce identically => `AMBIGUOUS PRE-AUTH DENIAL` — never the more
    convenient of the two.

    `unique_signal` is the only route to `tenant_access_denied`, and it is honoured only when it is
    one of `RECOGNISED_UNIQUE_DENIAL_SIGNALS` — which is EMPTY on this runtime. It exists so that the
    ambiguity is a *stated dependency on evidence that does not exist yet* rather than a hard-wired
    refusal, and so that adding a real signal later is a one-line change with a test already written.
    """
    denials = [row for row in rows if str(row[0]) in (CARRIER_MISMATCH_ACTION, ROUTE_DENIED_ACTION) and str(row[1]) == DENIAL_OUTCOME]
    if not denials:
        return DENIAL_EVIDENCE_ABSENT, (
            f"no durably homed denial row ({CARRIER_MISMATCH_ACTION}/{ROUTE_DENIED_ACTION}, outcome {DENIAL_OUTCOME!r}) exists "
            f"for this correlation id among the {len(rows)} row(s) found. With the durable sink unselected the Gateway "
            "emits to the in-memory no-sink emitter and NOTHING is written, so the denial reason is unobservable here"
        )
    actions = {str(row[0]) for row in denials}
    if actions == {CARRIER_MISMATCH_ACTION}:
        return DENIAL_CARRIER_MISMATCH, (
            "the durable record is a CarrierMismatch denial: the recognised carrier disagreed with the signed tenant "
            "claim, so the request was refused for its CARRIER, not for the principal's authorization"
        )
    if actions != {ROUTE_DENIED_ACTION} or len(denials) != 1:
        return DENIAL_INDETERMINATE, (
            f"the correlation carries {len(denials)} durable denial row(s) with action(s) {sorted(actions)}; one request "
            "produces exactly one durably homed denial record, so this shape is not interpretable"
        )
    _action, _outcome, has_actor, has_tenant, _has_carrier = denials[0]
    if not has_actor and not has_tenant:
        if unique_signal is not None and unique_signal in RECOGNISED_UNIQUE_DENIAL_SIGNALS:
            return DENIAL_TENANT_ACCESS_DENIED, (
                "the durable record is a RouteDenied denial carrying NO actor reference — emitted only from the "
                "authenticator-rejection branch, before any AuthContext exists — AND the authoritative signal "
                f"{unique_signal!r} uniquely separates it from {DENIAL_TENANT_NOT_READY!r}. That is genuine "
                "authorization denial"
            )
        return DENIAL_PRE_AUTH_AMBIGUOUS, (
            "the durable record is a RouteDenied denial carrying NO actor, tenant or carrier reference. The Gateway "
            f"emits EXACTLY this row for BOTH {DENIAL_TENANT_ACCESS_DENIED!r} (non-member of a Ready tenant, "
            f"auth_router/tenant_context.py:45) and {DENIAL_TENANT_NOT_READY!r} (member of a known-but-dormant tenant, "
            "tenant_context.py:47): models.py:96-97 gives not_ready() the same 403, http_authenticate_api.py:123-124 "
            "collapses every non-carrier-mismatch 403 to `forbidden`, and http_authenticator.py:119-124 repeats the "
            "collapse. No signal in this record separates them, and only one of the two is authorization denial — so "
            "this row cannot establish E48. Narrowing it is a production change and is out of scope here"
        )
    if has_actor and not has_tenant:
        return DENIAL_TENANT_CONTEXT_REQUIRED, (
            "the durable record is a RouteDenied denial carrying an ACTOR reference, which the Gateway emits only from "
            "the post-authentication dispatch branch: the bearer authenticated and simply carried no tenant claim. The "
            "principal was never refused access to the tenant"
        )
    return DENIAL_INDETERMINATE, (
        f"the durable RouteDenied row carries actor_ref present={bool(has_actor)} tenant_ref present={bool(has_tenant)}, "
        "a combination the Gateway's denial branches do not produce on this route"
    )


def e48_problems(status: int, body: bytes, rows: Sequence[Sequence[Any]], *, unique_signal: Optional[str] = None) -> List[str]:
    """Everything stopping the ZETA leg from being E48 evidence. An EMPTY list means E48 is satisfied.

    E48 is the Definition-of-Done line *"ZETA denial is genuine authorization denial"*. The
    predecessor asserted `status == 403 and not body` and nothing else — but ALL FOUR of
    `tenant_access_denied`, `tenant_not_ready`, `tenant_context_required` and `carrier_mismatch`
    render EXACTLY `403` with an empty body. A bearer that exercised the wrong one filed a non-ZETA
    denial **as** E48 evidence, and no part of the run could tell. The wire shape is necessary and it
    is not sufficient; the discriminator is the durable operational-audit record for the SAME
    request — as far as that record can go.

    It does not go all the way. `tenant_access_denied` and `tenant_not_ready` produce a
    BYTE-IDENTICAL durable row (see the derivation above), so on this runtime E48 resolves to
    `NOT AVAILABLE / UNPROVEN` rather than to a pass. That is a finding about the evidence available,
    not a redefinition of E48: the claim is unchanged, and what changed is that the harness no longer
    asserts it from a record that cannot carry it.
    """
    problems: List[str] = []
    if status != 403:
        problems.append(f"the ZETA-claim leg returned {status}, not 403 — an authorization denial on this route is a 403")
    if body:
        problems.append("the ZETA-claim denial carried a body; a fail-closed denial discloses nothing and its body is empty")
    reason, detail = classify_denial_reason(rows, unique_signal=unique_signal)
    if reason != E48_REQUIRED_DENIAL_REASON:
        # An UNPROVEN verdict and a REFUTED one are different findings and must read differently in
        # the artifact: the first says the evidence cannot decide, the second says it decided against.
        unproven = reason in (DENIAL_PRE_AUTH_AMBIGUOUS, DENIAL_EVIDENCE_ABSENT, DENIAL_INDETERMINATE)
        problems.append(
            f"{'E48 NOT AVAILABLE / UNPROVEN' if unproven else 'E48 NOT SATISFIED'} — the authoritative denial reason "
            f"for this request is {reason!r}, not {E48_REQUIRED_DENIAL_REASON!r}: {detail}. A 403 with an empty body is "
            "produced by all four denial reasons, so the wire response alone can never establish this claim"
        )
    return problems


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
    print("  store. `run` DOES open a read-only Control connection, but its only business-data read is the")
    print("  correlation-filtered denial record for a denial leg it actually reaches (plus pg_control_system()/")
    print("  current_database() metadata). It never reads control_tenants or a routing row; that cross-check is a")
    print("  separate Gate-B operator step. `status` itself opens no Control connection at all.")
    # N-2. This block states LEG REACHABILITY, and it is the operator-facing half of the same fact the
    # runbook states in prose: the harness DEFINES two isolation legs, and a current `run` executes the
    # first only. Saying "its own two isolation requests" here described a run this runtime cannot
    # perform — and `status` is the command an operator runs freely, and the one a bare invocation
    # resolves to, so it is where a wrong count does the most damage.
    print("  THE HARNESS DEFINES TWO INTENDED ISOLATION LEGS, AND ONLY THE FIRST IS CURRENTLY REACHABLE: cmd_run")
    print("  asserts on E48 before it issues the second (unregistered-tenant carrier) leg, and while GBR-4 is")
    print("  unresolved that assertion cannot pass — so THE SECOND ISOLATION LEG IS NOT REACHED WHILE GBR-4")
    print("  REMAINS UNRESOLVED. It is required-but-currently-unreachable, never already executed.")
    print("  BOTH LEGS REMAIN MANDATORY FOR FINAL ACCEPTANCE, so a complete two-leg isolation record is")
    print("  currently unproducible and a one-leg record is INCOMPLETE / NOT ACCEPTABLE AS FINAL ISOLATION")
    print("  EVIDENCE.")
    print("  E48 IS CURRENTLY UNPROVABLE FROM THE DURABLE RECORD: tenant_access_denied and tenant_not_ready emit a")
    print("  byte-identical RouteDenied row, so a no-reference denial is reported AMBIGUOUS, never as E48 satisfied.")
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
    control_dsn = _env(CONTROL_DSN_ENV)
    # ZETA_BEARER_ENV is MANDATORY, not optional. Instruction §11 requires the witness to separately
    # distinguish auth-stage denial from the unregistered-carrier leg; a run that skipped the
    # auth-stage leg and still exited 0 would file an incomplete record as a complete one.
    # CONTROL_DSN_ENV is MANDATORY for the same reason (RB-3): without the durable denial record the
    # E48 claim is unfalsifiable, and an unfalsifiable claim that still exits 0 is the defect.
    for name, value in (
        (BEARER_ENV, bearer),
        (ZETA_BEARER_ENV, zeta_bearer),
        (ACME_DSN_ENV, acme_dsn),
        (ZETA_DSN_ENV, zeta_dsn),
        (CONTROL_DSN_ENV, control_dsn),
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
    # The Control connection is READ-ONLY at the connection level and is used for exactly one
    # statement family: `read_denial_audit`. It is opened here, with the others, so a bad reference
    # fails attributably up front rather than in the middle of the isolation legs.
    control = psycopg.connect(control_dsn)
    control.read_only = True
    # Bound BEFORE the try so the `finally` block can never raise NameError over the real failure.
    # This is the one harness whose premise is that failures must be attributable; masking the
    # original exception with a bookkeeping error defeats exactly that.
    original: Optional[str] = None
    before_digest: Optional[str] = None
    acme_identity: Tuple[str, str] = ("", "")
    zeta_identity: Tuple[str, str] = ("", "")
    control_identity: Tuple[str, str] = ("", "")
    legs_ok = False
    restored_ok = False
    no_leak_ok = False
    # Whether the served PATCH was ISSUED. This — not the pre-state value — is the restore's signal:
    # the pre-state value is legitimately NULL for a lawful row, so it cannot mean "nothing to undo".
    write_attempted = False
    try:
        acme_identity = physical_identity(acme)
        zeta_identity = physical_identity(zeta)
        control_identity = physical_identity(control)
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

        # ---- ISOLATION: two legs, recorded and ASSERTED separately ---------------------------
        # Each leg mints its OWN correlation id and hands it to the Gateway, so the durable
        # operational-audit row for that exact request can be found afterwards. Without one the
        # Gateway mints an id this process never sees, and an audit row nobody can find is not
        # evidence (RB-3).
        zeta_correlation = uuid.uuid4().hex
        status, _headers, body = _http(
            "GET",
            url,
            bearer=zeta_bearer,
            body=None,
            headers={"X-Tenant-Id": ZETA_TENANT_ID, CORRELATION_HEADER: zeta_correlation},
        )
        # The audit read happens AFTER the response, and the denial record is written BEFORE the
        # denial is handed back (deny-with-evidence: a durable denial record that cannot persist
        # collapses the response to 503), so the row is committed by the time this runs.
        zeta_rows = read_denial_audit(control, zeta_correlation)
        zeta_reason, zeta_detail = classify_denial_reason(zeta_rows)
        artifacts["isolation_auth_stage"] = (
            f"status={status} durable_denial_reason={zeta_reason} durable_rows={len(zeta_rows)} body={body.decode('utf-8', 'replace')}"
        )
        e48 = e48_problems(status, body, zeta_rows)
        assert not e48, (
            "E48 NOT ESTABLISHED — the ZETA denial has not been shown to be genuine authorization denial:\n      "
            + "\n      ".join(e48)
            + "\n      A no-reference RouteDenied row is emitted identically for tenant_access_denied and for "
            "tenant_not_ready, so on this runtime E48 is UNPROVABLE from the durable record and this leg fails by "
            "construction. That is the honest outcome, not a harness defect: closing it needs either a production "
            "change that distinguishes the two reasons, or Dan's written decision to narrow Gate B / accept a "
            "labelled substitute artifact. Do NOT record E48 as satisfied from this run."
        )
        print(f"PASS: ISOLATION (AUTH STAGE) — 403, empty body, ZETA unchanged; durable denial reason {zeta_reason!r}")
        print(f"      E48 SATISFIED: {zeta_detail}")
        print("      SCOPE CAVEAT: this denial fires in the Auth Router, BEFORE any routing or tenant-DB contact.")
        print("      It proves AUTH-STAGE denial. It does NOT prove the Database Router would have refused.")

        # The second leg is NOT a router-stage proof and is no longer labelled as one (GBR-1): an
        # unregistered-tenant carrier presented with the ACME bearer is resolved as `carrier_mismatch`
        # in the Auth Router path — pre-routing, the same stage as the leg above. The denial is real
        # and is asserted; the STAGE is now OBSERVED from the durable record rather than claimed.
        carrier_correlation = uuid.uuid4().hex
        status, _headers, body = _http(
            "GET",
            url,
            bearer=bearer,
            body=None,
            headers={"X-Tenant-Id": "tenant-that-does-not-exist", CORRELATION_HEADER: carrier_correlation},
        )
        carrier_rows = read_denial_audit(control, carrier_correlation)
        carrier_reason, _carrier_detail = classify_denial_reason(carrier_rows)
        artifacts["isolation_unregistered_carrier"] = (
            f"status={status} durable_denial_reason={carrier_reason} durable_rows={len(carrier_rows)} "
            f"body={body.decode('utf-8', 'replace')}"
        )
        assert status != 200, (
            "ISOLATION BREACH: an unregistered-tenant carrier was answered 200. The record was served to a request "
            "carrying a tenant this topology does not know."
        )
        assert status in DENIAL_STATUSES and not body, (
            f"the unregistered-tenant carrier leg returned {status} with body-present={bool(body)}; a real denial must "
            f"be one of {DENIAL_STATUSES} with an EMPTY body. A 503 here is the upstream/audit collapse — it is NOT a "
            "denial and must not be recorded as isolation evidence."
        )
        print(f"PASS: ISOLATION (UNREGISTERED-TENANT CARRIER) — denied with {status}, empty body")
        print(f"      Durable denial reason OBSERVED: {carrier_reason!r} — recorded, not assumed.")
        print("      NOT a router-stage proof (GBR-1): this leg is resolved pre-routing, in the Auth Router path.")
        print("      Whether the Database Router itself would refuse remains UNPROVEN by this harness.")

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
                [acme_dsn or "", zeta_dsn or "", bearer or "", zeta_bearer or "", control_dsn or ""],
                [acme_identity[1], zeta_identity[1], control_identity[1]],
            )
            no_leak_ok = True
            print("PASS: NO-LEAK SCAN — no DSN, password, bearer token, or physical database name in any artifact")
        except AssertionError as exc:
            print(f"FAIL: {exc}")
        acme.close()
        zeta.close()
        control.close()

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
