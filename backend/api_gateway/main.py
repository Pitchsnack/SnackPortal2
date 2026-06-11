"""Entrypoint stub for api_gateway (SCAFFOLD ONLY).

Liveness is a static, non-disclosing placeholder. No app/router wiring, no auth,
no tenant routing, no database access. Concrete wiring is deferred to a later
build phase.
"""

from __future__ import annotations

from typing import Dict

SERVICE = "api_gateway"


def liveness() -> Dict[str, str]:
    # Static liveness placeholder — reveals no tenant/database detail.
    return {"service": SERVICE, "status": "alive", "build_phase": "1"}


def create_app() -> None:
    raise NotImplementedError("Build Phase 1 scaffold: api_gateway is not yet wired.")
