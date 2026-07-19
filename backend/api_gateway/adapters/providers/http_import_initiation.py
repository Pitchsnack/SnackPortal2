"""Production ``ImportInitiationPort`` over internal HTTP (stdlib urllib) — W1a composed-core.

The gateway side of the W1a composed-core import wire (the ``http_router_dispatch.py`` twin). A transport
CLIENT to the Import Service's internal initiate endpoint — reached over transport ONLY, never an in-process
import of ``import_service`` (IC-010 §H/§M; DAG independence), and containing no import-execution name (the
port method is ``initiate``, never ``start_import``). The gateway never resolves or opens a database
(IC-010 §X).

Serializes exactly the five references-only initiation keys ``{source_ref, target_tenant_ref, operation_key,
correlation_id, actor_ref}`` and validates the response is EXACTLY ``{"version": 1, "outcome": {state,
replayed, applied_count, noop_count, import_id}}`` with the correct primitive types. Every malformed /
wrong-shape / wrong-type / HTTP-error / timeout / transport-failure outcome collapses fail-closed to
``ImportInitiationOutcome(ok=False, ...)`` (IC-010 §L — the gateway maps a non-ok outcome to 503
``unavailable``; no error path downgrades to a less-isolated outcome or surfaces internal detail). Single
attempt, bounded timeout, no retry loop. References only — no DB handle, DB name, connection descriptor,
credential, topology, tenant row, source record, body, or payload crosses this boundary; the error taxonomy
is bounded to ``{unavailable, invalid}`` and never leaked.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from api_gateway.ports import ImportInitiationOutcome, ImportInitiationPort, ImportInitiationRequest

_INITIATE_PATH = "/internal/import/initiate"

# The single fail-closed outcome for every untrusted/unavailable case (IC-010 §L).
_FAIL_CLOSED = ImportInitiationOutcome(ok=False, state="", replayed=False, applied_count=0, noop_count=0, import_id="")

_OUTCOME_KEYS = frozenset({"state", "replayed", "applied_count", "noop_count", "import_id"})


class HttpImportInitiation(ImportInitiationPort):
    def __init__(self, base_url: str, timeout: float = 2.0) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout

    def initiate(self, request: ImportInitiationRequest) -> ImportInitiationOutcome:
        body = json.dumps(
            {
                "source_ref": request.source_ref,
                "target_tenant_ref": request.target_tenant_ref,
                "operation_key": request.operation_key,
                "correlation_id": request.correlation_id,
                "actor_ref": request.actor_ref,
            }
        ).encode("utf-8")
        http_request = urllib.request.Request(
            self._base + _INITIATE_PATH,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(http_request, timeout=self._timeout) as response:  # internal import URL
                return self._map(response.read())
        except urllib.error.HTTPError:
            # A bounded, mirrored 4xx/5xx (INVALID / UNAVAILABLE) is a fail-closed non-ok outcome; the body is
            # never read for a decision (no leak).
            return _FAIL_CLOSED
        except Exception:
            # Timeout / connection refused / any transport failure -> fail closed (single attempt).
            return _FAIL_CLOSED

    def _map(self, raw: bytes) -> ImportInitiationOutcome:
        try:
            data = json.loads(raw.decode("utf-8"))
        except Exception:
            return _FAIL_CLOSED
        if not isinstance(data, dict) or set(data.keys()) != {"version", "outcome"}:
            return _FAIL_CLOSED
        version = data["version"]
        if isinstance(version, bool) or version != 1:
            return _FAIL_CLOSED
        outcome = data["outcome"]
        if not isinstance(outcome, dict) or set(outcome.keys()) != set(_OUTCOME_KEYS):
            return _FAIL_CLOSED
        state = outcome["state"]
        replayed = outcome["replayed"]
        applied_count = outcome["applied_count"]
        noop_count = outcome["noop_count"]
        import_id = outcome["import_id"]
        if not isinstance(state, str) or not isinstance(import_id, str):
            return _FAIL_CLOSED
        if not isinstance(replayed, bool):
            return _FAIL_CLOSED
        if isinstance(applied_count, bool) or not isinstance(applied_count, int):
            return _FAIL_CLOSED
        if isinstance(noop_count, bool) or not isinstance(noop_count, int):
            return _FAIL_CLOSED
        return ImportInitiationOutcome(
            ok=True,
            state=state,
            replayed=replayed,
            applied_count=applied_count,
            noop_count=noop_count,
            import_id=import_id,
        )
